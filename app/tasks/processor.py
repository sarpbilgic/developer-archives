# tasks/processor.py
# The "Processor" Lambda function.
# Triggered by SQS messages from the Discoverer. Its job is to take a repo name,
# use the DataProcessingService to fetch, process, embed, and save it to the database.

import json
import asyncio
import os
from typing import Dict, Any

# Ensure the app module can be found (adjust path as needed for Lambda)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Import necessary components
from app.services.data_processing_service import DataProcessingService
from app.database import get_session
from app.settings import settings # Needed for initializing clients within the service if not using DI framework outside FastAPI

# --- Helper Function to Process a Single Message ---

async def process_single_repo(message_body: Dict[str, Any]):
    """
    Takes a single message body from SQS and processes the corresponding repository.
    Handles dependency creation and session management outside of FastAPI context.
    """
    full_name = message_body.get("full_name")
    if not full_name or '/' not in full_name:
        print(f"ERROR: Invalid message body received: {message_body}")
        return

    owner, repo = full_name.split('/', 1)
    print(f"INFO: Starting processing for repository: {owner}/{repo}")

    # Manually manage the database session as we are outside FastAPI's request lifecycle
    session_generator = get_session()
    db_session = None
    try:
        db_session = await anext(session_generator) # Get the session

        # Initialize the DataProcessingService MANUALLY with the session.
        # It will internally use the singleton instances of github_client and embedding_client.
        # We pass the session explicitly here.
        processing_service = DataProcessingService(session=db_session)

        # Execute the main processing logic
        await processing_service.process_and_save_repo(owner=owner, repo=repo)

    except Exception as e:
        # Log the error details for debugging
        import traceback
        print(f"CRITICAL ERROR processing {owner}/{repo}: {e}")
        print(traceback.format_exc()) # Print full stack trace
        # Depending on the error, you might want to implement retry logic
        # or send the message to a Dead Letter Queue (DLQ) if configured.
    finally:
        # ALWAYS ensure the database session is closed, even if errors occur.
        if db_session:
            await db_session.close()
            print(f"INFO: Database session closed for {owner}/{repo}")

# --- AWS Lambda Handler ---

def handler(event, context):
    """
    AWS Lambda entry point triggered by SQS.
    Processes messages received in the event batch.
    """
    print(f"INFO: Processor Lambda started. Received {len(event.get('Records', []))} messages.")
    start_time = time.time()

    # SQS sends messages in batches ('Records' is a list)
    messages_to_process = []
    for record in event.get("Records", []):
        try:
            # Parse the message body from the SQS record
            message_body = json.loads(record.get("body", "{}"))
            messages_to_process.append(message_body)
        except json.JSONDecodeError:
            print(f"ERROR: Could not decode SQS message body: {record.get('body')}")
            # Consider sending malformed messages to DLQ

    # Process messages sequentially for simplicity in this example.
    # For higher throughput, you could explore asyncio.gather here, but
    # be mindful of database connection limits and potential API rate limits.
    for body in messages_to_process:
        asyncio.run(process_single_repo(body))

    duration = time.time() - start_time
    print(f"INFO: Processor Lambda finished processing {len(messages_to_process)} messages in {duration:.2f} seconds.")
    # SQS trigger automatically deletes messages from the queue if the Lambda executes successfully.
    # If the function raises an exception, SQS will retry based on queue configuration.
    return {"status": "Success"}