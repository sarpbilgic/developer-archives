"""
Download and export the sentence-transformer model to ONNX format.
This produces identical embeddings to PyTorch but with much smaller runtime size.

Model: all-mpnet-base-v2 (768 dimensions)
"""

import os
import shutil
from pathlib import Path
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer

MODEL_NAME = 'sentence-transformers/all-mpnet-base-v2'
OUTPUT_DIR = '/install_dir/model'

print(f'Downloading and exporting model to ONNX: {MODEL_NAME}')

# Export model to ONNX format
# This converts the PyTorch model to ONNX while preserving weights
model = ORTModelForFeatureExtraction.from_pretrained(
    MODEL_NAME,
    export=True,  # Export to ONNX on the fly
    provider='CPUExecutionProvider'
)

# Download tokenizer (same as PyTorch version)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

# Save to output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

# Also save the sentence-transformers config files for compatibility
# Download original config files
from huggingface_hub import hf_hub_download

config_files = [
    'config_sentence_transformers.json',
    'sentence_bert_config.json', 
    'modules.json',
    '1_Pooling/config.json'
]

for config_file in config_files:
    try:
        downloaded = hf_hub_download(
            repo_id=MODEL_NAME,
            filename=config_file,
            cache_dir='/tmp/hf_cache'
        )
        dest_path = Path(OUTPUT_DIR) / config_file
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(downloaded, dest_path)
        print(f'  Copied config: {config_file}')
    except Exception as e:
        print(f'  Skipped config {config_file}: {e}')

print(f'\nModel successfully exported to ONNX at {OUTPUT_DIR}')

# Verify the model files
try:
    model_files = list(Path(OUTPUT_DIR).rglob('*'))
    print(f'\nModel directory contents ({len(model_files)} items):')
    
    total_size = 0
    for f in sorted(model_files):
        if f.is_file():
            size = f.stat().st_size
            total_size += size
            rel_path = f.relative_to(OUTPUT_DIR)
            if size > 1024 * 1024:
                print(f'  {rel_path} ({size / (1024 * 1024):.1f} MB)')
            elif size > 1024:
                print(f'  {rel_path} ({size / 1024:.1f} KB)')
            else:
                print(f'  {rel_path} ({size} bytes)')
    
    print(f'\nTotal model size: {total_size / (1024 * 1024):.1f} MB')
    
    # Verify ONNX model exists
    onnx_file = Path(OUTPUT_DIR) / 'model.onnx'
    if onnx_file.exists():
        print(f'\n✓ ONNX model file verified: {onnx_file.stat().st_size / (1024 * 1024):.1f} MB')
    else:
        raise FileNotFoundError('model.onnx not found!')

except Exception as e:
    print(f'ERROR verifying model directory: {e}')
    raise e

