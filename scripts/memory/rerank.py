#!/usr/bin/env python3
"""rerank.py — rerank optionnel des hits mémoire (bge-reranker-v2-m3 ONNX int8).

Contrat : docs/superpowers/specs/2026-06-10-rag-v3-contracts.md §Recherche.
  - Flag OFF par défaut (consommé par search_memory.py --rerank).
  - LAZY + fail-open : si le modèle n'est PAS déjà dans le cache HF local ->
    retourne None (le caller garde l'ordre RRF + log un warning). AUCUN download
    n'est jamais déclenché ici (HF_HUB_OFFLINE=1 sur Waza — REX 2026-06-07
    r0-interminable-mcp-orphelins-offline).
  - Top-30 -> top-k sur paires (query, document) via onnxruntime (CPU).

Résolution du modèle (premier qui matche) :
  1. env MEMORY_RERANK_MODEL_DIR : dossier contenant tokenizer.json + *.onnx
  2. cache HF (HF_HOME ou ~/.cache/huggingface) : models--<org>--<name> du repo
     env MEMORY_RERANK_MODEL_ID (défaut BAAI/bge-reranker-v2-m3), snapshot le plus
     récent contenant tokenizer.json + un .onnx (préférence aux noms *int8*/*quantized*).
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL_ID = os.getenv("MEMORY_RERANK_MODEL_ID", "BAAI/bge-reranker-v2-m3")
MAX_TOKENS = 512

_session = None
_tokenizer = None


def _find_onnx(model_dir: Path) -> Path | None:
    candidates = sorted(model_dir.rglob("*.onnx"))
    if not candidates:
        return None
    for pattern in ("int8", "quantized", "q8"):
        for candidate in candidates:
            if pattern in candidate.name.lower():
                return candidate
    return candidates[0]


def _resolve_model_dir() -> Path | None:
    override = os.getenv("MEMORY_RERANK_MODEL_DIR")
    if override:
        path = Path(override).expanduser()
        return path if path.is_dir() else None
    hf_home = Path(os.getenv("HF_HOME", "~/.cache/huggingface")).expanduser()
    repo_key = "models--" + DEFAULT_MODEL_ID.replace("/", "--")
    for base in (hf_home / "hub" / repo_key, hf_home / repo_key):
        snapshots = base / "snapshots"
        if not snapshots.is_dir():
            continue
        for snapshot in sorted(snapshots.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if (snapshot / "tokenizer.json").exists() and _find_onnx(snapshot):
                return snapshot
    return None


def _load() -> bool:
    """Charge session ONNX + tokenizer depuis le cache local. False = indisponible."""
    global _session, _tokenizer
    if _session is not None and _tokenizer is not None:
        return True
    model_dir = _resolve_model_dir()
    if model_dir is None:
        return False
    onnx_path = _find_onnx(model_dir)
    tokenizer_path = model_dir / "tokenizer.json"
    if onnx_path is None or not tokenizer_path.exists():
        return False
    try:  # imports lazy : onnxruntime/tokenizers viennent avec fastembed
        import onnxruntime  # type: ignore[import]
        from tokenizers import Tokenizer  # type: ignore[import]

        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        session = onnxruntime.InferenceSession(
            str(onnx_path), providers=["CPUExecutionProvider"]
        )
    except Exception:  # noqa: BLE001 — fail-open, le caller garde l'ordre RRF
        return False
    _session, _tokenizer = session, tokenizer
    return True


def rerank(query: str, documents: list[str], top_k: int = 5) -> list[tuple[int, float]] | None:
    """Rerank cross-encoder. Retourne [(index_document, score)] trié desc, ou None.

    None = modèle indisponible (absent du cache HF / erreur de chargement) — le
    caller DOIT conserver l'ordre d'origine et logger un warning (fail-open).
    """
    if not documents:
        return []
    if not _load():
        return None
    try:
        import numpy as np  # type: ignore[import]

        input_names = {inp.name for inp in _session.get_inputs()}
        scores: list[float] = []
        for document in documents:
            encoding = _tokenizer.encode(query, document)
            ids = np.array([encoding.ids], dtype=np.int64)
            mask = np.array([encoding.attention_mask], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in input_names:
                feeds["token_type_ids"] = np.array([encoding.type_ids], dtype=np.int64)
            logits = _session.run(None, feeds)[0]
            scores.append(float(np.asarray(logits).reshape(-1)[0]))
        order = sorted(range(len(documents)), key=lambda i: scores[i], reverse=True)
        return [(i, scores[i]) for i in order[:top_k]]
    except Exception:  # noqa: BLE001 — fail-open
        return None


if __name__ == "__main__":  # smoke manuel : python rerank.py "query" "doc1" "doc2"
    import sys

    if len(sys.argv) < 3:
        raise SystemExit("usage: rerank.py <query> <doc> [<doc>...]")
    result = rerank(sys.argv[1], list(sys.argv[2:]))
    print("indisponible (modèle absent du cache HF)" if result is None else result)
