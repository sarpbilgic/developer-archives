# test_github_client.py (DÜZELTİLMİŞ)

import asyncio
import httpx
import base64
import json
import sys
from pathlib import Path

# Projenin ana dizinini Python'un yoluna ekleyerek 'app' modülünü bulmasını sağlıyoruz
# Eğer test dosyanız app/tests/ içindeyse, bu yolun doğru olduğundan emin olun.
# Örneğin: sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
# Şimdilik basit tutalım:
try:
    from app.settings import settings
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parent))
    from app.settings import settings


# --- TEST EDİLECEK REPO ---
OWNER = "tiangolo"
REPO = "fastapi"
# -------------------------

async def main():
    print(f"--- GitHub API'sinden '{OWNER}/{REPO}' için veri çekiliyor... ---")

    token = settings.github_api_token
    if not token:
        print("\nHATA: GITHUB_API_TOKEN bulunamadı.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    # --- DÜZELTME BURADA ---
    # httpx istemcisini, yönlendirmeleri otomatik olarak takip edecek şekilde oluşturuyoruz.
    async with httpx.AsyncClient(follow_redirects=True) as client:
    # --- ----------------- ---
        
        repo_url = f"https://api.github.com/repos/{OWNER}/{REPO}"
        print(f"\n[1/3] Ana repo verisi isteniyor: {repo_url}")
        
        try:
            repo_response = await client.get(repo_url, headers=headers)
            repo_response.raise_for_status()
            repo_data = repo_response.json()
            
            print("\n--- 1. ANA REPO DETAYLARI (Seçilmiş Alanlar) ---")
            filtered_repo_data = {
                "full_name": repo_data.get("full_name"),
                "description": repo_data.get("description"),
                "stars": repo_data.get("stargazers_count"),
                "forks": repo_data.get("forks_count"),
                "language": repo_data.get("language"),
                "topics": repo_data.get("topics"),
                "pushed_at": repo_data.get("pushed_at"),
                "is_archived": repo_data.get("archived"),
                "owner_login": repo_data.get("owner", {}).get("login"),
                "owner_type": repo_data.get("owner", {}).get("type"),
            }
            print(json.dumps(filtered_repo_data, indent=2))

        except httpx.HTTPStatusError as e:
            print(f"HATA: Ana repo detayları alınamadı. Status Code: {e.response.status_code}")
            print(f"Mesaj: {e.response.text}")
            return

        # Geri kalan kod aynı...
        languages_url = f"https://api.github.com/repos/{OWNER}/{REPO}/languages"
        print(f"\n[2/3] Dil dağılımı isteniyor: {languages_url}")

        try:
            languages_response = await client.get(languages_url, headers=headers)
            languages_response.raise_for_status()
            languages_data = languages_response.json()
            
            print("\n--- 2. DİL DAĞILIMI (languages_breakdown) ---")
            print(json.dumps(languages_data, indent=2))

        except httpx.HTTPStatusError as e:
            print(f"HATA: Dil dağılımı alınamadı. Status Code: {e.response.status_code}")

        readme_url = f"https://api.github.com/repos/{OWNER}/{REPO}/readme"
        print(f"\n[3/3] README içeriği isteniyor: {readme_url}")

        try:
            readme_response = await client.get(readme_url, headers=headers)
            readme_response.raise_for_status()
            readme_data = readme_response.json()
            
            print("\n--- 3. README İÇERİĞİ (İlk 500 karakter) ---")
            encoded_content = readme_data.get("content", "")
            if encoded_content:
                decoded_content_bytes = base64.b64decode(encoded_content)
                readme_text = decoded_content_bytes.decode("utf-8")
                print(readme_text[:500] + "...")
            else:
                print("README bulunamadı veya içeriği boş.")

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                print("Bu repo için bir README dosyası bulunamadı.")
            else:
                print(f"HATA: README alınamadı. Status Code: {e.response.status_code}")


if __name__ == "__main__":
    # Eğer dosyanız app/tests/github_test.py ise, bu script'i çalıştırırken 
    # ana dizinde `python -m app.tests.github_test` komutunu kullanın.
    asyncio.run(main())