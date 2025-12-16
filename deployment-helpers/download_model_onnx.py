"""
Download and export the sentence-transformer model to ONNX format.
This produces identical embeddings to PyTorch but with much smaller runtime size.

Model: all-mpnet-base-v2 (768 dimensions)
"""

import os
import shutil
import argparse
from pathlib import Path
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def export_model(model_id, save_path):
    logger.info(f"Downloading and exporting {model_id} to ONNX...")
    
    # Export model to ONNX format
    # export=True converts the PyTorch model to ONNX while preserving weights
    # provider='CPUExecutionProvider' ensures it works on build machines without GPUs
    model = ORTModelForFeatureExtraction.from_pretrained(
        model_id,
        export=True,
        provider='CPUExecutionProvider'
    )

    # Download tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_id)

    # Save to output directory
    os.makedirs(save_path, exist_ok=True)
    model.save_pretrained(save_path)
    tokenizer.save_pretrained(save_path)

    # Also save the sentence-transformers config files for compatibility
    # These are needed so the model structure matches what the library expects
    config_files = [
        'config_sentence_transformers.json',
        'sentence_bert_config.json', 
        'modules.json',
        '1_Pooling/config.json'
    ]

    for config_file in config_files:
        try:
            downloaded = hf_hub_download(
                repo_id=model_id,
                filename=config_file,
                cache_dir='/tmp/hf_cache'
            )
            dest_path = Path(save_path) / config_file
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(downloaded, dest_path)
            logger.info(f'  Copied config: {config_file}')
        except Exception as e:
            logger.warning(f'  Skipped config {config_file}: {e}')

    logger.info(f'\nModel successfully exported to ONNX at {save_path}')
    verify_model(save_path)

def verify_model(save_path):
    # Verify the model files
    try:
        model_files = list(Path(save_path).rglob('*'))
        logger.info(f'\nModel directory contents ({len(model_files)} items):')
        
        total_size = 0
        for f in sorted(model_files):
            if f.is_file():
                size = f.stat().st_size
                total_size += size
                rel_path = f.relative_to(save_path)
                if size > 1024 * 1024:
                    logger.info(f'  {rel_path} ({size / (1024 * 1024):.1f} MB)')
                elif size > 1024:
                    logger.info(f'  {rel_path} ({size / 1024:.1f} KB)')
                else:
                    logger.info(f'  {rel_path} ({size} bytes)')
        
        logger.info(f'\nTotal model size: {total_size / (1024 * 1024):.1f} MB')
        
        # Verify ONNX model exists
        onnx_file = Path(save_path) / 'model.onnx'
        if onnx_file.exists():
            logger.info(f'\n✓ ONNX model file verified: {onnx_file.stat().st_size / (1024 * 1024):.1f} MB')
        else:
            raise FileNotFoundError('model.onnx not found!')

    except Exception as e:
        logger.error(f'ERROR verifying model directory: {e}')
        raise e

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_id", default="sentence-transformers/all-mpnet-base-v2")
    # This allows the Dockerfile to specify where to save the model
    parser.add_argument("--save_path", default="/install_dir/model") 
    args = parser.parse_args()

    # Create directory if it doesn't exist
    os.makedirs(args.save_path, exist_ok=True)

    export_model(args.model_id, args.save_path)