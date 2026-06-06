"""Tests pour memory_core.py — TDD obligatoire (pytest).

Couvre :
- classify_room : ≥1 cas par wing + par room documentée
- build_payload : wing/room non nuls, valid_to None, tous champs manifeste présents
- load_wing_room_lookup : clés = chemins résolus canoniques
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from memory_core import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNKING_STRATEGY_VERSION,
    SCHEMA_VERSION,
    build_payload,
    classify_doc_kind,
    classify_room,
    extract_structural_meta,
    load_wing_room_lookup,
    resolve_source,
)


# ===========================================================================
# classify_room — wing infra (VPAI)
# ===========================================================================
class TestClassifyRoomInfra:
    def test_caddy_role(self):
        assert classify_room("infra", "roles/caddy/templates/Caddyfile.j2") == "caddy-vpn"

    def test_caddy_keyword_in_path(self):
        assert classify_room("infra", "docs/guides/GUIDE-CADDY-VPN-ONLY.md") == "caddy-vpn"

    def test_postgres_role(self):
        assert classify_room("infra", "roles/postgres/tasks/main.yml") == "postgres"

    def test_grafana_monitoring(self):
        assert classify_room("infra", "roles/grafana/defaults/main.yml") == "monitoring"

    def test_loki_monitoring(self):
        assert classify_room("infra", "roles/loki/tasks/main.yml") == "monitoring"

    def test_prometheus_monitoring(self):
        assert classify_room("infra", "roles/prometheus/templates/config.yml.j2") == "monitoring"

    def test_alloy_monitoring(self):
        assert classify_room("infra", "roles/alloy/files/config.alloy") == "monitoring"

    def test_victoriametrics_monitoring(self):
        assert classify_room("infra", "roles/victoriametrics/defaults/main.yml") == "monitoring"

    def test_cadvisor_monitoring(self):
        assert classify_room("infra", "roles/cadvisor/tasks/main.yml") == "monitoring"

    def test_monitoring_role(self):
        assert classify_room("infra", "roles/monitoring/tasks/main.yml") == "monitoring"

    def test_docker_role(self):
        assert classify_room("infra", "roles/docker/tasks/main.yml") == "docker"

    def test_docker_stack(self):
        assert classify_room("infra", "docker-stack/compose.yml") == "docker"

    def test_n8n_role(self):
        assert classify_room("infra", "roles/n8n/templates/docker-compose.yml.j2") == "n8n"

    def test_n8n_script(self):
        assert classify_room("infra", "scripts/n8n-workflows/mop-route.json") == "n8n"

    def test_other_role(self):
        assert classify_room("infra", "roles/litellm/defaults/main.yml") == "ansible-roles"

    def test_playbooks_deploy(self):
        assert classify_room("infra", "playbooks/stacks/site.yml") == "deploy"

    def test_troubleshooting_doc_exact(self):
        # docs/TROUBLESHOOTING* → matcher exact du manifeste §3
        assert classify_room("infra", "docs/TROUBLESHOOTING.md") == "troubleshooting"

    def test_troubleshooting_keyword_in_path(self):
        # "troubleshooting" dans le chemin — sans caddy (caddy-vpn prendrait le dessus)
        assert classify_room("infra", "docs/guides/troubleshooting-deploy.md") == "troubleshooting"

    def test_caddy_wins_over_troubleshooting(self):
        # §3 ordre strict : "caddy" matche AVANT "troubleshooting"
        # "troubleshooting-caddy.md" contient "caddy" → caddy-vpn, PAS troubleshooting
        assert classify_room("infra", "docs/guides/troubleshooting-caddy.md") == "caddy-vpn"

    def test_docs_other(self):
        assert classify_room("infra", "docs/guides/GUIDE-OPENCLAW-UPGRADE.md") == "deploy"

    def test_planning(self):
        assert classify_room("infra", ".planning/STATE.md") == "deploy"

    def test_default_fallback(self):
        # fichier à la racine sans sous-dossier reconnu
        assert classify_room("infra", "Makefile") == "ansible-roles"


# ===========================================================================
# classify_room — wing saas
# ===========================================================================
class TestClassifyRoomSaas:
    def test_rag(self):
        assert classify_room("saas", "src/rag/qdrant.py") == "rag"

    def test_memory(self):
        assert classify_room("saas", "services/memory/store.py") == "rag"

    def test_qdrant_path(self):
        assert classify_room("saas", "workers/qdrant_ingest.py") == "rag"

    def test_embed(self):
        assert classify_room("saas", "lib/embed/encoder.ts") == "rag"

    def test_mind_state(self):
        assert classify_room("saas", "src/mind_state/index.ts") == "rag"

    def test_api(self):
        assert classify_room("saas", "src/api/routes/health.ts") == "api"

    def test_server(self):
        assert classify_room("saas", "src/server.ts") == "api"

    def test_handler(self):
        assert classify_room("saas", "src/handler/webhook.py") == "api"

    def test_frontend(self):
        assert classify_room("saas", "src/web/App.tsx") == "frontend"

    def test_ui_component(self):
        assert classify_room("saas", "src/components/Button.tsx") == "frontend"

    def test_pipeline(self):
        assert classify_room("saas", "workers/pipeline/ingest.py") == "pipeline"

    def test_scheduler(self):
        assert classify_room("saas", "src/scheduler.py") == "pipeline"

    def test_llama_worker(self):
        assert classify_room("saas", "services/llama-worker/run.py") == "pipeline"

    def test_prd_arch(self):
        assert classify_room("saas", "docs/ARCHITECTURE.md") == "prd-arch"

    def test_readme(self):
        assert classify_room("saas", "README.md") == "prd-arch"

    def test_planning(self):
        assert classify_room("saas", ".planning/ROADMAP.md") == "prd-arch"

    def test_default_api(self):
        # fichier sans segment reconnu → fallback api
        assert classify_room("saas", "Makefile") == "api"


# ===========================================================================
# classify_room — wing refdocs
# ===========================================================================
class TestClassifyRoomRefdocs:
    def test_automation_docs(self):
        # segment-docs/sous-dossier → strip "-docs" → techno
        assert classify_room("refdocs", "automation-docs/integrations/http.md") == "automation"

    def test_platform_docs(self):
        assert classify_room("refdocs", "platform-docs/providers/openai.md") == "platform"

    def test_openclaw_docs(self):
        assert classify_room("refdocs", "openclaw-docs/api/overview.md") == "openclaw"

    def test_wiki(self):
        assert classify_room("refdocs", "wiki/architecture.md") == "wiki"

    def test_typebot_docs(self):
        assert classify_room("refdocs", "typebot-docs/deploy/docker.md") == "typebot"

    def test_typebot_docs_prefix(self):
        assert classify_room("refdocs", "typebot-docs") == "typebot"

    def test_misc_fallback_isolated_file(self):
        # fichier isolé sans "/" → pas de segment techno → misc
        assert classify_room("refdocs", "somefile.md") == "misc"

    def test_misc_fallback_single_segment_no_slash(self):
        # segment seul sans sous-dossier → misc
        assert classify_room("refdocs", "orphan.rst") == "misc"


# ===========================================================================
# classify_room — wing tools
# ===========================================================================
class TestClassifyRoomTools:
    def test_n8n_workflows(self):
        assert classify_room("tools", "scripts/n8n-workflows/mop.json") == "n8n-workflows"

    def test_shell_script(self):
        assert classify_room("tools", "deploy.sh") == "scripts"

    def test_scripts_dir(self):
        assert classify_room("tools", "scripts/setup.py") == "scripts"

    def test_mcp(self):
        assert classify_room("tools", "mcp/server.py") == "mcp"

    def test_cli_fallback(self):
        assert classify_room("tools", "Makefile") == "cli"


# ===========================================================================
# classify_room — wing inconnu
# ===========================================================================
def test_classify_room_unknown_wing():
    result = classify_room("unknown_wing", "some/path.py")
    assert result == "misc"
    assert result  # jamais nul


def test_classify_room_never_null_all_wings():
    """Vérifie que classify_room ne retourne jamais une chaîne vide (invariant §5)."""
    cases = [
        ("infra", "Makefile"),
        ("saas", "Makefile"),
        ("refdocs", "orphan.md"),
        ("tools", "Makefile"),
        ("unknown", "anything.py"),
    ]
    for wing, path in cases:
        result = classify_room(wing, path)
        assert result, f"classify_room({wing!r}, {path!r}) a retourné vide"


# ===========================================================================
# build_payload
# ===========================================================================
REQUIRED_FIELDS = {
    # axes taxonomie
    "wing", "room", "doc_kind", "repo", "relative_path", "topic", "tags",
    "valid_from", "valid_to",
    # champs legacy
    "schema_version", "embedding_model", "embedding_dim",
    "chunking_strategy_version", "ref_doc_id", "namespace",
    "host_origin", "source_kind", "filename",
    "severity", "category", "phase",
    # champs chunk
    "language", "chunk_index", "chunk_count", "chunking_kind",
    "section", "title", "content_hash", "git_commit_sha", "indexed_at",
    # structural meta
    "functions", "classes", "imports", "exports", "variables",
}


def _make_payload(**overrides):
    defaults = dict(
        wing="infra",
        room="deploy",
        repo="VPAI",
        relative_path="playbooks/site.yml",
        path=Path("playbooks/site.yml"),
        topic="site",
        tags=["repo:VPAI"],
        chunk_index=0,
        chunk_count=1,
        chunk_kind="llama-sentence",
        section=None,
        chunk_title="site",
        content_hash="abc123",
        git_sha="deadbeef",
        struct_meta=None,
    )
    defaults.update(overrides)
    return build_payload(**defaults)


class TestBuildPayload:
    def test_wing_not_null(self):
        p = _make_payload(wing="infra", room="deploy")
        assert p["wing"] == "infra"
        assert p["wing"]  # jamais nul/vide

    def test_room_not_null(self):
        p = _make_payload(wing="saas", room="rag")
        assert p["room"] == "rag"
        assert p["room"]

    def test_valid_to_is_none(self):
        p = _make_payload()
        assert p["valid_to"] is None

    def test_valid_to_explicit_none(self):
        p = _make_payload(valid_to=None)
        assert p["valid_to"] is None

    def test_valid_to_dateable(self):
        p = _make_payload(valid_to="2026-12-31T00:00:00+00:00")
        assert p["valid_to"] == "2026-12-31T00:00:00+00:00"

    def test_all_required_fields_present(self):
        p = _make_payload()
        missing = REQUIRED_FIELDS - set(p.keys())
        assert not missing, f"Champs manquants dans le payload : {missing}"

    def test_schema_version(self):
        p = _make_payload()
        assert p["schema_version"] == SCHEMA_VERSION

    def test_namespace_equals_repo(self):
        p = _make_payload(repo="story-engine")
        assert p["namespace"] == "story-engine"

    def test_wing_empty_raises(self):
        with pytest.raises(AssertionError):
            _make_payload(wing="", room="deploy")

    def test_room_empty_raises(self):
        with pytest.raises(AssertionError):
            _make_payload(wing="infra", room="")

    def test_embedding_model_param(self):
        p = _make_payload(embedding_model="google/embeddinggemma-300m", embedding_dim=768)
        assert p["embedding_model"] == "google/embeddinggemma-300m"
        assert p["embedding_dim"] == 768

    def test_struct_meta_fields(self):
        sm = {"functions": ["foo"], "classes": ["Bar"], "imports": ["os"],
              "exports": [], "variables": ["X"]}
        p = _make_payload(struct_meta=sm)
        assert p["functions"] == ["foo"]
        assert p["classes"] == ["Bar"]
        assert p["variables"] == ["X"]

    def test_struct_meta_empty_default(self):
        p = _make_payload(struct_meta=None)
        assert p["functions"] == []
        assert p["classes"] == []

    def test_legacy_empty_strings(self):
        p = _make_payload()
        assert p["severity"] == ""
        assert p["category"] == ""
        assert p["phase"] == ""


# ===========================================================================
# load_wing_room_lookup
# ===========================================================================
class TestLoadWingRoomLookup:
    def test_keys_are_resolved_paths(self, tmp_path):
        sources_file = tmp_path / "sources.yml"
        data = {
            "sources": [
                {"name": "VPAI", "kind": "git_repo", "root": str(tmp_path / "VPAI"), "wing": "infra"},
                {"name": "story-engine", "kind": "git_repo", "root": str(tmp_path / "saas/story-engine"), "wing": "saas"},
            ]
        }
        sources_file.write_text(yaml.dump(data), encoding="utf-8")

        lookup = load_wing_room_lookup(sources_file)
        expected_keys = {
            Path(tmp_path / "VPAI").expanduser().resolve(),
            Path(tmp_path / "saas/story-engine").expanduser().resolve(),
        }
        assert set(lookup.keys()) == expected_keys

    def test_wing_values(self, tmp_path):
        sources_file = tmp_path / "sources.yml"
        data = {
            "sources": [
                {"name": "VPAI", "kind": "git_repo", "root": str(tmp_path / "VPAI"), "wing": "infra"},
            ]
        }
        sources_file.write_text(yaml.dump(data), encoding="utf-8")
        lookup = load_wing_room_lookup(sources_file)
        key = Path(tmp_path / "VPAI").expanduser().resolve()
        assert lookup[key]["wing"] == "infra"
        assert lookup[key]["name"] == "VPAI"

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_wing_room_lookup(tmp_path / "nonexistent.yml")
        assert result == {}

    def test_no_root_skipped(self, tmp_path):
        sources_file = tmp_path / "sources.yml"
        data = {"sources": [{"name": "X", "kind": "git_repo"}]}  # pas de root
        sources_file.write_text(yaml.dump(data), encoding="utf-8")
        lookup = load_wing_room_lookup(sources_file)
        assert lookup == {}

    def test_multiple_sources(self, tmp_path):
        sources_file = tmp_path / "sources.yml"
        roots = [tmp_path / f"repo{i}" for i in range(3)]
        wings = ["infra", "saas", "refdocs"]
        data = {
            "sources": [
                {"name": f"repo{i}", "root": str(roots[i]), "wing": wings[i]}
                for i in range(3)
            ]
        }
        sources_file.write_text(yaml.dump(data), encoding="utf-8")
        lookup = load_wing_room_lookup(sources_file)
        assert len(lookup) == 3
        for i, w in enumerate(wings):
            key = roots[i].expanduser().resolve()
            assert lookup[key]["wing"] == w


# ===========================================================================
# classify_doc_kind — vérification rapide (copie exacte)
# ===========================================================================
class TestClassifyDocKind:
    def test_rex(self):
        assert classify_doc_kind(Path("docs/rex/REX-2026.md")) == "rex"

    def test_code_py(self):
        assert classify_doc_kind(Path("src/main.py")) == "code"

    def test_config_yml(self):
        assert classify_doc_kind(Path("roles/caddy/defaults/main.yml")) == "config"

    def test_doc_md(self):
        assert classify_doc_kind(Path("README.md")) == "doc"


# ===========================================================================
# Constantes importables
# ===========================================================================
def test_constants_importable():
    assert CHUNK_SIZE == 1600
    assert CHUNK_OVERLAP == 200
    assert SCHEMA_VERSION == "memory_v2"
    assert CHUNKING_STRATEGY_VERSION == "2026-04-09"


# ===========================================================================
# resolve_source — contrat canonique (repo, wing, relative_path) — BLOCKER #1
# ===========================================================================
class TestResolveSource:
    def _lookup(self, tmp_path):
        """Construit un lookup réaliste : DOCS (refdocs, non-git arbre) +
        VPAI (infra) + une source imbriquée pour tester nearest-ancestor."""
        return {
            (tmp_path / "DOCS").resolve(): {"wing": "refdocs", "name": "DOCS"},
            (tmp_path / "VPAI").resolve(): {"wing": "infra", "name": "VPAI"},
            (tmp_path / "VPAI" / "nested").resolve(): {"wing": "saas", "name": "nested"},
        }

    def test_docs_nested_is_one_tree(self, tmp_path):
        """BLOCKER #1 : DOCS/n8n-docs/x.md → repo=DOCS, rel=n8n-docs/x.md
        (PAS repo=n8n-docs). classify_room verra le slash → room=n8n."""
        f = tmp_path / "DOCS" / "n8n-docs" / "x.md"
        repo, wing, rel = resolve_source(f, self._lookup(tmp_path))
        assert repo == "DOCS"
        assert wing == "refdocs"
        assert rel == "n8n-docs/x.md"
        assert classify_room(wing, rel) == "n8n"

    def test_vpai_role_file(self, tmp_path):
        f = tmp_path / "VPAI" / "roles" / "caddy" / "templates" / "Caddyfile.j2"
        repo, wing, rel = resolve_source(f, self._lookup(tmp_path))
        assert (repo, wing, rel) == ("VPAI", "infra", "roles/caddy/templates/Caddyfile.j2")
        assert classify_room(wing, rel) == "caddy-vpn"

    def test_nearest_ancestor_wins(self, tmp_path):
        """Source imbriquée : le chemin le plus long (nested) l'emporte sur VPAI."""
        f = tmp_path / "VPAI" / "nested" / "src" / "api.py"
        repo, wing, rel = resolve_source(f, self._lookup(tmp_path))
        assert repo == "nested"
        assert wing == "saas"
        assert rel == "src/api.py"

    def test_outside_all_sources_returns_none(self, tmp_path):
        f = tmp_path / "elsewhere" / "y.md"
        assert resolve_source(f, self._lookup(tmp_path)) is None

    def test_name_fallback_to_basename(self, tmp_path):
        lookup = {(tmp_path / "Repo").resolve(): {"wing": "infra", "name": ""}}
        repo, _, _ = resolve_source(tmp_path / "Repo" / "a.py", lookup)
        assert repo == "Repo"


