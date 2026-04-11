#!/usr/bin/env python3
"""
Index ComfyUI Documentation to Qdrant

Downloads llms-full.txt from docs.comfy.org (pre-rendered text),
chunks by markdown sections, generates embeddings via LiteLLM,
and stores in Qdrant for semantic search.

Usage:
    python3 scripts/index-comfyui-docs.py [--dry-run] [--test-search "query"]

Requirements (already in .venv):
    pip install qdrant-client requests openai
"""

import os
import sys
import json
import hashlib
import argparse
import re
from typing import List, Dict
from datetime import datetime

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from openai import OpenAI

# --- Configuration ---
QDRANT_URL = os.getenv("QDRANT_URL", "https://qd.ewutelo.cloud")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "https://llm.ewutelo.cloud/v1")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY")
EMBEDDING_MODEL = "embedding"
EMBEDDING_DIMENSIONS = 1536
COLLECTION_NAME = "comfyui-docs"

# Source: llms-full.txt is a pre-rendered text dump of all docs
LLMS_FULL_URL = "https://docs.comfy.org/llms-full.txt"
LLMS_INDEX_URL = "https://docs.comfy.org/llms.txt"

HEADERS = {
    "User-Agent": "ComfyUIDocIndexer/1.0 (VPAI Knowledge Graph Bot)"
}


