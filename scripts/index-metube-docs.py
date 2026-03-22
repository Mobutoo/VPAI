#!/usr/bin/env python3
"""Index MeTube documentation into Qdrant via LiteLLM embeddings.

Usage:
    python scripts/index-metube-docs.py

Reads docs/metube-docs-scraped.md, chunks by section (## headers),
generates embeddings via LiteLLM, and upserts into Qdrant collection 'metube-docs'.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

# --- Configuration ---
DOCS_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "metube-docs-scraped.md")
LITELLM_URL = os.environ.get("LITELLM_URL", "https://llm.ewutelo.cloud")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "https://qd.ewutelo.cloud")
QDRANT_KEY = os.environ.get("QDRANT_KEY", "")
COLLECTION = "metube-docs"
EMBEDDING_MODEL = "embedding"
VECTOR_SIZE = 1536
CHUNK_MAX_CHARS = 2000


def chunk_markdown(text: str) -> list[dict]:
    """Split markdown into chunks by ## headers, with metadata."""
    chunks = []
    current_title = "Introduction"
    current_url = ""
    current_lines = []

    for line in text.split("\n"):
        # Detect section headers
        if line.startswith("## "):
            # Save previous chunk
            if current_lines:
                content = "\n".join(current_lines).strip()
                if len(content) > 50:  # Skip tiny chunks
                    # Split oversized chunks
                    for sub in split_chunk(content, CHUNK_MAX_CHARS):
                        chunks.append({
                            "title": current_title,
                            "url": current_url,
                            "content": sub,
                        })
            current_title = line.lstrip("# ").strip()
            current_lines = []
        elif line.startswith("**Source:**") or line.startswith("Source:"):
            url_match = re.search(r"https?://[^\s)]+", line)
            if url_match:
                current_url = url_match.group(0)
        else:
            current_lines.append(line)

    # Last chunk
    if current_lines:
        content = "\n".join(current_lines).strip()
        if len(content) > 50:
            for sub in split_chunk(content, CHUNK_MAX_CHARS):
                chunks.append({
                    "title": current_title,
                    "url": current_url,
                    "content": sub,
                })

    return chunks


def split_chunk(text: str, max_chars: int) -> list[str]:
    """Split text into sub-chunks at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]
    parts = []
    current = ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 > max_chars and current:
            parts.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        parts.append(current.strip())
    return parts


def get_embedding(text: str) -> list[float]:
    """Get embedding vector from LiteLLM."""
    payload = json.dumps({
        "model": EMBEDDING_MODEL,
        "input": text[:8000],  # Truncate to avoid token limits
    }).encode()

    req = urllib.request.Request(
        f"{LITELLM_URL}/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {LITELLM_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        return data["data"][0]["embedding"]


def ensure_collection():
    """Create Qdrant collection if it doesn't exist."""
    # Check if exists
    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/{COLLECTION}",
        headers={"api-key": QDRANT_KEY},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"Collection '{COLLECTION}' exists")
        return
    except urllib.error.HTTPError:
        pass

    # Create
    payload = json.dumps({
        "vectors": {
            "size": VECTOR_SIZE,
            "distance": "Cosine",
        },
    }).encode()
    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/{COLLECTION}",
        data=payload,
        method="PUT",
        headers={
            "api-key": QDRANT_KEY,
            "Content-Type": "application/json",
        },
    )
    urllib.request.urlopen(req, timeout=15)
    print(f"Created collection '{COLLECTION}'")


def upsert_points(points: list[dict]):
    """Batch upsert points into Qdrant."""
    payload = json.dumps({"points": points}).encode()
    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/{COLLECTION}/points",
        data=payload,
        method="PUT",
        headers={
            "api-key": QDRANT_KEY,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        return data.get("status")


def main():
    if not LITELLM_KEY or not QDRANT_KEY:
        print("ERROR: Set LITELLM_KEY and QDRANT_KEY environment variables")
        sys.exit(1)

    # Read docs
    with open(DOCS_PATH) as f:
        content = f.read()
    print(f"Read {len(content)} chars from {DOCS_PATH}")

    # Chunk
    chunks = chunk_markdown(content)
    print(f"Split into {len(chunks)} chunks")

    # Create collection
    ensure_collection()

    # Embed + upsert in batches
    batch = []
    batch_size = 10
    total = len(chunks)
    errors = 0

    for i, chunk in enumerate(chunks):
        # Generate point ID from content hash
        point_id = int(hashlib.sha256(
            chunk["content"][:500].encode()
        ).hexdigest()[:15], 16)

        try:
            vector = get_embedding(
                f"{chunk['title']}: {chunk['content']}"
            )
        except Exception as e:
            print(f"  [{i+1}/{total}] ERROR embedding: {e}")
            errors += 1
            time.sleep(2)
            continue

        batch.append({
            "id": point_id,
            "vector": vector,
            "payload": {
                "title": chunk["title"],
                "url": chunk["url"],
                "content": chunk["content"][:3000],
                "source": "metube-official-docs",
            },
        })

        if len(batch) >= batch_size:
            status = upsert_points(batch)
            print(f"  [{i+1}/{total}] Upserted {len(batch)} points (status={status})")
            batch = []
            time.sleep(0.5)  # Rate limit

    # Final batch
    if batch:
        status = upsert_points(batch)
        print(f"  [{total}/{total}] Upserted {len(batch)} points (status={status})")

    print(f"\nDone: {total - errors} indexed, {errors} errors")
    print(f"Collection: {QDRANT_URL}/collections/{COLLECTION}")


if __name__ == "__main__":
    main()
