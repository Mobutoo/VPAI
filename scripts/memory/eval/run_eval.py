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

Mode gate (garde-fou anti-dérive silencieuse, audit mémoire 2026-07-17) :
  --assert-thresholds fait échouer le run (exit 3) si recall@1 ou mrr@10 tombe
  sous un seuil. N'altère PAS le mode rapport par défaut (sans le flag, le
  comportement/exit-code est inchangé) — réservé au run automatique/CI.
  Seuils configurables via --min-recall1/--min-mrr10 ou env
  EVAL_MIN_RECALL_1/EVAL_MIN_MRR_10 (défauts 0.70/0.80, cf audit).

Extensions 2026-07-17 (restauration recall@1, ops/loops/reports/2026-07-17-*) :
  - --prefetch-limit N : top-K candidats par canal avant fusion (défaut 30, contrat).
  - --fusion rrf|dbsf : stratégie Qdrant native (mode hybrid, FusionQuery serveur).
  - --manual-fusion : bypass FusionQuery serveur -> 2 requêtes séparées (dense-only,
    sparse-only, top --prefetch-limit chacune) + RRF pondéré recalculé côté client
    avec --rrf-k et --dense-weight/--sparse-weight. Qdrant-client 1.16 n'expose PAS
    le k RRF serveur (FusionQuery n'a qu'un champ `fusion`) -> seul --manual-fusion
    permet de le faire varier.
  - --rerank-light : cross-encoder léger (fastembed TextCrossEncoder, défaut
    Xenova/ms-marco-MiniLM-L-6-v2, ~90MB ONNX) rerank les --rerank-candidates
    premiers hits fusionnés sur le TEXTE COMPLET du chunk (payload `text`, PAS le
    snippet 160 car. — un cross-encoder jugé sur 30 mots est aveugle). Latence par
    requête loggée (`rerank_timings` dans le rapport JSON, médiane/max) — objectif
    <1.5s/requête pour un usage R0 interactif (cf bge-reranker-v2-m3 : 9.8s médiane,
    disqualifié, AI-MEMORY-AGENT-PROTOCOL.md §3.6).
  Défaut (aucun de ces flags) : comportement STRICTEMENT identique à avant (RRF
  serveur, prefetch=30, pas de rerank) — sibling test de non-régression obligatoire
  après modif de ce fichier (LOI R4/R6) : rejouer sans flag doit reproduire le
  dernier rapport commité au point près.
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
PREFETCH_LIMIT = 30  # contrat : prefetch dense/sparse limit 30 (défaut --prefetch-limit)
MRR_K = 10

