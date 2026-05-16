import asyncio
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr

from app.api.deps import current_user, require_admin
from app.core.db import execute, row, rows
from app.core.security import create_token, hash_password, verify_password
from app.services.assistant import chat, conversation_detail
from app.services.automations import run_workflow, run_workflow_chain
from app.services.cache import redis_ready
from app.services.evaluation import evaluate_response
from app.services.multimodal import describe_image
from app.services.rag import save_document
from app.services import vector_store
from app.services.webhooks import create_webhook, delete_webhook, dispatch_event_sync, list_webhooks, recent_deliveries

router = APIRouter(prefix="/api")


class SignupIn(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str = "admin"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ChatIn(BaseModel):
    message: str
    conversation_id: int | None = None


class WorkflowIn(BaseModel):
    workflow: str
    payload: dict = {}


class ChainIn(BaseModel):
    steps: list[str]
    payload: dict = {}


class WebhookCreate(BaseModel):
    url: str
    secret: str = "signing-secret-change-me"
    events: list[str] = ["*"]


class EvalIn(BaseModel):
    question: str
    answer: str
    expected_keywords: list[str] = []
    sources: list[dict] = []


@router.post("/auth/signup")
async def signup(data: SignupIn) -> dict:
    if row("SELECT id FROM users WHERE email = ?", (data.email,)):
        raise HTTPException(409, "Email already registered")
    execute(
        "INSERT INTO users (email, name, role, password_hash) VALUES (?, ?, ?, ?)",
        (data.email, data.name, data.role, hash_password(data.password)),
    )
    token = create_token(data.email, data.role)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/auth/login")
async def login(data: LoginIn) -> dict:
    user = row("SELECT * FROM users WHERE email = ?", (data.email,))
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return {
        "access_token": create_token(user["email"], user["role"]),
        "token_type": "bearer",
        "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]},
    }


@router.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return user


@router.post("/chat")
async def chat_route(
    data: ChatIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(current_user),
) -> dict:
    result = chat(user, data.message, data.conversation_id)
    if result.get("lead"):
        background_tasks.add_task(
            dispatch_event_sync,
            "lead.created",
            {"lead": result["lead"], "conversation_id": result["conversation_id"]},
        )
    return result


@router.post("/chat/stream")
async def chat_stream_route(
    data: ChatIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(current_user),
):
    result = await asyncio.to_thread(chat, user, data.message, data.conversation_id)
    if result.get("lead"):
        background_tasks.add_task(
            dispatch_event_sync,
            "lead.created",
            {"lead": result["lead"], "conversation_id": result["conversation_id"]},
        )

    async def event_gen():
        yield f"data: {json.dumps({'type': 'start', 'conversation_id': result['conversation_id']})}\n\n"
        text = result.get("answer") or ""
        step = 36
        for i in range(0, len(text), step):
            chunk = text[i : i + step]
            yield f"data: {json.dumps({'type': 'delta', 'text': chunk})}\n\n"
            await asyncio.sleep(0.012)
        done_payload = {
            "type": "done",
            "sources": result.get("sources"),
            "validation": result.get("validation"),
            "lead": result.get("lead"),
        }
        yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/conversations")
async def conversations(user: dict = Depends(current_user)) -> list[dict]:
    return rows("SELECT * FROM conversations WHERE user_id = ? ORDER BY id DESC", (user["id"],))


@router.get("/conversations/{conversation_id}")
async def conversation(conversation_id: int, user: dict = Depends(current_user)) -> dict:
    item = conversation_detail(conversation_id)
    if not item or item["user_id"] != user["id"]:
        raise HTTPException(404, "Conversation not found")
    return item


@router.post("/documents")
async def upload_document(file: UploadFile = File(...), user: dict = Depends(require_admin)) -> dict:
    return await save_document(file)


@router.get("/documents")
async def documents(user: dict = Depends(current_user)) -> list[dict]:
    return rows(
        """
        SELECT d.*,
          (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunks_count
        FROM documents d
        ORDER BY d.id DESC
        """
    )


@router.get("/leads")
async def leads(user: dict = Depends(require_admin)) -> list[dict]:
    return rows("SELECT * FROM leads ORDER BY id DESC")


@router.post("/workflows/run")
async def workflow(
    data: WorkflowIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_admin),
) -> dict:
    result = run_workflow(data.workflow, data.payload)
    if result.get("status") == "success":
        background_tasks.add_task(
            dispatch_event_sync,
            "workflow.completed",
            {"workflow": data.workflow, "output": result.get("output")},
        )
    return result


