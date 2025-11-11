from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download
import os

model_name = 'sentence-transformers/all-mpnet-base-v2'
print(f'Downloading model: {model_name}')

snapshot_download(
    repo_id=model_name,
    cache_dir='/tmp/model_cache'
)

m = SentenceTransformer(
    model_name,
    cache_folder='/tmp/model_cache',
    device='cpu'
)
m.save('/install_dir/model')
print('Model successfully saved to /install_dir/model')

try:
    model_files = os.listdir('/install_dir/model')
    print(f'Model directory contents ({len(model_files)} files):')
    for f in model_files[:10]:
        file_path = f'/install_dir/model/{f}'
        size = os.path.getsize(file_path) if os.path.isfile(file_path) else 'DIR'
        print(f'  {f} ({size} bytes)')

    total_size = sum(
        os.path.getsize(f'/install_dir/model/{f}')
        for f in model_files if os.path.isfile(f'/install_dir/model/{f}')
    )
    print(f'Total model size: {total_size / (1024 * 1024):.1f} MB')

except Exception as e:
    print(f'ERROR verifying model directory: {e}')
    raise e