# RRF k : Qdrant défaut = 2 (PAS 60, la valeur "standard" du papier Cormack et al. 2009
# reprise par la plupart des libs IR) — vérifié doc officielle
# https://qdrant.tech/documentation/concepts/hybrid-queries/ ("k is a constant, set to 2
# by default"), configurable côté serveur depuis v1.16.0 via query=RrfQuery(rrf=Rrf(k=N))
# (qdrant-client 1.16.2 expose bien RrfQuery/Rrf — vérifié introspection modèles pydantic).
# k=2 est TRÈS agressif (1/(2+0)=0.50 vs 1/(2+2)=0.25 : un doc qui glisse de 2 rangs sur UN
# canal perd déjà la moitié de son score de ce canal) -> hypothèse Piste B : un k plus grand
# lisse le bruit de classement introduit par la croissance du corpus (cf audit §3).
DEFAULT_RRF_K = 2  # défaut serveur Qdrant — PAS le "60" de la littérature générique
DEFAULT_RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
DEFAULT_FASTEMBED_CACHE = "/opt/workstation/data/ai-memory-worker/fastembed-cache"


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
    parser.add_argument(
        "--assert-thresholds", action="store_true",
        help="Mode gate (CI/cron) : exit 3 si recall@1 ou mrr@10 sous seuil. "
             "N'altère pas le rapport JSON ni le mode par défaut.",
    )
    parser.add_argument(
        "--min-recall1", type=float,
        default=float(os.getenv("EVAL_MIN_RECALL_1", "0.70")),
        help="Seuil recall@1 pour --assert-thresholds (défaut 0.70, env EVAL_MIN_RECALL_1)",
    )
    parser.add_argument(
        "--min-mrr10", type=float,
        default=float(os.getenv("EVAL_MIN_MRR_10", "0.80")),
        help="Seuil mrr@10 pour --assert-thresholds (défaut 0.80, env EVAL_MIN_MRR_10)",
    )
    parser.add_argument("--prefetch-limit", type=int, default=PREFETCH_LIMIT,
                        help=f"top-K candidats par canal avant fusion (défaut {PREFETCH_LIMIT}).")
    parser.add_argument("--fusion", choices=["rrf", "dbsf"], default="rrf",
                        help="Stratégie de fusion Qdrant native (mode hybrid uniquement).")
    parser.add_argument("--rrf-k", type=int, default=None,
                        help=f"k RRF natif serveur (RrfQuery(rrf=Rrf(k=N))), Qdrant >=1.16. "
                             f"Défaut serveur = {DEFAULT_RRF_K} si omis (pas de override).")
    parser.add_argument("--manual-fusion", action="store_true",
                        help="Bypass FusionQuery serveur : 2 requêtes séparées (dense/sparse) "
                             "+ RRF pondéré client (--rrf-k/--dense-weight/--sparse-weight). "
                             "Seul moyen de pondérer les CANAUX (RRF serveur est rank-only).")
    parser.add_argument("--dense-weight", type=float, default=1.0,
                        help="Poids canal dense pour --manual-fusion (défaut 1.0).")
    parser.add_argument("--sparse-weight", type=float, default=1.0,
                        help="Poids canal sparse/BM25 pour --manual-fusion (défaut 1.0).")
    parser.add_argument("--rerank-light", action="store_true",
                        help="Rerank cross-encoder léger (fastembed TextCrossEncoder) sur le "
                             "texte complet des --rerank-candidates premiers hits fusionnés.")
    parser.add_argument("--rerank-light-model", default=DEFAULT_RERANK_MODEL,
                        help=f"Modèle fastembed TextCrossEncoder (défaut {DEFAULT_RERANK_MODEL}).")
    parser.add_argument("--rerank-candidates", type=int, default=20,
                        help="Nombre de hits fusionnés (top-N) soumis au rerank léger (défaut 20).")
    parser.add_argument("--fastembed-cache", default=os.getenv("FASTEMBED_CACHE_PATH", DEFAULT_FASTEMBED_CACHE),
                        help="Cache modèles fastembed (défaut FASTEMBED_CACHE_PATH ou config worker).")
    return parser.parse_args()


def check_thresholds(metrics: dict, min_recall1: float, min_mrr10: float) -> list[str]:
    """Seuils franchis (liste vide = gate OK). Pure — testable sans Qdrant."""
    failures = []
    recall1 = metrics.get("recall@1", 0.0)
    mrr10 = metrics.get("mrr@10", 0.0)
    if recall1 < min_recall1:
        failures.append(f"recall@1 {recall1:.4f} < seuil {min_recall1:.4f}")
    if mrr10 < min_mrr10:
        failures.append(f"mrr@10 {mrr10:.4f} < seuil {min_mrr10:.4f}")
    return failures


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


PAYLOAD_FIELDS = ["repo", "relative_path", "doc_kind", "section", "text", "title"]


def run_query(
    client: QdrantClient,
    collection: str,
    mode: str,
    schema: dict,
    dense_vector: list[float],
    sparse_vector: "qmodels.SparseVector | None",
    limit: int,
    prefetch_limit: int = PREFETCH_LIMIT,
    fusion: str = "rrf",
    rrf_k: int | None = None,
):
    """Une requête top-k. Dense legacy (unnamed) ET v3 (nommé) supportés.

    with_payload inclut désormais `text` (chunk complet) — nécessaire au rerank léger
    (un cross-encoder jugé sur le snippet 160 car. est aveugle, cf docstring module).
    Coût : payload plus lourd sur le réseau, négligeable pour un harnais d'éval 76 q.
    """
    if mode == "hybrid":
        prefetch = [
            qmodels.Prefetch(query=dense_vector, using="dense", limit=prefetch_limit),
            qmodels.Prefetch(query=sparse_vector, using="bm25", limit=prefetch_limit),
        ]
        if fusion == "dbsf":
            fusion_query: object = qmodels.FusionQuery(fusion=qmodels.Fusion.DBSF)
        elif rrf_k is not None:
            # k RRF natif serveur (Qdrant >=1.16, défaut serveur k=2 — cf DEFAULT_RRF_K).
            fusion_query = qmodels.RrfQuery(rrf=qmodels.Rrf(k=rrf_k))
        else:
            fusion_query = qmodels.FusionQuery(fusion=qmodels.Fusion.RRF)
        response = client.query_points(
            collection_name=collection,
            prefetch=prefetch,
            query=fusion_query,
            limit=limit,
            with_payload=PAYLOAD_FIELDS,
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
            with_payload=PAYLOAD_FIELDS,
            with_vectors=False,
            **kwargs,
        )
    return response.points


