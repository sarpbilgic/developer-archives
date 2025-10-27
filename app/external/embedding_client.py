import os
import logging
from sentence_transformers import SentenceTransformer
from typing import List, Optional

logger = logging.getLogger(__name__)

class EmbeddingClient:

    def __init__(self, model_name: str = 'all-mpnet-base-v2', model_path: str = None):
        """
        Initializes the client and loads the specified sentence-transformer model.
        
        Args:
            model_name: The name of the model to load from Hugging Face.
            model_path: Optional path to a pre-downloaded model (for Lambda/offline use).
        """
        if model_path is None:
            model_path = os.getenv('MODEL_PATH', '/opt/model')
        
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
            
            logger.info(f"Loading embedding model: '{model_name}' (this may take a moment)")
            self.model = SentenceTransformer(model_name)
            logger.info(f"Embedding model '{model_name}' loaded successfully")

    def get_embedding(self, text: str) -> Optional[List[float]]:
        if not text or not isinstance(text, str) or not text.strip():
            return None

        embedding_array = self.model.encode(text)
        return embedding_array.tolist()

embedding_client = EmbeddingClient()