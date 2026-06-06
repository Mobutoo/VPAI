#!/usr/bin/env python3
"""memory_core.py — module partagé worker Waza + batch pod GPU/CPU.

Contient la logique canonique d'ingestion mémoire (taxonomie wing/room,
classify_doc_kind, payload, chunking, encodeur) extraite de index.py.j2.
ZÉRO Jinja2 — importable directement par worker ET batch pod.

Parité absolue : les imports ML (sentence-transformers, llama-index) sont
lazy-importés à l'intérieur des fonctions/classes qui en ont besoin.
Les 4 fonctions pures (classify_doc_kind, classify_room, load_wing_room_lookup,
build_payload) ne dépendent que de stdlib + pyyaml.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constantes module-level (importables par worker et batch pod)
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "memory_v2"
CHUNKING_STRATEGY_VERSION = "2026-04-09"
CHUNK_SIZE = 1600
CHUNK_OVERLAP = 200


# ---------------------------------------------------------------------------
# 1. classify_doc_kind — copie exacte de index.py.j2
# ---------------------------------------------------------------------------
def classify_doc_kind(path: Path) -> str:
    """Dérive le doc_kind d'un fichier depuis son chemin (copie exacte de index.py.j2)."""
    path_str = path.as_posix()
    path_lower = path_str.lower()
    suffix = path.suffix.lower()
    if (
        "rex" in path_lower
        or path.name.upper() == "LESSONS.MD"
        or any(part.lower() == "rex" for part in path.parts)
    ):
        return "rex"
    if path_str.startswith("docs/plans/"):
        return "plan"
    if path_str.startswith("docs/specs/"):
        return "spec"
    if path_str.startswith("scripts/n8n-workflows/"):
        return "workflow"
    if suffix in {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".sh", ".sql"}:
        return "code"
    if suffix in {".yml", ".yaml", ".j2", ".env", ".toml", ".ini", ".json"}:
        return "config"
    if suffix in {".md", ".rst", ".txt"}:
        return "doc"
    return "doc"


# ---------------------------------------------------------------------------
# 2. classify_room — NOUVEAU, implémente §3 du manifeste taxonomie
# ---------------------------------------------------------------------------
def classify_room(wing: str, relative_path: str) -> str:
    """Dérive le room depuis (wing, relative_path).

    Ordre = première règle qui matche, fallback par wing. Jamais nul.
    Source canonique : docs/runbooks/MEMORY-TAXONOMY-MANIFEST.md §3.
    """
    rp = relative_path.replace("\\", "/")
    rp_lower = rp.lower()

    # ------------------------------------------------------------------
    # wing infra (VPAI)
    # ------------------------------------------------------------------
    if wing == "infra":
        # roles/caddy* OU contient "caddy"
        if re.match(r"roles/caddy", rp) or "caddy" in rp_lower:
            return "caddy-vpn"
        # roles/postgres*
        if re.match(r"roles/postgres", rp):
            return "postgres"
        # roles/{grafana,loki,prometheus,alloy,victoriametrics,cadvisor,monitoring}*
        if re.match(
            r"roles/(grafana|loki|prometheus|alloy|victoriametrics|cadvisor|monitoring)",
            rp,
        ):
            return "monitoring"
        # roles/docker* ou docker-stack
        if re.match(r"roles/docker", rp) or "docker-stack" in rp_lower:
            return "docker"
        # contient "n8n" (roles/scripts)
        if "n8n" in rp_lower:
            return "n8n"
        # roles/* (autres)
        if re.match(r"roles/", rp):
            return "ansible-roles"
        # playbooks/*
        if re.match(r"playbooks/", rp):
            return "deploy"
        # docs/TROUBLESHOOTING* ou "troubleshooting" dans le chemin
        if re.match(r"docs/TROUBLESHOOTING", rp) or "troubleshooting" in rp_lower:
            return "troubleshooting"
        # docs/*, .planning/* (autres)
        if re.match(r"docs/", rp) or re.match(r"\.planning/", rp):
            return "deploy"
        # défaut
        return "ansible-roles"

    # ------------------------------------------------------------------
    # wing saas (room = concern)
    # ------------------------------------------------------------------
    if wing == "saas":
        if re.search(r"rag|memory|qdrant|embed|mind_state", rp_lower):
            return "rag"
        if re.search(r"api|server|routes|handler|endpoint", rp_lower):
            return "api"
        if re.search(r"web|frontend|ui|components|app/", rp_lower):
            return "frontend"
        if re.search(r"pipeline|worker|scheduler|ingest|llama-worker", rp_lower):
            return "pipeline"
        if re.search(r"PRD|ARCHITECTURE|\.planning|README|docs", rp):
            return "prd-arch"
        return "api"

    # ------------------------------------------------------------------
    # wing refdocs (room = techno)
    # ------------------------------------------------------------------
    if wing == "refdocs":
        # typebot-docs (en premier car contient "-docs")
        if re.match(r"typebot-docs/", rp) or rp_lower.startswith("typebot-docs"):
            return "typebot"
        # DOCS : 1er segment de chemin sans suffixe "-docs"
        # Condition : le chemin doit avoir au moins un "/" (sous-dossier présent)
        # sinon c'est un fichier isolé sans contexte techno → fallback misc
        # ex: "n8n-docs/x.md" → "n8n" ; "litellm-docs/y.md" → "litellm" ; "wiki/z.md" → "wiki"
        parts = rp.split("/")
        if len(parts) >= 2:
            first_seg = parts[0]
            # retirer le suffixe -docs si présent
            techno = re.sub(r"-docs$", "", first_seg, flags=re.IGNORECASE)
            if techno:
                return techno
        return "misc"

    # ------------------------------------------------------------------
    # wing tools
    # ------------------------------------------------------------------
    if wing == "tools":
        if "n8n" in rp_lower:
            return "n8n-workflows"
        if rp_lower.endswith(".sh") or re.match(r"scripts/", rp):
            return "scripts"
        if "mcp" in rp_lower:
            return "mcp"
        return "cli"

    # ------------------------------------------------------------------
    # Fallback ultime (wing inconnu)
    # ------------------------------------------------------------------
    return "misc"


