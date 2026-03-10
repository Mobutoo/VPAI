"""Reranker — Cross-encoder CPU pour re-scorer les resultats Qdrant.

Modele : ms-marco-MiniLM-L-6-v2 (CPU, ~300 MB)
Ameliore la precision RAG vs simple similarite cosinus.
"""
import logging
import os

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import CrossEncoder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reranker")

MODEL_NAME = os.environ.get("MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")
MAX_BATCH_SIZE = int(os.environ.get("MAX_BATCH_SIZE", "32"))

app = FastAPI(title="Reranker", version="1.0.0")
model: CrossEncoder = None


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    top_k: int = 3


class RerankResult(BaseModel):
    index: int
    score: float
    document: str


@app.on_event("startup")
async def startup():
    global model
    logger.info(f"Loading model: {MODEL_NAME}")
    model = CrossEncoder(MODEL_NAME, max_length=512)
    logger.info("Model loaded successfully")


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME}


@app.post("/rerank", response_model=list[RerankResult])
async def rerank(req: RerankRequest):
    if not req.documents:
        return []

    pairs = [[req.query, doc] for doc in req.documents[: MAX_BATCH_SIZE]]
    scores = model.predict(pairs)

    results = [
        RerankResult(index=i, score=float(score), document=req.documents[i])
        for i, score in enumerate(scores)
    ]
    results.sort(key=lambda x: x.score, reverse=True)

    return results[: req.top_k]
