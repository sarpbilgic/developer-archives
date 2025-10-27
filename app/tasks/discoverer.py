# tasks/discoverer.py
# The advanced "Discoverer" / "Hunter" Lambda function.
# Uses multiple strategies (initially language-focused) and state management
# to find high-quality repo candidates and queue them for processing.

import boto3
import json
import asyncio
import logging
import random
import time
import math
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.external.github_client import github_client
from app.settings import settings
from app.db import get_session
from app.services.data_processing_service import DataProcessingService

LANGUAGE_CONFIG: Dict[str, Dict] = {
    "Python":       {"stars": ">500", "target": 15000, "min_desc_words": 5, "min_forks": 30},
    "JavaScript":   {"stars": ">500", "target": 12000, "min_desc_words": 5, "min_forks": 30},
    "TypeScript":   {"stars": ">400", "target": 8000,  "min_desc_words": 5, "min_forks": 25},
    "Go":           {"stars": ">400", "target": 6000,  "min_desc_words": 5, "min_forks": 25},
    "Java":         {"stars": ">400", "target": 6000,  "min_desc_words": 5, "min_forks": 25},
    "Rust":         {"stars": ">300", "target": 5000,  "min_desc_words": 5, "min_forks": 20},
    
    "CSharp":       {"stars": ">300", "target": 4000,  "query_name": "c#", "min_desc_words": 5, "min_forks": 20},
    "CPP":          {"stars": ">300", "target": 4000,  "query_name": "c++", "min_desc_words": 5, "min_forks": 20},
    "PHP":          {"stars": ">300", "target": 3000,  "min_desc_words": 5, "min_forks": 20},
    "Ruby":         {"stars": ">300", "target": 3000,  "min_desc_words": 5, "min_forks": 20},
    "C":            {"stars": ">300", "target": 2500,  "query_name": "c", "min_desc_words": 4, "min_forks": 15},
    
    "Swift":        {"stars": ">250", "target": 2000,  "min_desc_words": 5, "min_forks": 15},
    "Kotlin":       {"stars": ">250", "target": 2000,  "min_desc_words": 5, "min_forks": 15},
    "Dart":         {"stars": ">200", "target": 1500,  "min_desc_words": 5, "min_forks": 12},
}
LANGUAGES_TO_CYCLE = list(LANGUAGE_CONFIG.keys())

SQS_QUEUE_URL = settings.sqs_queue_url
DYNAMODB_TABLE_NAME = settings.dynamodb_table_name
AWS_REGION = settings.aws_region

sqs_client = None
dynamodb_resource = None
state_table = None
if SQS_QUEUE_URL and DYNAMODB_TABLE_NAME and AWS_REGION:
    try:
        sqs_client = boto3.client("sqs", region_name=AWS_REGION)
        dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
        state_table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
    except Exception as e:
        logger.critical(f"Could not initialize AWS clients: {e}")
else:
    logger.critical("Missing SQS_QUEUE_URL, DYNAMODB_TABLE_NAME, or AWS_REGION in settings")


async def get_discovery_state(language: str) -> Tuple[int, int, bool]:
    """Reads state (page, count, completed) for a language from DynamoDB."""
    if not state_table: return 1, 0, False
    try:
        response = state_table.get_item(Key={"language": language})
        item = response.get("Item", {})
        page = int(item.get("page", 1))
        count = int(item.get("count", 0))
        completed = bool(item.get("completed", False))
        # GitHub Search API returns max 1000 results (10 pages of 100) for any query.
        # If page > 10, reset to page 1 and continue (different time periods will find new repos)
        if page > 10:
            logger.info(f"Page number for {language} exceeded 10, resetting to page 1")
            page = 1 # Reset page - time-based query will find different repos
            # Don't mark as completed - keep discovering until target is reached
        return page, count, completed
    except Exception as e:
        logger.error(f"Failed to read state for {language}: {e}")
        return 1, 0, False

