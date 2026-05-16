from dataclasses import dataclass
import json
import re
import os
import random
import time
import uuid
from dotenv import load_dotenv

# Load .env into environment so os.getenv() can access user-provided keys
load_dotenv()
import httpx

from app.core.db import execute


@dataclass
class AgentResult:
    plan: str
    answer: str
    validation: str


def synthesize_answer(question: str, context: list[dict], memories: list[dict]) -> str:
    """Generate a professional, synthesized answer from retrieved context."""
    def suggest_question() -> str:
        suggestions = [
            "What are the top 3 actions I should take this week to improve sales?",
            "What is the biggest bottleneck in my current sales process?",
            "Which customer segment should I focus on first for faster growth?",
            "What should I automate first to save time and reduce manual work?",
        ]

        if memories:
            company = next((m.get("value") for m in memories if m.get("key") == "company"), None)
            industry = next((m.get("value") for m in memories if m.get("key") == "industry"), None)
            if company or industry:
                lead_in = f"For {company or 'your business'}" if company else f"For a {industry} business"
                suggestions = [
                    f"{lead_in}, what is the most important thing to improve this month?",
                    f"{lead_in}, which customer problem should I solve first?",
                    f"{lead_in}, what is one simple change that could increase revenue quickly?",
                ]

        return "\n".join(f"- {item}" for item in random.sample(suggestions, k=min(3, len(suggestions))))

    q = question.strip()
    q_lower = q.lower()

    if any(phrase in q_lower for phrase in ["give me question", "give me a question", "question to ask", "what should i ask", "suggest a question", "ask me a question"]):
        return (
            "Here are a few questions you can ask:\n\n"
            f"{suggest_question()}\n\n"
            "If you want, I can make them more specific for sales, support, marketing, or operations."
        )

    if any(w in q_lower for w in ["pricing", "price", "cost", "plan", "how much", "fee", "billing"]):
        return (
            f"For {q}, a practical pricing answer is to use three clear tiers: Starter, Growth, and Premium.\n\n"
            "A strong plan usually does three things:\n"
            "- keeps the entry tier simple so new customers can start fast\n"
            "- ties the middle tier to the main business value you deliver\n"
            "- reserves the highest tier for teams that need support, automation, or custom work\n\n"
            "If you want, I can help draft a pricing page, a package comparison table, or a customer-ready quote structure."
        )

    if any(w in q_lower for w in ["sales", "revenue", "pipeline", "conversion", "close"]):
        return (
            f"For {q}, the fastest improvement usually comes from focusing on lead quality, follow-up speed, and one clear offer.\n\n"
            "Start with these three actions:\n"
            "- respond to new leads within minutes, not hours\n"
            "- remove one point of friction from the buying process\n"
            "- test a single offer with a clear outcome and deadline\n\n"
            "If you want, I can turn this into a week-by-week sales plan."
        )

    if any(w in q_lower for w in ["marketing", "traffic", "ads", "content", "seo"]):
        return (
            f"For {q}, the best move is usually to pick one audience, one message, and one channel.\n\n"
            "A simple plan is:\n"
            "- define the exact customer you want to reach\n"
            "- write one message that solves a painful problem\n"
            "- publish consistently on the channel where that customer already pays attention\n\n"
            "If you want, I can help draft a campaign or content plan."
        )

    if any(w in q_lower for w in ["support", "help", "issue", "problem", "ticket"]):
        return (
            f"For {q}, the best support answer is to reduce back-and-forth and give a clear next step.\n\n"
            "Use this structure:\n"
            "- acknowledge the issue in one sentence\n"
            "- give the immediate action the user should take\n"
            "- include the escalation path if the first step does not work\n\n"
            "If you want, I can draft a support reply or help-center article."
        )

    if any(w in q_lower for w in ["operations", "workflow", "process", "automation", "automate", "efficiency"]):
        return (
            f"For {q}, the best improvement is usually to remove manual work from the highest-volume task first.\n\n"
            "A practical approach is:\n"
            "- list the tasks your team repeats every day\n"
            "- pick the one that takes the most time and causes the most errors\n"
            "- automate that step before moving to lower-impact tasks\n\n"
            "If you want, I can help map the workflow and identify automation opportunities."
        )
    
    if not context:
        # More helpful, direct fallback when no documents match
        if any(w in q_lower for w in ["pricing", "price", "cost", "plan", "how much", "fee"]):
            return (
                f"For {q}, the cleanest approach is a 3-tier pricing model: Starter, Growth, and Premium.\n\n"
                "Make sure each tier has a clear jump in value, not just a higher price.\n"
                "If you want, I can help you sketch the actual tier names, features, and price anchors."
            )
        elif any(w in q_lower for w in ["integrate", "zapier", "salesforce", "api", "connect", "sync"]):
            return (
                f"For {q}, start by checking whether the integration needs to sync contacts, deals, or events.\n\n"
                "A practical rollout is:\n"
                "- define the exact data you need to move\n"
                "- map the trigger and destination system\n"
                "- test with one record type before scaling up\n\n"
                "If you want, I can help outline the data flow."
            )
        elif any(w in q_lower for w in ["demo", "schedule", "book", "meeting", "call"]):
            return (
                f"For {q}, the best next step is to propose 2 or 3 time windows and ask for the attendee count.\n\n"
                "A useful booking message includes:\n"
                "- preferred date and time zone\n"
                "- number of attendees\n"
                "- the main goal of the meeting\n\n"
                "If you want, I can draft the message for you."
            )
        elif any(w in q_lower for w in ["refund", "return", "cancel", "policy"]):
            return (
                f"For {q}, a good policy answer should clearly state eligibility, timelines, and the exception cases.\n\n"
                "If you are writing one, keep it short and explicit about who qualifies, how long it takes, and who approves it."
            )
        else:
            return (
                f"For {q}, I would answer it by identifying the main objective, the main constraint, and the fastest next action.\n\n"
                "If you want a better answer, tell me the industry, the goal, and whether you want strategy, copy, or an action plan."
            )
    
    # Extract key information from context
    combined_text = "\n".join(c["content"] for c in context)
    q_lower = question.lower()
    
    # Build professional, grounded answer
    answer_lines = ["✅ **Found in our documentation:**\n"]
    
    # Split into sentences and extract meaningful ones
    sentences = re.split(r'[.!?]+', combined_text)
    meaningful = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 20]
    
    # Add key insights from documents
    for sent in meaningful[:3]:
        if sent:
            answer_lines.append(f"  • {sent}")
    
    # Personalize with user memory
    if memories:
        answer_lines.append("\n📌 **Personalized for you:**")
        for m in memories[:2]:
            if m.get("key") and m.get("value"):
                key_name = m['key'].replace('_', ' ').title()
                answer_lines.append(f"  • {key_name}: {m['value']}")
    
    # Context-aware next steps
    answer_lines.append("\n**Recommended actions:**")
    
    if any(w in q_lower for w in ["price", "cost", "plan", "fee", "billing"]):
        answer_lines.append("  ✨ Review pricing tiers above")
        answer_lines.append("  💬 Ask about custom discounts for your volume")
        answer_lines.append("  📅 Book a demo for a personalized quote")
    elif any(w in q_lower for w in ["feature", "capability", "include", "offer"]):
        answer_lines.append("  📚 Explore related features")
        answer_lines.append("  🎥 Watch our product demo")
        answer_lines.append("  💬 Ask follow-up questions")
    elif any(w in q_lower for w in ["integrate", "api", "connect", "sync"]):
        answer_lines.append("  🔌 Check integration documentation")
        answer_lines.append("  💻 View code examples & APIs")
        answer_lines.append("  📞 Connect with our integration team")
    elif any(w in q_lower for w in ["support", "help", "issue", "problem"]):
        answer_lines.append("  🆘 Open a support ticket")
        answer_lines.append("  📖 Search our help center")
        answer_lines.append("  💬 Chat with support team")
    else:
        answer_lines.append("  📖 Read full documentation")
        answer_lines.append("  💬 Ask follow-up questions")
        answer_lines.append("  👥 Connect with our team")
    
    # Source attribution
    sources = set(c.get("document", "Unknown") for c in context if c.get("document"))
    if sources:
        sources_str = ", ".join(sorted(sources)[:2])
        answer_lines.append(f"\n_Source: {sources_str}_")
    
    return "\n".join(answer_lines)


