"""
Verify that ONNX and PyTorch produce identical embeddings.
Run this locally before deploying ONNX version to production.

Usage:
    python deployment-helpers/verify_onnx_embeddings.py
"""

import numpy as np
import sys

# Test texts - various lengths and content
TEST_TEXTS = [
    "A simple test sentence.",
    "FastAPI is a modern, fast web framework for building APIs with Python.",
    "Machine learning models can be optimized using ONNX Runtime for faster inference.",
    """
    This is a longer text that might appear in a GitHub README.
    It contains multiple sentences and discusses technical topics like
    database connections, API development, and cloud deployment.
    The purpose is to verify that longer texts produce identical embeddings.
    """,
    "🚀 Emoji test with special characters: <>&\"'",
]

def cosine_similarity(a, b):
    """Calculate cosine similarity between two vectors."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def main():
    print("=" * 60)
    print("ONNX vs PyTorch Embedding Verification")
    print("=" * 60)
    
    # Import PyTorch client
    print("\n[1/3] Loading PyTorch model (sentence-transformers)...")
    try:
        from sentence_transformers import SentenceTransformer
        pytorch_model = SentenceTransformer('all-mpnet-base-v2')
        print("      PyTorch model loaded successfully")
    except ImportError as e:
        print(f"      ERROR: Could not load PyTorch model: {e}")
        print("      Install with: pip install sentence-transformers")
        sys.exit(1)
    
    # Import ONNX client  
    print("\n[2/3] Loading ONNX model (optimum + onnxruntime)...")
    try:
        from transformers import AutoTokenizer
        from optimum.onnxruntime import ORTModelForFeatureExtraction
        
        model_name = 'sentence-transformers/all-mpnet-base-v2'
        onnx_model = ORTModelForFeatureExtraction.from_pretrained(
            model_name, 
            export=True,
            provider='CPUExecutionProvider'
        )
        onnx_tokenizer = AutoTokenizer.from_pretrained(model_name)
        print("      ONNX model loaded successfully")
    except ImportError as e:
        print(f"      ERROR: Could not load ONNX model: {e}")
        print("      Install with: pip install optimum[onnxruntime]")
        sys.exit(1)
    
    # Helper functions for ONNX
    def mean_pooling(model_output, attention_mask):
        input_mask_expanded = np.expand_dims(attention_mask, axis=-1)
        input_mask_expanded = np.broadcast_to(input_mask_expanded, model_output.shape).astype(np.float32)
        sum_embeddings = np.sum(model_output * input_mask_expanded, axis=1)
        sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        return sum_embeddings / sum_mask
    
    def normalize(embeddings):
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / np.clip(norms, a_min=1e-9, a_max=None)
    
    def get_onnx_embedding(text):
        inputs = onnx_tokenizer(text, padding=True, truncation=True, max_length=384, return_tensors='np')
        outputs = onnx_model(**inputs)
        embeddings = mean_pooling(outputs.last_hidden_state, inputs['attention_mask'])
        embeddings = normalize(embeddings)
        return embeddings[0]
    
    # Compare embeddings
    print("\n[3/3] Comparing embeddings...")
    print("-" * 60)
    
    all_pass = True
    for i, text in enumerate(TEST_TEXTS):
        # Get embeddings from both models
        pytorch_emb = pytorch_model.encode(text)
        onnx_emb = get_onnx_embedding(text)
        
        # Calculate metrics
        cos_sim = cosine_similarity(pytorch_emb, onnx_emb)
        max_diff = np.max(np.abs(pytorch_emb - onnx_emb))
        mean_diff = np.mean(np.abs(pytorch_emb - onnx_emb))
        
        # Check if they're close enough (accounting for floating point precision)
        is_identical = cos_sim > 0.9999 and max_diff < 1e-4
        status = "PASS" if is_identical else "FAIL"
        
        if not is_identical:
            all_pass = False
        
        text_preview = text[:50].replace('\n', ' ').strip() + "..." if len(text) > 50 else text.replace('\n', ' ')
        print(f"\nTest {i+1}: \"{text_preview}\"")
        print(f"  Cosine Similarity: {cos_sim:.8f}")
        print(f"  Max Difference:    {max_diff:.2e}")
        print(f"  Mean Difference:   {mean_diff:.2e}")
        print(f"  Status: [{status}]")
    
    # Summary
    print("\n" + "=" * 60)
    if all_pass:
        print("SUCCESS: All embeddings are identical!")
        print("You can safely switch to ONNX Runtime.")
        print("=" * 60)
        sys.exit(0)
    else:
        print("WARNING: Some embeddings differ significantly!")
        print("Review the results above before switching.")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()

