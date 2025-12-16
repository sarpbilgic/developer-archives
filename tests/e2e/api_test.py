import os
import pytest
import httpx
from pydantic import BaseModel, ValidationError, Field
from typing import List, Optional, Dict, Any


class SearchResultItem(BaseModel):
    """Schema for a single item in the search results."""
    id: int
    full_name: str
    description: Optional[str]
    github_url: str
    stars: int
    primary_language: Optional[str]
    topics: Optional[List[str]]
    languages_breakdown: Optional[Dict[str, int]]
    owner_avatar_url: Optional[str]
    owner_login: str
    owner_url: str
    pushed_at_github: Optional[Any] 
    similarity: Optional[float]

class RepositoryDetail(BaseModel):
    """Schema for the full repository detail response."""
    id: int
    full_name: str
    description: Optional[str]
    github_url: str
    stars: int
    watchers: int
    forks: int
    open_issues: int
    created_at_github: Any
    pushed_at_github: Optional[Any]
    primary_language: Optional[str]
    topics: Optional[List[str]]
    languages_breakdown: Optional[Dict[str, int]]
    owner_avatar_url: Optional[str]
    owner_login: str
    owner_url: str
    owner_type: str


API_BASE_URL = os.environ.get("API_BASE_URL")


if not API_BASE_URL:
    pytest.skip(
        "Skipping E2E tests: API_BASE_URL environment variable not set.", 
        allow_module_level=True
    )

@pytest.fixture(scope="module")
def api_client():
    """Create a persistent httpx client for all E2E tests."""
    # --- FIX: Increased timeout from 20 to 90 seconds for Lambda cold start ---
    with httpx.Client(base_url=API_BASE_URL, timeout=60.0, follow_redirects=True) as client:
        yield client

# --- E2E Tests ---

def test_get_root(api_client: httpx.Client):
    """Tests the root endpoint for a welcome message."""
    print(f"Testing GET {API_BASE_URL}/")
    response = api_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Developer Archives API"}

def test_search_missing_query(api_client: httpx.Client):
    """Tests that the search endpoint requires a query parameter."""
    print(f"Testing GET {API_BASE_URL}/api/v1/search (expect 422)")
    response = api_client.get("/api/v1/search")
    assert response.status_code == 422 

def test_search_and_validate_schema(api_client: httpx.Client):
    """Tests a valid search and validates the response schema."""
    query = "python"
    print(f"Testing GET /api/v1/search?query={query}")
    response = api_client.get(f"/api/v1/search?query={query}")
    assert response.status_code == 200
    
    try:
        results = response.json()
        assert isinstance(results, list)
        
        if results:
            print(f"Found {len(results)} results, validating schema of first item.")
            SearchResultItem.model_validate(results[0])
        else:
            print("Search returned 0 results, which is valid.")
    
    except ValidationError as e:
        pytest.fail(f"Search response for query '{query}' failed schema validation: {e}")
    except Exception as e:
        pytest.fail(f"Search response for query '{query}' was not valid JSON: {e}")

@pytest.mark.dependency(name="search_works", depends=["test_search_and_validate_schema"])
def test_get_project_details_and_readme(api_client: httpx.Client):
    """
    Tests the detail and README endpoints using a valid ID from the search.
    This test is skipped if the search returns no results.
    """
    print("\n--- Chained Test: test_get_project_details_and_readme ---")
    search_resp = api_client.get("/api/v1/search?query=fastapi&topics=python")
    assert search_resp.status_code == 200
    results = search_resp.json()

    if not results:
        pytest.skip("Search returned no results. Cannot test project detail/readme endpoints.")

    project_id = results[0].get("id")
    project_name = results[0].get("full_name")
    assert isinstance(project_id, int)
    print(f"Found project '{project_name}' (ID: {project_id}) from search.")


    print(f"Testing GET /api/v1/projects/{project_id}")
    detail_resp = api_client.get(f"/api/v1/projects/{project_id}")
    
    assert detail_resp.status_code == 200
    try:
        RepositoryDetail.model_validate(detail_resp.json())
        print("Project detail schema validated.")
    except ValidationError as e:
        pytest.fail(f"Project detail response for ID {project_id} failed schema validation: {e}")

    # --- 2. Test Project README Endpoint ---
    print(f"Testing GET /api/v1/projects/{project_id}/readme")
    readme_resp = api_client.get(f"/api/v1/projects/{project_id}/readme")
    
    assert readme_resp.status_code == 200
    assert "text/plain" in readme_resp.headers['content-type']
    assert len(readme_resp.text) > 10  # README should have some content
    print("Project README validated.")

def test_get_project_not_found(api_client: httpx.Client):
    """Tests that a non-existent project ID returns a 404."""
    project_id = 999999999  # An ID that will not exist
    print(f"Testing GET /api/v1/projects/{project_id} (expect 404)")
    response = api_client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 404

def test_get_readme_not_found(api_client: httpx.Client):
    """Tests that a non-existent project README returns a 404."""
    project_id = 999999999
    print(f"Testing GET /api/v1/projects/{project_id}/readme (expect 404)")
    response = api_client.get(f"/api/v1/projects/{project_id}/readme")
    assert response.status_code == 404