# ---------------------------------------------------------------------------
# 3. load_wing_room_lookup — charge sources.yml, retourne mapping path→{wing,name}
# ---------------------------------------------------------------------------
def load_wing_room_lookup(sources_path: str | Path) -> dict[Path, dict[str, str]]:
    """Charge sources.yml et retourne {Path(root).expanduser().resolve(): {wing, name}}.

    Room est dérivé par fichier (classify_room), pas stocké ici.
    """
    import yaml  # stdlib-safe, lazy import en cas de venv minimal

    path = Path(sources_path).expanduser()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}

    lookup: dict[Path, dict[str, str]] = {}
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        root_raw = source.get("root")
        name = source.get("name", "")
        wing = source.get("wing", "")
        if not root_raw:
            continue
        resolved = Path(root_raw).expanduser().resolve()
        lookup[resolved] = {"wing": wing, "name": name}
    return lookup


# ---------------------------------------------------------------------------
# 4. Helpers utilitaires (partagés, extraits de index.py.j2)
# ---------------------------------------------------------------------------
def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_topic(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ")).strip(" /:#-_\t")
    if not cleaned:
        return ""
    if len(cleaned) > 80:
        return ""
    return cleaned


def first_markdown_h1(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            return normalize_topic(stripped[2:])
        if not stripped.startswith(("#", ">", "-", "*", "`", "```")):
            break
    return ""


def extract_topic(repo: str, path: Path, text: str, doc_kind: str) -> str:
    """Extrait un topic (copie exacte de index.py.j2)."""
    if doc_kind in {"doc", "rex", "plan", "spec", "official-docs"}:
        h1 = first_markdown_h1(text)
        if h1:
            return h1

    parts = path.parts
    if len(parts) >= 2 and parts[0] == "roles":
        role_name = normalize_topic(parts[1])
        if role_name:
            return role_name

    generic_parents = {
        "src", "tests", "docs", "scripts", "templates", "defaults",
        "tasks", "handlers", "files", "vars", "reference_data", "assets",
    }
    if len(parts) >= 2:
        parent = normalize_topic(parts[-2])
        if parent and parent.lower() not in generic_parents and parent.lower() != repo.lower():
            return parent

    return normalize_topic(repo)


def source_kind_for(doc_kind: str) -> str:
    if doc_kind == "code":
        return "repo"
    if doc_kind == "official-docs":
        return "official-docs"
    return "repo-doc"


def detect_language(path: Path) -> str:
    mapping = {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".go": "go",
        ".sh": "shell", ".sql": "sql", ".yml": "yaml", ".yaml": "yaml",
        ".j2": "jinja2", ".json": "json", ".md": "markdown",
        ".rst": "rst", ".txt": "text",
    }
    return mapping.get(path.suffix.lower(), "text")


def build_tags(repo: str, doc_kind: str, language: str) -> list[str]:
    tags = [f"repo:{repo}", "host:waza", f"kind:{doc_kind}", f"lang:{language}"]
    if repo == "VPAI":
        tags.append("scope:infra")
    if repo == "flash-studio":
        tags.append("scope:flash")
    if repo == "story-engine":
        tags.append("scope:story-engine")
    if repo == "ops":
        tags.append("scope:ops")
    return sorted(set(tags))


def ref_doc_id(repo: str, relative_path: str) -> str:
    return f"waza:{repo}:{relative_path}"


# ---------------------------------------------------------------------------
# 5. build_payload — assemble le dict metadata complet (manifeste §1)
# ---------------------------------------------------------------------------
def build_payload(
    *,
    wing: str,
    room: str,
    repo: str,
    relative_path: str,
    path: Path,
    topic: str,
    tags: list[str],
    chunk_index: int,
    chunk_count: int,
    chunk_kind: str,
    section: str | None,
    chunk_title: str,
    content_hash: str,
    git_sha: str,
    struct_meta: dict[str, list[str]] | None = None,
    # paramètres injectés (non hardcodés — parité worker/pod)
    embedding_model: str = "google/embeddinggemma-300m",
    embedding_dim: int = 768,
    host_origin: str = "waza",
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> dict[str, Any]:
    """Assemble le payload complet du drawer (manifeste §1).

    wing et room NE PEUVENT PAS être nuls (assertion runtime).
    valid_to=None = drawer vivant.
    """
    assert wing, "wing ne peut pas être nul (manifeste §5)"
    assert room, "room ne peut pas être nul (manifeste §5)"

    doc_kind = classify_doc_kind(path)
    language = detect_language(path)
    source_kind = source_kind_for(doc_kind)
    ref_id = ref_doc_id(repo, relative_path)
    _now = valid_from or utcnow_iso()
    sm = struct_meta or {}

    return {
        # --- axes taxonomie (manifeste §1) ---
        "wing": wing,
        "room": room,
        "doc_kind": doc_kind,
        "repo": repo,
        "relative_path": relative_path,
        "topic": topic,
        "tags": tags,
        "valid_from": _now,
        "valid_to": valid_to,
        # --- champs legacy conservés (manifeste §1) ---
        "schema_version": SCHEMA_VERSION,
        "embedding_model": embedding_model,
        "embedding_dim": embedding_dim,
        "chunking_strategy_version": CHUNKING_STRATEGY_VERSION,
        "ref_doc_id": ref_id,
        "namespace": repo,
        "host_origin": host_origin,
        "source_kind": source_kind,
        "filename": path.name,
        "severity": "",
        "category": "",
        "phase": "",
        # --- champs chunk ---
        "language": language,
        "chunk_index": chunk_index,
        "chunk_count": chunk_count,
        "chunking_kind": chunk_kind,
        "section": section or "",
        "title": chunk_title,
        "content_hash": content_hash,
        "git_commit_sha": git_sha,
        "indexed_at": _now,
        # --- structural meta ---
        "functions": sm.get("functions", []),
        "classes": sm.get("classes", []),
        "imports": sm.get("imports", []),
        "exports": sm.get("exports", []),
        "variables": sm.get("variables", []),
    }


# ---------------------------------------------------------------------------
# 6. Chunk dataclass (partagé worker/pod)
# ---------------------------------------------------------------------------
@dataclass
class Chunk:
    title: str
    text: str
    chunk_kind: str
    section: str | None
    chunk_index: int
    chunk_count: int


# ---------------------------------------------------------------------------
# 7. Chunking — fonctions extraites de index.py.j2 (lazy-import llama-index)
# ---------------------------------------------------------------------------
def sliding_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Chunking glissant simple (pas de dépendance ML)."""
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end]
        if end < len(text):
            last_newline = chunk.rfind("\n")
            last_sentence = chunk.rfind(". ")
            boundary = max(last_newline, last_sentence)
            if boundary > chunk_size // 2:
                end = start + boundary + 1
                chunk = text[start:end]
        cleaned = chunk.strip()
        if cleaned:
            chunks.append(cleaned)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def llama_sentence_chunks(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[tuple[str | None, str]]:
    """Chunking par phrase via llama-index (lazy-import)."""
    from llama_index.core import Document  # type: ignore[import]
    from llama_index.core.node_parser import SentenceSplitter  # type: ignore[import]

    splitter = SentenceSplitter.from_defaults(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        include_metadata=True,
        include_prev_next_rel=False,
    )
    nodes = splitter.get_nodes_from_documents([Document(text=text)])
    chunks: list[tuple[str | None, str]] = []
    for node in nodes:
        content = node.text.strip()
        if content:
            chunks.append((None, content))
    return chunks or [(None, text)]


def llama_markdown_chunks(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[tuple[str | None, str]]:
    """Chunking markdown-section via llama-index (lazy-import)."""
    from llama_index.core import Document  # type: ignore[import]
    from llama_index.core.node_parser import (  # type: ignore[import]
        MarkdownNodeParser,
        SentenceSplitter,
    )

    markdown_parser = MarkdownNodeParser.from_defaults(
        include_metadata=True,
        include_prev_next_rel=False,
    )
    splitter = SentenceSplitter.from_defaults(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        include_metadata=True,
        include_prev_next_rel=False,
    )
    base_doc = Document(text=text)
    sections = markdown_parser.get_nodes_from_documents([base_doc])
    chunks: list[tuple[str | None, str]] = []
    for section in sections:
        section_text = section.text.strip()
        if not section_text:
            continue
        header_path = ""
        metadata = getattr(section, "metadata", {}) or {}
        for key in ("header_path", "header_path_separator", "section", "headers"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                header_path = value.strip()
                break
        split_nodes = splitter.get_nodes_from_documents(
            [Document(text=section_text, metadata=metadata)]
        )
        for node in split_nodes:
            content = node.text.strip()
            if content:
                chunks.append((header_path or None, content))
    return chunks or llama_sentence_chunks(text, chunk_size, overlap)


def build_chunks(
    path: Path,
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    max_chunks: int = 200,
) -> list[Chunk]:
    """Construit la liste de Chunk pour un fichier (lazy-import llama-index)."""
    kind = classify_doc_kind(path)
    title = path.stem.replace("-", " ").replace("_", " ").strip() or path.name
    if kind in {"doc", "rex", "plan", "spec", "official-docs"}:
        raw_chunks = llama_markdown_chunks(text, chunk_size, overlap)
        chunk_kind = "markdown-section"
    else:
        raw_chunks = llama_sentence_chunks(text, chunk_size, overlap)
        chunk_kind = "llama-sentence"

    limited = raw_chunks[:max_chunks]
    chunk_count = len(limited)
    result: list[Chunk] = []
    for idx, (section, chunk_text) in enumerate(limited):
        chunk_title = title if not section else f"{title} > {section}"
        result.append(
            Chunk(
                title=chunk_title,
                text=chunk_text,
                chunk_kind=chunk_kind,
                section=section,
                chunk_index=idx,
                chunk_count=chunk_count,
            )
        )
    return result


# ---------------------------------------------------------------------------
# 8. EmbeddingGemmaEncoder — extrait de index.py.j2 (lazy-import sentence-transformers)
# ---------------------------------------------------------------------------
class EmbeddingGemmaEncoder:
    """Encodeur sentence-transformers (fp32 CPU, normalize configurable).

    sentence-transformers est lazy-importé dans __init__ pour permettre
    l'import de memory_core sans torch installé (tests purs).
    """

    def __init__(self, model_name: str, normalize_embeddings: bool) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]

        self.model = SentenceTransformer(model_name)
        self.normalize_embeddings = normalize_embeddings

    def encode_query(self, query: str) -> list[float]:
        vector = self.model.encode(
            query,
            prompt_name="Retrieval-query",
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        return vector.tolist()

    def encode_documents(self, documents: list[tuple[str, str]]) -> list[list[float]]:
        prompts = []
        for title, text in documents:
            safe_title = title.strip() if title.strip() else "none"
            prompts.append(f"title: {safe_title} | text: {text}")
        vectors = self.model.encode(
            prompts,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]


# ---------------------------------------------------------------------------
# 9. node_id helper (partagé)
# ---------------------------------------------------------------------------
def make_node_id(ref_id: str, chunk_index: int, chunk_text: str) -> str:
    """Génère un UUID déterministe pour un chunk (même logique que index.py.j2)."""
    digest = sha256_text(f"{ref_id}:{chunk_index}:{chunk_text}")
    return str(uuid.UUID(digest[:32]))
