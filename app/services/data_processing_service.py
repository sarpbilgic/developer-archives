# app/services/data_processing_service.py

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlmodel.ext.asyncio.session import AsyncSession
from bs4 import BeautifulSoup
import base64

# Import all the necessary components from our layered architecture
from app.db import get_session  # FIXED: Correct module name
from app.external.github_client import GitHubClient, github_client as default_github_client # Default instance
from app.external.embedding_client import EmbeddingClient, embedding_client as default_embedding_client # Default instance
from app.external.s3_client import S3Client, s3_client as default_s3_client  # S3 for README storage
from app.data_access.repositories.project_repository import ProjectRepository
from app.models.project import Project
from app.services.readme_extractor import ReadmeExtractor, readme_extractor as default_readme_extractor

# Optional FastAPI import (only used when running as API server, not Lambda)
try:
    from fastapi import Depends
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    Depends = None

class DataProcessingService:
    """
    Orchestrates the entire process of fetching, cleaning, processing,
    and preparing repository data for storage. This is the "Analyst" layer.

    Works in both FastAPI (with Depends via get_data_processing_service)
    and Lambda/script (manual injection) contexts.
    """
    def __init__(
        self,
        session: AsyncSession, # Session is always required
        gh_client: Optional[GitHubClient] = None, # Optional: falls back to default singleton
        embed_client: Optional[EmbeddingClient] = None, # Optional: falls back to default singleton
        s3_client: Optional[S3Client] = None, # Optional: falls back to default singleton
        extractor: Optional[ReadmeExtractor] = None # Optional: falls back to default singleton
    ):
        """
        Initializes the service with dependencies.

        Args:
            session: The database session (required).
            gh_client: GitHub client instance (optional, defaults to singleton).
            embed_client: Embedding client instance (optional, defaults to singleton).
            s3_client: S3 client instance (optional, defaults to singleton).
            extractor: README extractor instance (optional, defaults to singleton).
        """
        self.session = session
        # Use provided clients or fall back to the default singleton instances
        self.github_client = gh_client or default_github_client
        self.embedding_client = embed_client or default_embedding_client
        self.s3_client = s3_client or default_s3_client
        self.readme_extractor = extractor or default_readme_extractor
        # Repository depends on the session provided to this service instance
        self.project_repo = ProjectRepository(self.session)

    async def process_and_save_repo(self, owner: str, repo: str) -> Optional[Project]:
        """
        Main public method to handle the end-to-end data ingestion for a single repository.
        Fetches, processes, embeds, and saves data.
        
        ARCHITECTURE: Single-Vector + S3 Hybrid
        - Full README stored in S3 (for display only)
        - README intro + features extracted (for embedding)
        - SINGLE embedding combines all search-relevant info
        - No chunks table (simpler, faster, more efficient!)
        """
        print(f"INFO: [DataProcessingService] Starting processing for {owner}/{repo}")
        
        # 1. Fetch all raw data using the GitHub client
        raw_data = await self.github_client.get_all_repo_data_for_processing(owner=owner, repo=repo)

        if not raw_data:
            print(f"WARN: [DataProcessingService] No raw data received for {owner}/{repo}. Skipping.")
            return None

        # 2. Process README: Upload to S3 and extract search text
        readme_s3_key = None
        readme_word_count = 0
        readme_search_text = ""
        
        readme_raw = raw_data.get("readme_raw")
        if readme_raw and readme_raw.get("content"):
            try:
                print(f"INFO: [DataProcessingService] Processing README for {owner}/{repo}")
                
                # Decode the base64-encoded README
                encoded_content = readme_raw["content"]
                decoded_bytes = base64.b64decode(encoded_content)
                full_readme_html = decoded_bytes.decode("utf-8")
                
                # Count words in full README (for metadata)
                soup = BeautifulSoup(full_readme_html, 'html.parser')
                readme_word_count = len(soup.get_text().split())
                
                # Upload full README to S3 (for user viewing)
                print(f"INFO: [DataProcessingService] Uploading README to S3 for {owner}/{repo}")
                readme_s3_key = self.s3_client.upload_readme(owner, repo, full_readme_html)
                
                # Extract intro + features ONLY (for embedding)
                print(f"INFO: [DataProcessingService] Extracting search text from README")
                readme_search_text = self.readme_extractor.extract_search_text(
                    full_readme_html,
                    max_words=250  # Safe margin for 384 token limit
                )
                
                print(f"INFO: [DataProcessingService] README: {readme_word_count} words total, {len(readme_search_text.split())} words for embedding")
                
            except Exception as e:
                print(f"ERROR: [DataProcessingService] README processing failed for {owner}/{repo}. Error: {e}")
                import traceback
                traceback.print_exc()
                # Continue without README data
        
        # 3. Build combined embedding text (metadata + README)
        print(f"INFO: [DataProcessingService] Building combined embedding text")
        embedding_text = self._build_combined_embedding_text(
            details=raw_data["details"],
            languages=raw_data["languages"],
            readme_text=readme_search_text
        )
        
        # 4. Generate SINGLE embedding
        print(f"INFO: [DataProcessingService] Generating embedding for {owner}/{repo}")
        project_embedding = self.embedding_client.get_embedding(embedding_text)
        
        if not project_embedding:
            print(f"WARN: [DataProcessingService] Could not generate embedding for {owner}/{repo}")

        # 5. Map the data to the Project SQLModel
        print(f"INFO: [DataProcessingService] Mapping data to model for {owner}/{repo}")
        try:
            project_model = self._map_to_project_model(
                details=raw_data["details"],
                languages=raw_data["languages"],
                readme_s3_key=readme_s3_key,
                readme_word_count=readme_word_count,
                embedding=project_embedding
            )

        except (KeyError, TypeError, ValueError) as e:
            print(f"ERROR: [DataProcessingService] Mapping data failed for {owner}/{repo}. Error: {e}")
            import traceback
            traceback.print_exc()
            return None

        # 6. Save the project to the database
        print(f"INFO: [DataProcessingService] Saving {owner}/{repo} to database...")
        try:
            saved_project = await self.project_repo.upsert(project=project_model)
            print(f"SUCCESS: [DataProcessingService] Saved project {saved_project.full_name} (ID: {saved_project.id})")
            return saved_project
            
        except Exception as e:
            # Catch potential database errors during upsert
            print(f"ERROR: [DataProcessingService] Database save failed for {owner}/{repo}. Error: {e}")
            import traceback
            traceback.print_exc()
            await self.session.rollback()
            return None


    def _build_combined_embedding_text(
        self,
        details: Dict[str, Any],
        languages: Dict[str, int],
        readme_text: str
    ) -> str:
        """
        Tüm repo bilgisini tek, optimize edilmiş text'e dönüştürür.
        
        Combines:
        - Project metadata (name, description)
        - Tech stack (languages, topics)
        - Quality signals (stars, maintenance)
        - README content (intro + features ONLY)
        
        Target: ~300 words max (safe for 384 token limit)
        
        Returns:
            Optimized text for semantic search
        """
        # Extract metadata
        full_name = details.get("full_name", "")
        description = details.get("description", "")
        primary_lang = details.get("language", "")
        all_langs = list(languages.keys())[:5]  # Top 5 languages
        topics = details.get("topics", [])[:10]  # Top 10 topics
        stars = details.get("stargazers_count", 0)
        is_archived = details.get("archived", False)
        pushed_at = details.get("pushed_at")
        
        # Build quality/popularity signal
        quality_signal = ""
        if stars > 50000:
            quality_signal = "Extremely popular project with very large community."
        elif stars > 10000:
            quality_signal = "Very popular and widely used project."
        elif stars > 1000:
            quality_signal = "Popular project with active community."
        
        # Build maintenance signal
        maintenance_signal = ""
        if is_archived:
            maintenance_signal = "This project is archived and no longer maintained."
        elif pushed_at:
            try:
                last_push = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                days_since_push = (datetime.now(timezone.utc) - last_push).days
                
                if days_since_push <= 30:
                    maintenance_signal = "Actively maintained with recent updates."
                elif days_since_push > 365:
                    maintenance_signal = "Has not been updated in over a year."
            except (ValueError, TypeError):
                pass
        
        # Combine all parts (order matters: most important first)
        parts = [
            f"Repository: {full_name}." if full_name else "",
            f"Description: {description}." if description else "",
            f"Primary programming language: {primary_lang}." if primary_lang else "",
            f"Technologies used: {', '.join(all_langs)}." if all_langs else "",
            f"Topics and keywords: {', '.join(topics)}." if topics else "",
            quality_signal,
            maintenance_signal,
            f"\n{readme_text}" if readme_text else ""
        ]
        
        # Join and clean up
        combined = " ".join(filter(None, parts))
        
        # Safety truncation (should rarely trigger with 250-word README limit)
        words = combined.split()
        if len(words) > 300:
            combined = " ".join(words[:300])
            print(f"WARN: [DataProcessingService] Embedding text truncated to 300 words")
        
        return combined

    def _map_to_project_model(
        self,
        details: Dict[str, Any],
        languages: Dict[str, int],
        readme_s3_key: Optional[str],
        readme_word_count: int,
        embedding: Optional[List[float]] # Accept Optional list
    ) -> Project:
        """
        Maps the various dictionaries of data into a single, validated Project SQLModel object.
        Includes safe parsing for dates.
        
        NEW: README stored in S3, not in DB.
        """
        owner_info = details.get("owner", {})

        def parse_datetime_str(datetime_str: Optional[str]) -> Optional[datetime]:
            """Safely parses ISO 8601 datetime strings from the GitHub API."""
            if not datetime_str: return None
            try:
                # Handles the 'Z' for UTC timezone correctly
                return datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
            except ValueError:
                print(f"WARN: Could not parse datetime string: {datetime_str}")
                return None # Return None if parsing fails

        # Create the Project model instance
        project = Project(
            full_name=details["full_name"], # Assume full_name always exists if details exist
            description=details.get("description"),
            owner_login=owner_info.get("login"),
            owner_avatar_url=owner_info.get("avatar_url"),
            owner_url=owner_info.get("html_url"),
            owner_type=owner_info.get("type"),
            primary_language=details.get("language"),
            languages_breakdown=languages if languages else {}, # Ensure it's a dict
            is_archived=details.get("archived", False),
            topics=details.get("topics") if details.get("topics") else [], # Ensure it's a list
            stars=details.get("stargazers_count", 0),
            forks=details.get("forks_count", 0),
            watchers=details.get("watchers_count", 0),
            open_issues=details.get("open_issues_count", 0),
            created_at_github=parse_datetime_str(details.get("created_at")),
            pushed_at_github=parse_datetime_str(details.get("pushed_at")),
            github_url=details.get("html_url"),
            homepage_url=details.get("homepage"),
            # NEW: S3-based README storage
            readme_s3_key=readme_s3_key,
            readme_word_count=readme_word_count,
            project_embedding=embedding # Assign the embedding vector (can be None)
            # last_indexed_at is handled by default_factory in the model
        )
        return project

# --- FastAPI Dependency Function ---
# Only available when FastAPI is installed (not in Lambda)

if FASTAPI_AVAILABLE:
    async def get_data_processing_service(
        session: AsyncSession = Depends(get_session) # Get session via FastAPI dependency
        # No need to explicitly depend on clients here, __init__ handles defaults
    ) -> DataProcessingService:
        """
        FastAPI dependency factory to create an instance of DataProcessingService.
        Injects the database session and relies on singleton clients for others.
        """
        return DataProcessingService(session=session)