def download_docs() -> str:
    """Download llms-full.txt from docs.comfy.org."""
    print(f"Downloading {LLMS_FULL_URL}...")
    resp = requests.get(LLMS_FULL_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    text = resp.text
    print(f"  Downloaded {len(text):,} chars")
    return text


def parse_llms_index() -> Dict[str, str]:
    """Parse llms.txt to map section titles to URLs."""
    print(f"Downloading {LLMS_INDEX_URL}...")
    resp = requests.get(LLMS_INDEX_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    # llms.txt format: lines like "- [Title](url): description"
    url_map = {}
    for line in resp.text.split("\n"):
        match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", line)
        if match:
            title = match.group(1).strip()
            url = match.group(2).strip()
            if not url.startswith("http"):
                url = f"https://docs.comfy.org{url}"
            url_map[title] = url

    print(f"  Parsed {len(url_map)} URL mappings from index")
    return url_map


def chunk_llms_full(text: str, url_map: Dict[str, str]) -> List[Dict]:
    """Split llms-full.txt into chunks by markdown sections.

    The file uses # and ## headers to separate pages/sections.
    We split on # (page-level) and sub-chunk long pages.
    """
    chunks = []
    now = datetime.utcnow().isoformat()

    # Split by top-level # headers (page boundaries)
    # llms-full.txt typically has: # Title\n\nURL: ...\n\ncontent
    pages = re.split(r"\n(?=# [^#])", text)

    for page in pages:
        page = page.strip()
        if not page or len(page) < 50:
            continue

        # Extract title from first # line
        lines = page.split("\n")
        title = lines[0].lstrip("# ").strip()

        # Try to extract URL from content or map
        url = url_map.get(title, "")
        if not url:
            # Try matching with "URL: ..." line
            for line in lines[:5]:
                if line.startswith("URL:") or line.startswith("url:"):
                    url = line.split(":", 1)[1].strip()
                    break

        if not url:
            # Fuzzy match: try partial title match
            for map_title, map_url in url_map.items():
                if map_title.lower() in title.lower() or title.lower() in map_title.lower():
                    url = map_url
                    break

        if not url:
            url = "https://docs.comfy.org"

        # Determine category from URL path
        category = "general"
        if "/tutorials/" in url:
            category = "tutorials"
        elif "/custom-nodes/" in url:
            category = "custom-nodes"
        elif "/built-in-nodes/" in url:
            category = "built-in-nodes"
        elif "/development/" in url:
            category = "development"
        elif "/api-reference/" in url:
            category = "api-reference"
        elif "/interface/" in url:
            category = "interface"
        elif "/installation/" in url:
            category = "installation"
        elif "/registry/" in url:
            category = "registry"
        elif "/manager/" in url:
            category = "manager"
        elif "/troubleshooting/" in url:
            category = "troubleshooting"
        elif "/comfy-cli/" in url:
            category = "cli"
        elif "/specs/" in url:
            category = "specs"

        # Sub-chunk by ## sections within the page
        sections = re.split(r"\n(?=## )", page)

        for si, section in enumerate(sections):
            section = section.strip()
            if len(section) < 50:
                continue

            # Get section subtitle
            section_lines = section.split("\n")
            if section_lines[0].startswith("## "):
                subtitle = section_lines[0].lstrip("# ").strip()
                section_title = f"{title} > {subtitle}"
            else:
                section_title = title
                subtitle = ""

            # Further split if section is too long (>1500 chars)
            if len(section) > 1500:
                sub_chunks = split_at_boundary(section, 1200, 200)
            else:
                sub_chunks = [section]

            for ci, chunk_text in enumerate(sub_chunks):
                chunk_text = chunk_text.strip()
                if len(chunk_text) < 50:
                    continue

                chunk_id = hashlib.md5(
                    f"{url}::{si}::{ci}".encode()
                ).hexdigest()

                chunks.append({
                    "id": chunk_id,
                    "url": url,
                    "title": section_title,
                    "category": category,
                    "chunk_index": ci,
                    "total_chunks": len(sub_chunks),
                    "text": chunk_text,
                    "scraped_at": now,
                })

    print(f"Created {len(chunks)} chunks from {len(pages)} pages")
    return chunks


def split_at_boundary(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks at sentence/line boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        if end < len(text):
            last_period = chunk.rfind(". ")
            last_newline = chunk.rfind("\n")
            break_point = max(last_period, last_newline)

            if break_point > chunk_size // 2:
                chunk = chunk[:break_point + 1]
                end = start + break_point + 1

        stripped = chunk.strip()
        if len(stripped) > 50:
            chunks.append(stripped)
        start = end - overlap

    return chunks


class QdrantIndexer:
    """Index chunks into Qdrant with embeddings from LiteLLM."""

    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str,
        litellm_url: str,
        litellm_key: str,
        collection_name: str,
    ):
        # Use host/port/https for Qdrant behind Caddy reverse proxy
        from urllib.parse import urlparse as _urlparse
        _parsed = _urlparse(qdrant_url)
        _host = _parsed.hostname or qdrant_url
        _port = _parsed.port or (443 if _parsed.scheme == "https" else 6333)
        _https = _parsed.scheme == "https"
        self.qdrant = QdrantClient(
            host=_host, port=_port, api_key=qdrant_api_key, https=_https,
        )
        self.openai_client = OpenAI(base_url=litellm_url, api_key=litellm_key)
        self.collection_name = collection_name

    def ensure_collection(self):
        """Create collection if not exists."""
        collections = self.qdrant.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            print(f"Creating collection: {self.collection_name}")
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSIONS,
                    distance=Distance.COSINE,
                ),
            )
        else:
            print(f"Collection exists: {self.collection_name}")

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding via LiteLLM proxy."""
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text[:8000],
        )
        return response.data[0].embedding

    def index_chunks(self, chunks: List[Dict], batch_size: int = 10):
        """Index all chunks with embeddings into Qdrant."""
        self.ensure_collection()

        points = []
        errors = 0

        for i, chunk in enumerate(chunks):
            print(
                f"  [{i+1}/{len(chunks)}] {chunk['title'][:50]}... ",
                end="",
                flush=True,
            )

            try:
                embedding = self.generate_embedding(chunk["text"])
            except Exception as e:
                print(f"FAIL: {e}")
                errors += 1
                continue

            point = PointStruct(
                id=chunk["id"],
                vector=embedding,
                payload={
                    "url": chunk["url"],
                    "title": chunk["title"],
                    "category": chunk["category"],
                    "text": chunk["text"],
                    "chunk_index": chunk["chunk_index"],
                    "total_chunks": chunk["total_chunks"],
                    "scraped_at": chunk["scraped_at"],
                    "source": "comfyui_docs",
                },
            )
            points.append(point)
            print("OK")

            # Upload in batches
            if len(points) >= batch_size:
                self.qdrant.upsert(
                    collection_name=self.collection_name,
                    points=points,
                )
                print(f"  -> Uploaded batch of {len(points)} points")
                points = []

        # Upload remaining
        if points:
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            print(f"  -> Uploaded final batch of {len(points)} points")

        indexed = len(chunks) - errors
        print(f"\nIndexed {indexed}/{len(chunks)} chunks to '{self.collection_name}'")
        if errors:
            print(f"  ({errors} embedding errors)")

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Test semantic search."""
        print(f"\nSearching: {query}")
        query_embedding = self.generate_embedding(query)

        results = self.qdrant.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=limit,
        )

        return [
            {
                "score": hit.score,
                "title": hit.payload["title"],
                "url": hit.payload["url"],
                "category": hit.payload.get("category", ""),
                "text": hit.payload["text"][:200] + "...",
            }
            for hit in results
        ]


