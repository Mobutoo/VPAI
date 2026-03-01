#!/usr/bin/env python3
"""
Index Plane Documentation to Qdrant

Scrape docs.plane.so and developers.plane.so, chunk content, generate embeddings,
and store in Qdrant for semantic search by OpenClaw agents.

Usage:
    python3 scripts/index-plane-docs.py [--dry-run] [--verbose]

Requirements:
    pip install qdrant-client requests beautifulsoup4 openai python-dotenv
"""

import os
import sys
import json
import hashlib
import argparse
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from openai import OpenAI

# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "https://qd.ewutelo.cloud")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "https://llm.ewutelo.cloud/v1")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
COLLECTION_NAME = "plane_docs"

# Documentation URLs to scrape
DOC_ROOTS = [
    "https://docs.plane.so/",
    "https://developers.plane.so/",
]

# User agent
HEADERS = {
    "User-Agent": "PlaneDocIndexer/1.0 (VPAI Knowledge Graph Bot)"
}


class PlaneDocsScraper:
    """Scrape Plane documentation websites."""

    def __init__(self, base_urls: List[str], max_pages: int = 200):
        self.base_urls = base_urls
        self.max_pages = max_pages
        self.visited = set()
        self.pages = []
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def is_valid_doc_url(self, url: str) -> bool:
        """Check if URL belongs to documentation domains."""
        parsed = urlparse(url)
        return any(
            parsed.netloc == urlparse(base).netloc
            for base in self.base_urls
        )

    def scrape_page(self, url: str) -> Optional[Dict]:
        """Scrape a single page and extract content."""
        if url in self.visited or len(self.visited) >= self.max_pages:
            return None

        self.visited.add(url)
        print(f"📄 Scraping: {url}")

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ Error fetching {url}: {e}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract main content (adjust selectors based on actual site structure)
        # Common doc site patterns: article, main, .content, .documentation
        main_content = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_="content")
            or soup.find(class_="documentation")
            or soup.find("body")
        )

        if not main_content:
            print(f"⚠️  No main content found on {url}")
            return None

        # Remove navigation, footer, sidebar, code blocks (preserve text)
        for tag in main_content.find_all(["nav", "footer", "aside", "script", "style"]):
            tag.decompose()

        # Extract text
        text = main_content.get_text(separator="\n", strip=True)

        # Extract title
        title = (
            soup.find("h1").get_text(strip=True) if soup.find("h1")
            else soup.title.string if soup.title
            else url.split("/")[-1]
        )

        # Extract links for crawling
        links = []
        for link in main_content.find_all("a", href=True):
            absolute_url = urljoin(url, link["href"])
            if self.is_valid_doc_url(absolute_url) and "#" not in absolute_url:
                links.append(absolute_url)

        return {
            "url": url,
            "title": title,
            "text": text,
            "links": links,
            "scraped_at": datetime.utcnow().isoformat(),
        }

    def scrape_all(self) -> List[Dict]:
        """Scrape all documentation pages (BFS crawl)."""
        queue = list(self.base_urls)

        while queue and len(self.visited) < self.max_pages:
            url = queue.pop(0)

            if url in self.visited:
                continue

            page_data = self.scrape_page(url)
            if page_data:
                self.pages.append(page_data)
                # Add discovered links to queue
                for link in page_data["links"]:
                    if link not in self.visited:
                        queue.append(link)

        print(f"\n✅ Scraped {len(self.pages)} pages")
        return self.pages


class DocumentChunker:
    """Chunk documents into semantic segments."""

    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind(". ")
                last_newline = chunk.rfind("\n")
                break_point = max(last_period, last_newline)

                if break_point > self.chunk_size // 2:
                    chunk = chunk[:break_point + 1]
                    end = start + break_point + 1

            chunks.append(chunk.strip())
            start = end - self.overlap

        return chunks

    def chunk_pages(self, pages: List[Dict]) -> List[Dict]:
        """Chunk all pages into segments."""
        chunks = []

        for page in pages:
            text_chunks = self.chunk_text(page["text"])

            for i, chunk_text in enumerate(text_chunks):
                chunk_id = hashlib.md5(
                    f"{page['url']}::{i}".encode()
                ).hexdigest()

                chunks.append({
                    "id": chunk_id,
                    "url": page["url"],
                    "title": page["title"],
                    "chunk_index": i,
                    "total_chunks": len(text_chunks),
                    "text": chunk_text,
                    "scraped_at": page["scraped_at"],
                })

        print(f"📦 Created {len(chunks)} chunks from {len(pages)} pages")
        return chunks


