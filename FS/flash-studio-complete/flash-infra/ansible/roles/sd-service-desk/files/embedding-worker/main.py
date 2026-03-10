"""Embedding Worker — Ingestion continue vers Qdrant + Typesense.

Recoit des webhooks de Discourse (nouveau post) et Zammad (ticket resolu),
chunk le contenu, genere des embeddings via LiteLLM, et upsert dans Qdrant.
Indexe aussi dans Typesense pour la recherche instantanee.
"""
import hashlib
import json
import logging
import os
from typing import Optional

import httpx
import redis.asyncio as redis
import tiktoken
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("embedding-worker")

app = FastAPI(title="Embedding Worker", version="1.0.0")

# --- Config ---
QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
TYPESENSE_URL = os.environ.get("TYPESENSE_URL", "")
TYPESENSE_API_KEY = os.environ.get("TYPESENSE_API_KEY", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/2")
LITELLM_URL = os.environ["LITELLM_URL"]
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "64"))

COLLECTIONS = ["docs", "tickets", "runbooks"]
EMBEDDING_DIM = 1536  # text-embedding-3-small dimension

# --- Clients ---
qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
redis_client: Optional[redis.Redis] = None
tokenizer = tiktoken.get_encoding("cl100k_base")


class IngestRequest(BaseModel):
    collection: str  # docs, tickets, runbooks
    source_id: str
    title: str
    content: str
    metadata: dict = {}


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def chunk_text(text: str, max_tokens: int, overlap: int) -> list[str]:
    tokens = tokenizer.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(tokenizer.decode(chunk_tokens))
        if end >= len(tokens):
            break
        start = end - overlap
    return chunks


async def get_embedding(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{LITELLM_URL}/embeddings",
            headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
            json={"model": EMBEDDING_MODEL, "input": text},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


async def index_typesense(collection: str, doc_id: str, title: str, content: str):
    if not TYPESENSE_URL:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{TYPESENSE_URL}/collections/{collection}/documents",
            headers={"X-TYPESENSE-API-KEY": TYPESENSE_API_KEY},
            json={"id": doc_id, "title": title, "content": content},
            params={"action": "upsert"},
        )


@app.on_event("startup")
async def startup():
    global redis_client
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

    for collection in COLLECTIONS:
        try:
            qdrant.get_collection(collection)
        except Exception:
            qdrant.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM, distance=Distance.COSINE
                ),
            )
            logger.info(f"Created Qdrant collection: {collection}")

    if TYPESENSE_URL:
        async with httpx.AsyncClient(timeout=10) as client:
            for col in COLLECTIONS:
                try:
                    await client.get(
                        f"{TYPESENSE_URL}/collections/{col}",
                        headers={"X-TYPESENSE-API-KEY": TYPESENSE_API_KEY},
                    )
                except Exception:
                    await client.post(
                        f"{TYPESENSE_URL}/collections",
                        headers={"X-TYPESENSE-API-KEY": TYPESENSE_API_KEY},
                        json={
                            "name": col,
                            "fields": [
                                {"name": "title", "type": "string"},
                                {"name": "content", "type": "string"},
                            ],
                        },
                    )
                    logger.info(f"Created Typesense collection: {col}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(req: IngestRequest):
    if req.collection not in COLLECTIONS:
        raise HTTPException(400, f"Unknown collection: {req.collection}")

    c_hash = content_hash(req.content)

    # Idempotency check via Redis
    cache_key = f"embed:{req.collection}:{req.source_id}"
    cached = await redis_client.get(cache_key)
    if cached == c_hash:
        return {"status": "skipped", "reason": "content unchanged"}

    chunks = chunk_text(req.content, CHUNK_SIZE, CHUNK_OVERLAP)
    points = []

    for i, chunk in enumerate(chunks):
        embedding = await get_embedding(chunk)
        point_id = f"{req.source_id}-{i}"
        points.append(
            PointStruct(
                id=abs(hash(point_id)) % (2**63),
                vector=embedding,
                payload={
                    "source_id": req.source_id,
                    "chunk_index": i,
                    "title": req.title,
                    "content": chunk,
                    "content_hash": c_hash,
                    "relevance_score": 1.0,
                    **req.metadata,
                },
            )
        )

    qdrant.upsert(collection_name=req.collection, points=points)

    await index_typesense(req.collection, req.source_id, req.title, req.content)

    await redis_client.set(cache_key, c_hash, ex=86400 * 30)

    logger.info(
        f"Ingested {len(chunks)} chunks for {req.collection}/{req.source_id}"
    )
    return {"status": "ingested", "chunks": len(chunks)}


@app.post("/webhook/discourse")
async def webhook_discourse(request: Request):
    body = await request.json()
    post = body.get("post", {})
    if not post:
        return {"status": "ignored"}

    await ingest(
        IngestRequest(
            collection="docs",
            source_id=f"discourse-{post.get('id', '')}",
            title=post.get("topic_title", ""),
            content=post.get("raw", ""),
            metadata={
                "source": "discourse",
                "category": post.get("category_slug", ""),
                "author": post.get("username", ""),
            },
        )
    )
    return {"status": "ok"}


@app.post("/webhook/zammad")
async def webhook_zammad(request: Request):
    body = await request.json()
    ticket = body.get("ticket", {})
    article = body.get("article", {})
    if not ticket or ticket.get("state", {}).get("name") != "closed":
        return {"status": "ignored"}

    content = f"Question: {ticket.get('title', '')}\n\nAnswer: {article.get('body', '')}"
    await ingest(
        IngestRequest(
            collection="tickets",
            source_id=f"zammad-{ticket.get('id', '')}",
            title=ticket.get("title", ""),
            content=content,
            metadata={
                "source": "zammad",
                "group": ticket.get("group", {}).get("name", ""),
                "priority": ticket.get("priority", {}).get("name", ""),
            },
        )
    )
    return {"status": "ok"}
