#!/usr/bin/env python3
"""Qdrant rebuild tool — Plan A / M2 (memory system rebuild).

Subcommands:
  --inventory   READ-ONLY. List every collection with point count + vector dim,
                classified MEMORY (wipe) / CACHE (wipe, regenerates) / APP (SPARE)
                / UNKNOWN (human review — never auto-touched).
  --snapshot    Snapshot the MEMORY collections only (rollback insurance). Safe.
  --create      Create memory_v2 (768d cosine) + the 6 payload indexes. Safe.
  --wipe        DESTRUCTIVE. Delete MEMORY + CACHE collections. Requires
                --confirm and a typed phrase. NEVER touches APP or UNKNOWN.

For deep per-collection reports (payload keys, samples, JSON/MD), use the existing
worker tool instead: roles/llamaindex-memory-worker/templates/inventory_collections.py.j2
(deployed at /opt/workstation/ai-memory-worker/). This tool focuses on the
rebuild-specific wipe classification (D9) + snapshot/wipe/create.

Connection mirrors search_memory.py: env QDRANT_URL / QDRANT_API_KEY (fallback to
config.yml). Load the worker env first:
  set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a

Spec: docs/superpowers/specs/2026-06-05-memory-system-rebuild-design.md (D9)
Plan: docs/superpowers/plans/2026-06-05-memory-rebuild-core.md (Task 2)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm
except ImportError:  # pragma: no cover
    sys.exit(
        "qdrant_client introuvable. Lance avec le venv du worker:\n"
        "  /opt/workstation/ai-memory-worker/.venv/bin/python "
        "scripts/memory/qdrant_rebuild.py --inventory"
    )

# --- Target schema (D2/D3 §3) ---------------------------------------------
TARGET_COLLECTION = "memory_v2"
TARGET_DIM = 768  # embeddinggemma-300m (D8)
PAYLOAD_INDEXES = ["wing", "room", "doc_kind", "repo", "topic", "tags"]

# --- Classification (spec §4 wipe perimeter, D9) --------------------------
# Exact names to wipe (memory/RAG perimeter).
MEMORY_EXACT = {
    "memory_v1",
    "mop_kb",
    "vpai_rex",
    "operational-rex",
    "rex_lessons",
    "dev-knowledge",
    "content_index",
}
# Suffix marking fragmented official-docs collections (e.g. comfyui-docs).
MEMORY_SUFFIXES = ("-docs",)
# Cache: wipe, LiteLLM regenerates it on demand.
CACHE_EXACT = {"semantic_cache"}
# APP collections — SPARE, never auto-touched (runtime app data, not re-ingestable).
# Spared by explicit human review 2026-06-05 (app/runtime data, not repo memory).
APP_EXACT = {"brand-voice", "model-registry", "palais_memory", "videoref_styles"}
APP_PREFIXES = (
    "jarvis-", "jarvis_", "flash-", "flash_",
    "app-factory", "zimboo", "macgyver",
)

WIPE_CONFIRM_PHRASE = "WIPE MEMORY"


def classify(name: str) -> str:
    """Return one of: TARGET, MEMORY, CACHE, APP, UNKNOWN."""
    if name == TARGET_COLLECTION:
        return "TARGET"
    if name in CACHE_EXACT:
        return "CACHE"
    if name in APP_EXACT or name.startswith(APP_PREFIXES):
        return "APP"
    if name in MEMORY_EXACT or name.endswith(MEMORY_SUFFIXES):
        return "MEMORY"
    return "UNKNOWN"


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
    timeout = int(os.getenv("QDRANT_TIMEOUT", "30"))
    # client 1.16.x vs server 1.18.x: skip the major/minor compat guard (read+admin ops OK).
    return QdrantClient(
        url=url, api_key=api_key, timeout=timeout, verify=verify, check_compatibility=False
    )


def _vector_dim(info) -> int | str:
    """Best-effort extraction of the vector size from get_collection()."""
    try:
        params = info.config.params.vectors
        if hasattr(params, "size"):  # single unnamed vector
            return params.size
        if isinstance(params, dict):  # named vectors
            return ", ".join(f"{k}:{v.size}" for k, v in params.items())
    except Exception:  # noqa: BLE001
        pass
    return "?"


def gather(client: QdrantClient) -> list[dict]:
    rows: list[dict] = []
    for c in client.get_collections().collections:
        name = c.name
        try:
            info = client.get_collection(name)
            dim = _vector_dim(info)
            count = client.count(name, exact=True).count
        except Exception as exc:  # noqa: BLE001
            dim, count = "ERR", f"err:{exc}"
        rows.append({"name": name, "class": classify(name), "dim": dim, "count": count})
    return rows


def cmd_inventory(client: QdrantClient, args: argparse.Namespace) -> int:
    rows = sorted(gather(client), key=lambda r: (r["class"], r["name"]))
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(r["class"], []).append(r)
    order = ["TARGET", "MEMORY", "CACHE", "APP", "UNKNOWN"]
    legend = {
        "TARGET": "→ collection cible (ne pas toucher au wipe)",
        "MEMORY": "→ WIPE (mémoire/RAG, ré-ingérable)",
        "CACHE": "→ WIPE (régénéré par LiteLLM)",
        "APP": "→ SPARE (données runtime apps, JAMAIS touché)",
        "UNKNOWN": "→ REVIEW HUMAIN (jamais auto-wipe)",
    }
    for cls in order:
        items = buckets.get(cls, [])
        if not items:
            continue
        print(f"\n== {cls} {legend[cls]} ==")
        for r in items:
            print(f"  {r['name']:<28} dim={str(r['dim']):<10} points={r['count']}")
    unknown = buckets.get("UNKNOWN", [])
    if unknown:
        print(
            f"\n⚠️  {len(unknown)} collection(s) UNKNOWN — à classer à la main "
            "avant tout wipe (ni MEMORY ni APP)."
        )
    print("\n(lecture seule — aucune modification effectuée)")
    return 0


def _memory_targets(client: QdrantClient) -> list[str]:
    return [r["name"] for r in gather(client) if r["class"] in {"MEMORY", "CACHE"}]


def cmd_snapshot(client: QdrantClient, args: argparse.Namespace) -> int:
    targets = [r["name"] for r in gather(client) if r["class"] == "MEMORY"]
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"created": datetime.now(timezone.utc).isoformat(), "snapshots": []}
    for name in targets:
        snap = client.create_snapshot(collection_name=name, wait=True)
        manifest["snapshots"].append(
            {"collection": name, "snapshot": getattr(snap, "name", str(snap))}
        )
        print(f"  snapshot {name} → {getattr(snap, 'name', snap)}")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest: {out / 'manifest.json'} ({len(targets)} collection(s))")
    print("NB: snapshots côté serveur Qdrant; télécharge-les pour un rollback offsite.")
    return 0


def cmd_create(client: QdrantClient, args: argparse.Namespace) -> int:
    if client.collection_exists(TARGET_COLLECTION):
        print(f"{TARGET_COLLECTION} existe déjà — rien à créer.")
    else:
        client.create_collection(
            collection_name=TARGET_COLLECTION,
            vectors_config=qm.VectorParams(size=TARGET_DIM, distance=qm.Distance.COSINE),
        )
        print(f"créé {TARGET_COLLECTION} (dim={TARGET_DIM}, cosine)")
    for field in PAYLOAD_INDEXES:
        try:
            client.create_payload_index(
                TARGET_COLLECTION, field_name=field, field_schema=qm.PayloadSchemaType.KEYWORD
            )
            print(f"  index payload: {field}")
        except Exception as exc:  # noqa: BLE001 (index may already exist)
            print(f"  index payload: {field} (skip: {exc})")
    info = client.get_collection(TARGET_COLLECTION)
    print(f"\nOK — {TARGET_COLLECTION} dim={_vector_dim(info)} indexes={PAYLOAD_INDEXES}")
    return 0


def cmd_wipe(client: QdrantClient, args: argparse.Namespace) -> int:
    targets = _memory_targets(client)
    print("Cibles WIPE (MEMORY + CACHE):")
    for n in targets:
        print(f"  - {n}")
    spared = [r["name"] for r in gather(client) if r["class"] in {"APP", "UNKNOWN"}]
    print(f"Épargnés (APP + UNKNOWN): {', '.join(spared) or '(aucun)'}")
    if args.confirm != WIPE_CONFIRM_PHRASE:
        print(f"\n⛔ REFUS — destructif. Relance:  --wipe --confirm '{WIPE_CONFIRM_PHRASE}'")
        return 2
    for name in targets:
        client.delete_collection(collection_name=name)
        print(f"  supprimé {name}")
    print(f"\nWipe terminé ({len(targets)} collection(s)). APP/UNKNOWN intacts.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--inventory", action="store_true", help="lister + classer (lecture seule)")
    g.add_argument("--snapshot", action="store_true", help="snapshot des collections MEMORY")
    g.add_argument("--create", action="store_true", help="créer memory_v2 + indexes")
    g.add_argument("--wipe", action="store_true", help="DESTRUCTIF: supprimer MEMORY+CACHE")
    p.add_argument("--json", action="store_true", help="(inventory) sortie JSON")
    p.add_argument("--out", default="~/qdrant-snapshots", help="(snapshot) dossier manifest")
    p.add_argument("--confirm", default="", help=f"(wipe) phrase: '{WIPE_CONFIRM_PHRASE}'")
    args = p.parse_args()

    client = make_client()
    if args.inventory:
        return cmd_inventory(client, args)
    if args.snapshot:
        return cmd_snapshot(client, args)
    if args.create:
        return cmd_create(client, args)
    if args.wipe:
        return cmd_wipe(client, args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
