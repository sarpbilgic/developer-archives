from fastapi import Query, HTTPException, Depends, APIRouter
from typing import List, Optional
from app.external.embedding_client import get_embedding_client, EmbeddingClient
from app.db import get_session 
from sqlmodel.ext.asyncio.session import AsyncSession 
from app.schemas.search import SearchResultItem
from app.data_access.repositories.search_repository import SearchRepository
from sqlalchemy.exc import SQLAlchemyError
import httpx
import logging 

router = APIRouter()

@router.get("/search", response_model=List[SearchResultItem])
async def search(
    query: str = Query(..., min_length=3, max_length=500, description="Search query"),
    language: Optional[str] = Query(None, description="Filter by language"),
    min_stars: Optional[int] = Query(None, ge=0, description="Filter by minimum stars"),
    topics: Optional[List[str]] = Query(None, description="Filter by topics"),
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    session: AsyncSession = Depends(get_session),
    embed_client: EmbeddingClient = Depends(get_embedding_client)
):
    try:
        logging.info(f"Generating embedding for query: {query}")
        query_embedding = embed_client.get_embedding(query)
    except (httpx.RequestError, ConnectionError) as e:
        logging.error(f"Failed to connect to embedding client: {e}")
        raise HTTPException(
            status_code=503, 
            detail="Embedding client is not available",
        )
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=500, 
            detail="An unexpected error occurred",
        )
    try:
        search_repository = SearchRepository(session)
        results = await search_repository.search_projects(
            query_embedding=query_embedding,
            language=language,
            min_stars=min_stars,
            topics=topics,
            page=page,
            page_size=page_size,
        )
        return results
    except SQLAlchemyError as e:
        logging.error(f"Database error occurred during search: {e}")
        raise HTTPException(
            status_code=500,
            detail="A database error occurred"
        )
    except Exception as e:
        logging.error(f"Failed to search projects: {e}")
        raise HTTPException(
            status_code=500, 
            detail="An unexpected error occurred",
        )
   