# ===========================================================================
# extract_structural_meta — parité BLOCKER #2 (déplacé de index.py.j2)
# ===========================================================================
class TestExtractStructuralMeta:
    def test_python_functions_classes_imports(self):
        src = (
            "import os\n"
            "from pathlib import Path\n"
            "def top():\n    pass\n"
            "async def atop():\n    pass\n"
            "class Foo:\n    def method(self):\n        pass\n"
        )
        meta = extract_structural_meta(Path("m.py"), src)
        assert meta["functions"] == ["top", "atop"]  # méthodes exclues
        assert meta["classes"] == ["Foo"]
        assert "os" in meta["imports"] and "pathlib" in meta["imports"]

    def test_python_syntax_error_safe(self):
        meta = extract_structural_meta(Path("bad.py"), "def (:\n")
        assert meta["functions"] == []

    def test_ts_imports_exports(self):
        src = 'import {x} from "./a";\nexport function go() {}\nexport const K = 1;\n'
        meta = extract_structural_meta(Path("c.ts"), src)
        assert "./a" in meta["imports"]
        assert "go" in meta["exports"] and "K" in meta["exports"]

    def test_yaml_jinja_variables(self):
        meta = extract_structural_meta(Path("t.j2"), "x: {{ foo_bar }}\ny: {{ baz }}\n")
        assert "foo_bar" in meta["variables"] and "baz" in meta["variables"]

    def test_unknown_suffix_empty(self):
        meta = extract_structural_meta(Path("a.md"), "# hi")
        assert all(v == [] for v in meta.values())
