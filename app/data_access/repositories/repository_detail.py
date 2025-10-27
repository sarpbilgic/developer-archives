from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import select, asc
import logging
from app.models.project import Project
from app.schemas.repository import RepositoryDetail as RepositoryDetailSchema
from app.external.s3_client import s3_client

class RepositoryDetail:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_repository_detail(self, project_id: int) -> Optional[RepositoryDetailSchema]:
        statement = select(Project).where(Project.id == project_id)
        result = await self.session.execute(statement)
        project = result.scalar_one_or_none()
        if project:
            return RepositoryDetailSchema.from_attributes(project)
        return None
    
    async def get_repository_readme(self, project_id: int) -> Optional[str]:
        statement = select(Project.readme_s3_key).where(Project.id == project_id)
        result = await self.session.execute(statement)
        readme_s3_key = result.scalar_one_or_none()
        if readme_s3_key:
            try:
                return s3_client.get_readme(readme_s3_key)
            except Exception as e:
                logging.error(f"Failed to get README from S3 for key {readme_s3_key}: {e}")
                return None
        return None
