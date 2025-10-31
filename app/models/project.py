# app/models/project.py

from typing import List, Optional, Dict
from sqlmodel import Field, SQLModel, Column, ARRAY, Text, DateTime
from pgvector.sqlalchemy import Vector
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.dialects.postgresql import JSONB

class ProcessingStatus(str, Enum):
    DISCOVERED = "discovered"  
    EMBEDDING_IN_PROGRESS = "embedding_in_progress" 
    COMPLETED = "completed"  
    FAILED = "failed"  

class Project(SQLModel, table=True):

    __tablename__ = 'projects'

    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(unique=True, nullable=False, index=True, max_length=255)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    owner_login: str = Field(index=True, max_length=255)
    owner_avatar_url: Optional[str] = Field(default=None, max_length=255)
    owner_url: str = Field(max_length=255)
    owner_type: str = Field(index=True, max_length=50) 

    primary_language: Optional[str] = Field(default=None, index=True, max_length=100)
    languages_breakdown: Optional[Dict] = Field(default=None, sa_column=Column(JSONB))
    is_archived: bool = Field(default=False, index=True)
    topics: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(Text)))
    stars: int = Field(default=0, index=True)
    forks: int = Field(default=0)
    watchers: int = Field(default=0)
    open_issues: int = Field(default=0)
    created_at_github: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    
    pushed_at_github: datetime = Field(sa_column=Column(DateTime(timezone=True), index=True))
    
    github_url: str = Field(max_length=255)
    homepage_url: Optional[str] = Field(default=None, max_length=255)
    

    readme_s3_key: Optional[str] = Field(default=None, max_length=500, index=True)
    readme_word_count: Optional[int] = Field(default=None)
    readme_content: Optional[str] = Field(default=None, sa_column=Column(Text))  # DEPRECATED

    project_embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))
    last_indexed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    processing_status: str = Field(
        default=ProcessingStatus.DISCOVERED.value,
        max_length=50,
        index=True,
        nullable=False
    )