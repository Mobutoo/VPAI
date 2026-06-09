#!/usr/bin/env python3
"""MCP stdio server — thin wrapper around memory search (collection from config.yml).

SOURCE OF TRUTH : repo VPAI roles/llamaindex-memory-worker/files/mcp_search.py.
(Le fichier vivait uniquement dans /opt/workstation/ai-memory-worker/ — copié dans le
rôle 2026-06-10 puis modifié ICI ; le déploiement du rôle recopie ce fichier vers /opt.)

Contrat 2026-06-10 (docs/superpowers/specs/2026-06-10-rag-v3-contracts.md §Recherche) :
  - Détection auto du schéma collection : named (v3) -> hybrid dense+bm25 RRF ;
    unnamed (v2) -> dense legacy. fastembed indisponible -> fallback dense (fail-open).
  - Floor 0.50 sur le score dense cosine (env MEMORY_MIN_SCORE) -> sous le floor,
    réponse `not found` (hygiène d'injection hooks : jamais de hit hors-sujet).
  - Format compact : `score | repo/relative_path | section | snippet 1 ligne`.

Uses same embeddings as the ai-memory-worker (google/embeddinggemma-300m, 768d).
Model preloads in background thread; tool calls wait up to 120s.
"""
import sys, json, os, threading, logging
from pathlib import Path
import yaml

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.disable(logging.WARNING)

_CONFIG_PATH = Path("/opt/workstation/configs/ai-memory-worker/config.yml")
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
PREFETCH_LIMIT = 30
MIN_SCORE = float(os.environ.get("MEMORY_MIN_SCORE", "0.50"))

_model = None
_client = None
_config = None
_named = False          # schéma collection : vecteurs nommés (v3) ?
_sparse_encoder = None  # Bm25SparseEncoder si named + fastembed dispo, sinon None
_ready = threading.Event()
_lock = threading.Lock()


def _load() -> None:
    global _model, _client, _config, _named, _sparse_encoder
    try:
        with _CONFIG_PATH.open() as fh:
            _config = yaml.safe_load(fh)
        hf_home = _config["paths"]["hf_home"]
        os.environ.setdefault("HF_HOME", hf_home)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", hf_home)
        from sentence_transformers import SentenceTransformer
        from qdrant_client import QdrantClient
        m = SentenceTransformer(_config["embedding"]["model_name"])
        c = QdrantClient(
            url=os.environ.get("QDRANT_URL", _config["qdrant_url"]),
            api_key=os.environ.get("QDRANT_API_KEY"),
            timeout=int(os.environ.get("QDRANT_TIMEOUT", _config["qdrant_timeout"])),
            verify=str(os.environ.get("QDRANT_VERIFY_TLS",
                        _config.get("qdrant_verify_tls", True))).lower() == "true",
        )
        named = False
        sparse = None
        try:
            info = c.get_collection(_config["collection_name"])
            named = isinstance(info.config.params.vectors, dict)
        except Exception:
            named = False
        if named:
            try:
                # MÊME wrapper sparse que l'ingestion (memory_core, déployé à côté).
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from memory_core import Bm25SparseEncoder
                sparse = Bm25SparseEncoder()
            except Exception:
                sparse = None  # fastembed absent -> fallback dense (fail-open)
        with _lock:
            _model = m
            _client = c
            _named = named
            _sparse_encoder = sparse
    except Exception:
        pass
    finally:
        _ready.set()


def _write(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def _handle(req: dict) -> None:
    method = req.get("method", "")
    rid = req.get("id")
    if method == "initialize":
        _write({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "memory-search", "version": "2.0.0"},
        }})
    elif method in ("notifications/initialized", "notifications/cancelled"):
        pass
    elif method == "tools/list":
        _write({"jsonrpc": "2.0", "id": rid, "result": {"tools": [{
            "name": "qdrant-find",
            "description": (
                "Semantic+lexical (hybrid RRF) search in memory (REX, plans, docs, runbooks). "
                "Use for R0 memory lookup before any work on known topics. "
                "Returns compact lines `score | repo/path | section | snippet` "
                "or `not found` (score floor)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "limit": {"type": "integer", "default": 5, "description": "Max results"},
                    "repo": {"type": "string", "description": "Filter by repo (e.g. VPAI, flash-studio)"},
                    "doc_kind": {"type": "string", "description": "Filter by doc_kind (doc, config, runbook...)"},
                    "topic": {"type": "string", "description": "Filter by topic"},
                },
                "required": ["query"],
            },
        }]}})
    elif method == "tools/call":
        name = req.get("params", {}).get("name")
        args = req.get("params", {}).get("arguments", {})
        if name == "qdrant-find":
            text = _do_search(args)
            _write({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": text}]
            }})
        else:
            _write({"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32601, "message": f"Unknown tool: {name}"
            }})
    else:
        if rid is not None:
            _write({"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32601, "message": f"Unknown method: {method}"
            }})


