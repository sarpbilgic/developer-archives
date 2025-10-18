# app/external/embedding_client.py

from sentence_transformers import SentenceTransformer
from typing import List, Optional

class EmbeddingClient:
    """
    A client responsible for creating text embeddings using a sentence-transformer model.
    
    This class is designed to be a singleton, loading the heavyweight model only once
    when the application starts, and then providing fast embedding generation on demand.
    """
    def __init__(self, model_name: str = 'all-mpnet-base-v2'):
        """
        Initializes the client and loads the specified sentence-transformer model.
        This is a slow, one-time operation.
        
        Args:
            model_name: The name of the model to load from Hugging Face.
        """
        # This print statement is very useful for debugging. You will see it once
        # when your FastAPI application starts up.
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