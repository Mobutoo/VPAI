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

import ast as _ast
import hashlib
import re
import subprocess
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
MAX_CHUNKS_PER_FILE = 200

# Filtres de selection de fichiers — MIROIR de
# roles/llamaindex-memory-worker/defaults/main.yml (include_extensions /
# exclude_dirs / max_file_bytes). DOIVENT rester synchronises : le worker lit son
# config.yml (rendu des defaults), le pod lit ces constantes. Divergence = trous
# (un fichier ignore d'un cote), pas de corruption — le worker incremental rattrape.
INCLUDE_EXTENSIONS = {
    ".md", ".txt", ".rst", ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".sh",
    ".sql", ".json", ".yml", ".yaml", ".j2", ".env", ".toml", ".ini",
}
EXCLUDE_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".turbo", ".venv", "venv",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".playwright-mcp", "coverage",
}
MAX_FILE_BYTES = 1048576


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


def resolve_source(
    abs_path: str | Path, lookup: dict[Path, dict[str, str]]
) -> tuple[str, str, str] | None:
    """Autorité UNIQUE du contrat (repo, wing, relative_path) — worker ET pod.

    Trouve la source racine ANCÊTRE LA PLUS PROCHE (chemin le plus long) de
    abs_path et retourne (repo_name, wing, relative_path-relatif-à-cette-racine).

    Contrat canonique (BLOCKER parité #1) : repo = NOM de la source de plus haut
    niveau (ex. "DOCS"), relative_path inclut les sous-dossiers (ex.
    "n8n-docs/x.md"). PAS d'expansion des repos git imbriqués. Le worker comme le
    pod doivent obéir à CE contrat pour des ref_doc_id / node_id identiques.

    Retourne None si abs_path est hors de toute source configurée.
    """
    resolved = Path(abs_path).expanduser().resolve()
    best_root: Path | None = None
    best_meta: dict[str, str] | None = None
    best_rel: Path | None = None
    for root, meta in lookup.items():
        try:
            rel = resolved.relative_to(root)
        except ValueError:
            continue
        if best_root is None or len(root.parts) > len(best_root.parts):
            best_root, best_meta, best_rel = root, meta, rel
    if best_root is None or best_meta is None or best_rel is None:
        return None
    repo = best_meta.get("name") or best_root.name
    wing = best_meta.get("wing", "")
    return repo, wing, best_rel.as_posix()


# ---------------------------------------------------------------------------
# 4. Helpers utilitaires (partagés, extraits de index.py.j2)
# ---------------------------------------------------------------------------
def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash du contenu fichier (copie exacte de index.py.j2 — parité)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit_sha(repo_root: Path, file_path: Path) -> str:
    """Dernier commit SHA touchant file_path (copie exacte de index.py.j2 — parité)."""
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo_root), "log", "-n", "1", "--format=%H", "--",
                str(Path(file_path).relative_to(repo_root)),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    return result.stdout.strip()


def build_repo_git_shas(repo_root: Path) -> dict[str, str]:
    """Map {chemin_relatif: dernier_commit_SHA} pour TOUT le repo en 1 traversée git.

    Remplace ~N subprocess `git_commit_sha` (1 par fichier = 66% du temps d'ingestion
    bulk mesuré 2026-06-06) par UN SEUL `git log`. Parité STRICTE avec git_commit_sha :
    git log est reverse-chronologique -> la PREMIÈRE occurrence d'un chemin = son commit
    le plus récent = exactement ce que `git log -n 1 -- <path>` renvoie par fichier.
    `core.quotePath=false` -> chemins UTF-8 bruts (pas d'octal \\xxx) ; `--no-renames`
    aligne sur git_commit_sha (qui ne suit pas les renommages). git_sha = payload-only
    (hors node_id) -> un miss éventuel ne casse pas l'idempotence.
    """
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(repo_root), "log",
             "--format=C:%H", "--name-only", "--no-renames"],
            check=False, capture_output=True, text=True,
        )
    except OSError:
        return {}
    shas: dict[str, str] = {}
    cur = ""
    for line in result.stdout.split("\n"):
        if line.startswith("C:"):
            cur = line[2:]
        elif line and cur and line not in shas:
            shas[line] = cur  # 1re occurrence = commit le plus récent (reverse-chrono)
    return shas