def _dense_cosine(query_vector, point_vector):
    """Cosinus client-side (vecteurs normalisés -> produit scalaire)."""
    if point_vector is None:
        return None
    vec = point_vector.get(DENSE_VECTOR_NAME) if isinstance(point_vector, dict) else point_vector
    if vec is None:
        return None
    return float(sum(a * b for a, b in zip(query_vector, vec)))


def _snippet(payload: dict) -> str:
    text = payload.get("text")
    if not text:
        node_content = payload.get("_node_content")
        if node_content:
            try:
                text = json.loads(node_content).get("text", "")
            except (json.JSONDecodeError, AttributeError):
                text = ""
    text = " ".join(str(text or payload.get("title") or "").split())
    return text[:160]


def _do_search(args: dict) -> str:
    _ready.wait(timeout=120)
    with _lock:
        m, c, cfg, named, sparse = _model, _client, _config, _named, _sparse_encoder
    if m is None or c is None:
        return json.dumps({"error": "model failed to load"})
    from qdrant_client.http import models as rest
    vector = m.encode(
        args["query"],
        prompt_name=cfg["embedding"]["query_prompt_name"],
        normalize_embeddings=bool(cfg["embedding"]["normalize_embeddings"]),
        show_progress_bar=False,
    ).tolist()
    conditions = []
    for field in ("repo", "doc_kind", "topic"):
        val = args.get(field)
        if val:
            conditions.append(rest.FieldCondition(
                key=field, match=rest.MatchValue(value=val)
            ))
    query_filter = rest.Filter(must=conditions) if conditions else None
    limit = int(args.get("limit", 5))

    if named and sparse is not None:
        # Hybrid RRF (contrat §Recherche) : prefetch dense + bm25, fusion serveur.
        sparse_indices, sparse_values = sparse.encode_query(args["query"])
        resp = c.query_points(
            collection_name=cfg["collection_name"],
            prefetch=[
                rest.Prefetch(query=vector, using=DENSE_VECTOR_NAME,
                              limit=PREFETCH_LIMIT, filter=query_filter),
                rest.Prefetch(query=rest.SparseVector(indices=sparse_indices,
                                                      values=sparse_values),
                              using=SPARSE_VECTOR_NAME, limit=PREFETCH_LIMIT,
                              filter=query_filter),
            ],
            query=rest.FusionQuery(fusion=rest.Fusion.RRF),
            limit=limit,
            with_payload=True,
            with_vectors=[DENSE_VECTOR_NAME],
        )
    else:
        resp = c.query_points(
            collection_name=cfg["collection_name"],
            query=vector,
            using=DENSE_VECTOR_NAME if named else None,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=[DENSE_VECTOR_NAME] if named else False,
        )

    lines = []
    best = 0.0
    for pt in resp.points:
        payload = pt.payload or {}
        if named:
            cos = _dense_cosine(vector, getattr(pt, "vector", None))
        else:
            cos = float(pt.score)
        if cos is not None and cos > best:
            best = cos
        # Floor sur le score dense cosine — hygiène d'injection : pas de hit hors-sujet.
        if cos is None or cos < MIN_SCORE:
            continue
        repo_path = f"{payload.get('repo', '?')}/{payload.get('relative_path', '?')}"
        section = payload.get("section") or "-"
        lines.append(f"{cos:.2f} | {repo_path} | {section} | {_snippet(payload)}")
    if not lines:
        return f"not found (best dense score {best:.3f} < floor {MIN_SCORE})"
    return "\n".join(lines)


def main() -> None:
    threading.Thread(target=_load, daemon=True).start()
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
            _handle(req)
        except (json.JSONDecodeError, Exception):
            pass


if __name__ == "__main__":
    main()
