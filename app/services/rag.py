import hashlib
import re
from collections import Counter
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.db import execute, row, rows
from app.services.cache import cache_get_json, cache_set_json
from app.services import vector_store

WORD_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]+")


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def chunk_text(text: str, size: int = 650, overlap: int = 90) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + size]))
        start += max(1, size - overlap)
    return chunks


def _cache_key(query: str) -> str:
    q = query.strip().lower()[:800]
    h = hashlib.sha256(q.encode("utf-8", errors="ignore")).hexdigest()
    return f"rag:v2:{h}"


def _lexical_retrieve(query: str, limit: int = 4) -> list[dict]:
    q_terms = Counter(tokenize(query))
    if not q_terms:
        return []
    scored: list[tuple[float, dict]] = []
    for chunk in rows(
        "SELECT chunks.*, documents.filename FROM chunks JOIN documents ON documents.id = chunks.document_id"
    ):
        c_terms = Counter((chunk["terms"] or "").split())
        overlap = sum(min(q_terms[t], c_terms[t]) for t in q_terms)
        score = overlap / max(1, len(q_terms))
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "chunk_id": chunk["id"],
            "document": chunk["filename"],
            "content": chunk["content"],
            "score": round(score, 4),
            "vector": False,
        }
        for score, chunk in scored[:limit]
    ]


def retrieve(query: str, limit: int = 4) -> list[dict]:
    settings = get_settings()
    key = _cache_key(query)
    cached = cache_get_json(key)
    if isinstance(cached, list) and cached:
        return cached[:limit]

    results: list[dict] = []
    seen_ids: set[int] = set()

    for cid_str, dist in vector_store.query_vectors(query, limit=limit * 2):
        try:
            cid = int(cid_str)
        except ValueError:
            continue
        chunk = row(
            "SELECT chunks.*, documents.filename FROM chunks JOIN documents ON documents.id = chunks.document_id WHERE chunks.id = ?",
            (cid,),
        )
        if not chunk or chunk["id"] in seen_ids:
            continue
        seen_ids.add(chunk["id"])
        d = float(dist)
        score = max(0.01, 1.0 / (1.0 + d))
        results.append(
            {
                "chunk_id": chunk["id"],
                "document": chunk["filename"],
                "content": chunk["content"],
                "score": round(score, 4),
                "vector": True,
            }
        )
        if len(results) >= limit:
            break

    if len(results) < limit:
        for item in _lexical_retrieve(query, limit=limit * 3):
            cid = item.get("chunk_id")
            if cid in seen_ids:
                continue
            seen_ids.add(int(cid))
            results.append(item)
            if len(results) >= limit:
                break

    results = results[:limit]
    if results:
        cache_set_json(key, results, settings.rag_cache_ttl_seconds)
    return results


def _index_chunks(doc_id: int, filename: str, chunks_list: list[str]) -> int:
    count = 0
    batch: list[dict] = []
    for chunk in chunks_list:
        terms = " ".join(tokenize(chunk))
        cid = execute(
            "INSERT INTO chunks (document_id, content, terms) VALUES (?, ?, ?)",
            (doc_id, chunk, terms),
        )
        count += 1
        batch.append(
            {
                "id": str(cid),
                "text": chunk,
                "metadata": {"document_id": int(doc_id), "sqlite_chunk_id": int(cid), "filename": str(filename)},
            }
        )
    if batch:
        vector_store.upsert_chunks(batch)
    return count


async def save_document(file: UploadFile) -> dict:
    settings = get_settings()
    safe_name = Path(file.filename or "document.txt").name
    raw = await file.read()
    text = raw.decode("utf-8", errors="ignore")
    if not text.strip():
        text = f"Uploaded file {safe_name} could not be decoded as text. Add a text export for best retrieval."
    target = settings.upload_path / safe_name
    target.write_bytes(raw)
    summary = summarize(text)
    doc_id = execute(
        "INSERT INTO documents (filename, path, summary) VALUES (?, ?, ?)",
        (safe_name, str(target), summary),
    )
    chunks_list = chunk_text(text)
    n = _index_chunks(doc_id, safe_name, chunks_list)
    doc = row("SELECT * FROM documents WHERE id = ?", (doc_id,)) or {}
    doc["chunks_count"] = n
    return doc


def index_text_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    summary = summarize(text)
    doc_id = execute(
        "INSERT INTO documents (filename, path, summary) VALUES (?, ?, ?)",
        (path.name, str(path), summary),
    )
    chunks_list = chunk_text(text)
    n = _index_chunks(doc_id, path.name, chunks_list)
    doc = row("SELECT * FROM documents WHERE id = ?", (doc_id,)) or {}
    doc["chunks_count"] = n
    return doc


def summarize(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= 220:
        return cleaned
    return cleaned[:217].rsplit(" ", 1)[0] + "..."
