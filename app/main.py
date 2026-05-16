from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.core.db import init_db, row
from app.services.cache import redis_ready
from app.services.rag import index_text_file
from app.services import vector_store

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")


@app.on_event("startup")
async def startup() -> None:
    init_db()
    sample = Path("data/sample_knowledge.txt")
    if sample.exists() and row("SELECT COUNT(*) AS count FROM documents")["count"] == 0:
        index_text_file(sample)


app.include_router(router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def dashboard() -> FileResponse:
    return FileResponse(Path("app/templates/index.html"))


@app.get("/health")
async def health() -> dict:
    chroma_ok = vector_store.get_collection() is not None
    return {
        "status": "ok",
        "app": settings.app_name,
        "redis_cache": redis_ready(),
        "chroma_vector_store": chroma_ok,
        "bonus_features": {
            "streaming_chat": True,
            "webhooks": True,
            "redis_caching": redis_ready(),
            "vector_rag": chroma_ok,
            "voice_ui": True,
            "multimodal_upload": True,
            "workflow_chain": True,
            "evaluation_api": True,
            "agent_trace_meta": True,
        },
    }