class QdrantIndexer:
    """Index chunks into Qdrant with embeddings."""

    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str,
        litellm_url: str,
        litellm_key: str,
        collection_name: str,
    ):
        self.qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        self.openai_client = OpenAI(base_url=litellm_url, api_key=litellm_key)
        self.collection_name = collection_name

    def ensure_collection(self):
        """Create Qdrant collection if not exists."""
        collections = self.qdrant.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            print(f"🆕 Creating collection: {self.collection_name}")
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSIONS,
                    distance=Distance.COSINE,
                ),
            )
        else:
            print(f"✅ Collection exists: {self.collection_name}")

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding via LiteLLM (OpenAI-compatible endpoint)."""
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding

    def index_chunks(self, chunks: List[Dict], batch_size: int = 10):
        """Index chunks with embeddings to Qdrant."""
        self.ensure_collection()

        points = []
        for i, chunk in enumerate(chunks):
            print(f"🔢 Embedding chunk {i+1}/{len(chunks)}: {chunk['title'][:50]}...")

            try:
                embedding = self.generate_embedding(chunk["text"])
            except Exception as e:
                print(f"❌ Error embedding chunk {chunk['id']}: {e}")
                continue

            point = PointStruct(
                id=chunk["id"],
                vector=embedding,
                payload={
                    "url": chunk["url"],
                    "title": chunk["title"],
                    "text": chunk["text"],
                    "chunk_index": chunk["chunk_index"],
                    "total_chunks": chunk["total_chunks"],
                    "scraped_at": chunk["scraped_at"],
                    "source": "plane_docs",
                },
            )
            points.append(point)

            # Upload in batches
            if len(points) >= batch_size:
                self.qdrant.upsert(
                    collection_name=self.collection_name,
                    points=points,
                )
                print(f"✅ Uploaded batch of {len(points)} points")
                points = []

        # Upload remaining points
        if points:
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            print(f"✅ Uploaded final batch of {len(points)} points")

        print(f"\n🎉 Indexed {len(chunks)} chunks to Qdrant collection '{self.collection_name}'")

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Test semantic search."""
        print(f"\n🔍 Searching: {query}")
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
                "text": hit.payload["text"][:200] + "...",
            }
            for hit in results
        ]


def main():
    parser = argparse.ArgumentParser(description="Index Plane docs to Qdrant")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't index")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--max-pages", type=int, default=200, help="Max pages to scrape")
    parser.add_argument("--test-search", type=str, help="Test search query after indexing")
    args = parser.parse_args()

    # Validate environment
    if not QDRANT_API_KEY:
        print("❌ Error: QDRANT_API_KEY not set")
        sys.exit(1)
    if not LITELLM_API_KEY:
        print("❌ Error: LITELLM_API_KEY not set")
        sys.exit(1)

    print("🚀 Plane Documentation Indexer")
    print(f"📚 Scraping: {', '.join(DOC_ROOTS)}")
    print(f"🎯 Target collection: {COLLECTION_NAME}")
    print(f"🔢 Embedding model: {EMBEDDING_MODEL}\n")

    # Step 1: Scrape documentation
    scraper = PlaneDocsScraper(base_urls=DOC_ROOTS, max_pages=args.max_pages)
    pages = scraper.scrape_all()

    if not pages:
        print("❌ No pages scraped. Exiting.")
        sys.exit(1)

    # Save scraped pages (for debugging)
    with open("/tmp/plane_docs_scraped.json", "w") as f:
        json.dump(pages, f, indent=2)
    print(f"💾 Saved scraped pages to /tmp/plane_docs_scraped.json")

    # Step 2: Chunk documents
    chunker = DocumentChunker(chunk_size=1000, overlap=200)
    chunks = chunker.chunk_pages(pages)

    # Save chunks (for debugging)
    with open("/tmp/plane_docs_chunks.json", "w") as f:
        json.dump(chunks, f, indent=2)
    print(f"💾 Saved chunks to /tmp/plane_docs_chunks.json")

    if args.dry_run:
        print("\n🏁 Dry run complete. Exiting without indexing.")
        return

    # Step 3: Index to Qdrant
    indexer = QdrantIndexer(
        qdrant_url=QDRANT_URL,
        qdrant_api_key=QDRANT_API_KEY,
        litellm_url=LITELLM_BASE_URL,
        litellm_key=LITELLM_API_KEY,
        collection_name=COLLECTION_NAME,
    )

    indexer.index_chunks(chunks, batch_size=10)

    # Step 4: Test search
    if args.test_search:
        results = indexer.search(args.test_search, limit=5)
        print("\n📊 Search Results:")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. [{result['score']:.3f}] {result['title']}")
            print(f"   {result['url']}")
            print(f"   {result['text']}")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
