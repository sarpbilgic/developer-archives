# app/services/data_processing_service.py

import base64
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

# Import all the necessary components from our layered architecture
from app.database import get_session
from app.external.github_client import GitHubClient, github_client
from app.external.embedding_client import EmbeddingClient, embedding_client
from app.data_access.repositories.project_repository import ProjectRepository
from app.models.project import Project
from app.services.embedding_text_builder import EmbeddingTextBuilder # <-- Import our new builder

class DataProcessingService:
    """
    Orchestrates the entire process of fetching, cleaning, processing,
    and preparing repository data for storage. This is the "Analyst" layer.
    """
    def __init__(
        self,
        session: AsyncSession = Depends(get_session),
        gh_client: GitHubClient = Depends(lambda: github_client),
        embed_client: EmbeddingClient = Depends(lambda: embedding_client)
    ):
        """
        Initializes the service with all its dependencies using FastAPI's Dependency Injection.
        """
        self.session = session
        self.github_client = gh_client
        self.embedding_client = embed_client
        # The repository is also a dependency, which needs the database session to work.
        self.project_repo = ProjectRepository(self.session)

    async def process_and_save_repo(self, owner: str, repo: str) -> Optional[Project]:
        """
        Main public method to handle the end-to-end data ingestion for a single repository.
        """
        # 1. Dispatch the "Field Agent" (GitHubClient) to gather all raw data.
        raw_data = await self.github_client.get_all_repo_data_for_processing(owner=owner, repo=repo)
        
        if not raw_data:
            # The client has already logged the reason for failure.
            return None

        # 2. Instantiate our specialized builder with the raw data.
        builder = EmbeddingTextBuilder(raw_data)
        
        # 3. Ask the builder to construct the perfect, context-rich text for embedding.
        embedding_text = builder.build()
        
        # 4. Get the cleaned readme from the builder (it has already done the work).
        cleaned_readme = builder.cleaned_readme

        # 5. Generate the insight (embedding vector) from the prepared text.
        embedding_vector = self.embedding_client.get_embedding(embedding_text)

        # 6. Map all the processed and generated data into a final report (the SQLModel object).
        try:
            project_model = self._map_to_project_model(
                details=raw_data["details"], 
                languages=raw_data["languages"],
                readme_content=cleaned_readme, 
                embedding=embedding_vector
            )
        except (KeyError, TypeError) as e:
            print(f"ERROR: Mapping data failed for {owner}/{repo}. Missing key or wrong type: {e}")
            return None

        # 7. Submit the report to the archives (save to the database).
        saved_project = await self.project_repo.upsert(project=project_model)
        print(f"SUCCESS: Processed and saved {saved_project.full_name}")
        return saved_project

    def _map_to_project_model(
        self, 
        details: Dict[str, Any], 
        languages: Dict[str, int], 
        readme_content: Optional[str], 
        embedding: List[float]
    ) -> Project:
        """
        Maps the various dictionaries of data into a single, validated Project SQLModel object.
        This is the final step before writing to the database.
        """
        owner_info = details.get("owner", {})
        
        def parse_datetime_str(datetime_str: Optional[str]) -> Optional[datetime]:
            """Safely parses ISO 8601 datetime strings from the GitHub API."""
            if not datetime_str: return None
            # The replace("Z", "+00:00") is crucial for Python's fromisoformat
            return datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))

        return Project(
            # Pass all data to the model for validation
            full_name=details["full_name"],
            description=details.get("description"),
            owner_login=owner_info.get("login"),
            owner_avatar_url=owner_info.get("avatar_url"),
            owner_url=owner_info.get("html_url"),
            owner_type=owner_info.get("type"),
            primary_language=details.get("language"),
            languages_breakdown=languages,
            is_archived=details.get("archived", False),
            topics=details.get("topics"),
            stars=details.get("stargazers_count", 0),
            forks=details.get("forks_count", 0),
            watchers=details.get("watchers_count", 0),
            open_issues=details.get("open_issues_count", 0),
            created_at_github=parse_datetime_str(details.get("created_at")),
            pushed_at_github=parse_datetime_str(details.get("pushed_at")),
            github_url=details.get("html_url"),
            homepage_url=details.get("homepage"),
            readme_content=readme_content,
            project_embedding=embedding
        )