def extract_structural_meta(path: Path, text: str) -> dict[str, list[str]]:
    """Métadonnées structurelles (functions/classes/imports/exports/variables).

    Copie exacte de index.py.j2 — partagée worker/pod pour garantir des payloads
    identiques (BLOCKER parité #2). Stdlib only (ast + re).
    """
    suffix = Path(path).suffix.lower()
    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []
    exports: list[str] = []
    variables: list[str] = []

    if suffix == ".py":
        try:
            tree = _ast.parse(text)
            # IN-02: top-level only — exclude class methods from functions list
            for node in tree.body:
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    functions.append(node.name)
                elif isinstance(node, _ast.ClassDef):
                    classes.append(node.name)
            # WR-02: capture both `from X import Y` and plain `import X`
            _from_imports = [
                node.module
                for node in _ast.walk(tree)
                if isinstance(node, _ast.ImportFrom) and node.module
            ]
            _plain_imports = [
                alias.name.split(".")[0]
                for node in _ast.walk(tree)
                if isinstance(node, _ast.Import)
                for alias in node.names
            ]
            imports = list(dict.fromkeys(_from_imports + _plain_imports))
        except SyntaxError:
            pass

    elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
        imports = re.findall(r"from\s+['\"]([^'\"]+)['\"]", text)
        exports = re.findall(
            r"export\s+(?:default\s+)?(?:function|class|const|type|interface)\s+(\w+)", text
        )

    elif suffix in {".yml", ".yaml", ".j2"}:
        variables = list(dict.fromkeys(re.findall(r"\{\{\s*([a-zA-Z_]\w*)", text)))

    return {
        "functions": functions[:50],
        "classes": classes[:20],
        "imports": imports[:40],
        "exports": exports[:40],
        "variables": variables[:60],
    }


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

    def encode_documents(
        self, documents: list[tuple[str, str]], batch_size: int | None = None
    ) -> list[list[float]]:
        prompts = []
        for title, text in documents:
            safe_title = title.strip() if title.strip() else "none"
            prompts.append(f"title: {safe_title} | text: {text}")
        # batch_size : ST défaut=32. Sur GPU, un batch plus grand (256+) = matmuls plus
        # gros -> meilleure occupation SM. Vecteurs équivalents à tolérance fp près
        # (padding/réduction du batch décale ~1e-6, < divergence ARM/x86 déjà acceptée ;
        # node_id=texte inchangé). None -> défaut ST (parité stricte worker).
        kwargs: dict[str, Any] = {
            "normalize_embeddings": self.normalize_embeddings,
            "show_progress_bar": False,
        }
        if batch_size is not None:
            kwargs["batch_size"] = batch_size
        vectors = self.model.encode(prompts, **kwargs)
        return [vector.tolist() for vector in vectors]


# ---------------------------------------------------------------------------
# 9. node_id helper (partagé)
# ---------------------------------------------------------------------------
def make_node_id(ref_id: str, chunk_index: int, chunk_text: str) -> str:
    """Génère un UUID déterministe pour un chunk (même logique que index.py.j2)."""
    digest = sha256_text(f"{ref_id}:{chunk_index}:{chunk_text}")
    return str(uuid.UUID(digest[:32]))


# ---------------------------------------------------------------------------
# 10. iter_source_files — walk filtré partagé (worker + pod), stdlib only
# ---------------------------------------------------------------------------
def iter_source_files(
    root: Path,
    include_ext: set[str] | None = None,
    exclude_dirs: set[str] | None = None,
    max_file_bytes: int = MAX_FILE_BYTES,
):
    """Itère les fichiers indexables sous `root` (filtres canoniques partagés).

    Même logique que le worker (iter_repo_files) : filtre par extension, taille,
    et élague les répertoires exclus. Yield des chemins absolus.
    """
    import os

    inc = include_ext if include_ext is not None else INCLUDE_EXTENSIONS
    exc = exclude_dirs if exclude_dirs is not None else EXCLUDE_DIRS
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in exc]
        current = Path(current_root)
        for filename in files:
            path = current / filename
            if path.suffix.lower() not in inc:
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
            except FileNotFoundError:
                continue
            yield path


# ---------------------------------------------------------------------------
# 11. to_text_nodes — chunks -> list[TextNode] (PARTAGÉ worker+pod, parité node)
# ---------------------------------------------------------------------------
def to_text_nodes(
    *,
    repo: str,
    path: Path,
    relative_path: str,
    wing: str,
    room: str,
    topic: str,
    content_hash: str,
    git_sha: str,
    chunks: list[Chunk],
    struct_meta: dict[str, list[str]] | None = None,
    embedding_model: str = "google/embeddinggemma-300m",
    embedding_dim: int = 768,
    host_origin: str = "waza",
    valid_from: str | None = None,
):
    """Construit les TextNode (id_ déterministe + payload complet) pour un fichier.

    SOURCE UNIQUE worker+pod : garantit que les deux produisent des node_id et
    payloads IDENTIQUES. TextNode est lazy-importé (llama-index) pour permettre
    l'import de memory_core sans la dépendance (tests purs).

    Les axes embedding_model/dim/host_origin sont des PARAMÈTRES (le worker passe
    ses valeurs Jinja rendues ; le pod passe les mêmes littéraux). host_origin
    DOIT rester "waza" des deux côtés (ref_doc_id/tags/node_id en dépendent).
    """
    from llama_index.core.schema import TextNode  # type: ignore[import]

    tags = build_tags(repo, classify_doc_kind(path), detect_language(path))
    ref_id = ref_doc_id(repo, relative_path)
    now = valid_from or utcnow_iso()
    nodes = []
    for chunk in chunks:
        metadata = build_payload(
            wing=wing,
            room=room,
            repo=repo,
            relative_path=relative_path,
            path=path,
            topic=topic,
            tags=tags,
            chunk_index=chunk.chunk_index,
            chunk_count=chunk.chunk_count,
            chunk_kind=chunk.chunk_kind,
            section=chunk.section,
            chunk_title=chunk.title,
            content_hash=content_hash,
            git_sha=git_sha,
            struct_meta=struct_meta,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            host_origin=host_origin,
            valid_from=now,
        )
        node_id = make_node_id(ref_id, chunk.chunk_index, chunk.text)
        nodes.append(TextNode(id_=node_id, text=chunk.text, metadata=metadata))
    return nodes