def main():
    parser = argparse.ArgumentParser(description="Index ComfyUI docs to Qdrant")
    parser.add_argument("--dry-run", action="store_true", help="Download and chunk only")
    parser.add_argument("--test-search", type=str, help="Test search query after indexing")
    parser.add_argument(
        "--collection", type=str, default=COLLECTION_NAME, help="Qdrant collection name"
    )
    args = parser.parse_args()

    # Validate environment
    if not args.dry_run:
        if not QDRANT_API_KEY:
            print("Error: QDRANT_API_KEY not set")
            sys.exit(1)
        if not LITELLM_API_KEY:
            print("Error: LITELLM_API_KEY not set")
            sys.exit(1)

    print("=== ComfyUI Documentation Indexer ===")
    print(f"Source:     {LLMS_FULL_URL}")
    print(f"Collection: {args.collection}")
    print(f"Embedding:  {EMBEDDING_MODEL}\n")

    # Step 1: Download docs
    full_text = download_docs()
    url_map = parse_llms_index()

    # Save raw download
    with open("/tmp/comfyui_llms_full.txt", "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"Saved raw text to /tmp/comfyui_llms_full.txt")

    # Step 2: Chunk
    chunks = chunk_llms_full(full_text, url_map)

    with open("/tmp/comfyui_docs_chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"Saved chunks to /tmp/comfyui_docs_chunks.json")

    if args.dry_run:
        print("\nDry run complete. No indexing.")
        if chunks:
            # Show stats
            categories = {}
            for c in chunks:
                categories[c["category"]] = categories.get(c["category"], 0) + 1
            print(f"\nChunks by category:")
            for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
                print(f"  {cat}: {count}")
            print(f"\nSample chunk:")
            print(f"  Title: {chunks[0]['title']}")
            print(f"  URL:   {chunks[0]['url']}")
            print(f"  Cat:   {chunks[0]['category']}")
            print(f"  Text:  {chunks[0]['text'][:200]}...")
        return

    # Step 3: Index to Qdrant
    indexer = QdrantIndexer(
        qdrant_url=QDRANT_URL,
        qdrant_api_key=QDRANT_API_KEY,
        litellm_url=LITELLM_BASE_URL,
        litellm_key=LITELLM_API_KEY,
        collection_name=args.collection,
    )

    indexer.index_chunks(chunks, batch_size=10)

    # Step 4: Test search
    if args.test_search:
        results = indexer.search(args.test_search, limit=5)
        print("\nSearch Results:")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. [{result['score']:.3f}] {result['title']}")
            print(f"   {result['url']}")
            print(f"   {result['text']}")

    print("\nDone!")


if __name__ == "__main__":
    main()
