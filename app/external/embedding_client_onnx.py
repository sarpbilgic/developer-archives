# app/external/embedding_client_onnx.py
"""
ONNX Runtime-based embedding client.
Produces identical embeddings to PyTorch version but with ~10x smaller runtime.

Model: all-mpnet-base-v2 (768 dimensions)
"""

import os
import logging
import numpy as np
from typing import List, Optional

from transformers import AutoTokenizer
from optimum.onnxruntime import ORTModelForFeatureExtraction

logger = logging.getLogger(__name__)


def mean_pooling(model_output: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    """
    Mean pooling - same as sentence-transformers implementation.
    Takes the mean of all token embeddings, weighted by attention mask.
    """
    # model_output shape: (batch_size, seq_len, hidden_size)
    # attention_mask shape: (batch_size, seq_len)
    
    # Expand attention mask for broadcasting
    input_mask_expanded = np.expand_dims(attention_mask, axis=-1)
    input_mask_expanded = np.broadcast_to(
        input_mask_expanded, 
        model_output.shape
    ).astype(np.float32)
    
    # Sum embeddings weighted by mask
    sum_embeddings = np.sum(model_output * input_mask_expanded, axis=1)
    sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
    
    return sum_embeddings / sum_mask


def normalize(embeddings: np.ndarray) -> np.ndarray:
    """L2 normalize embeddings - same as sentence-transformers."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / np.clip(norms, a_min=1e-9, a_max=None)


class EmbeddingClientONNX:
    """
    ONNX Runtime-based embedding client.
    Drop-in replacement for EmbeddingClient with identical output.
    """
    
    def __init__(self, model_name: str = 'sentence-transformers/all-mpnet-base-v2', model_path: str = None):
        if model_path is None:
            model_path = os.getenv('MODEL_PATH', '/var/task/model')
        
        if os.path.exists(model_path):
            logger.info(f"Loading ONNX embedding model from {model_path}")
            try:
                model_files = os.listdir(model_path)[:10]
                logger.debug(f"Model directory contents: {model_files}")
            except Exception as e:
                logger.debug(f"Could not list model directory: {e}")
            
            # Load ONNX model and tokenizer from local path
            self.model = ORTModelForFeatureExtraction.from_pretrained(
                model_path,
                provider='CPUExecutionProvider'
            )
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            logger.info("ONNX embedding model loaded from cache successfully")
        else:
            logger.warning(f"Model path {model_path} does not exist")
            logger.info(f"Loading ONNX model from Hugging Face: '{model_name}'")
            
            # Export and load from HuggingFace
            self.model = ORTModelForFeatureExtraction.from_pretrained(
                model_name,
                export=True,
                provider='CPUExecutionProvider'
            )
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            logger.info(f"ONNX model '{model_name}' loaded successfully")

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.
        Returns 768-dimensional normalized vector (identical to PyTorch version).
        """
        if not text or not isinstance(text, str) or not text.strip():
            return None
        
        # Tokenize (same as sentence-transformers)
        inputs = self.tokenizer(
            text,
            padding=True,
            truncation=True,
            max_length=384,
            return_tensors='np'
        )
        
        # Run ONNX inference
        outputs = self.model(**inputs)
        
        # Get the last hidden state
        # outputs is a dict-like object with 'last_hidden_state'
        last_hidden_state = outputs.last_hidden_state
        
        # Mean pooling (same as sentence-transformers all-mpnet-base-v2)
        embeddings = mean_pooling(last_hidden_state, inputs['attention_mask'])
        
        # L2 normalize (same as sentence-transformers)
        embeddings = normalize(embeddings)
        
        # Return as list (batch size is 1)
        return embeddings[0].tolist()

    def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts efficiently.
        """
        results = []
        valid_texts = []
        valid_indices = []
        
        # Filter out invalid texts
        for i, text in enumerate(texts):
            if text and isinstance(text, str) and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)
        
        if not valid_texts:
            return [None] * len(texts)
        
        # Batch tokenize
        inputs = self.tokenizer(
            valid_texts,
            padding=True,
            truncation=True,
            max_length=384,
            return_tensors='np'
        )
        
        # Run ONNX inference
        outputs = self.model(**inputs)
        last_hidden_state = outputs.last_hidden_state
        
        # Mean pooling and normalize
        embeddings = mean_pooling(last_hidden_state, inputs['attention_mask'])
        embeddings = normalize(embeddings)
        
        # Build result list with None for invalid inputs
        results = [None] * len(texts)
        for idx, embedding in zip(valid_indices, embeddings):
            results[idx] = embedding.tolist()
        
        return results


# Singleton pattern for Lambda reuse
_cached_client: Optional[EmbeddingClientONNX] = None


def get_embedding_client() -> EmbeddingClientONNX:
    """Get or create the cached embedding client."""
    global _cached_client
    
    if _cached_client is None:
        logger.info("Cold start: Initializing ONNX EmbeddingClient and loading model...")
        _cached_client = EmbeddingClientONNX()
        logger.info("ONNX model loaded and cached for future requests.")
    
    return _cached_client

