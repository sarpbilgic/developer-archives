# app/external/s3_client.py

import boto3
from typing import Optional
from botocore.exceptions import ClientError


class S3Client:
    """
    Client for storing and retrieving README files from S3.
    
    READMEs are stored in S3 instead of PostgreSQL because:
    - They're large (10-100 KB each, 75K repos = 7.5 GB)
    - They're rarely accessed after processing (cold data)
    - S3 is much cheaper than RDS for cold storage
    - Reduces DB load and improves query performance
    """
    
    def __init__(self, bucket_name: Optional[str] = None):
        """
        Initialize S3 client with the README bucket.
        
        Args:
            bucket_name: S3 bucket name for storing READMEs.
                        If None, loads from settings (SSM or .env)
        """
        self.s3 = boto3.client('s3')
        
        if bucket_name is None:
            # Load from settings (SSM or .env)
            from app.settings import settings
            bucket_name = settings.s3_readme_bucket or "developer-archives-readmes"
        
        self.bucket = bucket_name
        print(f"INFO: [S3Client] Using bucket: {self.bucket}")
    
    def upload_readme(self, owner: str, repo: str, content: str) -> str:
        """
        Upload a README file to S3 and return the S3 key.
        
        The key format is: repos/{owner}/{repo}/README.md
        This structure allows for easy organization and future expansion
        (e.g., storing other repo files like CONTRIBUTING.md).
        
        Args:
            owner: Repository owner (GitHub username or org)
            repo: Repository name
            content: Full README content (HTML or Markdown)
        
        Returns:
            S3 key (path) where the README was stored
            
        Raises:
            ClientError: If S3 upload fails
        """
        # Construct the S3 key (path)
        key = f"repos/{owner}/{repo}/README.md"
        
        try:
            # Upload to S3
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content.encode('utf-8'),
                ContentType='text/markdown',
                # Use Standard-IA storage class for cost optimization
                # (will transition to IA after 30 days via lifecycle policy)
                StorageClass='STANDARD',
                # Add metadata for debugging and analytics
                Metadata={
                    'owner': owner,
                    'repo': repo,
                    'content-length': str(len(content))
                }
            )
            
            print(f"INFO: [S3Client] Uploaded README for {owner}/{repo} to s3://{self.bucket}/{key}")
            return key
            
        except ClientError as e:
            print(f"ERROR: [S3Client] Failed to upload README for {owner}/{repo}. Error: {e}")
            raise
    
    def get_readme(self, s3_key: str) -> Optional[str]:
        """
        Retrieve a README file from S3.
        
        This is typically only used when a user explicitly requests to view
        the full README (rare event, ~1-5% of queries).
        
        Args:
            s3_key: S3 key (path) of the README
        
        Returns:
            README content as string, or None if not found
        """
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
            
            print(f"INFO: [S3Client] Retrieved README from s3://{self.bucket}/{s3_key}")
            return content
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"WARN: [S3Client] README not found at s3://{self.bucket}/{s3_key}")
                return None
            else:
                print(f"ERROR: [S3Client] Failed to retrieve README from {s3_key}. Error: {e}")
                raise
    
    def delete_readme(self, s3_key: str) -> bool:
        """
        Delete a README file from S3.
        
        Used for cleanup when a repository is removed from the database.
        
        Args:
            s3_key: S3 key (path) of the README to delete
        
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=s3_key)
            print(f"INFO: [S3Client] Deleted README at s3://{self.bucket}/{s3_key}")
            return True
            
        except ClientError as e:
            print(f"ERROR: [S3Client] Failed to delete README at {s3_key}. Error: {e}")
            return False


# Singleton instance (similar pattern to embedding_client)
s3_client = S3Client()

