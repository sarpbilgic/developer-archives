import json
import asyncio
import logging
import os
import time
import traceback
from typing import Dict, Any, List
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db import get_session
from app.external.github_client import RateLimitError

logger = logging.getLogger(__name__)

async def process_single_repo(message_body: Dict[str, Any], message_id: str) -> Dict[str, Any]:
    """Takes a project_id from SQS, loads from DB, and creates embeddings."""
    project_id = message_body.get("project_id")
    if not project_id:
        logger.error(f"Invalid message body received (missing project_id): {message_body}")
        return {"success": False, "message_id": message_id, "error": "Invalid message body"}

    logger.info(f"Starting embedding generation for project ID: {project_id}")

    session_generator = get_session()
    db_session = None
    try:
        db_session = await anext(session_generator)
        from app.services.data_processing_service import DataProcessingService
        processing_service = DataProcessingService(session=db_session)
        result = await processing_service.create_and_save_embeddings(project_id=project_id)
        
        if result:
            logger.info(f"Project ID {project_id} ({result.full_name}) embeddings created successfully")
            return {"success": True, "message_id": message_id}
        else:
            logger.error(f"Failed to create embeddings for project ID {project_id}")
            return {"success": False, "message_id": message_id, "error": "Embedding creation failed"}

    except RateLimitError as e:
        logger.info(f"Rate limit hit for project ID {project_id}, will retry: {e}")
        return {"success": False, "message_id": message_id, "error": "Rate limit hit"}
    
    except Exception as e:
        logger.critical(f"Error processing project ID {project_id}: {e}")
        logger.debug(traceback.format_exc())
        return {"success": False, "message_id": message_id, "error": str(e)}
    finally:
        if db_session:
            await db_session.close()
            logger.debug(f"Database session closed for project ID {project_id}")

async def process_all_repos(messages_with_ids: List[tuple]) -> List[Dict[str, Any]]:
    """Processes all SQS messages in parallel using asyncio.gather."""
    if not messages_with_ids:
        logger.info("No messages to process")
        return []
    
    logger.info(f"Starting parallel processing of {len(messages_with_ids)} repositories")
    tasks = [process_single_repo(body, msg_id) for body, msg_id in messages_with_ids]
    results = await asyncio.gather(*tasks)
    
    success_count = sum(1 for r in results if r.get("success"))
    error_count = len(results) - success_count
    logger.info(f"Parallel processing complete. Success: {success_count}, Errors: {error_count}")
    
    return results

def handler(event, context):
    """AWS Lambda entry point triggered by SQS. Processes messages using partial batch response."""
    logger.info(f"Processor Lambda started. Received {len(event.get('Records', []))} messages")
    start_time = time.time()

    messages_with_ids = []
    for record in event.get("Records", []):
        try:
            message_body = json.loads(record.get("body", "{}"))
            message_id = record.get("messageId")
            messages_with_ids.append((message_body, message_id))
        except json.JSONDecodeError:
            logger.error(f"Could not decode SQS message body: {record.get('body')}")
            message_id = record.get("messageId")
            if message_id:
                messages_with_ids.append(({"project_id": None}, message_id))

    batch_item_failures = []
    
    if messages_with_ids:
        results = asyncio.run(process_all_repos(messages_with_ids))
        
        for result in results:
            if not result.get("success"):
                batch_item_failures.append({
                    "itemIdentifier": result.get("message_id")
                })
                logger.warning(f"Message {result.get('message_id')} will be retried. Error: {result.get('error')}")
        
        success_count = len(results) - len(batch_item_failures)
        logger.info(f"Batch complete. Success: {success_count}/{len(results)}, Failures: {len(batch_item_failures)}")
    else:
        logger.warning("No valid messages to process in this batch")

    duration = time.time() - start_time
    logger.info(f"Processor Lambda finished in {duration:.2f} seconds")
    
    return {
        "batchItemFailures": batch_item_failures
    }