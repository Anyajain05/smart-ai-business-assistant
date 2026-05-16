import json
import re

from app.core.db import execute, row, rows
from app.services.agents import run_agents
from app.services.leads import extract_lead
from app.services.rag import retrieve


def remember_from_text(user_id: int, text: str) -> None:
    patterns = {
        "preferred_contact": r"prefer(?:red)? contact(?: is|:)?\s+([a-zA-Z ]+)",
        "company": r"(?:my company is|we are|company is)\s+([A-Z][\w&. -]+)",
        "industry": r"(?:industry is|we work in)\s+([a-zA-Z &-]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if match:
            execute(
                """
                INSERT INTO memories (user_id, key, value) VALUES (?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
                """,
                (user_id, key, match.group(1).strip()[:160]),
            )


def chat(user: dict, message: str, conversation_id: int | None = None) -> dict:
    if conversation_id is None:
        conversation_id = execute(
            "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
            (user["id"], message[:60] or "Conversation"),
        )
    execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (conversation_id, "user", message),
    )
    remember_from_text(user["id"], message)
    memories = rows("SELECT key, value FROM memories WHERE user_id = ? ORDER BY id DESC", (user["id"],))
    context = retrieve(message)
    agent_result = run_agents(message, context, memories, conversation_id)
    lead = extract_lead(message, conversation_id)
    meta = {"sources": context, "validation": agent_result.validation, "lead_id": lead["id"] if lead else None}
    execute(
        "INSERT INTO messages (conversation_id, role, content, meta) VALUES (?, ?, ?, ?)",
        (conversation_id, "assistant", agent_result.answer, json.dumps(meta)),
    )
    execute("INSERT INTO usage_metrics (event, quantity) VALUES (?, ?)", ("assistant_message", 1))
    return {
        "conversation_id": conversation_id,
        "answer": agent_result.answer,
        "sources": context,
        "validation": agent_result.validation,
        "lead": lead,
    }


def conversation_detail(conversation_id: int) -> dict | None:
    convo = row("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
    if not convo:
        return None
    convo["messages"] = rows("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,))
    return convo
