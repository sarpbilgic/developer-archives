import boto3
import logging
from typing import Optional
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3Client:
    """Client for storing and retrieving README files from S3."""
    
    def __init__(self, bucket_name: Optional[str] = None):
        self.s3 = boto3.client('s3')
        
        if bucket_name is None:
            from app.settings import settings
            bucket_name = settings.s3_readme_bucket or "developer-archives-readmes"
        
        self.bucket = bucket_name
        logger.info(f"S3Client initialized with bucket: {self.bucket}")
    
    def upload_readme(self, owner: str, repo: str, content: str) -> str:
        """Upload README to S3 and return the S3 key."""
        key = f"repos/{owner}/{repo}/README.md"
        
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content.encode('utf-8'),
                ContentType='text/markdown',
                StorageClass='STANDARD',
                Metadata={
                    'owner': owner,
                    'repo': repo,
                    'content-length': str(len(content))
                }
            )
            
            logger.info(f"Uploaded README for {owner}/{repo} to s3://{self.bucket}/{key}")
            return key
            
        except ClientError as e:
            logger.error(f"Failed to upload README for {owner}/{repo}: {e}")
            raise
    
    def get_readme(self, s3_key: str) -> Optional[str]:
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
            logger.info(f"Retrieved README from s3://{self.bucket}/{s3_key}")
            return content
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"README not found at s3://{self.bucket}/{s3_key}")
                return None
            else:
                logger.error(f"Failed to retrieve README from {s3_key}: {e}")
                raise
    
    def delete_readme(self, s3_key: str) -> bool:
        """Delete a README file from S3."""
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=s3_key)
            logger.info(f"Deleted README at s3://{self.bucket}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete README at {s3_key}: {e}")
            return False

s3_client = S3Client()

