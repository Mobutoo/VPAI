"""Documentation search command via Qdrant semantic search."""
import click

from .main import cli, pass_ctx


@cli.command("docs")
@click.argument("query")
@click.option("--limit", default=5, help="Max results")
@click.option("--category", default=None, help="Filter by category (e.g., built-in-nodes, api-reference)")
@pass_ctx
def docs(ctx, query, limit, category):
    """Search ComfyUI documentation via Qdrant."""
    qdrant_url = ctx.config.get("qdrant_url", "")
    qdrant_api_key = ctx.config.get("qdrant_api_key", "")
    collection = ctx.config.get("qdrant_collection", "comfyui-docs")
    litellm_url = ctx.config.get("litellm_url", "")
    litellm_api_key = ctx.config.get("litellm_api_key", "")

    if not qdrant_url or not litellm_url:
        ctx.error("Qdrant/LiteLLM not configured. Set qdrant_url and litellm_url in config.")
        return

    try:
        from openai import OpenAI
        from qdrant_client import QdrantClient
        from urllib.parse import urlparse
    except ImportError:
        ctx.error("Install docs extras: pip install comfyui-cli[docs]")
        return

    # Generate query embedding
    openai_client = OpenAI(base_url=litellm_url, api_key=litellm_api_key)
    try:
        embedding_resp = openai_client.embeddings.create(
            model="embedding",
            input=query[:8000],
        )
        query_vector = embedding_resp.data[0].embedding
    except Exception as e:
        ctx.error(f"Embedding generation failed: {e}")
        return

    # Search Qdrant
    parsed = urlparse(qdrant_url)
    host = parsed.hostname or qdrant_url
    port = parsed.port or (443 if parsed.scheme == "https" else 6333)
    https = parsed.scheme == "https"

    qdrant = QdrantClient(host=host, port=port, api_key=qdrant_api_key, https=https)

    filter_condition = None
    if category:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        filter_condition = Filter(
            must=[FieldCondition(key="category", match=MatchValue(value=category))]
        )

    try:
        results = qdrant.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            query_filter=filter_condition,
        )
    except Exception as e:
        ctx.error(f"Qdrant search failed: {e}")
        return

    docs_results = [
        {
            "score": round(hit.score, 3),
            "title": hit.payload.get("title", ""),
            "url": hit.payload.get("url", ""),
            "category": hit.payload.get("category", ""),
            "text": hit.payload.get("text", "")[:500],
        }
        for hit in results
    ]

    def human(data):
        if not data:
            return "No results found."
        lines = []
        for i, r in enumerate(data, 1):
            lines.append(f"\n{i}. [{r['score']}] {r['title']}")
            lines.append(f"   {r['url']}")
            lines.append(f"   {r['text'][:200]}...")
        return "\n".join(lines)

    ctx.output(docs_results, human)
