import re

from app.core.db import execute, row

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d[\d .()-]{7,}\d)")


def classify_lead(text: str) -> str:
    lowered = text.lower()
    hot = ["urgent", "today", "asap", "buy", "pricing", "book", "demo", "contract", "quote"]
    warm = ["interested", "next week", "budget", "proposal", "compare", "evaluate"]
    if any(term in lowered for term in hot):
        return "hot"
    if any(term in lowered for term in warm):
        return "warm"
    return "cold"


def extract_lead(text: str, conversation_id: int | None = None) -> dict | None:
    lowered = text.lower()
    intent_terms = ["email", "phone", "call", "demo", "quote", "pricing", "interested", "contact", "book"]
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    if not email and not phone and not any(term in lowered for term in intent_terms):
        return None
    name = None
    name_match = re.search(r"(?:i am|i'm|my name is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    if name_match:
        name = name_match.group(1)
    company = None
    company_match = re.search(r"(?:from|at)\s+([A-Z][\w&.-]+(?:\s+[A-Z][\w&.-]+)?)", text)
    if company_match:
        company = company_match.group(1)
    temperature = classify_lead(text)
    follow_up = build_follow_up(name or "there", temperature, text)
    lead_id = execute(
        """
        INSERT INTO leads (name, email, phone, company, need, temperature, source_conversation_id, follow_up)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            email.group(0) if email else None,
            phone.group(0) if phone else None,
            company,
            text[:1000],
            temperature,
            conversation_id,
            follow_up,
        ),
    )
    return row("SELECT * FROM leads WHERE id = ?", (lead_id,))


def build_follow_up(name: str, temperature: str, need: str) -> str:
    opener = "Thanks for reaching out"
    if temperature == "hot":
        action = "I can help you schedule a priority call and prepare a tailored quote."
    elif temperature == "warm":
        action = "I can send a short proposal and answer the main evaluation questions."
    else:
        action = "I can share a useful overview and check whether this is a fit."
    return f"Hi {name}, {opener}. {action} Based on your note: {need[:180]}"
