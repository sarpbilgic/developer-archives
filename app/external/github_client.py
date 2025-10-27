import httpx
import base64
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.settings import settings

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when GitHub API rate limit is critically low."""
    pass

class GitHubClient:
    
    BASE_URL = "https://api.github.com"

    def __init__(self):
        self.token = settings.github_api_token
        if not self.token:
            raise ValueError("GITHUB_API_TOKEN environment variable not found.")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        self._client = httpx.AsyncClient(
            headers=self.headers, 
            follow_redirects=True,
            timeout=20.0
        )
        self._api_semaphore = asyncio.Semaphore(2)

    async def _make_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Internal method to make a request and handle rate limiting."""
        async with self._api_semaphore:
            response = await self._client.request(method, url, **kwargs)
            
            remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
            
            if remaining < 100:
                logger.info(f"GitHub API rate limit at {remaining} requests remaining")
            
            if remaining < 5:
                logger.critical(f"GitHub API rate limit critically low ({remaining} left)")
                raise RateLimitError("GitHub API rate limit exceeded. Failing fast.")
            
            response.raise_for_status()
            return response

    async def search_repositories(
        self, 
        query: str, 
        sort: str = "stars", 
        order: str = "desc", 
        per_page: int = 100, 
        page: int = 1
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.BASE_URL}/search/repositories"
        params = {
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": per_page,
            "page": page
        }
        try:
            response = await self._make_request("GET", url, params=params)
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Repository search failed for query '{query}': {e}")
            return None

    async def get_repo_details(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetches the main metadata for a single repository."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}"
        try:
            response = await self._make_request("GET", url)
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.info(f"Could not get repo details for {owner}/{repo}: {e}")
            return None

    async def get_repo_languages(self, owner: str, repo: str) -> Optional[Dict[str, int]]:
        """Fetches the language breakdown for a single repository."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/languages"
        try:
            response = await self._make_request("GET", url)
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.info(f"Could not get languages for {owner}/{repo}: {e}")
            return None

    async def get_repo_readme(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetches the raw README data."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/readme"
        try:
            response = await self._make_request("GET", url)
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.info(f"Could not get README for {owner}/{repo}: {e}")
            return None

    async def get_all_repo_data_for_processing(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetches all necessary data for a single repo in parallel."""
        results = await asyncio.gather(
            self.get_repo_details(owner, repo),
            self.get_repo_languages(owner, repo),
            self.get_repo_readme(owner, repo),
            return_exceptions=True
        )

        repo_details, repo_languages, readme_data = results

        if isinstance(repo_details, Exception) or not repo_details:
            logger.critical(f"Could not fetch main details for {owner}/{repo}")
            return None

        return {
            "details": repo_details,
            "languages": repo_languages if not isinstance(repo_languages, Exception) else {},
            "readme_raw": readme_data if not isinstance(readme_data, Exception) else None
        }


github_client = GitHubClient()