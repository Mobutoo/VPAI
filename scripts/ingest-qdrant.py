#!/usr/bin/env python3
"""Ingest REX and guideline documents into Qdrant vpai_rex collection.

Chunks markdown by ## sections, generates 1536-dim embeddings via LiteLLM,
and upserts into Qdrant with structured metadata.

Usage:
    python3 ingest-qdrant.py \
        --litellm-url http://litellm:4000 \
        --litellm-key sk-xxx \
        --qdrant-url http://qdrant:6333 \
        --qdrant-key xxx \
        --files docs/REX-SESSION-2026-03-10.md docs/GUIDE-DOCKER-SECURITY-HARDENING.md

Runs inside a Docker container on the backend network (has access to litellm and qdrant).
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.request
import urllib.error


def chunk_markdown(text: str, source_file: str) -> list[dict]:
    """Split markdown into chunks by ## sections."""
    chunks = []
    current_section = ""
    current_lines = []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_lines and current_section:
                chunk_text = "\n".join(current_lines).strip()
                if len(chunk_text) > 50:
                    chunks.append({
                        "section_title": current_section,
                        "text": chunk_text,
                    })
            current_section = line.lstrip("# ").strip()
            current_lines = [line]
        elif line.startswith("### "):
            # Sub-sections become their own chunks
            if current_lines and current_section:
                chunk_text = "\n".join(current_lines).strip()
                if len(chunk_text) > 50:
                    chunks.append({
                        "section_title": current_section,
                        "text": chunk_text,
                    })
            current_section = line.lstrip("# ").strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Last chunk
    if current_lines and current_section:
        chunk_text = "\n".join(current_lines).strip()
        if len(chunk_text) > 50:
            chunks.append({
                "section_title": current_section,
                "text": chunk_text,
            })

    return chunks


def get_embedding(text: str, litellm_url: str, litellm_key: str) -> list[float]:
    """Get 1536-dim embedding from LiteLLM proxy."""
    payload = json.dumps({
        "model": "embedding",
        "input": text[:8000],  # Truncate to fit token limit
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{litellm_url}/v1/embeddings",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {litellm_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["data"][0]["embedding"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  ERROR embedding: {e.code} — {body[:200]}", file=sys.stderr)
        raise


def upsert_point(
    point_id: int,
    vector: list[float],
    payload: dict,
    qdrant_url: str,
    qdrant_key: str,
    collection: str = "vpai_rex",
) -> None:
    """Upsert a single point into Qdrant."""
    body = json.dumps({
        "points": [{
            "id": point_id,
            "vector": vector,
            "payload": payload,
        }],
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{qdrant_url}/collections/{collection}/points?wait=true",
        data=body,
        method="PUT",
        headers={
            "Content-Type": "application/json",
            "api-key": qdrant_key,
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        if result.get("status") != "ok":
            print(f"  WARNING: upsert status={result.get('status')}", file=sys.stderr)


def stable_id(text: str) -> int:
    """Generate a stable numeric ID from text content."""
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def classify_chunk(section_title: str, source_file: str) -> dict:
    """Classify a chunk by type, category, and severity."""
    title_lower = section_title.lower()

    # Determine type
    if "rex-" in title_lower or "piege" in title_lower or "symptome" in title_lower:
        doc_type = "lesson"
    elif "principe" in title_lower or "regle" in title_lower:
        doc_type = "principle"
    elif "checklist" in title_lower or "pattern" in title_lower:
        doc_type = "guideline"
    elif "guide" in source_file.lower():
        doc_type = "guideline"
    else:
        doc_type = "lesson"

    # Determine category
    if any(k in title_lower for k in ["socket", "docker", "container", "compose"]):
        category = "docker-security"
    elif any(k in title_lower for k in ["caddy", "header", "tls", "hsts"]):
        category = "caddy-security"
    elif any(k in title_lower for k in ["qdrant", "alloy", "grafana", "victoria", "monitoring"]):
        category = "monitoring"
    elif any(k in title_lower for k in ["secret", "env_file", "password", "vault"]):
        category = "secrets-management"
    elif any(k in title_lower for k in ["reseau", "network", "subnet"]):
        category = "network-segmentation"
    elif any(k in title_lower for k in ["healthcheck", "health"]):
        category = "healthchecks"
    elif any(k in title_lower for k in ["privilege", "user", "root", "capability", "cap_"]):
        category = "least-privilege"
    else:
        category = "docker-security"

    # Determine severity
    if any(k in title_lower for k in ["critical", "critique", "c3", "socket"]):
        severity = "critical"
    elif any(k in title_lower for k in ["crash", "permission denied", "403"]):
        severity = "high"
    elif any(k in title_lower for k in ["dry", "snippet", "override"]):
        severity = "medium"
    else:
        severity = "medium"

    return {"type": doc_type, "category": category, "severity": severity}


def main():
    parser = argparse.ArgumentParser(description="Ingest docs into Qdrant")
    parser.add_argument("--litellm-url", required=True)
    parser.add_argument("--litellm-key", required=True)
    parser.add_argument("--qdrant-url", required=True)
    parser.add_argument("--qdrant-key", required=True)
    parser.add_argument("--collection", default="vpai_rex")
    parser.add_argument("--files", nargs="+", required=True)
    args = parser.parse_args()

    total_chunks = 0
    total_upserted = 0

    for filepath in args.files:
        print(f"\n=== Processing: {filepath}")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            print(f"  SKIP: file not found", file=sys.stderr)
            continue

        source_file = filepath.split("/")[-1]

        # Extract metadata from filename
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", source_file)
        date = date_match.group(1) if date_match else "2026-03-10"

        session_match = re.search(r"SESSION-", source_file)
        is_rex = session_match is not None or "REX" in source_file.upper()

        chunks = chunk_markdown(content, source_file)
        print(f"  Found {len(chunks)} chunks")
        total_chunks += len(chunks)

        for i, chunk in enumerate(chunks):
            classification = classify_chunk(chunk["section_title"], source_file)

            payload = {
                "source_project": "vpai",
                "source_file": source_file,
                "section_title": chunk["section_title"],
                "category": classification["category"],
                "type": classification["type"],
                "severity": classification["severity"],
                "date": date,
                "text": chunk["text"],
            }

            if is_rex:
                payload["session"] = "16"

            point_id = stable_id(f"{source_file}:{chunk['section_title']}")

            print(f"  [{i+1}/{len(chunks)}] {chunk['section_title'][:60]}...", end=" ")

            try:
                vector = get_embedding(chunk["text"], args.litellm_url, args.litellm_key)
                upsert_point(
                    point_id=point_id,
                    vector=vector,
                    payload=payload,
                    qdrant_url=args.qdrant_url,
                    qdrant_key=args.qdrant_key,
                    collection=args.collection,
                )
                print("OK")
                total_upserted += 1
            except Exception as e:
                print(f"FAIL: {e}")

    print(f"\n=== Done: {total_upserted}/{total_chunks} chunks upserted into {args.collection}")


if __name__ == "__main__":
    main()
