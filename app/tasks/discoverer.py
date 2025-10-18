# tasks/discoverer.py
# The advanced "Discoverer" / "Hunter" Lambda function.
# Uses multiple strategies (initially language-focused) and state management
# to find high-quality repo candidates and queue them for processing.

import boto3
import json
import asyncio
import random
import time
import math
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime, timedelta, timezone

# Ensure the app module can be found (adjust path as needed for Lambda)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.external.github_client import github_client
from app.settings import settings

# --- CURATED DISCOVERY STRATEGY ---
# AWS RDS Free Tier Analysis: 20GB can hold ~1M repos (detailed calc: STORAGE_CALCULATION.md)
# Gemini's 75k estimate was ultra-conservative. Real capacity: 1M+ repos!
# 
# CURRENT STRATEGY: Phase 2 - Balanced Quality & Quantity
# Total target: ~75,000 premium repos (uses ~1.2GB = 6% of capacity)
# Focus: Excellent search coverage with very high quality results
#
# FUTURE PHASES:
#   Phase 3: 200k repos (>200 stars) - uses ~3.2GB (16%)
#   Phase 4: 500k repos (>50 stars) - uses ~8GB (40%)
LANGUAGE_CONFIG: Dict[str, Dict] = {
    # Popular languages: Higher targets, maintain quality
    "Python":       {"stars": ">500", "target": 15000, "min_desc_words": 5, "min_forks": 30},
    "JavaScript":   {"stars": ">500", "target": 12000, "min_desc_words": 5, "min_forks": 30},
    "TypeScript":   {"stars": ">400", "target": 8000,  "min_desc_words": 5, "min_forks": 25},
    "Go":           {"stars": ">400", "target": 6000,  "min_desc_words": 5, "min_forks": 25},
    "Java":         {"stars": ">400", "target": 6000,  "min_desc_words": 5, "min_forks": 25},
    "Rust":         {"stars": ">300", "target": 5000,  "min_desc_words": 5, "min_forks": 20},
    
    # Mid-tier languages: Balanced coverage
    "CSharp":       {"stars": ">300", "target": 4000,  "query_name": "c#", "min_desc_words": 5, "min_forks": 20},
    "CPP":          {"stars": ">300", "target": 4000,  "query_name": "c++", "min_desc_words": 5, "min_forks": 20},
    "PHP":          {"stars": ">300", "target": 3000,  "min_desc_words": 5, "min_forks": 20},
    "Ruby":         {"stars": ">300", "target": 3000,  "min_desc_words": 5, "min_forks": 20},
    "C":            {"stars": ">300", "target": 2500,  "query_name": "c", "min_desc_words": 4, "min_forks": 15},
    
    # Emerging languages: Quality over quantity
    "Swift":        {"stars": ">250", "target": 2000,  "min_desc_words": 5, "min_forks": 15},
    "Kotlin":       {"stars": ">250", "target": 2000,  "min_desc_words": 5, "min_forks": 15},
    "Dart":         {"stars": ">200", "target": 1500,  "min_desc_words": 5, "min_forks": 12},
}
LANGUAGES_TO_CYCLE = list(LANGUAGE_CONFIG.keys())

# --- AWS Clients (Configured from settings) ---
SQS_QUEUE_URL = settings.sqs_queue_url
DYNAMODB_TABLE_NAME = settings.dynamodb_state_table_name
AWS_REGION = settings.aws_region

# Initialize AWS clients only if configuration is available
sqs_client = None
dynamodb_resource = None
state_table = None
if SQS_QUEUE_URL and DYNAMODB_TABLE_NAME and AWS_REGION:
    try:
        sqs_client = boto3.client("sqs", region_name=AWS_REGION)
        dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
        state_table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
    except Exception as e:
        print(f"FATAL: Could not initialize AWS clients. Error: {e}")
else:
    print("FATAL: Missing SQS_QUEUE_URL, DYNAMODB_TABLE_NAME, or AWS_REGION in settings.")

# --- State Management Functions ---

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
        # If page > 10, it means we've exhausted results for this query configuration.
        if page > 10:
            print(f"INFO: Page number for {language} exceeded 10. Marking as completed for this cycle.")
            completed = True
            page = 1 # Reset page for potential future runs with different criteria
        return page, count, completed
    except Exception as e:
        print(f"ERROR: Failed to read state for {language}: {e}")
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
        print(f"ERROR: Failed to update state for {language}: {e}")

async def select_next_language_to_search() -> Optional[str]:
    """
    Selects the next language to search using a simple round-robin based on a cursor.
    Skips languages marked as completed for this cycle.
    """
    if not state_table: return random.choice(LANGUAGES_TO_CYCLE) # Fallback
    try:
        cursor_item = state_table.get_item(Key={"language": "__CURSOR__"}).get("Item", {})
        current_index = cursor_item.get("index", -1)
        
        # Try to find the next non-completed language
        for i in range(len(LANGUAGES_TO_CYCLE)):
            next_index = (current_index + 1 + i) % len(LANGUAGES_TO_CYCLE)
            next_language = LANGUAGES_TO_CYCLE[next_index]
            _, _, completed = await get_discovery_state(next_language)
            if not completed:
                # Update cursor to the chosen language's index
                state_table.put_item(Item={"language": "__CURSOR__", "index": next_index})
                return next_language
                
        print("INFO: All language targets seem complete for this cycle.")
        return None # All languages might be marked complete

    except Exception as e:
        print(f"ERROR: Could not determine next language: {e}")
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
        
    # Filter 5: Must have topics (indicates proper tagging/discoverability)
    topics = repo_data.get("topics", [])
    if not topics or len(topics) < 2:  # At least 2 topics
        return False

    # Filter 6: Minimum fork count (indicates usefulness/adoption)
    min_forks = config.get("min_forks", 20)
    if repo_data.get("forks_count", 0) < min_forks:
        return False

    # Filter 7: Must have README (GitHub Search API includes this in results)
    # Note: has_wiki, has_pages are also available but README is most critical
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
    
    # === SOFT FILTER: Quality Score ===
    # Calculate overall quality score and reject if too low
    quality_score = calculate_quality_score(repo_data)
    MIN_QUALITY_SCORE = 40  # Out of 100 - adjust based on results
    
    if quality_score < MIN_QUALITY_SCORE:
        return False

    return True

