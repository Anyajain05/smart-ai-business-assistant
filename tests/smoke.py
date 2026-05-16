import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


with TestClient(app) as client:
    health = client.get("/health")
    print("health", health.status_code, health.json())

    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    print("login", login.status_code)
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    docs = client.get("/api/documents", headers=headers).json()
    print("docs", len(docs))

    chat = client.post(
        "/api/chat",
        headers=headers,
        json={
            "message": (
                "What are the pricing packages? My name is Alex from BrightCo "
                "and I need a demo today. alex@example.com"
            )
        },
    )
    print("chat", chat.status_code, chat.json()["validation"])

    leads = client.get("/api/leads", headers=headers).json()
    print("leads", len(leads))

    workflow = client.post(
        "/api/workflows/run",
        headers=headers,
        json={"workflow": "email_summary", "payload": {"text": "Please send pricing. Need a call tomorrow."}},
    )
    print("workflow", workflow.json()["status"], "attempts", workflow.json().get("attempts"))

    chain = client.post(
        "/api/workflows/chain",
        headers=headers,
        json={"steps": ["email_summary", "crm_sync"], "payload": {"text": "Short email. Please follow up."}},
    )
    print("chain", chain.status_code, chain.json().get("chain"))

    with client.stream(
        "POST",
        "/api/chat/stream",
        headers=headers,
        json={"message": "Hello from stream smoke test"},
    ) as stream:
        chunks: list[bytes] = []
        for part in stream.iter_bytes():
            chunks.append(part)
            if sum(len(c) for c in chunks) >= 400:
                break
        body = b"".join(chunks)
        print("stream", stream.status_code, body[:120])

    ev = client.post(
        "/api/evaluate",
        headers=headers,
        json={"question": "Do you have pricing?", "answer": "Yes, see our documentation for tiers.", "expected_keywords": ["pricing"]},
    )
    print("evaluate", ev.json().get("overall"))

    analytics = client.get("/api/analytics", headers=headers).json()
    print("analytics", analytics["totals"])
