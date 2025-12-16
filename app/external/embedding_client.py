# app/external/embedding_client.py
"""
Embedding client with automatic backend selection.
Supports both PyTorch (sentence-transformers) and ONNX Runtime backends.

Set EMBEDDING_CLIENT=onnx to use ONNX Runtime (smaller, faster).
Default is PyTorch for backwards compatibility.
"""

import os
import logging
from typing import List, Optional, Union

logger = logging.getLogger(__name__)

# Check which backend to use
EMBEDDING_BACKEND = os.getenv('EMBEDDING_CLIENT', 'pytorch').lower()


class EmbeddingClient:
    """PyTorch-based embedding client using sentence-transformers."""
    
    def __init__(self, model_name: str = 'all-mpnet-base-v2', model_path: str = None):
        from sentence_transformers import SentenceTransformer

        if model_path is None:
            model_path = os.getenv('MODEL_PATH', '/var/task/model')
        
        if os.path.exists(model_path):
            logger.info(f"Loading pre-cached embedding model from {model_path}")
            try:
                model_files = os.listdir(model_path)[:10]
                logger.debug(f"Model directory contents: {model_files}")
            except Exception as e:
                logger.debug(f"Could not list model directory: {e}")
                
            self.model = SentenceTransformer(model_path)
            logger.info("Embedding model loaded from cache successfully")
        else:
            logger.error(f"Model path {model_path} does not exist")
            try:
                parent_dir = os.path.dirname(model_path)
                if os.path.exists(parent_dir):
                    contents = os.listdir(parent_dir)[:10]  
                    logger.debug(f"Parent directory {parent_dir} contents: {contents}")
                else:
                    logger.debug(f"Parent directory {parent_dir} does not exist")
                    
                if os.path.exists("/var/task"):
                    task_contents = os.listdir("/var/task")[:15]
                    logger.debug(f"/var/task contents: {task_contents}")
            except Exception as e:
                logger.debug(f"Directory listing failed: {e}")
            
            logger.warning(f"Falling back to loading model from Hugging Face: '{model_name}'")
            self.model = SentenceTransformer(model_name)
            logger.info(f"Embedding model '{model_name}' loaded successfully")

    def get_embedding(self, text: str) -> Optional[List[float]]:
        if not text or not isinstance(text, str) or not text.strip():
            return None

        embedding_array = self.model.encode(text)
        return embedding_array.tolist()


# Type alias for either client
EmbeddingClientType = Union[EmbeddingClient, "EmbeddingClientONNX"]

_cached_client: Optional[EmbeddingClientType] = None


def get_embedding_client() -> EmbeddingClientType:
    """
    Get or create the cached embedding client.
    
    Automatically selects backend based on EMBEDDING_CLIENT env var:
    - 'onnx': Use ONNX Runtime (smaller, faster)
    - 'pytorch' (default): Use PyTorch/sentence-transformers
    """
    global _cached_client
    
    if _cached_client is None:
        if EMBEDDING_BACKEND == 'onnx':
            logger.info("Cold start: Initializing ONNX EmbeddingClient...")
            from app.external.embedding_client_onnx import EmbeddingClientONNX
            _cached_client = EmbeddingClientONNX()
            logger.info("ONNX model loaded and cached for future requests.")
        else:
            logger.info("Cold start: Initializing PyTorch EmbeddingClient...")
            _cached_client = EmbeddingClient()
            logger.info("PyTorch model loaded and cached for future requests.")

    return _cached_client