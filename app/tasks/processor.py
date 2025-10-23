# tasks/processor.py
# The "Processor" Lambda function.
# Triggered by SQS messages from the Discoverer. Its job is to take a repo name,
# use the DataProcessingService to fetch, process, embed, and save it to the database.

import json
import asyncio
import os
import time
from typing import Dict, Any, List

# Ensure the app module can be found (adjust path as needed for Lambda)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Import necessary components
from app.services.data_processing_service import DataProcessingService
from app.db import get_session
from app.external.github_client import RateLimitError
# Note: github_client and embedding_client are used by DataProcessingService internally (singleton pattern)

# --- Helper Function to Process a Single Message ---

async def process_single_repo(message_body: Dict[str, Any], message_id: str) -> Dict[str, Any]:
    """
    NEW FLOW: Takes a project_id from SQS, loads from DB, and creates embeddings.
    Handles dependency creation and session management outside of FastAPI context.
    
    Returns:
        Dict with 'success' (bool), 'message_id' (str), and optional 'error' (str)
    """
    # NEW: Parse project_id instead of full_name
    project_id = message_body.get("project_id")
    if not project_id:
        print(f"ERROR: Invalid message body received (missing project_id): {message_body}")
        return {"success": False, "message_id": message_id, "error": "Invalid message body"}

    print(f"INFO: Starting embedding generation for project ID: {project_id}")

    # Manually manage the database session as we are outside FastAPI's request lifecycle
    session_generator = get_session()
    db_session = None
    try:
        db_session = await anext(session_generator) # Get the session

        # Initialize the DataProcessingService MANUALLY with the session.
        # Lambda doesn't use FastAPI's Depends()
        # gh_client and embed_client will use singletons by default
        processing_service = DataProcessingService(session=db_session)

        # NEW: Execute the embedding generation logic only
        result = await processing_service.create_and_save_embeddings(project_id=project_id)
        
        if result:
            print(f"SUCCESS: Project ID {project_id} ({result.full_name}) embeddings created successfully")
            return {"success": True, "message_id": message_id}
        else:
            print(f"ERROR: Failed to create embeddings for project ID {project_id}")
            return {"success": False, "message_id": message_id, "error": "Embedding creation failed"}

    except RateLimitError as e:
        # Rate limit hit - this is not a critical error, just need to retry later
        print(f"INFO: Rate limit hit for project ID {project_id}. Returning to queue for retry. Error: {e}")
        # Return failure so SQS will retry this message later
        return {"success": False, "message_id": message_id, "error": "Rate limit hit"}
    
    except Exception as e:
        # Log the error details for debugging
        import traceback
        print(f"CRITICAL ERROR processing project ID {project_id}: {e}")
        print(traceback.format_exc()) # Print full stack trace
        
        # Return failure info instead of raising
        # This allows partial batch success
        return {"success": False, "message_id": message_id, "error": str(e)}
    finally:
        # ALWAYS ensure the database session is closed, even if errors occur.
        if db_session:
            await db_session.close()
            print(f"INFO: Database session closed for project ID {project_id}")

# --- Helper Function to Process All Messages in Parallel ---

async def process_all_repos(messages_with_ids: List[tuple]) -> List[Dict[str, Any]]:
    """
    Processes all SQS messages in parallel using asyncio.gather.
    
    Args:
        messages_with_ids: List of tuples (message_body, message_id)
        
    Returns:
        List of result dicts with 'success', 'message_id', and optional 'error'
    """
    if not messages_with_ids:
        print("INFO: No messages to process.")
        return []
    
    print(f"INFO: Starting parallel processing of {len(messages_with_ids)} repositories...")
    
    # Create tasks for all messages
    tasks = [process_single_repo(body, msg_id) for body, msg_id in messages_with_ids]
    
    # Process all tasks concurrently
    results = await asyncio.gather(*tasks)
    
    # Log results summary
    success_count = sum(1 for r in results if r.get("success"))
    error_count = len(results) - success_count
    
    print(f"INFO: Parallel processing complete. Success: {success_count}, Errors: {error_count}")
    
    return results

# --- AWS Lambda Handler ---

def handler(event, context):
    """
    AWS Lambda entry point triggered by SQS.
    Processes ALL messages in the batch CONCURRENTLY using asyncio.gather.
    
    PARTIAL BATCH RESPONSE:
    - Uses 'batchItemFailures' to report only failed messages
    - Successful messages are deleted from queue immediately
    - Failed messages are retried individually (no "all or nothing" waste)
    
    This dramatically improves throughput by preventing unnecessary retries.
    """
    print(f"INFO: Processor Lambda started. Received {len(event.get('Records', []))} messages.")
    start_time = time.time()

    # Parse SQS message batch with message IDs
    messages_with_ids = []
    for record in event.get("Records", []):
        try:
            message_body = json.loads(record.get("body", "{}"))
            message_id = record.get("messageId")
            messages_with_ids.append((message_body, message_id))
        except json.JSONDecodeError:
            print(f"ERROR: Could not decode SQS message body: {record.get('body')}")
            # Malformed messages - add to failures list
            message_id = record.get("messageId")
            if message_id:
                messages_with_ids.append(({"project_id": None}, message_id))

    # Process ALL messages in parallel (asyncio.gather)
    batch_item_failures = []
    
    if messages_with_ids:
        results = asyncio.run(process_all_repos(messages_with_ids))
        
        # Build list of failed message IDs for SQS
        for result in results:
            if not result.get("success"):
                batch_item_failures.append({
                    "itemIdentifier": result.get("message_id")
                })
                print(f"FAILED: Message {result.get('message_id')} will be retried. Error: {result.get('error')}")
        
        success_count = len(results) - len(batch_item_failures)
        print(f"INFO: Batch complete. Success: {success_count}/{len(results)}, Failures: {len(batch_item_failures)}")
    else:
        print("WARNING: No valid messages to process in this batch.")

    duration = time.time() - start_time
    print(f"INFO: Processor Lambda finished in {duration:.2f} seconds.")
    
    # Return partial batch response
    # SQS will only retry messages in batchItemFailures
    return {
        "batchItemFailures": batch_item_failures
    }