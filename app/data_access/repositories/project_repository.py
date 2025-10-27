from typing import Optional, List
from datetime import datetime, timezone
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from app.models.project import Project

class ProjectRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, project_id: int) -> Optional[Project]:
 
        statement = select(Project).where(Project.id == project_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()
    
    async def update_embedding(
        self, 
        project_id: int, 
        embedding: List[float], 
        processing_status: str
    ) -> Optional[Project]:

        statement = select(Project).where(Project.id == project_id)
        result = await self.session.execute(statement)
        project = result.scalar_one_or_none()
        
        if not project:
            return None
        
        project.project_embedding = embedding
        project.processing_status = processing_status
        project.last_indexed_at = datetime.now(timezone.utc)
        
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        
        return project

    async def upsert(self, project: Project) -> Project:

        project_data = project.dict(exclude_none=True)

        insert_stmt = pg_insert(Project).values(**project_data)

        update_columns = {
            col.name: getattr(insert_stmt.excluded, col.name)
            for col in Project.__table__.columns
            if col.name not in ["id", "full_name"] 
        }
        
        on_conflict_stmt = insert_stmt.on_conflict_do_update(
            index_elements=['full_name'], 
            set_=update_columns,
        )

        await self.session.execute(on_conflict_stmt)
        await self.session.commit()

        statement = select(Project).where(Project.full_name == project.full_name)
        result = await self.session.execute(statement)
        saved_project = result.scalar_one()
        
        return saved_project