async def update_discovery_state(language: str, page: int, count: int, completed: bool):
    """Updates state for a language in DynamoDB."""
    if not state_table: return
    try:
        state_table.put_item(
            Item={
                "language": language,
                "page": page,
                "count": count,
                "completed": completed,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Failed to update state for {language}: {e}")

async def select_next_language_to_search() -> Optional[str]:
    """
    Selects the next language to search using a simple round-robin based on a cursor.
    Skips languages marked as completed for this cycle.
    """
    if not state_table: return random.choice(LANGUAGES_TO_CYCLE) # Fallback
    try:
        cursor_item = state_table.get_item(Key={"language": "__CURSOR__"}).get("Item", {})
        current_index = int(cursor_item.get("index", -1))  # DynamoDB returns Decimal, convert to int
        
        # Try to find the next non-completed language
        for i in range(len(LANGUAGES_TO_CYCLE)):
            next_index = (current_index + 1 + i) % len(LANGUAGES_TO_CYCLE)
            next_language = LANGUAGES_TO_CYCLE[next_index]
            _, _, completed = await get_discovery_state(next_language)
            if not completed:
                # Update cursor to the chosen language's index
                state_table.put_item(Item={"language": "__CURSOR__", "index": next_index})
                return next_language
                
        logger.info("All language targets seem complete for this cycle")
        return None # All languages might be marked complete

    except Exception as e:
        logger.error(f"Could not determine next language: {e}")
        return random.choice(LANGUAGES_TO_CYCLE) # Fallback

# --- Quality Scoring & Filtering Function ---

def calculate_quality_score(repo_data: Dict[str, Any]) -> float:
    """
    Calculates a weighted quality score (0-100) for a repository.
    Higher scores indicate higher quality/relevance for search.
    """
    score = 0.0
    
    # Stars (max 30 points, logarithmic scale to avoid star-dominated results)
    stars = repo_data.get("stargazers_count", 0)
    if stars > 0:
        score += min(30, math.log10(stars + 1) * 7.5)  # 10 stars = 7.5pts, 100 = 15pts, 1000 = 22.5pts, 10000 = 30pts
    
    # Forks (max 15 points, indicates usefulness)
    forks = repo_data.get("forks_count", 0)
    if forks > 0:
        score += min(15, math.log10(forks + 1) * 5)
    
    # Watchers (max 10 points, indicates active interest)
    watchers = repo_data.get("watchers_count", 0)
    if watchers > 0:
        score += min(10, math.log10(watchers + 1) * 3.3)
    
    # Recent activity (max 15 points)
    pushed_at_str = repo_data.get("pushed_at")
    if pushed_at_str:
        try:
            last_push = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
            days_since_push = (datetime.now(timezone.utc) - last_push).days
            if days_since_push <= 30:
                score += 15
            elif days_since_push <= 90:
                score += 12
            elif days_since_push <= 180:
                score += 8
            elif days_since_push <= 365:
                score += 5
        except: pass
    
    # Topics/tags (max 10 points)
    topics = repo_data.get("topics", [])
    if topics:
        score += min(10, len(topics) * 2)  # 2 points per topic, max 10
    
    # Description quality (max 10 points)
    description = repo_data.get("description", "")
    if description:
        word_count = len(description.split())
        if word_count >= 10:
            score += 10
        elif word_count >= 6:
            score += 7
        elif word_count >= 4:
            score += 4
    
    # License exists (10 points - strong quality signal)
    if repo_data.get("license"):
        score += 10
    
    return score


def is_candidate_high_quality(repo_data: Dict[str, Any], config: Dict) -> bool:
    """
    Enhanced filter using search result data + quality scoring to assess repo quality.
    This is the PRIMARY QUALITY GATE - be strict here to maximize search relevance.
    """
    if not repo_data: 
        return False

    # === HARD FILTERS (immediate rejection) ===
    
    # Filter 1: Must NOT be a fork
    if repo_data.get("fork", True): 
        return False
        
    # Filter 2: Must NOT be archived
    if repo_data.get("archived", False): 
        return False

    # Filter 3: Must have a license (indicates serious/professional project)
    if not repo_data.get("license"):
        return False
    
    # Filter 4: Must have meaningful description
    description = repo_data.get("description")
    min_desc_words = config.get("min_desc_words", 5)
    if not description or len(description.split()) < min_desc_words:
        return False
        
    
    # Filter 6: Minimum fork count 
    min_forks = config.get("min_forks", 20)
    actual_min_forks = max(10, min_forks - 10)  # At least 10 forks, or config - 10
    if repo_data.get("forks_count", 0) < actual_min_forks:
        return False

    # Filter 7: Must have README (GitHub Search API includes this in results)
    if not repo_data.get("has_wiki") and not repo_data.get("has_pages"):
        # If no wiki and no pages, likely minimal documentation
        # We'll be lenient here but could be stricter
        pass

    # Filter 8: Check for abandonment signs
    open_issues = repo_data.get("open_issues_count", 0)
    pushed_at_str = repo_data.get("pushed_at")
    if open_issues > 200:  # Too many unresolved issues
        if pushed_at_str:
            try:
                last_push = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
                days_since_push = (datetime.now(timezone.utc) - last_push).days
                if days_since_push > 365:  # No push in 1+ year with 200+ issues
                    return False
            except: 
                pass

    # Filter 9: Fork/Star ratio check (avoid low-quality popular repos)
    stars = repo_data.get("stargazers_count", 0)
    forks = repo_data.get("forks_count", 0)
    if stars > 100 and forks > 0:
        fork_star_ratio = forks / stars
        if fork_star_ratio < 0.01:  # Less than 1% fork rate for popular repos
            # Could indicate tutorial/example repo with low practical value
            # Being lenient - you can adjust this threshold
            pass
    
    quality_score = calculate_quality_score(repo_data)
    MIN_QUALITY_SCORE = 30  # Out of 100 - lowered for better coverage (was 40)

    
    if quality_score < MIN_QUALITY_SCORE:
        return False

    return True


async def process_single_page(language: str, config: Dict, query: str, page: int) -> Tuple[int, int, List[float], bool]:
    """
    Process a single page of search results.
    
    NEW FLOW:
    1. Filter high-quality repos from search results
    2. Save each repo to database (status: "discovered")
    3. Send only project_id to SQS for embedding generation
    
    Returns:
        (processed_count, skipped_count, quality_scores, has_more_results)
    """
    logger.info(f"Searching page {page} for {language}")
    search_results = await github_client.search_repositories(
        query=query, 
        page=page, 
        per_page=100,
        sort="stars", 
        order="desc"
    )

    items = search_results.get("items", []) if search_results else []
    
    if not items:
        logger.info(f"No results on page {page}")
        return 0, 0, [], False

    # Process, filter, save to DB, and queue IDs
    messages_to_queue = []
    processed = 0
    skipped = 0
    scores = []
    
    # Create a database session for this batch
    session_generator = get_session()
    db_session = None
    
    try:
        db_session = await anext(session_generator)
        processing_service = DataProcessingService(session=db_session)

        for repo in items:
            repo_name = repo.get("full_name", "unknown")
            quality_score = calculate_quality_score(repo)
            scores.append(quality_score)
            
            if is_candidate_high_quality(repo, config):
                full_name = repo.get("full_name")
                if full_name:
                    # COMPLETE DATA FETCH: Save search results + fetch languages & README from API
                    # Discoverer is the "API heavy worker" - does all GitHub API calls
                    try:
                        saved_project = await processing_service.save_discovered_repo_from_search_results(repo)
                        
                        if saved_project:
                            # Queue only the project ID (minimal message)
                            messages_to_queue.append({
                                'Id': str(saved_project.id),
                                'MessageBody': json.dumps({
                                    "project_id": saved_project.id
                                })
                            })
                            processed += 1
                            
                            if quality_score >= 70:
                                logger.info(f"⭐ {full_name} (score: {quality_score:.1f}, ID: {saved_project.id})")
                            
                            # Send batch when we have 10 messages
                            if len(messages_to_queue) == 10:
                                try:
                                    sqs_client.send_message_batch(QueueUrl=SQS_QUEUE_URL, Entries=messages_to_queue)
                                    messages_to_queue = []
                                except Exception as e:
                                    logger.error(f"SQS batch failed: {e}")
                        else:
                            logger.warning(f"Failed to save {full_name} to database")
                            skipped += 1
                            
                    except Exception as e:
                        logger.error(f"Failed to process {full_name}: {e}")
                        skipped += 1
            else:
                skipped += 1

        # Send remaining messages
        if messages_to_queue:
            try:
                sqs_client.send_message_batch(QueueUrl=SQS_QUEUE_URL, Entries=messages_to_queue)
            except Exception as e:
                logger.error(f"Final SQS batch failed: {e}")
                
    finally:
        # Always close the database session
        if db_session:
            await db_session.close()

    has_more = len(items) == 100  # Full page = more results likely available
    return processed, skipped, scores, has_more


async def discover_and_queue():
    """
    Main orchestration logic for the Discoverer task.
    NOW PROCESSES MULTIPLE PAGES PER INVOCATION for 10x throughput!
    """
    if not sqs_client or not state_table:
        logger.critical("AWS clients not initialized, aborting")
        return

    language = await select_next_language_to_search()
    if not language: 
        logger.info("All languages completed for this cycle")
        return
        
    start_page, current_count, completed = await get_discovery_state(language)
    config = LANGUAGE_CONFIG[language]

    if completed or current_count >= config["target"]:
        logger.info(f"Target {config['target']} reached or cycle completed for {language}, skipping")
        if not completed:
             await update_discovery_state(language, 1, current_count, True)
        return

    # Construct GitHub Search Query
    lang_query_name = config.get("query_name", language.lower())
    two_years_ago = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    query = (
        f"language:{lang_query_name} "
        f"stars:{config['stars']} "
        f"fork:false "
        f"pushed:>{two_years_ago}"
    )
    
    logger.info(f"{'='*80}")
    logger.info(f"DISCOVERING: {language} (starting page {start_page})")
    logger.info(f"Query: {query}")
    logger.info(f"Progress: {current_count}/{config['target']} repos queued")
    logger.info(f"{'='*80}")
    
    # PROCESS MULTIPLE PAGES (10 pages = 1000 repos max per invocation)
    PAGES_PER_INVOCATION = 10
    total_processed = 0
    total_skipped = 0
    all_quality_scores = []
    current_page = start_page
    
    for page_offset in range(PAGES_PER_INVOCATION):
        page = start_page + page_offset
        
        # Stop if we've exceeded GitHub's 1000 result limit (page 10)
        # On next invocation, page will reset to 1 (see get_discovery_state)
        if page > 10:
            logger.info("Reached GitHub page limit (10), will reset to page 1 on next run")
            break
        
        # Stop if we've reached target
        if current_count + total_processed >= config["target"]:
            logger.info(f"Reached target {config['target']} repos, stopping discovery for {language}")
            completed = True
            break
        
        # Process this page
        processed, skipped, scores, has_more = await process_single_page(
            language, config, query, page
        )
        
        total_processed += processed
        total_skipped += skipped
        all_quality_scores.extend(scores)
        current_page = page + 1
        
        # Stop if no more results available
        if not has_more:
            logger.info(f"No more results available after page {page}, marking as complete")
            completed = True
            break
    
    # Log summary statistics
    avg_score = sum(all_quality_scores) / len(all_quality_scores) if all_quality_scores else 0
    max_score = max(all_quality_scores) if all_quality_scores else 0
    acceptance_rate = (total_processed / (total_processed + total_skipped) * 100) if (total_processed + total_skipped) > 0 else 0
    
    logger.info(f"{'='*80}")
    logger.info(f"SUMMARY for {language}:")
    logger.info(f"  Pages processed: {start_page} → {current_page - 1} ({current_page - start_page} pages)")
    logger.info(f"  Repos queued: {total_processed}")
    logger.info(f"  Repos skipped: {total_skipped}")
    logger.info(f"  Acceptance rate: {acceptance_rate:.1f}%")
    logger.info(f"  Quality scores - Avg: {avg_score:.1f} | Max: {max_score:.1f}")
    logger.info(f"  Total progress: {current_count + total_processed}/{config['target']}")
    logger.info(f"  Cycle completed: {completed}")
    logger.info(f"{'='*80}")

    # Update state
    new_count = current_count + total_processed
    await update_discovery_state(
        language, 
        current_page if not completed else 1, 
        new_count, 
        completed
    )

# --- AWS Lambda Handler ---
def handler(event, context):
    """AWS Lambda entry point."""
    logger.info("Discoverer Lambda V2 started")
    start_time = time.time()
    try:
        asyncio.run(discover_and_queue())
        duration = time.time() - start_time
        logger.info(f"Discoverer Lambda finished successfully in {duration:.2f} seconds")
        return {"status": "Success"}
    except Exception as e:
        duration = time.time() - start_time
        logger.critical(f"FATAL ERROR in Discoverer Lambda after {duration:.2f} seconds: {e}")
        raise e