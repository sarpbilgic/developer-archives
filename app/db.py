from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

from app.settings import settings

# Optimized for AWS RDS Free Tier (1GB RAM) + Parallel Processing
# Connection pool settings are CRITICAL for memory management
engine = create_async_engine(
    settings.database_url, 
    echo=False, 
    future=True,
    pool_size=4,          # Max 5 base connections (conservative for multi-instance)
    max_overflow=1,       # Allow 3 extra under load (total: 8 per Lambda)
    pool_pre_ping=True,   # Verify connections before use (important for Lambda)
    pool_recycle=3600,    # Recycle connections after 1 hour
    # Lambda note: Multiple instances can run simultaneously!
    # Free Tier RDS limit: ~20 connections total
    # With 3 Lambda instances: 3 × 8 = 24 connections (can exceed limit!)
    # With 2 Lambda instances: 2 × 8 = 16 connections (safe)
    # Pool will queue connections if all are busy - prevents overflow
)

# Create a single sessionmaker for all sessions (reusable, efficient)
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_session() -> AsyncSession:
    """
    Yields a database session from the connection pool.
    Reuses the global sessionmaker for efficiency.
    """
    async with async_session_maker() as session:
        yield session