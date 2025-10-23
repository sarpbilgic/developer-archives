# app/external/embedding_client.py

import os
from sentence_transformers import SentenceTransformer
from typing import List, Optional

class EmbeddingClient:
    """
    A client responsible for creating text embeddings using a sentence-transformer model.
    
    This class is designed to be a singleton, loading the heavyweight model only once
    when the application starts, and then providing fast embedding generation on demand.
    """
    def __init__(self, model_name: str = 'all-mpnet-base-v2', model_path: str = None):
        """
        Initializes the client and loads the specified sentence-transformer model.
        This is a slow, one-time operation.
        
        Args:
            model_name: The name of the model to load from Hugging Face.
            model_path: Optional path to a pre-downloaded model (for Lambda/offline use).
        """
        # Check if we're in Lambda with pre-loaded model
        if model_path is None:
            model_path = os.getenv('MODEL_PATH', '/opt/model')
        
        # Try to load from pre-downloaded path first (Lambda optimization)
        if os.path.exists(model_path):
            print(f"INFO: Loading pre-cached embedding model from {model_path}...")
            self.model = SentenceTransformer(model_path)
            print(f"INFO: Embedding model loaded from cache successfully.")
        else:
            # Fallback: Load from HuggingFace (for local development)
            print(f"INFO: Loading embedding model: '{model_name}'... (This may take a moment)")
            # Load the model from the sentence-transformers library.
            # It will be downloaded from the internet the first time it's used.
            self.model = SentenceTransformer(model_name)
            print(f"INFO: Embedding model '{model_name}' loaded successfully.")

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generates an embedding vector for a given piece of text.
        
        This is a fast operation as the model is already in memory.

        Args:
            text: The input string to be embedded.

        Returns:
            A list of floats representing the vector, or None if the input is invalid.
        """
        # Handle empty or invalid input gracefully.
        if not text or not isinstance(text, str) or not text.strip():
            return None
        
        # The .encode() method returns a NumPy array.
        embedding_array = self.model.encode(text)
        
        # We convert the NumPy array to a standard Python list, which is what
        # our SQLModel and Pydantic models expect.
        return embedding_array.tolist()

# --- THE SINGLETON PATTERN ---
# We create a single, global instance of our client.
# When other files in our project `import embedding_client`, they will all
# receive this exact same instance, ensuring the model is only ever loaded once.
embedding_client = EmbeddingClient()