from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime

class SearchResultItem(BaseModel):
    id: int
    full_name: str
    description: Optional[str] = None
    github_url: str
    stars: int
    primary_language: Optional[str] = None
    topics: Optional[List[str]] = None
    languages_breakdown: Optional[Dict[str, int]] = None
    owner_avatar_url: Optional[str] = None
    owner_login: str
    owner_url: str
    pushed_at_github: Optional[datetime] = None
    similarity: Optional[float] = None

    class Config:
        from_attributes = True