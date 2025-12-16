import os
import boto3
import logging
from dotenv import load_dotenv
from functools import cached_property


load_dotenv()
logger = logging.getLogger(__name__)

class Settings:
    def __init__(self):
        self._database_url = os.getenv("DATABASE_URL")
        """
        self.db_host = os.getenv("DB_HOST")
        self.db_port = os.getenv("DB_PORT")
        self.db_name = os.getenv("DB_NAME")
        self.db_username = os.getenv("DB_USERNAME")
        self.db_password = os.getenv("DB_PASSWORD")
        """
        self.aws_region = os.getenv("AWS_REGION")
        self.github_api_token = os.getenv("GITHUB_API_TOKEN")
        self.sqs_queue_url = os.getenv("SQS_URL")
        self.dynamodb_table_name = os.getenv("DYNAMODB_TABLE_NAME")
        self.s3_readme_bucket = os.getenv("S3_README_BUCKET")  
    
        if self._database_url is None:
            logger.info("Local .env file not found, loading settings from AWS Parameter Store")
            self._load_from_ssm()

    
    def _load_from_ssm(self):
        ssm_client = boto3.client('ssm', region_name=os.getenv("AWS_REGION", "eu-central-1"))
        def get_parameter(name, with_decryption=False):
            """Parameter Store"""
            try:
                response = ssm_client.get_parameter(
                    Name=name,
                    WithDecryption=with_decryption
                )
                return response['Parameter']['Value']
            except ssm_client.exceptions.ParameterNotFound:
                logger.warning(f"SSM parameter not found: {name}")
                return None

        self._database_url = get_parameter('/dev/developer-archives/DATABASE_URL')
        self.aws_region = get_parameter('/dev/developer-archives/AWS_REGION')
        self.sqs_queue_url = get_parameter('/dev/developer-archives/SQS_URL')
        self.dynamodb_table_name = get_parameter('/dev/developer-archives/DYNAMODB_TABLE_NAME')
        self.s3_readme_bucket = get_parameter('/dev/developer-archives/S3_README_BUCKET')  
        self.github_api_token = get_parameter('/dev/developer-archives/GITHUB_API_TOKEN', with_decryption=True)
        

    @cached_property
    def database_url(self) -> str:
        url = self._database_url
        if not url:
            raise ValueError("Database connection details are missing.")
            
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        if "?" in url:
            base_url, params = url.split("?", 1)
            param_pairs = [p for p in params.split("&") if not p.startswith(("sslmode=", "channel_binding="))]
            if param_pairs:
                url = f"{base_url}?{'&'.join(param_pairs)}"
            else:
                url = base_url
            
        return url


settings = Settings()
