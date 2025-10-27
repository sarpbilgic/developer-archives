from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime

class RepositoryDetail(BaseModel):
    id: int
    full_name: str
    description: Optional[str] = None
    github_url: str
    stars: int
    watchers: int
    forks: int
    open_issues: int
    created_at_github: datetime
    pushed_at_github: Optional[datetime] = None 
    primary_language: Optional[str] = None
    topics: Optional[List[str]] = None
    languages_breakdown : Optional[Dict[str, int]] = None
    owner_avatar_url: Optional[str] = None
    owner_login: str
    owner_url: str
    owner_type: str
    
    class Config:
        from_attributes = True