def run_channel_query(
    client: QdrantClient,
    collection: str,
    using: str,
    vector,
    limit: int,
):
    """Requête mono-canal (dense OU sparse seul, PAS de fusion serveur) — brique de
    --manual-fusion. Payload complet (cf PAYLOAD_FIELDS) pour permettre le rerank léger
    en aval sans requête supplémentaire."""
    response = client.query_points(
        collection_name=collection,
        query=vector,
        using=using,
        limit=limit,
        with_payload=PAYLOAD_FIELDS,
        with_vectors=False,
    )
    return response.points


def manual_rrf_fusion(
    dense_points, sparse_points, k: float, dense_weight: float, sparse_weight: float, limit: int,
):
    """RRF pondéré par canal recalculé côté client (rang 0-based, comme Qdrant —
    cf doc officielle : 'Qdrant uses zero-based rank positions'). Seul moyen de faire
    varier k ET pondérer dense vs sparse indépendamment (FusionQuery serveur ne pondère
    pas les canaux, RrfQuery ne fait varier QUE k, pas de poids par canal).

    Dédup par point id (un même chunk peut apparaître dans les deux canaux) ; le point
    "gagnant" conservé pour le payload est celui du canal dense s'il est présent (score
    dense_score aval en dépend), sinon sparse.
    """
    scores: dict[str, float] = {}
    point_by_id: dict[str, object] = {}
    for rank, point in enumerate(dense_points):
        pid = str(point.id)
        scores[pid] = scores.get(pid, 0.0) + dense_weight / (k + rank)
        point_by_id[pid] = point
    for rank, point in enumerate(sparse_points):
        pid = str(point.id)
        scores[pid] = scores.get(pid, 0.0) + sparse_weight / (k + rank)
        if pid not in point_by_id:
            point_by_id[pid] = point
    ordered_ids = sorted(scores, key=lambda pid: scores[pid], reverse=True)
    return [point_by_id[pid] for pid in ordered_ids[:limit]]


