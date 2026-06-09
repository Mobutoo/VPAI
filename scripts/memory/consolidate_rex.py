#!/usr/bin/env python3
"""consolidate_rex.py — Consolidation hebdo des REX (contrat RAG v3 2026-06-10).

Lit les `docs/rex/*.md` modifiés depuis moins de N jours (défaut 14), les groupe
par topic (frontmatter `topic:` prioritaire, sinon slug dérivé du nom de fichier),
appelle LiteLLM (proxy OpenAI-compatible, modèle économique) pour produire une
synthèse de 5 à 10 lignes par topic, et écrit `docs/memory-consolidated/<topic>.md`
avec frontmatter (`consolidated: true`, `sources: [...]`). Le worker mémoire
indexe ensuite ces fichiers comme n'importe quel doc (doc_kind auto `doc`).

Idempotent : un topic est sauté si sa synthèse est plus récente que TOUTES ses
sources (mtime). `--force` regénère tout.

Config (env — chargée par systemd via EnvironmentFile=memory-worker.env) :
  LITELLM_BASE_URL  (défaut https://llm.ewutelo.cloud/v1)
  LITELLM_API_KEY   (REQUIS hors --dry-run)
  LITELLM_MODEL     (défaut claude-haiku — modèle économique, cap budget LiteLLM)

Usage :
  consolidate_rex.py --rex-dir ~/work/infra/VPAI/docs/rex \
      --out-dir ~/work/infra/VPAI/docs/memory-consolidated [--max-age-days 14] \
      [--model claude-haiku] [--dry-run] [--force]

Budget : 1 run/semaine (timer systemd-user), gardé par le cap LiteLLM existant.
Stdlib uniquement — tourne sur le venv worker sans dépendance supplémentaire.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE_URL = "https://llm.ewutelo.cloud/v1"
DEFAULT_MODEL = "claude-haiku"
DEFAULT_MAX_AGE_DAYS = 14
# Bornes prompt : chaque REX tronqué, total du groupe capé (modèle économique).
MAX_CHARS_PER_FILE = 8000
MAX_CHARS_PER_TOPIC = 24000
HTTP_TIMEOUT_S = 120
HTTP_RETRIES = 2

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}[a-z]?", re.IGNORECASE)
FRONTMATTER_TOPIC_RE = re.compile(r"^topic:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", re.MULTILINE)

SYSTEM_PROMPT = (
    "Tu consolides des retours d'expérience (REX) techniques d'une stack "
    "self-hosted (Ansible, Docker, n8n, Qdrant, LiteLLM, Raspberry Pi). "
    "Produis une synthèse en français de 5 à 10 lignes MAXIMUM : faits établis, "
    "pièges identifiés, décisions prises, commandes/valeurs critiques. "
    "Pas de préambule, pas de conclusion, pas de markdown lourd — des lignes "
    "denses et factuelles (puces '- ' acceptées). Ne rien inventer : uniquement "
    "ce qui figure dans les extraits fournis."
)


def log(message: str) -> None:
    print(f"[consolidate-rex] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consolidation des REX récents via LiteLLM.")
    parser.add_argument("--rex-dir", required=True, help="Répertoire docs/rex à scanner")
    parser.add_argument("--out-dir", required=True, help="Répertoire docs/memory-consolidated de sortie")
    parser.add_argument("--max-age-days", type=int,
                        default=int(os.environ.get("CONSOLIDATE_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS)),
                        help=f"Fenêtre de fraîcheur des REX (défaut {DEFAULT_MAX_AGE_DAYS} jours)")
    parser.add_argument("--model", default=os.environ.get("LITELLM_MODEL", DEFAULT_MODEL),
                        help=f"Modèle LiteLLM économique (défaut {DEFAULT_MODEL})")
    parser.add_argument("--base-url", default=os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL),
                        help="Base URL du proxy LiteLLM (OpenAI-compatible)")
    parser.add_argument("--force", action="store_true",
                        help="Regénère même si la synthèse est plus récente que les sources")
    parser.add_argument("--dry-run", action="store_true",
                        help="Liste les topics/fichiers sans appeler LiteLLM ni écrire")
    return parser.parse_args()


def topic_from_filename(path: Path) -> str:
    """Slug topic dérivé du nom de fichier REX.

    REX-SESSION-2026-06-06-memory-bulk-gpu-bf16.md -> memory-bulk-gpu-bf16
    REX-MOP-AUDIT-2026-04-11.md                    -> mop-audit
    REX-SESSION-2026-02-23b.md                     -> rex-session-2026-02-23b (fallback stem)
    """
    stem = path.stem
    slug = re.sub(r"^REX-", "", stem, flags=re.IGNORECASE)
    slug = re.sub(r"^SESSION-", "", slug, flags=re.IGNORECASE)
    slug = DATE_RE.sub("", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-").lower()
    if not slug:
        slug = stem.lower()
    return sanitize_topic(slug)


def sanitize_topic(raw: str) -> str:
    """Topic -> nom de fichier sûr (pas de séparateurs, pas d'espaces)."""
    slug = raw.strip().lower().replace(" ", "-").replace("/", "-")
    slug = re.sub(r"[^a-z0-9._-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-.")
    return slug or "divers"


def topic_for(path: Path, text: str) -> str:
    """Frontmatter `topic:` prioritaire, sinon slug du nom de fichier."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            match = FRONTMATTER_TOPIC_RE.search(text[3:end])
            if match:
                return sanitize_topic(match.group(1))
    return topic_from_filename(path)


@dataclass
class RexFile:
    path: Path
    mtime: float
    text: str


def collect_recent(rex_dir: Path, max_age_days: int) -> dict[str, list[RexFile]]:
    cutoff = time.time() - max_age_days * 86400
    groups: dict[str, list[RexFile]] = {}
    for path in sorted(rex_dir.glob("*.md")):
        mtime = path.stat().st_mtime
        if mtime < cutoff:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        topic = topic_for(path, text)
        groups.setdefault(topic, []).append(RexFile(path=path, mtime=mtime, text=text))
    return groups


def is_fresh(out_file: Path, sources: list[RexFile]) -> bool:
    """True si la synthèse existe et est plus récente que TOUTES ses sources."""
    if not out_file.exists():
        return False
    return out_file.stat().st_mtime >= max(item.mtime for item in sources)


def build_user_prompt(topic: str, sources: list[RexFile]) -> str:
    parts = [f"Topic : {topic}. Synthétise les REX suivants (5-10 lignes au total) :"]
    budget = MAX_CHARS_PER_TOPIC
    for item in sources:
        excerpt = item.text[:min(MAX_CHARS_PER_FILE, budget)]
        budget -= len(excerpt)
        parts.append(f"\n=== {item.path.name} ===\n{excerpt}")
        if budget <= 0:
            parts.append("\n[extraits suivants tronqués — budget prompt atteint]")
            break
    return "\n".join(parts)


def call_litellm(base_url: str, api_key: str, model: str, user_prompt: str) -> str:
    """POST /chat/completions (proxy LiteLLM OpenAI-compatible). Retry simple."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps({
        "model": model,
        "max_tokens": 600,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, HTTP_RETRIES + 1):
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
                body = json.loads(response.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"].strip()
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
            last_error = exc
            log(f"appel LiteLLM échoué (tentative {attempt}/{HTTP_RETRIES}): {exc}")
            time.sleep(5 * attempt)
    raise RuntimeError(f"LiteLLM injoignable après {HTTP_RETRIES} tentatives: {last_error}")


def write_consolidated(out_file: Path, topic: str, model: str,
                       sources: list[RexFile], synthesis: str) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    source_names = [item.path.name for item in sources]
    lines = [
        "---",
        "consolidated: true",
        f"topic: {topic}",
        f"generated_at: {generated_at}",
        f"model: {model}",
        "sources:",
    ]
    lines += [f"  - docs/rex/{name}" for name in source_names]
    lines += [
        "---",
        "",
        f"# Synthèse consolidée — {topic}",
        "",
        synthesis,
        "",
    ]
    out_file.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    rex_dir = Path(args.rex_dir).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    if not rex_dir.is_dir():
        log(f"ERREUR: rex-dir introuvable: {rex_dir}")
        return 1

    groups = collect_recent(rex_dir, args.max_age_days)
    if not groups:
        log(f"aucun REX modifié depuis {args.max_age_days} jours dans {rex_dir} — rien à faire")
        return 0

    api_key = os.environ.get("LITELLM_API_KEY", "")
    if not args.dry_run and not api_key:
        log("ERREUR: LITELLM_API_KEY absent de l'environnement (memory-worker.env)")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    written = 0
    skipped = 0
    for topic, sources in sorted(groups.items()):
        out_file = out_dir / f"{topic}.md"
        if not args.force and is_fresh(out_file, sources):
            skipped += 1
            log(f"skip (à jour): {topic} ({len(sources)} source(s))")
            continue
        if args.dry_run:
            names = ", ".join(item.path.name for item in sources)
            log(f"dry-run: {topic} <- {names}")
            continue
        try:
            synthesis = call_litellm(args.base_url, api_key, args.model,
                                     build_user_prompt(topic, sources))
            write_consolidated(out_file, topic, args.model, sources, synthesis)
            written += 1
            log(f"écrit: {out_file} ({len(sources)} source(s))")
        except RuntimeError as exc:
            failures += 1
            log(f"ERREUR topic {topic}: {exc}")

    log(f"bilan: {written} écrit(s), {skipped} à jour, {failures} échec(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
