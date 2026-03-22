#!/usr/bin/env python3
"""Index vref CLI documentation into Qdrant."""
import hashlib, json, os, sys, time, urllib.request, urllib.error

DOCS_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "vref-cli-docs.md")
LITELLM_URL = os.environ.get("LITELLM_URL", "https://llm.ewutelo.cloud")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "https://qd.ewutelo.cloud")
QDRANT_KEY = os.environ.get("QDRANT_KEY", "")
COLLECTION = "vref-cli-docs"

def chunk_md(text):
    chunks, title, lines = [], "Introduction", []
    for line in text.split("\n"):
        if line.startswith("## "):
            if lines:
                c = "\n".join(lines).strip()
                if len(c) > 50:
                    chunks.append({"title": title, "content": c[:2000]})
            title, lines = line.lstrip("# ").strip(), []
        else:
            lines.append(line)
    if lines:
        c = "\n".join(lines).strip()
        if len(c) > 50:
            chunks.append({"title": title, "content": c[:2000]})
    return chunks

def embed(text):
    req = urllib.request.Request(f"{LITELLM_URL}/v1/embeddings",
        data=json.dumps({"model":"embedding","input":text[:8000]}).encode(),
        headers={"Authorization":f"Bearer {LITELLM_KEY}","Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["data"][0]["embedding"]

def main():
    with open(DOCS_PATH) as f: text = f.read()
    chunks = chunk_md(text)
    print(f"Read {len(text)} chars, {len(chunks)} chunks")
    # Create collection
    try:
        urllib.request.urlopen(urllib.request.Request(f"{QDRANT_URL}/collections/{COLLECTION}",
            headers={"api-key":QDRANT_KEY}), timeout=5)
    except:
        urllib.request.urlopen(urllib.request.Request(f"{QDRANT_URL}/collections/{COLLECTION}",
            data=json.dumps({"vectors":{"size":1536,"distance":"Cosine"}}).encode(),
            method="PUT", headers={"api-key":QDRANT_KEY,"Content-Type":"application/json"}), timeout=10)
        print(f"Created collection {COLLECTION}")
    # Index
    batch = []
    for i, c in enumerate(chunks):
        pid = int(hashlib.sha256(c["content"][:500].encode()).hexdigest()[:15], 16)
        vec = embed(c["title"] + ": " + c["content"])
        batch.append({"id":pid,"vector":vec,"payload":{"title":c["title"],"content":c["content"],"source":"vref-cli-docs"}})
        if len(batch) >= 5:
            urllib.request.urlopen(urllib.request.Request(f"{QDRANT_URL}/collections/{COLLECTION}/points",
                data=json.dumps({"points":batch}).encode(), method="PUT",
                headers={"api-key":QDRANT_KEY,"Content-Type":"application/json"}), timeout=15)
            print(f"  [{i+1}/{len(chunks)}] upserted {len(batch)}")
            batch = []
            time.sleep(0.3)
    if batch:
        urllib.request.urlopen(urllib.request.Request(f"{QDRANT_URL}/collections/{COLLECTION}/points",
            data=json.dumps({"points":batch}).encode(), method="PUT",
            headers={"api-key":QDRANT_KEY,"Content-Type":"application/json"}), timeout=15)
        print(f"  [{len(chunks)}/{len(chunks)}] upserted {len(batch)}")
    print(f"Done: {len(chunks)} indexed")

if __name__ == "__main__": main()
