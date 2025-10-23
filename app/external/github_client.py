# app/external/github_client.py (FINAL VERSION)

import httpx
import base64
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.settings import settings

class GitHubClient:
    """
    A robust, production-ready client for interacting with the GitHub API.
    Handles authentication, rate limiting, error handling, and discovery.
    
    CONCURRENCY CONTROL:
    - Uses asyncio.Semaphore to limit parallel API calls
    - Prevents sudden rate limit spikes across multiple Lambda instances
    - Reduces 403 errors and retry overhead
    """
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
            timeout=20.0 # Increase timeout for potentially slower search APIs
        )
        
        # Semaphore to limit concurrent API calls
        # Even though we have 5000 req/hr, limiting concurrency prevents:
        # - Sudden spikes that trigger 403 errors
        # - Multiple Lambda instances overwhelming the rate limit
        # - Connection pool exhaustion
        self._api_semaphore = asyncio.Semaphore(3)  # Max 3 concurrent API calls per instance

    async def _make_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Internal method to make a request and handle rate limiting.
        
        IMPROVED STRATEGY:
        - Uses semaphore to limit concurrent calls (prevents spikes)
        - Only pauses when CRITICALLY low (< 5 remaining)
        - Log warnings for monitoring but DON'T block unnecessarily
        - Let multiple Lambda instances share the rate limit pool
        """
        async with self._api_semaphore:  # Limit concurrent API calls
            response = await self._client.request(method, url, **kwargs)
            
            # --- INTELLIGENT RATE LIMIT HANDLING ---
            remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
            
            # Warning threshold: Log but don't block
            if remaining < 100:
                print(f"INFO: GitHub API rate limit at {remaining} requests remaining")
            
            # CRITICAL threshold: Only pause when truly necessary
            if remaining < 5:
                reset_timestamp = int(response.headers.get("X-RateLimit-Reset", 0))
                reset_time = datetime.fromtimestamp(reset_timestamp, tz=timezone.utc)
                now = datetime.now(timezone.utc)
                sleep_duration = (reset_time - now).total_seconds()
                
                if sleep_duration > 0:
                    print(f"CRITICAL: GitHub API rate limit critically low ({remaining} left). Pausing for {sleep_duration:.2f} seconds.")
                    await asyncio.sleep(sleep_duration + 2) # Add 2s buffer
            # --- -------------------------------- ---
            
            response.raise_for_status() # Raise an exception for 4xx/5xx errors
            return response

    async def search_repositories(
        self, 
        query: str, 
        sort: str = "stars", 
        order: str = "desc", 
        per_page: int = 100, 
        page: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Searches for repositories using the GitHub Search API.
        This is the primary tool for the "Discoverer" service.
        """
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
            print(f"ERROR: Repository search failed for query '{query}': {e}")
            return None

    async def get_repo_details(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetches the main metadata for a single repository."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}"
        try:
            response = await self._make_request("GET", url)
            return response.json()
        except httpx.HTTPStatusError as e:
            # This is expected if a repo is deleted or made private
            print(f"INFO: Could not get repo details for {owner}/{repo}: {e}")
            return None

    async def get_repo_languages(self, owner: str, repo: str) -> Optional[Dict[str, int]]:
        """Fetches the language breakdown for a single repository."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/languages"
        try:
            response = await self._make_request("GET", url)
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"INFO: Could not get languages for {owner}/{repo}: {e}")
            return None

    async def get_repo_readme(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetches the raw README data (including encoded content)."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/readme"
        try:
            response = await self._make_request("GET", url)
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None # It's normal for a repo to not have a README
            print(f"INFO: Could not get README for {owner}/{repo}: {e}")
            return None

    async def get_all_repo_data_for_processing(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """
        The main orchestration method used by the "Analyst" service.
        It efficiently fetches all necessary data for a single repo in parallel.
        """
        # Use asyncio.gather to send all 3 API requests concurrently
        results = await asyncio.gather(
            self.get_repo_details(owner, repo),
            self.get_repo_languages(owner, repo),
            self.get_repo_readme(owner, repo),
            return_exceptions=True
        )

        repo_details, repo_languages, readme_data = results

        if isinstance(repo_details, Exception) or not repo_details:
            print(f"CRITICAL: Could not fetch main details for {owner}/{repo}. Aborting processing for this repo.")
            return None

        # Consolidate all raw data into a single, clean dictionary
        return {
            "details": repo_details,
            "languages": repo_languages if not isinstance(repo_languages, Exception) else {},
            "readme_raw": readme_data if not isinstance(readme_data, Exception) else None
        }

# A single, reusable instance for the rest of our application
github_client = GitHubClient()