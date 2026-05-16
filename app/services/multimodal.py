"""Image understanding via OpenAI vision when configured; safe stub otherwise."""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx


def describe_image(image_bytes: bytes, mime: str = "image/png") -> dict[str, Any]:
    """Return a textual description and optional structured tags."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "mode": "stub",
            "description": (
                "Image received. Set OPENAI_API_KEY to enable vision analysis (gpt-4o-mini). "
                "Until then, attach a short text caption in chat alongside the image."
            ),
            "tags": [],
        }

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe this image briefly for a business assistant. List key objects or text visible, and any implied business context.",
                    },
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ],
        "max_tokens": 400,
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    text = ""
    if data.get("choices"):
        text = data["choices"][0].get("message", {}).get("content") or ""
    return {"mode": "openai_vision", "description": text.strip(), "model": model, "tags": _quick_tags(text)}


def _quick_tags(text: str) -> list[str]:
    tags: list[str] = []
    lowered = text.lower()
    for t in ["invoice", "logo", "chart", "screenshot", "product", "receipt", "signature", "diagram"]:
        if t in lowered:
            tags.append(t)
    return tags[:8]
