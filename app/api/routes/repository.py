from fastapi import HTTPException, Depends, APIRouter
from fastapi.responses import PlainTextResponse
from sqlmodel.ext.asyncio.session import AsyncSession 
from app.db import get_session 
from app.schemas.repository import RepositoryDetail as RepositoryDetailSchema
from app.data_access.repositories.repository_detail import RepositoryDetail
from sqlalchemy.exc import SQLAlchemyError
import logging

router = APIRouter()

@router.get("/projects/{project_id}", response_model=RepositoryDetailSchema)
async def get_repository_detail(
    project_id: int, 
    session: AsyncSession = Depends(get_session)
):
    try:
        repository_detail = RepositoryDetail(session)
        result = await repository_detail.get_repository_detail(project_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting repository detail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.get("/projects/{project_id}/readme", response_class=PlainTextResponse)
async def get_repository_readme(
    project_id: int,
    session: AsyncSession = Depends(get_session)
):
    try:
        repository_detail = RepositoryDetail(session)
        result = await repository_detail.get_repository_readme(project_id)
        if result is None:
            raise HTTPException(status_code=404, detail="README not found for this project")
        return PlainTextResponse(result, media_type="text/plain")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting repository readme: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")