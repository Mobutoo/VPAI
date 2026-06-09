#!/usr/bin/env python3
"""run_eval.py — Harness d'éval retrieval mémoire (contrat RAG v3 2026-06-10).

Évalue une collection Qdrant contre le golden-set (golden.yml) :
recall@1, recall@5, MRR@10, breakdown par doc_kind.

Match = AU MOINS UN expected_path (`repo:relative_path`) présent dans le
top-k (payload Qdrant `repo` + `relative_path`).

Modes :
  - dense  : vecteur dense seul. Rétro-compat : détection auto du schéma de
    collection (vecteur unnamed = memory_v2 ; vecteur nommé "dense" = memory_v3).
  - hybrid : Query API `query_points` avec prefetch dense (limit 30,
    using="dense") + sparse BM25 (limit 30, using="bm25") -> fusion RRF.
    Requiert une collection à vecteurs nommés dense+bm25 (memory_v3) et
    `fastembed` installé (lazy-import — le mode dense n'en dépend pas).

Tourne sur le venv worker Waza :
  set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a
  /opt/workstation/ai-memory-worker/.venv/bin/python scripts/memory/eval/run_eval.py \
    --collection memory_v2 --mode dense

Comparaison : --baseline <eval.json> affiche le diff par métrique.
Sortie JSON : .planning/eval/ (défaut), STRICTEMENT lecture seule côté Qdrant.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from qdrant_client import QdrantClient
from qdrant_client import models as qmodels

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[2]  # scripts/memory/eval -> racine VPAI
DEFAULT_GOLDEN = EVAL_DIR / "golden.yml"
DEFAULT_OUT_DIR = REPO_ROOT / ".planning" / "eval"
DEFAULT_CONFIG = "/opt/workstation/configs/ai-memory-worker/config.yml"
PREFETCH_LIMIT = 30  # contrat : prefetch dense/sparse limit 30
MRR_K = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eval retrieval mémoire (golden-set).")
    parser.add_argument("--collection", required=True, help="Collection Qdrant cible")
    parser.add_argument("--mode", choices=["dense", "hybrid"], default="dense")
    parser.add_argument("--limit", type=int, default=10, help="top-k récupéré (>= 10 pour MRR@10)")
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN), help="Chemin golden.yml")
    parser.add_argument("--out", default=None, help="Fichier JSON de sortie (défaut .planning/eval/)")
    parser.add_argument("--baseline", default=None, help="JSON d'une éval précédente -> diff par métrique")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="config.yml worker (modèle/Qdrant)")
    parser.add_argument("--max-questions", type=int, default=None,
                        help="Sous-ensemble des N premières questions (smoke test)")
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def make_client(config: dict) -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QDRANT_URL", config["qdrant_url"]),
        api_key=os.getenv("QDRANT_API_KEY"),
        timeout=int(os.getenv("QDRANT_TIMEOUT", config.get("qdrant_timeout", 30))),
        verify=str(os.getenv("QDRANT_VERIFY_TLS", config.get("qdrant_verify_tls", True))).lower() == "true",
        check_compatibility=False,  # serveur 1.18 vs client 1.16 — warning inutile
    )


def detect_schema(client: QdrantClient, collection: str) -> dict:
    """Détecte le schéma de la collection : vecteur unnamed (v2) ou nommés (v3).

    Retourne {"named": bool, "dense_name": str|None, "sparse_names": [str...]}.
    """
    info = client.get_collection(collection)
    vectors = info.config.params.vectors
    sparse = info.config.params.sparse_vectors or {}
    if isinstance(vectors, dict):
        return {
            "named": True,
            "dense_name": "dense" if "dense" in vectors else next(iter(vectors), None),
            "sparse_names": sorted(sparse.keys()),
        }
    return {"named": False, "dense_name": None, "sparse_names": sorted(sparse.keys())}


class DenseEncoder:
    """Encodeur de requêtes dense — mêmes invariants que search_memory.py."""

    def __init__(self, config: dict) -> None:
        from sentence_transformers import SentenceTransformer  # lazy: import lourd

        emb = config["embedding"]
        self.model = SentenceTransformer(emb["model_name"])
        self.prompt_name = emb["query_prompt_name"]
        self.normalize = bool(emb["normalize_embeddings"])

    def encode_queries(self, queries: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            queries,
            prompt_name=self.prompt_name,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]


class SparseEncoder:
    """Encodeur sparse BM25 (FastEmbed Qdrant/bm25) — requêtes uniquement.

    Lazy : fastembed n'est importé qu'en mode hybrid. Côté requête le texte
    sparse est la query brute (build_sparse_text du contrat concerne les
    documents : relative_path + section + chunk_text).
    """

    MODEL_NAME = "Qdrant/bm25"

    def __init__(self) -> None:
        try:
            from fastembed import SparseTextEmbedding  # lazy import
        except ImportError as exc:  # message actionnable, pas de crash obscur
            raise SystemExit(
                "mode hybrid: paquet `fastembed` absent du venv. "
                "Installer fastembed (sibling test /tmp d'abord — contrat RAG v3) "
                f"ou utiliser --mode dense. ({exc})"
            )
        self.model = SparseTextEmbedding(model_name=self.MODEL_NAME)

    def encode_query(self, query: str) -> "qmodels.SparseVector":
        emb = next(iter(self.model.query_embed(query)))
        return qmodels.SparseVector(
            indices=emb.indices.tolist(), values=emb.values.tolist()
        )


def run_query(
    client: QdrantClient,
    collection: str,
    mode: str,
    schema: dict,
    dense_vector: list[float],
    sparse_vector: "qmodels.SparseVector | None",
    limit: int,
):
    """Une requête top-k. Dense legacy (unnamed) ET v3 (nommé) supportés."""
    if mode == "hybrid":
        prefetch = [
            qmodels.Prefetch(query=dense_vector, using="dense", limit=PREFETCH_LIMIT),
            qmodels.Prefetch(query=sparse_vector, using="bm25", limit=PREFETCH_LIMIT),
        ]
        response = client.query_points(
            collection_name=collection,
            prefetch=prefetch,
            query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
            limit=limit,
            with_payload=["repo", "relative_path", "doc_kind", "section"],
            with_vectors=False,
        )
    else:
        kwargs = {}
        if schema["named"]:
            kwargs["using"] = schema["dense_name"]
        response = client.query_points(
            collection_name=collection,
            query=dense_vector,
            limit=limit,
            with_payload=["repo", "relative_path", "doc_kind", "section"],
            with_vectors=False,
            **kwargs,
        )
    return response.points


def evaluate(points, expected: set[str]) -> dict:
    """Rang (1-based) du premier hit (repo:relative_path ∈ expected), hits dédupliqués.

    Les chunks successifs d'un même fichier comptent pour UN seul rang :
    le rang est compté sur les fichiers distincts rencontrés.
    """
    seen_files: list[str] = []
    first_hit_rank = None
    for point in points:
        payload = point.payload or {}
        key = f"{payload.get('repo')}:{payload.get('relative_path')}"
        if key not in seen_files:
            seen_files.append(key)
        if first_hit_rank is None and key in expected:
            first_hit_rank = seen_files.index(key) + 1
    return {"rank": first_hit_rank, "top_files": seen_files[:MRR_K]}


def aggregate(results: list[dict]) -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0}
    recall_1 = sum(1 for r in results if r["rank"] == 1) / n
    recall_5 = sum(1 for r in results if r["rank"] is not None and r["rank"] <= 5) / n
    mrr_10 = sum(
        1.0 / r["rank"] for r in results if r["rank"] is not None and r["rank"] <= MRR_K
    ) / n
    return {
        "n": n,
        "recall@1": round(recall_1, 4),
        "recall@5": round(recall_5, 4),
        "mrr@10": round(mrr_10, 4),
    }


def print_diff(current: dict, baseline_path: Path) -> None:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    base_metrics = baseline.get("metrics", {})
    cur_metrics = current.get("metrics", {})
    print(f"\n=== Diff vs baseline {baseline_path} "
          f"({baseline.get('collection')}/{baseline.get('mode')}) ===")
    for key in ("recall@1", "recall@5", "mrr@10"):
        old = base_metrics.get(key)
        new = cur_metrics.get(key)
        if old is None or new is None:
            print(f"{key:>10}: n/a")
            continue
        delta = new - old
        arrow = "=" if abs(delta) < 1e-9 else ("UP" if delta > 0 else "DOWN")
        print(f"{key:>10}: {old:.4f} -> {new:.4f}  ({delta:+.4f} {arrow})")
    base_kinds = baseline.get("by_doc_kind", {})
    for kind, metrics in sorted(current.get("by_doc_kind", {}).items()):
        old = base_kinds.get(kind, {}).get("recall@5")
        new = metrics.get("recall@5")
        if old is not None and new is not None:
            print(f"{('recall@5['+kind+']'):>18}: {old:.4f} -> {new:.4f}  ({new-old:+.4f})")


def main() -> int:
    args = parse_args()
    if args.limit < MRR_K:
        print(f"[warn] --limit {args.limit} < {MRR_K} : MRR@10 sera tronqué au top-{args.limit}",
              file=sys.stderr)

    golden = load_yaml(Path(args.golden))
    questions = golden.get("questions", []) or []
    if args.max_questions:
        questions = questions[: args.max_questions]
    if not questions:
        print("golden.yml vide — rien à évaluer", file=sys.stderr)
        return 1

    config = load_yaml(Path(args.config))
    client = make_client(config)
    schema = detect_schema(client, args.collection)

    if args.mode == "hybrid":
        if not schema["named"] or schema["dense_name"] != "dense" or "bm25" not in schema["sparse_names"]:
            print(
                f"mode hybrid impossible sur '{args.collection}' : schéma "
                f"named={schema['named']} dense={schema['dense_name']} "
                f"sparse={schema['sparse_names']} (requis: dense + bm25). "
                "Utiliser --mode dense.",
                file=sys.stderr,
            )
            return 2
        sparse_encoder = SparseEncoder()
    else:
        sparse_encoder = None

    print(f"[eval] collection={args.collection} mode={args.mode} schema="
          f"{'named' if schema['named'] else 'unnamed'} questions={len(questions)} "
          f"limit={args.limit}")

    encoder = DenseEncoder(config)
    t_encode = time.monotonic()
    dense_vectors = encoder.encode_queries([q["query"] for q in questions])
    encode_s = time.monotonic() - t_encode

    results: list[dict] = []
    t_search = time.monotonic()
    for question, dense_vector in zip(questions, dense_vectors):
        sparse_vector = (
            sparse_encoder.encode_query(question["query"]) if sparse_encoder else None
        )
        points = run_query(
            client, args.collection, args.mode, schema, dense_vector, sparse_vector,
            args.limit,
        )
        expected = set(question["expected_paths"])
        outcome = evaluate(points, expected)
        results.append(
            {
                "query": question["query"],
                "doc_kind": question.get("doc_kind", "doc"),
                "expected_paths": sorted(expected),
                "rank": outcome["rank"],
                "top_files": outcome["top_files"],
                "note": question.get("note", ""),
            }
        )
        status = f"rank={outcome['rank']}" if outcome["rank"] else "MISS"
        print(f"  [{status:>8}] {question['query'][:80]}")
    search_s = time.monotonic() - t_search

    by_kind: dict[str, list[dict]] = {}
    for result in results:
        by_kind.setdefault(result["doc_kind"], []).append(result)

    report = {
        "schema_version": "eval-v1",
        "collection": args.collection,
        "mode": args.mode,
        "limit": args.limit,
        "golden": str(Path(args.golden).resolve()),
        "questions": len(results),
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "timings": {"encode_s": round(encode_s, 2), "search_s": round(search_s, 2)},
        "metrics": aggregate(results),
        "by_doc_kind": {kind: aggregate(items) for kind, items in sorted(by_kind.items())},
        "misses": [
            {"query": r["query"], "expected": r["expected_paths"], "top_files": r["top_files"][:5]}
            for r in results
            if r["rank"] is None
        ],
        "details": results,
    }

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = DEFAULT_OUT_DIR / f"eval-{args.collection}-{args.mode}-{stamp}.json"
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        # Copie déployée sous /opt : parents[2] -> /opt/.planning (non inscriptible).
        # Fail-safe : ne jamais perdre un rapport d'éval déjà calculé.
        fallback = Path.cwd() / out_path.name
        print(f"[warn] écriture {out_path} impossible ({exc}) -> {fallback}", file=sys.stderr)
        out_path = fallback
        out_path.write_text(rendered, encoding="utf-8")

    metrics = report["metrics"]
    print(f"\n=== {args.collection} / {args.mode} — {metrics['n']} questions ===")
    print(f"  recall@1 = {metrics['recall@1']:.4f}")
    print(f"  recall@5 = {metrics['recall@5']:.4f}")
    print(f"  mrr@10   = {metrics['mrr@10']:.4f}")
    for kind, kind_metrics in report["by_doc_kind"].items():
        print(f"  [{kind}] n={kind_metrics['n']} r@1={kind_metrics['recall@1']:.4f} "
              f"r@5={kind_metrics['recall@5']:.4f} mrr@10={kind_metrics['mrr@10']:.4f}")
    print(f"  encode={report['timings']['encode_s']}s search={report['timings']['search_s']}s")
    print(f"  -> {out_path}")

    if args.baseline:
        print_diff(report, Path(args.baseline))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
