"""Lightweight AI response evaluation (rubric scoring for SME quality checks)."""

from __future__ import annotations

import re
from typing import Any


def evaluate_response(
    question: str,
    answer: str,
    sources: list[dict[str, Any]],
    expected_keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Return structured scores without calling an external judge model."""
    answer_l = answer.lower()
    question_l = question.lower()

    grounded = bool(sources) and any(
        s.get("content") and len(str(s.get("content", ""))) > 20 for s in sources
    )
    cites_docs = "found in our documentation" in answer_l or "source:" in answer_l or "retrieved" in answer_l

    hedge_phrases = [
        "i don't have",
        "not in the documents",
        "no strong document",
        "cannot confirm",
        "unclear",
        "need more",
    ]
    cautious = any(p in answer_l for p in hedge_phrases)

    keyword_hits = 0
    expected_keywords = expected_keywords or []
    for kw in expected_keywords:
        if kw.lower() in answer_l:
            keyword_hits += 1

    length_ok = 40 <= len(answer) <= 8000
    not_empty = len(answer.strip()) > 5

    scores = {
        "grounded_retrieval": 1.0 if grounded else 0.0,
        "citation_style": 1.0 if cites_docs or grounded else 0.3,
        "hallucination_guard": 1.0 if (cautious or grounded or len(answer) < 500) else 0.6,
        "keyword_coverage": keyword_hits / max(1, len(expected_keywords)) if expected_keywords else None,
        "length_ok": 1.0 if length_ok else 0.4,
        "completeness": 1.0 if not_empty else 0.0,
    }
    parts = [scores["grounded_retrieval"], scores["citation_style"], scores["hallucination_guard"], scores["length_ok"], scores["completeness"]]
    if scores["keyword_coverage"] is not None:
        parts.append(float(scores["keyword_coverage"]))
    overall = round(sum(parts) / len(parts), 3)

    return {
        "overall": overall,
        "scores": scores,
        "signals": {
            "grounded": grounded,
            "cautious_language": cautious,
            "question_preview": question_l[:120],
            "num_sources": len(sources or []),
        },
    }


def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)