def call_llm(question: str, context: list[dict], memories: list[dict]) -> str:
    """Call an external LLM (OpenAI-compatible) if configured via OPENAI_API_KEY.
    Returns the model's answer as text. Raises on HTTP/API errors.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    # Build a chat-style prompt with retrieved context and short memory hints
    system_prompt = (
        "You are a helpful, concise business assistant. Use the provided documents and user memory to answer. "
        "If information is missing, be candid and ask for clarifying details."
    )

    context_text = "\n\n".join([f"Source: {c['document']}\n{c['content']}" for c in (context or [])])
    memory_text = "\n".join([f"{m.get('key')}: {m.get('value')}" for m in (memories or [])])

    user_prompt = """
    Question:
    {question}

    Retrieved documents:
    {context_text}

    User memory:
    {memory_text}

    Provide a clear, actionable answer and cite sources where relevant.
    """.format(question=question, context_text=context_text or "(none)", memory_text=memory_text or "(none)")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.6")),
        "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "800")),
    }

    url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1/chat/completions")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Extract assistant content from the first choice
    if "choices" in data and len(data["choices"]) > 0:
        content = data["choices"][0]["message"].get("content")
        return content or ""
    # Fallback
    return ""


def call_hf_llm(question: str, context: list[dict], memories: list[dict]) -> str:
    """Call Hugging Face Inference API using `HUGGINGFACE_API_KEY`.
    Returns the generated text or raises on errors.
    """
    api_key = os.getenv("HUGGINGFACE_API_KEY")
    if not api_key:
        raise RuntimeError("HUGGINGFACE_API_KEY not set")

    model = os.getenv("HUGGINGFACE_MODEL", "google/flan-t5-large")
    url = f"https://api-inference.huggingface.co/models/{model}"

    context_text = "\n\n".join([f"Source: {c['document']}\n{c['content']}" for c in (context or [])])
    memory_text = "\n".join([f"{m.get('key')}: {m.get('value')}" for m in (memories or [])])

    prompt = (
        f"Question:\n{question}\n\nRetrieved documents:\n{context_text or '(none)'}\n\n"
        f"User memory:\n{memory_text or '(none)'}\n\nProvide a clear, actionable answer and cite sources where relevant."
    )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": int(os.getenv("HUGGINGFACE_MAX_TOKENS", "300")), "temperature": float(os.getenv("HUGGINGFACE_TEMPERATURE", "0.6"))}}

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Many HF text-generation models return a list of dicts with 'generated_text'
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        if "generated_text" in data[0]:
            return data[0]["generated_text"]
        # some models return [{'text': ...}]
        if "text" in data[0]:
            return data[0]["text"]
    # Some model endpoints return a plain string
    if isinstance(data, str):
        return data
    # Fallback: stringify the JSON
    return json.dumps(data)


def run_agents(question: str, context: list[dict], memories: list[dict], conversation_id: int | None) -> AgentResult:
    trace_id = str(uuid.uuid4())
    t0 = time.perf_counter()
    has_context = bool(context)
    plan = "Use retrieved business documents, conversation memory, and lead intent checks."
    if not has_context:
        plan += " No strong document match found, so keep answer cautious and ask for source material."

    t_plan_ms = int((time.perf_counter() - t0) * 1000)
    execute(
        "INSERT INTO agent_logs (conversation_id, agent, decision, latency_ms, meta) VALUES (?, ?, ?, ?, ?)",
        (
            conversation_id,
            "Planner",
            plan,
            t_plan_ms,
            json.dumps(
                {
                    "trace_id": trace_id,
                    "phase": "planner",
                    "has_context": has_context,
                    "retrieval_chunks": len(context or []),
                }
            ),
        ),
    )

    # If an external LLM is configured, prefer it for live, real answers.
    force = str(os.getenv("FORCE_LLM", "false")).lower() in ("1", "true", "yes")
    answer = ""
    used_llm = False
    t_exec0 = time.perf_counter()
    try:
        if os.getenv("HUGGINGFACE_API_KEY") and (force or has_context):
            answer = call_hf_llm(question, context, memories)
            used_llm = bool(answer)
        elif os.getenv("OPENAI_API_KEY") and (force or has_context):
            answer = call_llm(question, context, memories)
            used_llm = bool(answer)
    except Exception:
        answer = ""

    if not answer:
        answer = synthesize_answer(question, context, memories)

    t_exec_ms = int((time.perf_counter() - t_exec0) * 1000)
    execute(
        "INSERT INTO agent_logs (conversation_id, agent, decision, latency_ms, meta) VALUES (?, ?, ?, ?, ?)",
        (
            conversation_id,
            "Executor",
            answer,
            t_exec_ms,
            json.dumps(
                {
                    "trace_id": trace_id,
                    "phase": "executor",
                    "llm": used_llm,
                    "answer_chars": len(answer or ""),
                }
            ),
        ),
    )

    validation = "Grounded in retrieved chunks." if has_context else "Answered with a local business heuristic because no retrieval match or LLM response was available."
    t_val0 = time.perf_counter()
    confidence = 0.85 if has_context and used_llm else (0.75 if has_context else 0.45)
    validation_meta = json.dumps(
        {
            "trace_id": trace_id,
            "phase": "validator",
            "confidence": confidence,
            "monitoring": "trace_export_v1",
        }
    )
    execute(
        "INSERT INTO agent_logs (conversation_id, agent, decision, latency_ms, meta) VALUES (?, ?, ?, ?, ?)",
        (conversation_id, "Validator", validation, int((time.perf_counter() - t_val0) * 1000), validation_meta),
    )
    return AgentResult(plan=plan, answer=answer, validation=validation)
