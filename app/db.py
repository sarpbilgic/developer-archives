from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

from app.settings import settings

engine = create_async_engine(
    settings.database_url, 
    echo=False, 
    future=True,
    pool_size=2,          
    max_overflow=1,       
    pool_pre_ping=True,  
    pool_recycle=1800,    
    pool_timeout=10,      
    connect_args={
        "server_settings": {
            "application_name": "developer-archives-lambda",
            "statement_timeout": "300000", 
            "idle_in_transaction_session_timeout": "60000",  
        }
    }
)

async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session