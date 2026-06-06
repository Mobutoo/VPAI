#!/usr/bin/env python3
"""pod_ingest.py — batch d'ingestion mémoire bulk (pod CPU x86 -> Qdrant memory_v2).

Importe `memory_core` (module PARTAGÉ avec le worker Waza) : classify/chunk/encode/
payload/node_id sont STRICTEMENT identiques au worker. La seule différence voulue
est la plateforme du wheel torch (x86 vs ARM) -> valeurs vecteurs ~0.99999 cos
(accepté, non bit-exact). Le contrat d'identité (node_id) ne dépend QUE du texte
de chunk + (repo, relative_path) -> identique des deux côtés si les pins le sont.

PRÉREQUIS PARITÉ (sinon node_id divergent) :
  - Python 3.12.x + requirements.lock.txt (freeze du venv worker).
  - punkt nltk présent (cf README) — SentenceSplitter en dépend.
  - chaque source stagée EXACTEMENT à son root mappé (pas de double-nesting).

Connexion Qdrant via env (comme search_memory.py / qdrant_rebuild.py) :
  export QDRANT_URL=...  QDRANT_API_KEY=...  [QDRANT_VERIFY_TLS=true] [QDRANT_TIMEOUT=60]

Usage :
  # 1) preflight — vérifie roots + lookup, aucun upsert
  python pod_ingest.py --sources sources.pod.yml --preflight
  # 2) spot-check parité — dump déterministe node_id pour UN fichier (à diff Waza vs pod)
  python pod_ingest.py --sources sources.pod.yml --verify-sample /staging/VPAI/CLAUDE.md
  # 3) dry-run borné
  python pod_ingest.py --sources sources.pod.yml --dry-run --limit 50
  # 4) bulk
  python pod_ingest.py --sources sources.pod.yml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# memory_core est attendu à côté (scripts/memory/) — ajouter le parent au path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory_core import (  # noqa: E402
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    MAX_CHUNKS_PER_FILE,
    EmbeddingGemmaEncoder,
    build_chunks,
    build_repo_git_shas,
    classify_doc_kind,
    classify_room,
    extract_structural_meta,
    extract_topic,
    git_commit_sha,
    load_wing_room_lookup,
    ref_doc_id,
    resolve_source,
    sha256_file,
    to_text_nodes,
)

EMBEDDING_MODEL = "google/embeddinggemma-300m"
EMBEDDING_DIM = 768
NORMALIZE = True
HOST_ORIGIN = "waza"  # PARITÉ : doit rester "waza" (ref_doc_id/tags/node_id en dépendent)

# Miroir de config.yml.j2 payload_indexes (ordre indifférent).
PAYLOAD_INDEX_FIELDS = [
    "wing", "room", "doc_kind", "repo", "host_origin", "source_kind",
    "severity", "category", "phase", "topic", "tags",
    "functions", "classes", "imports", "exports", "variables",
]


def log(msg: str) -> None:
    print(f"[pod_ingest] {msg}", flush=True)


def build_client():
    from qdrant_client import QdrantClient

    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    if not url:
        sys.exit("QDRANT_URL absent (export depuis memory-worker.env).")
    if not api_key:
        sys.exit("QDRANT_API_KEY absent.")
    verify = os.getenv("QDRANT_VERIFY_TLS", "true").lower() == "true"
    timeout = int(os.getenv("QDRANT_TIMEOUT", "60"))
    return QdrantClient(
        url=url, api_key=api_key, timeout=timeout, verify=verify,
        check_compatibility=False,
    )


def build_vector_store(client, collection: str):
    from qdrant_client.http import models as rest
    from llama_index.vector_stores.qdrant import QdrantVectorStore

    payload_indexes = [
        {"field_name": f, "field_schema": rest.PayloadSchemaType.KEYWORD}
        for f in PAYLOAD_INDEX_FIELDS
    ]
    return QdrantVectorStore(
        collection_name=collection,
        client=client,
        index_doc_id=True,
        payload_indexes=payload_indexes,
    )


def process_one(file_abs: Path, lookup, encoder, host_origin: str, git_shas_by_root=None):
    """Construit les TextNode pour un fichier (embeddings inclus si encoder!=None).

    git_shas_by_root : dict {root: {rel: sha}} précalculé (1 traversée git/repo, cf
    build_repo_git_shas) — évite ~1 subprocess git/fichier (66% du temps bulk mesuré).
    None -> fallback git_commit_sha par-fichier (verify-sample/benchmark, parité testée).
    """
    resolved = resolve_source(file_abs, lookup)
    if resolved is None:
        return None
    repo, wing, rel = resolved
    if not wing:
        return None
    room = classify_room(wing, rel)
    try:
        text = file_abs.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    chunks = build_chunks(Path(rel), text, CHUNK_SIZE, CHUNK_OVERLAP, MAX_CHUNKS_PER_FILE)
    if not chunks:
        return None
    topic = extract_topic(repo, Path(rel), text, classify_doc_kind(Path(rel)))
    content_hash = sha256_file(file_abs)
    # git_sha : repo_root = root de la source (clone). "" si non-git (DOCS rsync) — non
    # inclus dans node_id (payload only), divergence acceptée vs worker pour ces sources.
    src_root = _source_root_for(file_abs, lookup)
    if git_shas_by_root is not None:
        git_sha = git_shas_by_root.get(src_root, {}).get(rel, "") if src_root else ""
    else:
        git_sha = git_commit_sha(src_root, file_abs) if src_root else ""
    struct_meta = extract_structural_meta(Path(rel), text)
    nodes = to_text_nodes(
        repo=repo,
        path=Path(rel),  # PARITÉ : chemin RELATIF (comme le worker) — classify_doc_kind en dépend
        relative_path=rel,
        wing=wing,
        room=room,
        topic=topic,
        content_hash=content_hash,
        git_sha=git_sha,
        chunks=chunks,
        struct_meta=struct_meta,
        embedding_model=EMBEDDING_MODEL,
        embedding_dim=EMBEDDING_DIM,
        host_origin=host_origin,
    )
    # Embeddings par batch (mêmes prompts que le worker via encoder partagé).
    if encoder is not None:
        embeddings = encoder.encode_documents([(n.metadata["title"], n.text) for n in nodes])
        for n, emb in zip(nodes, embeddings, strict=True):
            n.embedding = emb
    return repo, wing, room, rel, nodes


def _source_root_for(file_abs: Path, lookup) -> Path | None:
    resolved = file_abs.resolve()
    best = None
    for root in lookup:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if best is None or len(root.parts) > len(best.parts):
            best = root
    return best


def cmd_preflight(args, lookup) -> int:
    log(f"lookup: {len(lookup)} sources")
    missing = 0
    for root, meta in lookup.items():
        exists = root.exists()
        if not exists:
            missing += 1
        nfiles = 0
        if exists:
            from memory_core import iter_source_files
            nfiles = sum(1 for _ in iter_source_files(root))
        log(f"  {meta['name']:<14} wing={meta['wing']:<8} files={nfiles:<6} {'OK' if exists else 'MISSING'} {root}")
    if missing:
        log(f"FAIL — {missing} source root(s) absent (staging incomplet).")
        return 1
    log("preflight OK")
    return 0


def cmd_verify_sample(args, lookup) -> int:
    """Dump déterministe pour UN fichier — à exécuter sur Waza (venv worker) ET sur le pod,
    puis diff. node_ids + chunk_count + sha(chunk_text) identiques == parité prouvée."""
    f = Path(args.verify_sample).expanduser().resolve()
    if not f.exists():
        sys.exit(f"fichier absent: {f}")
    res = process_one(f, lookup, encoder=None, host_origin=args.host_origin)
    if res is None:
        sys.exit(f"fichier non indexable / hors source: {f}")
    repo, wing, room, rel, nodes = res
    out = {
        "repo": repo, "wing": wing, "room": room, "relative_path": rel,
        "ref_doc_id": ref_doc_id(repo, rel),
        "chunk_count": len(nodes),
        "nodes": [
            {
                "node_id": n.id_,
                "chunk_index": n.metadata["chunk_index"],
                "chunk_text_sha256": hashlib.sha256(n.text.encode("utf-8")).hexdigest(),
            }
            for n in nodes
        ],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_benchmark(args, lookup) -> int:
    """Bench HONNÊTE du chemin OPTIMISÉ sur CE hardware.

    Mirror exact du bulk optimisé : git SHAs précalculés + build CPU sans embed +
    encode BATCHÉ cross-fichier (batch_size=encode_batch). Sépare temps CPU (build :
    chunk+metadata) et GPU (encode) -> dit où est le goulot, pas juste un débit global.
    Reporte device + dtype. Fail-fast si EXPECT_CUDA=1 et GPU non utilisé / non-fp32.
    """
    n = args.benchmark
    encoder = EmbeddingGemmaEncoder(EMBEDDING_MODEL, NORMALIZE)
    try:
        param = next(encoder.model.parameters())
        device = str(param.device)
        dtype = str(param.dtype)
    except Exception:  # noqa: BLE001
        device, dtype = "unknown", "unknown"

    expect_cuda = os.environ.get("EXPECT_CUDA", "") == "1"
    if expect_cuda and not device.startswith("cuda"):
        log(f"FAIL EXPECT_CUDA=1 mais device={device} (GPU non utilisé) — abort fail-fast")
        return 2
    if expect_cuda and dtype != "torch.float32":
        log(f"FAIL EXPECT_CUDA=1 mais dtype={dtype} (≠ fp32) — vecteurs divergents vs Waza/CPU, abort")
        return 2

    from memory_core import iter_source_files

    git_shas_by_root = {root: build_repo_git_shas(root) for root in lookup if root.exists()}
    files = chunks = 0
    t_cpu = t_gpu = 0.0
    buf: list = []
    for root, meta in lookup.items():
        if not root.exists() or files >= n:
            continue
        for file_abs in iter_source_files(root):
            if files >= n:
                break
            s = time.monotonic()
            res = process_one(file_abs, lookup, None, args.host_origin, git_shas_by_root)
            t_cpu += time.monotonic() - s
            if res is None:
                continue
            files += 1
            buf.extend(res[4])
            chunks += len(res[4])

    prompts = [(x.metadata["title"], x.text) for x in buf]
    fp32_vecs = []
    if prompts:  # encode fp32 batché (gros matmul) — mesure du débit GPU réel
        s = time.monotonic()
        fp32_vecs = encoder.encode_documents(prompts, batch_size=args.encode_batch)
        t_gpu += time.monotonic() - s
    dur = t_cpu + t_gpu
    rate = chunks / max(1e-6, dur)
    enc_rate = chunks / max(1e-6, t_gpu)

    # MESURE bf16 (cuda only) : dérive vecteurs + débit. EmbeddingGemma est Gemma-dérivé
    # (bf16-natif) -> bf16 active les tensor cores L4 (30->~240 TFLOP). Gate qualité =
    # dérive cosinus MESURÉE (pas dogme fp32). min>0.999 -> bf16 sûr pour mixer avec les
    # vecteurs worker fp32. Vecteurs normalisés -> cosinus = produit scalaire.
    drift = "skip(non-cuda)"
    bf16_rate = 0.0
    if device.startswith("cuda") and fp32_vecs:
        try:
            import numpy as np, torch
            samp = min(400, len(prompts))
            s = time.monotonic()
            with torch.autocast("cuda", dtype=torch.bfloat16):
                bf16_vecs = encoder.encode_documents(prompts[:samp], batch_size=args.encode_batch)
            bf16_rate = samp / max(1e-6, time.monotonic() - s)
            a = np.array(fp32_vecs[:samp]); b = np.array(bf16_vecs)
            cos = (a * b).sum(axis=1)  # normalisés -> dot = cosinus
            drift = f"min={cos.min():.5f} mean={cos.mean():.5f} n={samp}"
        except Exception as exc:  # noqa: BLE001
            drift = f"ERR {type(exc).__name__}: {exc}"

    log(
        f"BENCH files={files} chunks={chunks} dur={dur:.1f}s rate={rate:.1f} "
        f"cpu_build={t_cpu:.1f}s gpu_encode={t_gpu:.1f}s enc_rate={enc_rate:.1f} "
        f"batch={args.encode_batch} device={device} dtype={dtype} "
        f"bf16_drift=[{drift}] bf16_rate={bf16_rate:.1f}"
    )
    return 0


def cmd_ingest(args, lookup) -> int:
    encoder = None if args.dry_run else EmbeddingGemmaEncoder(EMBEDDING_MODEL, NORMALIZE)
    vector_store = None
    if not args.dry_run:
        client = build_client()
        vector_store = build_vector_store(client, args.collection)
        log(f"qdrant connected -> collection={args.collection}")

    from memory_core import iter_source_files

    # PHASE GIT : 1 traversée git/repo (au lieu de ~1 subprocess/fichier = 66% du temps
    # bulk mesuré 2026-06-06). Parité stricte vérifiée vs git_commit_sha (300/300).
    t_git = time.monotonic()
    git_shas_by_root = {root: build_repo_git_shas(root) for root in lookup if root.exists()}
    log(f"git SHAs précalculés: {sum(len(d) for d in git_shas_by_root.values())} fichiers "
        f"/ {len(git_shas_by_root)} repos en {time.monotonic()-t_git:.1f}s")

    seen = indexed_files = indexed_chunks = skipped = errors = 0
    t_cpu = t_gpu = 0.0  # instrumentation : build (CPU) vs encode (GPU)
    pending: list = []   # TextNode SANS embedding, accumulés cross-fichier
    t0 = time.monotonic()

    def flush():
        """Encode TOUT le buffer en 1 appel (gros matmul GPU) puis upsert."""
        nonlocal pending, t_gpu
        if not pending:
            return
        if encoder is not None:
            s = time.monotonic()
            embs = encoder.encode_documents(
                [(n.metadata["title"], n.text) for n in pending], batch_size=args.encode_batch
            )
            for n, e in zip(pending, embs, strict=True):
                n.embedding = e
            t_gpu += time.monotonic() - s
        if vector_store is not None:
            vector_store.add(pending)
        pending = []

    for root, meta in lookup.items():
        if not root.exists():
            log(f"WARN source absente, ignorée: {meta['name']} {root}")
            continue
        for file_abs in iter_source_files(root):
            if args.limit and seen >= args.limit:
                break
            seen += 1
            try:
                # encoder=None -> build SANS embedding (encode batché au flush)
                s = time.monotonic()
                res = process_one(file_abs, lookup, None, args.host_origin, git_shas_by_root)
                t_cpu += time.monotonic() - s
            except Exception as exc:  # noqa: BLE001
                errors += 1
                log(f"ERROR {file_abs}: {type(exc).__name__}: {exc}")
                continue
            if res is None:
                skipped += 1
                continue
            _, _, _, rel, nodes = res
            indexed_files += 1
            indexed_chunks += len(nodes)
            if args.dry_run:
                if seen % 500 == 0:
                    log(f"dry-run seen={seen} files={indexed_files} chunks={indexed_chunks}")
                continue
            pending.extend(nodes)
            if len(pending) >= args.flush_chunks:
                flush()
            if seen % 500 == 0:
                el = time.monotonic() - t0
                log(f"seen={seen} files={indexed_files} chunks={indexed_chunks} "
                    f"({indexed_chunks/max(1e-6,el):.0f} ch/s | cpu={t_cpu:.0f}s gpu={t_gpu:.0f}s)")
        if args.limit and seen >= args.limit:
            break
    flush()
    dur = time.monotonic() - t0
    log(
        f"DONE seen={seen} indexed_files={indexed_files} indexed_chunks={indexed_chunks} "
        f"skipped={skipped} errors={errors} dur={dur:.0f}s "
        f"cpu_build={t_cpu:.0f}s gpu_encode={t_gpu:.0f}s "
        f"({indexed_chunks/max(1e-6,dur):.1f} ch/s) dry_run={args.dry_run}"
    )
    return 1 if errors else 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bulk memory ingestion pod -> Qdrant memory_v2.")
    p.add_argument("--sources", required=True, help="sources.pod.yml (mapping root->wing/name).")
    p.add_argument("--collection", default="memory_v2")
    p.add_argument("--batch-size", type=int, default=128, help="(déprécié) points par upsert — voir --flush-chunks.")
    p.add_argument("--flush-chunks", type=int, default=1024, help="chunks accumulés avant encode batché + upsert.")
    p.add_argument("--encode-batch", type=int, default=64, help="batch_size GPU (256 OOM sur L4 24GB avec seq 2048 ; 64 = 1/4 footprint, sûr).")
    p.add_argument("--limit", type=int, default=0, help="max fichiers (0 = illimité).")
    p.add_argument("--host-origin", default=HOST_ORIGIN, help="PARITÉ: garder 'waza'.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--preflight", action="store_true", help="vérifie roots/lookup puis sort.")
    p.add_argument("--verify-sample", help="dump déterministe node_id pour UN fichier puis sort.")
    p.add_argument("--benchmark", type=int, default=0, help="bench chemin optimisé sur N vrais fichiers puis sort.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    lookup = load_wing_room_lookup(args.sources)
    if not lookup:
        sys.exit(f"lookup vide — {args.sources} introuvable ou sans `sources:`/`wing:`.")
    if args.preflight:
        return cmd_preflight(args, lookup)
    if args.verify_sample:
        return cmd_verify_sample(args, lookup)
    if args.benchmark:
        return cmd_benchmark(args, lookup)
    return cmd_ingest(args, lookup)


if __name__ == "__main__":
    sys.exit(main())
