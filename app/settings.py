# settings.py (DÜZELTİLMİŞ)

import os
import boto3
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        # ... (init metodunun ilk kısmı aynı kalır)
        self.db_host = os.getenv("DB_HOST")
        self.db_port = os.getenv("DB_PORT")
        self.db_name = os.getenv("DB_NAME")
        self.db_username = os.getenv("DB_USERNAME")
        self.db_password = os.getenv("DB_PASSWORD")
        self.github_api_token = os.getenv("GITHUB_API_TOKEN")

        if self.db_host is None:
            print("Local .env file not found. Loading settings from AWS Parameter Store...")
            self._load_from_ssm()

    def _load_from_ssm(self):
        # ... (_load_from_ssm metodunuz aynı kalır)
        # Sadece bir tutarlılık önerisi: AWS'teki parametre isminizi /dev/code-compass/... olarak değiştirebilirsiniz.
        ssm_client = boto3.client('ssm', region_name=os.getenv("AWS_REGION", "eu-central-1"))
        # ... fonksiyonun geri kalanı ...

    @property
    def database_url(self) -> str:
        """Dynamically builds the database URL after settings are loaded."""
        return (
            f"postgresql+asyncpg://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

# Artık tek bir global settings nesnemiz var.
settings = Settings()