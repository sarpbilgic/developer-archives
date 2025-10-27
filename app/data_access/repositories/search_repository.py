from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, asc
import logging
from app.models.project import Project
from app.schemas.search import SearchResultItem

class SearchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_projects(
        self, 
        query_embedding: List[float], 
        page: int,                       
        page_size: int,
        language: Optional[str] = None,  
        min_stars: Optional[int] = None,
        topics: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        selected = [
            Project.id,
            Project.full_name,
            Project.description,
            Project.github_url,
            Project.stars,
            Project.primary_language,
            Project.topics,
            Project.languages_breakdown,
            Project.owner_avatar_url,
            Project.owner_login,
            Project.owner_url,
            Project.pushed_at_github,
            (Project.project_embedding.cosine_distance(query_embedding).label('similarity'))
        ]
        statement = select(*selected).where(Project.project_embedding != None)

        if min_stars is not None:
            statement = statement.where(Project.stars >= min_stars)
        if language is not None:
            statement = statement.where(Project.primary_language == language)
        if topics is not None:
            statement = statement.where(Project.topics.op('&&')(topics))

        offset = (page - 1) * page_size
        statement = statement.order_by(asc('similarity')).offset(offset).limit(page_size)

        try:
            result = await self.session.execute(statement)
            return result.mappings().all()
        except Exception as e:
            logging.error(f"Failed to search projects: {e}")
            raise e