@router.post("/workflows/chain")
async def workflow_chain(
    data: ChainIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_admin),
) -> dict:
    if not data.steps:
        raise HTTPException(400, "steps must not be empty")
    allowed = {"email_summary", "crm_sync", "calendar_booking"}
    for s in data.steps:
        if s not in allowed:
            raise HTTPException(400, f"Unknown step: {s}")
    result = run_workflow_chain(data.steps, data.payload)
    background_tasks.add_task(
        dispatch_event_sync,
        "workflow.chain.completed",
        {"steps": data.steps, "result": result},
    )
    return result


@router.get("/workflows/logs")
async def workflow_logs(user: dict = Depends(require_admin)) -> list[dict]:
    return rows("SELECT * FROM workflow_logs ORDER BY id DESC LIMIT 100")


@router.get("/analytics")
async def analytics(user: dict = Depends(require_admin)) -> dict:
    lead_counts = rows("SELECT temperature, COUNT(*) AS count FROM leads GROUP BY temperature")
    return {
        "totals": {
            "leads": row("SELECT COUNT(*) AS count FROM leads")["count"],
            "conversations": row("SELECT COUNT(*) AS count FROM conversations")["count"],
            "documents": row("SELECT COUNT(*) AS count FROM documents")["count"],
            "workflow_runs": row("SELECT COUNT(*) AS count FROM workflow_logs")["count"],
            "assistant_messages": row(
                "SELECT COALESCE(SUM(quantity), 0) AS count FROM usage_metrics WHERE event = 'assistant_message'"
            )["count"],
        },
        "lead_temperatures": lead_counts,
        "recent_agent_logs": rows("SELECT * FROM agent_logs ORDER BY id DESC LIMIT 20"),
        "recent_workflows": rows("SELECT * FROM workflow_logs ORDER BY id DESC LIMIT 20"),
        "bonus": {
            "redis_cache": redis_ready(),
            "chroma_vector": vector_store.get_collection() is not None,
            "webhooks_registered": row("SELECT COUNT(*) AS count FROM webhooks")["count"],
        },
    }


@router.get("/webhooks")
async def webhooks_list(user: dict = Depends(require_admin)) -> list[dict]:
    return list_webhooks()


@router.post("/webhooks")
async def webhooks_create(data: WebhookCreate, user: dict = Depends(require_admin)) -> dict:
    if not data.url.startswith("http"):
        raise HTTPException(400, "url must be http(s)")
    wid = create_webhook(data.url, data.secret, data.events)
    return {"id": wid, "url": data.url, "events": data.events}


@router.delete("/webhooks/{webhook_id}")
async def webhooks_delete(webhook_id: int, user: dict = Depends(require_admin)) -> dict:
    delete_webhook(webhook_id)
    return {"deleted": webhook_id}


@router.get("/monitoring/deliveries")
async def monitoring_deliveries(user: dict = Depends(require_admin)) -> list[dict]:
    return recent_deliveries(80)


@router.post("/evaluate")
async def evaluate_route(data: EvalIn, user: dict = Depends(current_user)) -> dict:
    scores = evaluate_response(data.question, data.answer, data.sources, data.expected_keywords)
    execute(
        "INSERT INTO evaluation_runs (user_id, question, answer, scores_json) VALUES (?, ?, ?, ?)",
        (user["id"], data.question, data.answer, json.dumps(scores)),
    )
    return scores


@router.get("/evaluate/history")
async def evaluate_history(user: dict = Depends(require_admin)) -> list[dict]:
    return rows("SELECT * FROM evaluation_runs ORDER BY id DESC LIMIT 50")


@router.post("/media/analyze")
async def media_analyze(file: UploadFile = File(...), user: dict = Depends(current_user)) -> dict:
    raw = await file.read()
    if len(raw) > 6 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 6MB)")
    mime = file.content_type or "image/png"
    if not mime.startswith("image/"):
        raise HTTPException(400, "Please upload an image file")
    return describe_image(raw, mime=mime)
