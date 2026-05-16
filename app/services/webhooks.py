"""Outbound webhooks with HMAC signatures and delivery logging."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.db import execute, rows

log = logging.getLogger(__name__)


def list_webhooks() -> list[dict[str, Any]]:
    return rows("SELECT id, url, events, active, created_at FROM webhooks ORDER BY id DESC")


def create_webhook(url: str, secret: str, events: list[str] | None = None) -> int:
    ev = json.dumps(events or ["*"])
    return execute("INSERT INTO webhooks (url, secret, events) VALUES (?, ?, ?)", (url, secret, ev))


def delete_webhook(webhook_id: int) -> None:
    execute("DELETE FROM webhook_deliveries WHERE webhook_id = ?", (webhook_id,))
    execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))


def _parse_events(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else ["*"]
    except json.JSONDecodeError:
        return ["*"]


def dispatch_event_sync(event: str, payload: dict[str, Any]) -> None:
    settings = get_settings()
    hooks = rows("SELECT * FROM webhooks WHERE active = 1")
    if not hooks:
        return
    body = json.dumps(payload, separators=(",", ":"), default=str)
    for hook in hooks:
        events = _parse_events(hook.get("events") or "")
        if "*" not in events and event not in events:
            continue
        sig = hmac.new(
            str(hook["secret"]).encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
            "X-Webhook-Signature": f"sha256={sig}",
        }
        try:
            with httpx.Client(timeout=settings.webhook_timeout_seconds) as client:
                resp = client.post(hook["url"], content=body, headers=headers)
            ok = 200 <= resp.status_code < 300
            execute(
                "INSERT INTO webhook_deliveries (webhook_id, event, status_code, success, detail) VALUES (?, ?, ?, ?, ?)",
                (
                    hook["id"],
                    event,
                    resp.status_code,
                    1 if ok else 0,
                    (resp.text or "")[:2000],
                ),
            )
        except Exception as exc:
            log.warning("Webhook delivery failed: %s", exc)
            execute(
                "INSERT INTO webhook_deliveries (webhook_id, event, status_code, success, detail) VALUES (?, ?, ?, ?, ?)",
                (hook["id"], event, 0, 0, str(exc)[:2000]),
            )


def recent_deliveries(limit: int = 50) -> list[dict[str, Any]]:
    return rows(
        "SELECT wd.*, w.url FROM webhook_deliveries wd JOIN webhooks w ON w.id = wd.webhook_id ORDER BY wd.id DESC LIMIT ?",
        (limit,),
    )
