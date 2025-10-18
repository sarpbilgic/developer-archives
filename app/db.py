from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

from app.settings import settings

# Optimized for AWS RDS Free Tier (1GB RAM)
# Connection pool settings are CRITICAL for memory management
engine = create_async_engine(
    settings.database_url, 
    echo=False, 
    future=True,
    pool_size=5,          # Max 5 connections (default 5)
    max_overflow=3,       # Allow 3 extra connections under load (total max: 8)
    pool_pre_ping=True,   # Verify connections before use
    pool_recycle=3600,    # Recycle connections after 1 hour
    # Each connection: ~5-10 MB RAM
    # Total pool: ~80 MB max (acceptable for 1GB RAM)
)

async def get_session() -> AsyncSession:
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session