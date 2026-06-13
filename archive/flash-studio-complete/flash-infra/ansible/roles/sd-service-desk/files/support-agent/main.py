"""Support Agent RAG — Draft reponses automatiques pour tickets Zammad.

Pipeline :
1. Embed la question du ticket
2. Qdrant -> top-20 chunks (docs + tickets similaires)
3. Reranker -> top-3 pertinents
4. LLM (claude-sonnet via LiteLLM) -> draft reponse
5. Confiance > 90% -> post reponse + close
6. Confiance 50-90% -> note interne (agent humain valide)
7. Confiance < 50% -> escalade directe
"""
import json
import logging
import os

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, Request
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Filter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("support-agent")

app = FastAPI(title="Support Agent RAG", version="1.0.0")

QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
RERANKER_URL = os.environ["RERANKER_URL"]
ZAMMAD_URL = os.environ["ZAMMAD_URL"]
ZAMMAD_API_TOKEN = os.environ.get("ZAMMAD_API_TOKEN", "")
LITELLM_URL = os.environ["LITELLM_URL"]
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/2")
CONFIDENCE_AUTO_CLOSE = float(os.environ.get("CONFIDENCE_AUTO_CLOSE", "0.9"))
CONFIDENCE_DRAFT = float(os.environ.get("CONFIDENCE_DRAFT", "0.5"))

qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
redis_client = None


class TicketEvent(BaseModel):
    ticket_id: int
    title: str
    body: str
    customer_email: str = ""


@app.on_event("startup")
async def startup():
    global redis_client
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Support agent started")


@app.get("/health")
async def health():
    return {"status": "ok", "model": LLM_MODEL}


async def get_embedding(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{LITELLM_URL}/embeddings",
            headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
            json={"model": "text-embedding-3-small", "input": text},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


async def search_qdrant(query_embedding: list[float], collections: list[str], limit: int = 20):
    all_results = []
    for col in collections:
        try:
            results = qdrant.search(
                collection_name=col,
                query_vector=query_embedding,
                limit=limit,
            )
            for r in results:
                all_results.append({
                    "content": r.payload.get("content", ""),
                    "title": r.payload.get("title", ""),
                    "source": col,
                    "score": r.score,
                    "relevance_score": r.payload.get("relevance_score", 1.0),
                })
        except Exception as e:
            logger.warning(f"Search failed for {col}: {e}")
    # Weight by relevance_score (feedback loop)
    all_results.sort(
        key=lambda x: x["score"] * x["relevance_score"], reverse=True
    )
    return all_results[:limit]


async def rerank(query: str, documents: list[str], top_k: int = 3):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{RERANKER_URL}/rerank",
            json={"query": query, "documents": documents, "top_k": top_k},
        )
        resp.raise_for_status()
        return resp.json()


async def generate_response(question: str, context_docs: list[dict]) -> dict:
    context = "\n\n---\n\n".join(
        [f"[{d.get('source', 'unknown')}] {d.get('title', '')}\n{d.get('document', d.get('content', ''))}" for d in context_docs]
    )

    prompt = f"""You are a Flash Studio support agent. Answer the customer's question based ONLY on the provided context.
If the context doesn't contain enough information, say so honestly.
Rate your confidence from 0.0 to 1.0 based on how well the context answers the question.

Context:
{context}

Customer question: {question}

Respond in JSON format:
{{"answer": "your answer here", "confidence": 0.85, "sources_used": ["source1", "source2"]}}"""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{LITELLM_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2000,
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except (json.JSONDecodeError, IndexError):
        return {"answer": content, "confidence": 0.3, "sources_used": []}


async def post_zammad_note(ticket_id: int, content: str, internal: bool = True):
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"{ZAMMAD_URL}/api/v1/ticket_articles",
            headers={
                "Authorization": f"Bearer {ZAMMAD_API_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "ticket_id": ticket_id,
                "body": content,
                "content_type": "text/html",
                "type": "note",
                "internal": internal,
            },
        )


async def update_zammad_ticket_state(ticket_id: int, state: str):
    async with httpx.AsyncClient(timeout=15) as client:
        await client.put(
            f"{ZAMMAD_URL}/api/v1/tickets/{ticket_id}",
            headers={
                "Authorization": f"Bearer {ZAMMAD_API_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"state": state},
        )


@app.post("/process-ticket")
async def process_ticket(event: TicketEvent):
    question = f"{event.title}\n{event.body}"

    # 1. Embed
    embedding = await get_embedding(question)

    # 2. Search Qdrant
    results = await search_qdrant(embedding, ["docs", "tickets", "runbooks"])
    if not results:
        return {"status": "no_context", "action": "escalate"}

    # 3. Rerank
    documents = [r["content"] for r in results]
    reranked = await rerank(question, documents, top_k=3)

    # 4. Generate response
    response = await generate_response(question, reranked)
    confidence = response.get("confidence", 0.0)
    answer = response.get("answer", "")

    # 5. Route based on confidence
    if confidence >= CONFIDENCE_AUTO_CLOSE:
        await post_zammad_note(event.ticket_id, answer, internal=False)
        await update_zammad_ticket_state(event.ticket_id, "closed")
        action = "auto_closed"
    elif confidence >= CONFIDENCE_DRAFT:
        draft_note = f"<strong>[AI Draft — Confidence: {confidence:.0%}]</strong><br><br>{answer}"
        await post_zammad_note(event.ticket_id, draft_note, internal=True)
        action = "draft_posted"
    else:
        escalation_note = f"<strong>[AI Escalation — Confidence: {confidence:.0%}]</strong><br>Unable to generate a confident response. Human review required."
        await post_zammad_note(event.ticket_id, escalation_note, internal=True)
        action = "escalated"

    logger.info(f"Ticket {event.ticket_id}: {action} (confidence={confidence:.2f})")
    return {"status": "processed", "action": action, "confidence": confidence}


@app.post("/webhook/zammad")
async def webhook_zammad(request: Request):
    body = await request.json()
    ticket = body.get("ticket", {})
    article = body.get("article", {})

    if not ticket or not article:
        return {"status": "ignored"}

    state = ticket.get("state", {}).get("name", "")
    if state not in ("new", "open"):
        return {"status": "ignored", "reason": f"state={state}"}

    event = TicketEvent(
        ticket_id=ticket["id"],
        title=ticket.get("title", ""),
        body=article.get("body", ""),
        customer_email=ticket.get("customer", {}).get("email", ""),
    )

    return await process_ticket(event)