class LightCrossEncoder:
    """Rerank cross-encoder léger (fastembed TextCrossEncoder, ONNX CPU) — alternative
    à rerank.py (bge-reranker-v2-m3, 568M params, 9.8s médiane/requête sur Pi — cf
    AI-MEMORY-AGENT-PROTOCOL.md §3.6, disqualifié pour R0 interactif).

    Défaut Xenova/ms-marco-MiniLM-L-6-v2 (~23M params, ~90MB ONNX) — anglais MS MARCO,
    PAS multilingue par design. golden.yml est ~35% FR/65% EN (heuristique mots-outils
    FR sur les 76 questions) — à valider empiriquement sur les questions FR avant tout
    usage prod (cf rapport final, sibling test toy FR/EN concluant mais non exhaustif).
    """

    def __init__(self, model_name: str, cache_dir: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder  # lazy: import lourd

        self.model = TextCrossEncoder(model_name=model_name, cache_dir=cache_dir)

    def score(self, query: str, documents: list[str]) -> list[float]:
        return list(self.model.rerank(query, documents))


def rerank_light_points(encoder: LightCrossEncoder, query: str, points: list, top_n: int):
    """Rerank les top_n premiers `points` (chunks) sur le texte COMPLET du payload
    (`text`, fallback `title`) — PAS un snippet tronqué. Retourne les points réordonnés
    (top_n rerankés en tête, reste inchangé derrière) + la latence mesurée (secondes)."""
    if not points:
        return points, 0.0
    head = points[:top_n]
    tail = points[top_n:]
    documents = [
        (p.payload or {}).get("text") or (p.payload or {}).get("title") or "" for p in head
    ]
    t0 = time.monotonic()
    scores = encoder.score(query, documents)
    elapsed = time.monotonic() - t0
    order = sorted(range(len(head)), key=lambda i: scores[i], reverse=True)
    reranked_head = [head[i] for i in order]
    return reranked_head + tail, elapsed


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

    if args.manual_fusion and args.mode != "hybrid":
        print("--manual-fusion requiert --mode hybrid", file=sys.stderr)
        return 2

    rerank_encoder = None
    if args.rerank_light:
        rerank_encoder = LightCrossEncoder(args.rerank_light_model, args.fastembed_cache)

    effective_rrf_k = args.rrf_k if args.rrf_k is not None else DEFAULT_RRF_K
    fetch_limit = max(args.limit, args.rerank_candidates) if args.rerank_light else args.limit

    print(f"[eval] collection={args.collection} mode={args.mode} schema="
          f"{'named' if schema['named'] else 'unnamed'} questions={len(questions)} "
          f"limit={args.limit} prefetch_limit={args.prefetch_limit} fusion={args.fusion} "
          f"manual_fusion={args.manual_fusion} rrf_k={effective_rrf_k if (args.manual_fusion or args.rrf_k) else 'server-default'} "
          f"rerank_light={args.rerank_light}"
          + (f" rerank_model={args.rerank_light_model} rerank_candidates={args.rerank_candidates}"
             if args.rerank_light else ""))

    encoder = DenseEncoder(config)
    t_encode = time.monotonic()
    dense_vectors = encoder.encode_queries([q["query"] for q in questions])
    encode_s = time.monotonic() - t_encode

    results: list[dict] = []
    rerank_timings: list[float] = []
    t_search = time.monotonic()
    for question, dense_vector in zip(questions, dense_vectors):
        sparse_vector = (
            sparse_encoder.encode_query(question["query"]) if sparse_encoder else None
        )
        if args.manual_fusion:
            dense_points = run_channel_query(
                client, args.collection, "dense", dense_vector, args.prefetch_limit,
            )
            sparse_points = run_channel_query(
                client, args.collection, "bm25", sparse_vector, args.prefetch_limit,
            )
            points = manual_rrf_fusion(
                dense_points, sparse_points, effective_rrf_k,
                args.dense_weight, args.sparse_weight, fetch_limit,
            )
        else:
            points = run_query(
                client, args.collection, args.mode, schema, dense_vector, sparse_vector,
                fetch_limit, prefetch_limit=args.prefetch_limit, fusion=args.fusion,
                rrf_k=args.rrf_k,
            )

        if args.rerank_light:
            points, rerank_s = rerank_light_points(
                rerank_encoder, question["query"], points, args.rerank_candidates,
            )
            rerank_timings.append(rerank_s)

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
        rerank_suffix = f" ({rerank_timings[-1]:.2f}s)" if args.rerank_light else ""
        print(f"  [{status:>8}]{rerank_suffix} {question['query'][:80]}")
    search_s = time.monotonic() - t_search

    by_kind: dict[str, list[dict]] = {}
    for result in results:
        by_kind.setdefault(result["doc_kind"], []).append(result)

    rerank_stats = None
    if args.rerank_light and rerank_timings:
        sorted_t = sorted(rerank_timings)
        mid = len(sorted_t) // 2
        median_t = sorted_t[mid] if len(sorted_t) % 2 else (sorted_t[mid - 1] + sorted_t[mid]) / 2
        rerank_stats = {
            "model": args.rerank_light_model,
            "candidates": args.rerank_candidates,
            "median_s": round(median_t, 3),
            "max_s": round(max(sorted_t), 3),
            "min_s": round(min(sorted_t), 3),
        }

    report = {
        "schema_version": "eval-v1",
        "collection": args.collection,
        "mode": args.mode,
        "limit": args.limit,
        "golden": str(Path(args.golden).resolve()),
        "questions": len(results),
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "params": {
            "prefetch_limit": args.prefetch_limit,
            "fusion": args.fusion,
            "manual_fusion": args.manual_fusion,
            "rrf_k": effective_rrf_k if (args.manual_fusion or args.rrf_k is not None) else None,
            "dense_weight": args.dense_weight if args.manual_fusion else None,
            "sparse_weight": args.sparse_weight if args.manual_fusion else None,
            "rerank_light": args.rerank_light,
        },
        "rerank_timings": rerank_stats,
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
    if rerank_stats:
        print(f"  rerank[{rerank_stats['model']}] median={rerank_stats['median_s']}s "
              f"max={rerank_stats['max_s']}s min={rerank_stats['min_s']}s "
              f"(n={len(rerank_timings)}, candidates={rerank_stats['candidates']})")
    print(f"  -> {out_path}")

    if args.baseline:
        print_diff(report, Path(args.baseline))

    if args.assert_thresholds:
        failures = check_thresholds(metrics, args.min_recall1, args.min_mrr10)
        if failures:
            print("\n[GATE FAIL] dérive mémoire détectée :", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            print(f"  rapport complet -> {out_path}", file=sys.stderr)
            return 3
        print(
            f"\n[GATE OK] recall@1={metrics['recall@1']:.4f} (>= {args.min_recall1:.4f})  "
            f"mrr@10={metrics['mrr@10']:.4f} (>= {args.min_mrr10:.4f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
