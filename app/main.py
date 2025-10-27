from fastapi import FastAPI
from app.api.routes.search import router as search_router
from app.api.routes.repository import router as repository_router

app = FastAPI(
    title="Developer Archives API",
    description="API for semantic search on Github repositories",
    version="1.0.0"
)

app.include_router(search_router, prefix="/api/v1", tags=["search"])
app.include_router(repository_router, prefix="/api/v1", tags=["repository"])


@app.get("/")
async def root():
    return {"message": "Welcome to the Developer Archives API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)