# --- Main Discovery Logic ---

async def discover_and_queue():
    """
    Main orchestration logic for the Discoverer task.
    """
    if not sqs_client or not state_table:
        print("FATAL: AWS clients not initialized. Aborting.")
        return

    language = await select_next_language_to_search()
    if not language: return
        
    page, current_count, completed = await get_discovery_state(language)
    config = LANGUAGE_CONFIG[language]

    if completed or current_count >= config["target"]:
        print(f"INFO: Target {config['target']} reached or cycle completed for {language}. Skipping.")
        if not completed: # Mark as complete if target is reached
             await update_discovery_state(language, 1, current_count, True)
        return

    # --- Construct GitHub Search Query ---
    lang_query_name = config.get("query_name", language.lower())
    two_years_ago = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    query = (
        f"language:{lang_query_name} "
        f"stars:{config['stars']} "
        f"fork:false "
        f"pushed:>{two_years_ago}"
    )
    
    print(f"Searching GitHub: '{query}', Page: {page}")
    search_results = await github_client.search_repositories(
        query=query, 
        page=page, 
        per_page=100, # Request max allowed per page
        sort="stars", 
        order="desc"
    )

    items = search_results.get("items", []) if search_results else []
    
    if not items:
        print(f"INFO: No results found for {language} on page {page}. Marking as completed for cycle.")
        await update_discovery_state(language, 1, current_count, True) # Mark completed
        return

    # --- Process, Filter, and Queue Results ---
    messages_to_queue = []
    processed_in_batch = 0
    skipped_in_batch = 0
    quality_scores = []  # Track quality scores for statistics

    for repo in items:
        repo_name = repo.get("full_name", "unknown")
        quality_score = calculate_quality_score(repo)
        quality_scores.append(quality_score)
        
        if is_candidate_high_quality(repo, config):
            full_name = repo.get("full_name")
            if full_name:
                messages_to_queue.append({
                    'Id': full_name.replace('/', '-').replace('.', '_'), # Make ID SQS Batch compatible
                    'MessageBody': json.dumps({
                        "full_name": full_name,
                        "quality_score": round(quality_score, 2),
                        "stars": repo.get("stargazers_count", 0)
                    })
                })
                processed_in_batch += 1
                
                # Log high-quality candidates (for monitoring)
                if quality_score >= 70:
                    print(f"  ⭐ EXCELLENT: {full_name} (score: {quality_score:.1f}, stars: {repo.get('stargazers_count', 0)})")
                
                if len(messages_to_queue) == 10: # Send in batches of 10
                    try:
                        sqs_client.send_message_batch(QueueUrl=SQS_QUEUE_URL, Entries=messages_to_queue)
                        messages_to_queue = []
                    except Exception as e:
                        print(f"ERROR: Failed to send batch to SQS: {e}")
                        # Consider breaking or logging failed IDs
        else:
            skipped_in_batch += 1

    # Send any remaining messages
    if messages_to_queue:
        try:
            sqs_client.send_message_batch(QueueUrl=SQS_QUEUE_URL, Entries=messages_to_queue)
        except Exception as e:
            print(f"ERROR: Failed to send final batch to SQS: {e}")

    # --- Log Statistics ---
    avg_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    max_score = max(quality_scores) if quality_scores else 0
    min_score = min(quality_scores) if quality_scores else 0
    acceptance_rate = (processed_in_batch / len(items) * 100) if items else 0
    
    print(f"Batch completed for {language} page {page}:")
    print(f"Queued: {processed_in_batch} | Skipped: {skipped_in_batch} | Acceptance Rate: {acceptance_rate:.1f}%")
    print(f"Quality Scores - Avg: {avg_score:.1f} | Max: {max_score:.1f} | Min: {min_score:.1f}")

    # --- Update State for Next Run ---
    new_page = page + 1
    new_count = current_count + processed_in_batch
    # Check completion based on target OR if we got less results than requested (likely last page)
    is_complete_for_cycle = new_count >= config["target"] or len(items) < 100 or new_page > 10
    
    await update_discovery_state(language, new_page if not is_complete_for_cycle else 1, new_count, is_complete_for_cycle)
    print(f"State updated for {language}: Next page {new_page if not is_complete_for_cycle else 1}, Total found {new_count}/{config['target']}, Completed cycle: {is_complete_for_cycle}")

# --- AWS Lambda Handler ---
def handler(event, context):
    """AWS Lambda entry point."""
    print("Discoverer Lambda V2 started.")
    start_time = time.time()
    try:
        asyncio.run(discover_and_queue())
        duration = time.time() - start_time
        print(f"Discoverer Lambda finished successfully in {duration:.2f} seconds.")
        return {"status": "Success"}
    except Exception as e:
        duration = time.time() - start_time
        print(f"FATAL ERROR in Discoverer Lambda after {duration:.2f} seconds: {e}")
        # Add more detailed logging here (e.g., traceback)
        raise e # Raise exception to let Lambda know it failed