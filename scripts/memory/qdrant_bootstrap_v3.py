#!/usr/bin/env python3
"""Bootstrap idempotent de la collection memory_v3 (hybrid dense+sparse BM25).

Contrat normatif : docs/superpowers/specs/2026-06-10-rag-v3-contracts.md §Collection.
  - Vecteurs nommés : `dense` 768d Cosine (HNSW m=16, ef_construct=100 — identique v2)
                      + `bm25` sparse, modifier=idf.
  - on_disk_payload: true.
  - Index payload : keyword sur wing/room/doc_kind/repo/topic/tags/host_origin/source_kind
    (DROP legacy severity/category/phase) ; integer sur use_count ;
    datetime sur valid_from / last_used_at.

Idempotent : crée la collection si absente ; si présente, VÉRIFIE le schéma
(named dense 768 cosine + bm25 idf + on_disk_payload) et sort 1 en cas de mismatch
— jamais de drop/recreate. memory_v2 n'est JAMAIS touchée (invariant #5).

Connexion : env QDRANT_URL / QDRANT_API_KEY (mirror qdrant_rebuild.py) :
  set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a
  python scripts/memory/qdrant_bootstrap_v3.py [--collection memory_v3] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm
except ImportError:  # pragma: no cover
    sys.exit(
        "qdrant_client introuvable. Lance avec le venv du worker:\n"
        "  /opt/workstation/ai-memory-worker/.venv/bin/python "
        "scripts/memory/qdrant_bootstrap_v3.py"
    )

# --- Schéma cible (contrat 2026-06-10) -------------------------------------
TARGET_COLLECTION = "memory_v3"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
DENSE_DIM = 768
HNSW_M = 16
HNSW_EF_CONSTRUCT = 100

KEYWORD_INDEXES = [
    "wing", "room", "doc_kind", "repo", "topic", "tags", "host_origin", "source_kind",
]
INTEGER_INDEXES = ["use_count"]
DATETIME_INDEXES = ["valid_from", "last_used_at"]


def make_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    if not url:
        sys.exit(
            "QDRANT_URL absent. Charge l'env du worker:\n"
            "  set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a"
        )
    if not api_key:
        sys.exit("QDRANT_API_KEY absent (idem: charger memory-worker.env).")
    verify = os.getenv("QDRANT_VERIFY_TLS", "true").lower() == "true"
    timeout = int(os.getenv("QDRANT_TIMEOUT", "60"))
    return QdrantClient(
        url=url, api_key=api_key, timeout=timeout, verify=verify, check_compatibility=False
    )


def create_collection(client: QdrantClient, collection: str) -> None:
    client.create_collection(
        collection_name=collection,
        vectors_config={
            DENSE_VECTOR_NAME: qm.VectorParams(
                size=DENSE_DIM,
                distance=qm.Distance.COSINE,
                hnsw_config=qm.HnswConfigDiff(m=HNSW_M, ef_construct=HNSW_EF_CONSTRUCT),
            ),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: qm.SparseVectorParams(modifier=qm.Modifier.IDF),
        },
        on_disk_payload=True,
    )
    print(
        f"créé {collection} (dense={DENSE_DIM}d cosine hnsw m={HNSW_M} "
        f"ef={HNSW_EF_CONSTRUCT} + {SPARSE_VECTOR_NAME} sparse idf, on_disk_payload)"
    )


def verify_schema(client: QdrantClient, collection: str) -> list[str]:
    """Retourne la liste des écarts schéma (vide = conforme)."""
    issues: list[str] = []
    info = client.get_collection(collection)
    params = info.config.params

    vectors = params.vectors
    if not isinstance(vectors, dict):
        issues.append(f"vecteur UNNAMED (attendu vecteurs nommés '{DENSE_VECTOR_NAME}')")
    else:
        dense = vectors.get(DENSE_VECTOR_NAME)
        if dense is None:
            issues.append(f"vecteur nommé '{DENSE_VECTOR_NAME}' absent")
        else:
            if dense.size != DENSE_DIM:
                issues.append(f"dense.size={dense.size} (attendu {DENSE_DIM})")
            if dense.distance != qm.Distance.COSINE:
                issues.append(f"dense.distance={dense.distance} (attendu Cosine)")

    sparse = getattr(params, "sparse_vectors", None) or {}
    bm25 = sparse.get(SPARSE_VECTOR_NAME) if isinstance(sparse, dict) else None
    if bm25 is None:
        issues.append(f"vecteur sparse '{SPARSE_VECTOR_NAME}' absent")
    elif bm25.modifier != qm.Modifier.IDF:
        issues.append(f"bm25.modifier={bm25.modifier} (attendu idf)")

    if not getattr(params, "on_disk_payload", False):
        issues.append("on_disk_payload=false (attendu true)")
    return issues


def ensure_payload_indexes(client: QdrantClient, collection: str) -> None:
    plan = (
        [(f, qm.PayloadSchemaType.KEYWORD) for f in KEYWORD_INDEXES]
        + [(f, qm.PayloadSchemaType.INTEGER) for f in INTEGER_INDEXES]
        + [(f, qm.PayloadSchemaType.DATETIME) for f in DATETIME_INDEXES]
    )
    existing = client.get_collection(collection).payload_schema or {}
    for field, schema in plan:
        if field in existing:
            print(f"  index payload: {field} (déjà présent: {existing[field].data_type})")
            continue
        client.create_payload_index(collection, field_name=field, field_schema=schema)
        print(f"  index payload: {field} ({schema.value})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--collection", default=TARGET_COLLECTION)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="affiche le plan sans rien créer (aucune mutation Qdrant)",
    )
    args = parser.parse_args()

    if args.dry_run:
        print(f"[dry-run] collection={args.collection}")
        print(f"[dry-run] dense={DENSE_DIM}d cosine (m={HNSW_M}, ef={HNSW_EF_CONSTRUCT})")
        print(f"[dry-run] sparse={SPARSE_VECTOR_NAME} modifier=idf, on_disk_payload=true")
        print(f"[dry-run] keyword={KEYWORD_INDEXES}")
        print(f"[dry-run] integer={INTEGER_INDEXES} datetime={DATETIME_INDEXES}")
        return 0

    client = make_client()
    if client.collection_exists(args.collection):
        issues = verify_schema(client, args.collection)
        if issues:
            print(f"SCHEMA MISMATCH sur {args.collection} (existante, NON modifiée):")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        print(f"{args.collection} existe déjà — schéma conforme.")
    else:
        create_collection(client, args.collection)
    ensure_payload_indexes(client, args.collection)
    info = client.get_collection(args.collection)
    print(f"OK — {args.collection} points={info.points_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
