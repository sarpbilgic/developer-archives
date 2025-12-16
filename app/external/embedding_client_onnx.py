"""
ONNX Runtime-based embedding client.
Produces identical embeddings to PyTorch version but with ~10x smaller runtime.

Model: all-mpnet-base-v2 (768 dimensions)
"""

import os
import sys
import logging

# ============================================================================
# NUCLEAR OPTION: Monkey-patch ONNX Runtime before ANY imports
# ============================================================================
# This prevents the DefaultLogger crash by patching SessionOptions GLOBALLY
# before optimum/transformers can create any sessions.

import onnxruntime as ort

# Silence ONNX completely
ort.set_default_logger_severity(4)

# Store original SessionOptions.__init__
_original_session_options_init = ort.SessionOptions.__init__

# Monkey-patch to inject our settings into EVERY SessionOptions created
def _patched_session_options_init(self, *args, **kwargs):
    _original_session_options_init(self, *args, **kwargs)
    # Apply Lambda-safe settings to EVERY session created
    try:
        self.log_severity_level = 4  # FATAL
        self.intra_op_num_threads = 1
        self.inter_op_num_threads = 1
        self.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    except Exception:
        pass  # Ignore if already set

ort.SessionOptions.__init__ = _patched_session_options_init

# Also patch the InferenceSession to always use our settings
_original_inference_session_init = ort.InferenceSession.__init__

def _patched_inference_session_init(self, *args, **kwargs):
    # Inject our session options if none provided
    if 'sess_options' not in kwargs:
        sess_opts = ort.SessionOptions()
        sess_opts.log_severity_level = 4
        sess_opts.intra_op_num_threads = 1
        sess_opts.inter_op_num_threads = 1
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        kwargs['sess_options'] = sess_opts
    elif kwargs['sess_options'] is not None:
        # Update existing options
        try:
            kwargs['sess_options'].log_severity_level = 4
            kwargs['sess_options'].intra_op_num_threads = 1
            kwargs['sess_options'].inter_op_num_threads = 1
        except Exception:
            pass
    
    # Force CPU provider
    if 'providers' not in kwargs:
        kwargs['providers'] = ['CPUExecutionProvider']
    
    _original_inference_session_init(self, *args, **kwargs)

ort.InferenceSession.__init__ = _patched_inference_session_init

# ============================================================================
# Now safe to import everything else
# ============================================================================

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
    input_mask_expanded = np.expand_dims(attention_mask, axis=-1)
    input_mask_expanded = np.broadcast_to(
        input_mask_expanded, 
        model_output.shape
    ).astype(np.float32)
    
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
        
        # Create strict session options
        sess_options = ort.SessionOptions()
        sess_options.log_severity_level = 4
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        
        if os.path.exists(model_path):
            logger.info(f"Loading ONNX embedding model from {model_path}")
            try:
                self.model = ORTModelForFeatureExtraction.from_pretrained(
                    model_path,
                    provider='CPUExecutionProvider',
                    session_options=sess_options
                )
                self.tokenizer = AutoTokenizer.from_pretrained(model_path)
                logger.info("ONNX embedding model loaded from cache successfully")
            except Exception as e:
                logger.error(f"Failed to load ONNX model: {e}")
                raise
        else:
            logger.warning(f"Model path {model_path} does not exist")
            logger.info(f"Loading ONNX model from Hugging Face: '{model_name}'")
            
            try:
                self.model = ORTModelForFeatureExtraction.from_pretrained(
                    model_name,
                    export=True,
                    provider='CPUExecutionProvider',
                    session_options=sess_options
                )
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                logger.info(f"ONNX model '{model_name}' loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load ONNX model: {e}")
                raise

    def get_embedding(self, text: str) -> Optional[List[float]]:
        if not text or not isinstance(text, str) or not text.strip():
            return None
        
        try:
            # Tokenize
            inputs = self.tokenizer(
                text,
                padding=True,
                truncation=True,
                max_length=384,
                return_tensors='np'
            )
            
            # Run ONNX inference
            outputs = self.model(**inputs)
            
            # Mean pooling and Normalize
            last_hidden_state = outputs.last_hidden_state
            embeddings = mean_pooling(last_hidden_state, inputs['attention_mask'])
            embeddings = normalize(embeddings)
            
            return embeddings[0].tolist()
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        valid_texts = []
        valid_indices = []
        
        for i, text in enumerate(texts):
            if text and isinstance(text, str) and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)
        
        if not valid_texts:
            return [None] * len(texts)
        
        try:
            inputs = self.tokenizer(
                valid_texts,
                padding=True,
                truncation=True,
                max_length=384,
                return_tensors='np'
            )
            
            outputs = self.model(**inputs)
            embeddings = mean_pooling(outputs.last_hidden_state, inputs['attention_mask'])
            embeddings = normalize(embeddings)
            
            results = [None] * len(texts)
            for idx, embedding in zip(valid_indices, embeddings):
                results[idx] = embedding.tolist()
            
            return results
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            return [None] * len(texts)


_cached_client: Optional[EmbeddingClientONNX] = None

def get_embedding_client() -> EmbeddingClientONNX:
    global _cached_client
    if _cached_client is None:
        logger.info("Cold start: Initializing ONNX EmbeddingClient...")
        _cached_client = EmbeddingClientONNX()
        logger.info("ONNX model loaded.")
    return _cached_client