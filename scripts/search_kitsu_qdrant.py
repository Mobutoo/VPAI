#!/usr/bin/env python3
"""Search kitsu-docs in Qdrant for production pipeline best practices."""
import asyncio, aiohttp, os, json

async def search():
    h = {"api-key": os.environ["QDRANT_API_KEY"], "Content-Type": "application/json"}
    url = os.environ["QDRANT_URL"]
    lh = {"Authorization": f"Bearer {os.environ['LITELLM_API_KEY']}", "Content-Type": "application/json"}
    lu = os.environ["LITELLM_URL"]

    queries = [
        "how to create project sequence shot breakdown casting assets Kitsu production",
        "preview files upload comment task status workflow publish revision Kitsu",
        "concept art mood board asset linking shot casting breakdown Kitsu",
        "short film production setup steps sequence shots assets pipeline",
    ]

    async with aiohttp.ClientSession() as s:
        for q in queries:
            er = await s.post(f"{lu}/v1/embeddings", headers=lh,
                             json={"model": "embedding", "input": q})
            emb = await er.json()
            vec = emb["data"][0]["embedding"]

            sr = await s.post(f"{url}/collections/kitsu-docs/points/search",
                             headers=h, json={"vector": vec, "limit": 4, "with_payload": True})
            data = await sr.json()
            results = data.get("result", [])

            print(f"\n=== Q: {q[:70]} ===")
            for r in results:
                p = r.get("payload", {})
                score = r.get("score", 0)
                title = p.get("title", p.get("section", p.get("filename", "?")))
                text = p.get("text", p.get("content", ""))[:400]
                print(f"  [{score:.2f}] {title}")
                print(f"    {text}\n")

asyncio.run(search())
