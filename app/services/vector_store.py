"""ChromaDB vector index for semantic RAG (embeddings + persistent vector store)."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.core.config import get_settings

log = logging.getLogger(__name__)

_collection = None
_chroma_failed: str | None = None


def _embedding_function():
    from chromadb.utils import embedding_functions

    key = os.getenv("OPENAI_API_KEY") or get_settings().openai_api_key
    if key:
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=key,
            model_name=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        )
    return embedding_functions.DefaultEmbeddingFunction()


def get_collection():
    """Return Chroma collection or None if unavailable."""
    global _collection, _chroma_failed
    if _chroma_failed:
        return None
    if _collection is not None:
        return _collection
    import os

    os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
    try:
        import chromadb
    except ImportError as exc:
        _chroma_failed = str(exc)
        log.warning("chromadb not installed: %s", exc)
        return None

    settings = get_settings()
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    try:
        client = chromadb.PersistentClient(path=str(settings.chroma_dir.resolve()))
        _collection = client.get_or_create_collection(
            name="business_kb",
            metadata={"description": "SME knowledge chunks"},
            embedding_function=_embedding_function(),
        )
        return _collection
    except Exception as exc:
        _chroma_failed = str(exc)
        log.warning("Chroma init failed, lexical RAG only: %s", exc)
        return None


def reset_client_for_tests() -> None:
    global _collection, _chroma_failed
    _collection = None
    _chroma_failed = None


def upsert_chunks(entries: list[dict[str, Any]]) -> None:
    """entries: dict with keys id (str), document, metadata (flat), optional document is content text."""
    col = get_collection()
    if not col or not entries:
        return
    ids = [e["id"] for e in entries]
    documents = [e["text"] for e in entries]
    metadatas = [e["metadata"] for e in entries]
    try:
        col.upsert(ids=ids, documents=documents, metadatas=metadatas)
    except Exception as exc:
        log.warning("Chroma upsert failed: %s", exc)


def delete_chunks_for_document(document_id: int) -> None:
    col = get_collection()
    if not col:
        return
    try:
        col.delete(where={"document_id": document_id})
    except Exception as exc:
        log.warning("Chroma delete failed: %s", exc)


def query_vectors(query: str, limit: int = 6) -> list[tuple[str, float]]:
    """Return list of (chunk_sqlite_id_str, distance_or_similarity_proxy)."""
    col = get_collection()
    if not col:
        return []
    try:
        res = col.query(query_texts=[query], n_results=limit)
        ids_out: list[str] = []
        dists: list[float] = []
        if res.get("ids") and res["ids"][0]:
            ids_out = list(res["ids"][0])
        if res.get("distances") and res["distances"][0]:
            dists = [float(x) for x in res["distances"][0]]
        out: list[tuple[str, float]] = []
        for i, cid in enumerate(ids_out):
            d = dists[i] if i < len(dists) else 0.0
            out.append((str(cid), d))
        return out
    except Exception as exc:
        log.warning("Chroma query failed: %s", exc)
        return []
