import json
import time
from datetime import datetime, timedelta
from typing import Any

from app.core.db import execute, row, rows


def _execute_once(workflow: str, payload: dict) -> dict:
    if workflow == "email_summary":
        return email_summary(payload.get("text", ""))
    if workflow == "crm_sync":
        return crm_sync(payload)
    if workflow == "calendar_booking":
        return calendar_booking(payload)
    raise ValueError("Unknown workflow")


def run_workflow(workflow: str, payload: dict) -> dict:
    """Run a single automation with autonomous retries on transient failures."""
    last_exc: Exception | None = None
    output: dict[str, Any] | None = None
    attempts = 0
    max_attempts = 3
    for attempt in range(max_attempts):
        attempts = attempt + 1
        try:
            output = _execute_once(workflow, payload)
            status = "success"
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(min(2**attempt, 6))
    if last_exc is not None:
        status = "failed"
        output = {
            "error": str(last_exc),
            "attempts": attempts,
            "fallback": "Notify an operator and retry after checking the payload.",
        }
    assert output is not None
    execute(
        "INSERT INTO workflow_logs (workflow, status, input, output) VALUES (?, ?, ?, ?)",
        (workflow, status, json.dumps(payload), json.dumps(output)),
    )
    return {"workflow": workflow, "status": status, "output": output, "attempts": attempts}


def run_workflow_chain(steps: list[str], payload: dict) -> dict:
    """Run multiple automations in order; stops on first failure."""
    results: list[dict[str, Any]] = []
    for step in steps:
        res = run_workflow(step, payload)
        results.append(res)
        if res.get("status") != "success":
            break
    return {"chain": True, "steps": steps, "results": results}


def email_summary(text: str) -> dict:
    if not (text or "").strip():
        raise ValueError("Email text is required for summarization")
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    return {
        "summary": ". ".join(sentences[:2]) or "No email text supplied.",
        "action_items": [s for s in sentences if any(w in s.lower() for w in ["please", "need", "send", "book", "follow"])][:5],
    }


def crm_sync(payload: dict) -> dict:
    lead_id = payload.get("lead_id")
    lead = row("SELECT * FROM leads WHERE id = ?", (lead_id,)) if lead_id else None
    if not lead:
        recent = rows("SELECT * FROM leads ORDER BY id DESC LIMIT 1")
        lead = recent[0] if recent else None
    return {"synced": bool(lead), "destination": "Demo CRM / Sheets", "record": lead}


def calendar_booking(payload: dict) -> dict:
    start = datetime.utcnow() + timedelta(days=1)
    return {
        "status": "tentative",
        "slot": start.replace(minute=0, second=0, microsecond=0).isoformat() + "Z",
        "attendee": payload.get("email", "lead@example.com"),
    }
