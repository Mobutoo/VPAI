# brick.yml P1 — Schéma + validation + générateur backup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implémenter les étapes 1 et 2 du séquencement de la spec brick.yml (`~/work/saas/optimus/docs/specs/2026-08-05-brick-manifest-design.md` §8) : schéma JSON + `--validate`, puis générateur backup + garde CI, prouvé par la migration opportuniste de TREK.

**Architecture:** Un script unique `scripts/brick_generate.py` (pattern `scripts/ci/check-prisme-role.py` : stdlib + PyYAML + jsonschema, pas de framework) lit `roles/*/brick.yml`, les valide (JSON Schema Draft 2020-12 + assertions conditionnelles §5), et génère `roles/backup-config/vars/bricks_backup_<env>.yml` — un fichier de vars Ansible PAR environnement, committé, consommé par `pre-backup.sh.j2` et `backup-cleanup.sh.j2` via boucles Jinja2 (sélection par `brick_backup_env`, défini explicitement dans l'inventaire, jamais en défaut de rôle). La CI rejoue la génération et échoue sur tout diff (garde de dérive §4).

**Tech Stack:** Python 3.12 (`.venv` VPAI), PyYAML, jsonschema 4.x, pytest 9 (tests), Jinja2 (déjà présents dans `.venv`). CI GitHub Actions (`.github/workflows/ci.yml`, job lint).

## Global Constraints

- Repo cible : `/home/mobuone/work/infra/VPAI` (les rôles, le backup et la CI y vivent). La spec source vit dans optimus et n'est PAS modifiée par ce plan.
- Remote git : `git@github-seko:Mobutoo/vpai.git` — jamais `github.com`. Commits sur `main`.
- `identity.digest` : pattern strict `^sha256:[a-f0-9]{64}$` (spec §5 #1).
- `backup.strategy` absent = REFUS DUR ; liste vide acceptée uniquement avec `backup.disabled_reason` string non vide (spec §5 #2).
- Alertes minimales `service_down` + `restart_loop` pour toute brique avec `runtime.healthcheck` ; `http_5xx_rate` interdit si `exposure.vhost.mode` absent ou `none` (spec §5 #5).
- `exposure.vhost.mode: public` exige `dns_proof` structuré `{record_type, value, validated_at, validated_by}` (spec §5 #6).
- Jamais `:latest`/`:stable`/`:main` dans `identity.image` (spec §5 #7, garde CI existante « Check no latest tags »).
- `deployment.compose` ∈ `{generated, local}` obligatoire (spec §5 #8).
- Fichiers générés : en-tête `# GÉNÉRÉ DEPUIS brick.yml — NE PAS ÉDITER À LA MAIN`, sortie déterministe (deux runs = octets identiques), yamllint-clean (`.yamllint.yml` : line-length 160 warning, document-start disable).
- La tâche « Deploy pre-backup script » garde son `no_log: true` (fuite `--diff` du 2026-08-04, commit `9b16605`) — ne jamais le retirer.
- Ansible : FQCN obligatoire, `changed_when`/`failed_when` explicites sur command/shell (aucune nouvelle tâche shell prévue ici).
- Sur waza, `docker` sans `--context local` tape la PROD Sese — toujours expliciter le contexte.
- Pas de secret en clair nulle part : `brick.yml` ne contient que des `vault_ref`, jamais de valeur.
- Le script s'appelle `brick_generate.py` (underscore — importable par pytest) ; la spec dit `brick-generate.py`, écart de nommage assumé et documenté dans le docstring.

---

### Task 1: Schéma JSON + chargement + `--validate` structurel

**Files:**
- Create: `scripts/brick.schema.json`
- Create: `scripts/brick_generate.py`
- Create: `tests/brick/conftest.py` (sys.path racine — cf. note stratégie d'import en fin de Step 5)
- Create: `tests/brick/fixtures/umami-valid.yml`
- Test: `tests/brick/test_validate.py`

**Interfaces:**
- Produces: `load_manifest(path: Path) -> dict` (lève `BrickError` si YAML invalide) ; `validate_manifest(manifest: dict, path: Path, versions: dict) -> list[str]` (liste vide = valide, chaque erreur préfixée du chemin du manifeste) ; `find_manifests(repo: Path) -> list[Path]` ; `load_versions(repo: Path) -> dict` ; constante `GENERATED_HEADER`. CLI : `python3 scripts/brick_generate.py --validate [--repo DIR]`, exit 0 si tous valides, 1 sinon, messages sur stderr.

- [ ] **Step 1: Écrire la fixture valide** (l'exemple Umami de la spec §2, digest factice bien formé)

`tests/brick/fixtures/umami-valid.yml`:
```yaml
apiVersion: optimus.brick/v1
kind: Brick

identity:
  name: umami
  version: "2.20.0"
  image: "ghcr.io/umami-software/umami:postgresql-v2.20.0"
  digest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  phase: phase3
  category: apps

deployment:
  compose: generated
  environments: ["sese"]

runtime:
  env:
    DATABASE_URL: { vault_ref: vault_umami_database_url }
    APP_SECRET: { vault_ref: vault_umami_app_secret }
    TRACKER_SCRIPT_NAME: "stats"
  resources:
    memory_limit: "384m"
    memory_reservation: "128m"
    cpu_limit: "0.5"
  healthcheck:
    test: ["CMD-SHELL", "wget -qO- http://localhost:3000/api/heartbeat || exit 1"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 40s
  networks:
    - frontend
    - backend
  volumes: []

exposure:
  vhost:
    mode: vpn_only
    subdomain: "stats"
    upstream_port: 3000

backup:
  strategy:
    - kind: postgres_dump
      database: umami
  retention: inherit

monitoring:
  scrape: true
  metrics_endpoint: null
  alerts:
    - kind: service_down
    - kind: restart_loop
    - kind: http_5xx_rate
      threshold: "5%"
      window: 5m

logging:
  driver: json-file
  max_size: "10m"
  max_file: "3"

dependencies:
  - postgresql
```

- [ ] **Step 2: Écrire les tests structurels (rouges)**

`tests/brick/test_validate.py`:
```python
import copy
from pathlib import Path

import yaml

from scripts.brick_generate import load_manifest, validate_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def valid():
    return yaml.safe_load((FIXTURES / "umami-valid.yml").read_text())


def errors_of(manifest, versions=None):
    return validate_manifest(manifest, Path("roles/umami/brick.yml"), versions or {})


def test_valid_manifest_passes():
    assert errors_of(valid()) == []


def test_load_manifest_reads_fixture():
    m = load_manifest(FIXTURES / "umami-valid.yml")
    assert m["identity"]["name"] == "umami"


def test_digest_malformed_fails():
    m = valid()
    m["identity"]["digest"] = "sha256:tooshort"
    assert any("digest" in e for e in errors_of(m))


def test_digest_absent_fails():
    m = valid()
    del m["identity"]["digest"]
    assert any("digest" in e for e in errors_of(m))


def test_backup_strategy_key_absent_fails():
    m = valid()
    del m["backup"]["strategy"]
    assert any("strategy" in e for e in errors_of(m))


def test_missing_memory_limit_fails():
    m = valid()
    del m["runtime"]["resources"]["memory_limit"]
    assert any("memory_limit" in e for e in errors_of(m))


def test_missing_healthcheck_fails():
    m = valid()
    del m["runtime"]["healthcheck"]
    assert any("healthcheck" in e for e in errors_of(m))


def test_compose_enum_enforced():
    m = valid()
    m["deployment"]["compose"] = "manual"
    assert any("compose" in e for e in errors_of(m))


def test_compose_absent_fails():
    m = valid()
    del m["deployment"]["compose"]
    assert any("compose" in e for e in errors_of(m))


def test_latest_tag_fails():
    m = valid()
    m["identity"]["image"] = "ghcr.io/umami-software/umami:latest"
    assert any("image" in e for e in errors_of(m))


def test_unknown_top_level_key_fails():
    m = valid()
    m["extra_field"] = {"foo": 1}
    assert errors_of(m) != []


def test_dotdot_in_backup_src_fails():
    m = valid()
    m["backup"]["strategy"] = [
        {"kind": "volume_tar", "archive": "evil", "src": "/opt/app/../../etc"}
    ]
    assert errors_of(m) != []
```

- [ ] **Step 3: Vérifier que les tests échouent**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 -m pytest tests/brick -q`
Expected: erreurs de collection `ModuleNotFoundError: No module named 'scripts.brick_generate'`

- [ ] **Step 4: Écrire le schéma JSON**

`scripts/brick.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "optimus.brick/v1",
  "title": "Optimus brick manifest v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["apiVersion", "kind", "identity", "deployment", "runtime", "backup", "monitoring", "logging"],
  "properties": {
    "apiVersion": { "const": "optimus.brick/v1" },
    "kind": { "const": "Brick" },
    "identity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "version", "image", "digest", "phase", "category"],
      "properties": {
        "name": { "type": "string", "pattern": "^[a-z][a-z0-9-]*$" },
        "version": { "type": "string", "minLength": 1 },
        "image": { "type": "string", "minLength": 1, "not": { "pattern": ":(latest|stable|main)$" } },
        "digest": { "type": "string", "pattern": "^sha256:[a-f0-9]{64}$" },
        "phase": { "type": "string", "pattern": "^phase[0-9]+$" },
        "category": { "enum": ["apps", "platform", "provision", "monitoring", "ops"] }
      }
    },
    "deployment": {
      "type": "object",
      "additionalProperties": false,
      "required": ["compose"],
      "properties": {
        "compose": { "enum": ["generated", "local"] },
        "environments": { "type": "array", "items": { "type": "string", "minLength": 1 } }
      }
    },
    "runtime": {
      "type": "object",
      "additionalProperties": false,
      "required": ["resources", "healthcheck"],
      "properties": {
        "env": {
          "type": "object",
          "additionalProperties": {
            "oneOf": [
              { "type": ["string", "number", "boolean"] },
              {
                "type": "object",
                "additionalProperties": false,
                "required": ["vault_ref"],
                "properties": { "vault_ref": { "type": "string", "pattern": "^vault_[a-z0-9_]+$" } }
              }
            ]
          }
        },
        "resources": {
          "type": "object",
          "additionalProperties": false,
          "required": ["memory_limit", "cpu_limit"],
          "properties": {
            "memory_limit": { "type": "string", "pattern": "^[0-9]+[mMgG]$" },
            "memory_reservation": { "type": "string", "pattern": "^[0-9]+[mMgG]$" },
            "cpu_limit": { "type": "string", "pattern": "^[0-9]+(\\.[0-9]+)?$" }
          }
        },
        "healthcheck": {
          "type": "object",
          "additionalProperties": false,
          "required": ["test"],
          "properties": {
            "test": { "type": "array", "items": { "type": "string" }, "minItems": 1 },
            "interval": { "type": "string" },
            "timeout": { "type": "string" },
            "retries": { "type": "integer", "minimum": 1 },
            "start_period": { "type": "string" }
          }
        },
        "networks": { "type": "array", "items": { "type": "string", "minLength": 1 } },
        "volumes": { "type": "array", "items": { "type": "string", "minLength": 1 } }
      }
    },
    "exposure": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "vhost": {
          "type": "object",
          "additionalProperties": false,
          "required": ["mode"],
          "properties": {
            "mode": { "enum": ["public", "vpn_only", "none"] },
            "subdomain": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$" },
            "upstream_port": { "type": "integer", "minimum": 1, "maximum": 65535 },
            "dns_proof": {
              "type": "object",
              "additionalProperties": false,
              "required": ["record_type", "value", "validated_at", "validated_by"],
              "properties": {
                "record_type": { "enum": ["A", "AAAA", "CNAME"] },
                "value": { "type": "string", "minLength": 1 },
                "validated_at": { "type": "string", "minLength": 1 },
                "validated_by": { "type": "string", "minLength": 1 }
              }
            }
          }
        }
      }
    },
    "backup": {
      "type": "object",
      "additionalProperties": false,
      "required": ["strategy"],
      "properties": {
        "strategy": {
          "type": "array",
          "items": {
            "oneOf": [
              {
                "type": "object",
                "additionalProperties": false,
                "required": ["kind", "database"],
                "properties": {
                  "kind": { "const": "postgres_dump" },
                  "database": { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" }
                }
              },
              {
                "type": "object",
                "additionalProperties": false,
                "required": ["kind", "archive", "src"],
                "properties": {
                  "kind": { "const": "volume_tar" },
                  "archive": { "type": "string", "pattern": "^[a-z][a-z0-9-]*$" },
                  "src": {
                    "type": "string",
                    "pattern": "^(/[A-Za-z0-9._/-]+|\\{\\{ [a-z][a-z0-9_]* \\}\\})$",
                    "not": { "pattern": "(^|/)\\.\\.(/|$)" }
                  },
                  "include": {
                    "type": "array",
                    "items": {
                      "type": "string",
                      "pattern": "^[A-Za-z0-9._][A-Za-z0-9._/-]*$",
                      "not": { "pattern": "(^|/)\\.\\.(/|$)" }
                    },
                    "minItems": 1
                  }
                }
              }
            ]
          }
        },
        "disabled_reason": { "type": "string", "minLength": 1 },
        "retention": {}
      }
    },
    "monitoring": {
      "type": "object",
      "additionalProperties": false,
      "required": ["scrape"],
      "properties": {
        "scrape": { "type": "boolean" },
        "metrics_endpoint": { "type": ["string", "null"] },
        "alerts": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["kind"],
            "properties": {
              "kind": { "enum": ["service_down", "restart_loop", "http_5xx_rate"] },
              "threshold": { "type": "string" },
              "window": { "type": "string" }
            }
          }
        }
      }
    },
    "logging": {
      "type": "object",
      "additionalProperties": false,
      "required": ["driver", "max_size", "max_file"],
      "properties": {
        "driver": { "const": "json-file" },
        "max_size": { "const": "10m" },
        "max_file": { "const": "3" }
      }
    },
    "dependencies": { "type": "array", "items": { "type": "string", "minLength": 1 } }
  }
}
```

- [ ] **Step 5: Écrire le script (validation structurelle seule)**

`scripts/brick_generate.py`:
```python
#!/usr/bin/env python3
"""brick_generate — validation et génération depuis roles/*/brick.yml.

Spec source : ~/work/saas/optimus/docs/specs/2026-08-05-brick-manifest-design.md
(§2 schéma, §4 générateurs, §5 assertions). La spec nomme l'outil
`brick-generate.py` ; le fichier est nommé avec underscore pour être importable
par pytest — le comportement CLI est identique.

Commandes :
  --validate                    valide tous les roles/*/brick.yml (assertions §5)
  --lint                        liste les manifestes orphelins de tout environnement
  --generate backup --env NOM   (ré)génère roles/backup-config/vars/bricks_backup_<NOM>.yml
  ... --check                   ne réécrit pas : échoue (exit 1) si le fichier committé diffère
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "brick.schema.json"
GENERATED_HEADER = "# GÉNÉRÉ DEPUIS brick.yml — NE PAS ÉDITER À LA MAIN\n"

_schema_validator: Draft202012Validator | None = None


class BrickError(Exception):
    """Manifeste illisible (YAML invalide, fichier absent)."""


def _validator() -> Draft202012Validator:
    global _schema_validator
    if _schema_validator is None:
        _schema_validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text()))
    return _schema_validator


def find_manifests(repo: Path = REPO) -> list[Path]:
    return sorted(repo.glob("roles/*/brick.yml"))


def load_manifest(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except OSError as exc:
        raise BrickError(f"{path}: illisible : {exc}") from exc
    except yaml.YAMLError as exc:
        raise BrickError(f"{path}: YAML invalide : {exc}") from exc
    if not isinstance(data, dict):
        raise BrickError(f"{path}: le manifeste doit être un mapping YAML")
    return data


def load_versions(repo: Path = REPO) -> dict:
    versions_path = repo / "inventory/group_vars/all/versions.yml"
    if not versions_path.exists():
        return {}
    return yaml.safe_load(versions_path.read_text()) or {}


def validate_manifest(manifest: dict, path: Path, versions: dict) -> list[str]:
    errors: list[str] = []
    for err in sorted(_validator().iter_errors(manifest), key=lambda e: list(e.absolute_path)):
        where = ".".join(str(p) for p in err.absolute_path) or "<racine>"
        errors.append(f"{path}: [{where}] {err.message}")
    # Les assertions conditionnelles (§5 #2/#5/#6, cross-check versions.yml)
    # arrivent en Task 2 — ce stub garde la signature stable.
    return errors


def cmd_validate(repo: Path) -> int:
    manifests = find_manifests(repo)
    if not manifests:
        print("Aucun roles/*/brick.yml — rien à valider.")
        return 0
    versions = load_versions(repo)
    all_errors: list[str] = []
    for path in manifests:
        try:
            all_errors.extend(validate_manifest(load_manifest(path), path, versions))
        except BrickError as exc:
            all_errors.append(str(exc))
    for error in all_errors:
        print(f"ERREUR: {error}", file=sys.stderr)
    print(f"{len(manifests)} manifeste(s), {len(all_errors)} erreur(s).")
    return 1 if all_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args(argv)
    if args.validate:
        return cmd_validate(args.repo)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

Stratégie d'import UNIQUE (revue Codex 2026-08-05, MED import) : PAS de `tests/brick/__init__.py`, PAS de `scripts/__init__.py`, PAS d'importlib. Un seul fichier `tests/brick/conftest.py` :
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
```
La racine du repo sur `sys.path` rend `scripts.brick_generate` et `tests.brick.test_validate` importables comme **namespace packages** (PEP 420, aucun `__init__.py` requis). Tous les tests du plan importent donc directement `from scripts.brick_generate import ...` — supprimer la mention `tests/brick/__init__.py` de la liste des fichiers de cette task (créer uniquement `conftest.py`).

- [ ] **Step 6: Vérifier que les tests passent**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 -m pytest tests/brick -q`
Expected: `12 passed`

- [ ] **Step 7: Vérifier le CLI à vide (aucun brick.yml dans le repo encore)**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 scripts/brick_generate.py --validate`
Expected: `Aucun roles/*/brick.yml — rien à valider.` exit 0

- [ ] **Step 8: yamllint sur la fixture**

Run: `cd ~/work/infra/VPAI && .venv/bin/yamllint -c .yamllint.yml tests/brick/fixtures/umami-valid.yml`
Expected: exit 0 (warnings line-length tolérés)

- [ ] **Step 9: Commit**

```bash
cd ~/work/infra/VPAI
git add scripts/brick.schema.json scripts/brick_generate.py tests/brick/
git commit -m "feat(brick): schéma JSON optimus.brick/v1 + validation structurelle

Étape 1 du séquencement de la spec brick-manifest (optimus
docs/specs/2026-08-05-brick-manifest-design.md §8) : les manifestes
roles/*/brick.yml peuvent être écrits et validés avant tout générateur."
```

---

### Task 2: Assertions conditionnelles §5 + cross-check versions.yml + `--lint`

**Files:**
- Modify: `scripts/brick_generate.py` (fonction `validate_manifest` + CLI `--lint`)
- Test: `tests/brick/test_validate.py` (ajouts)

**Interfaces:**
- Consumes: `validate_manifest`, `load_versions` de Task 1.
- Produces: `validate_manifest` complète (assertions #2, #5, #6 + cross-check `<name>_image` vs `versions.yml`) ; CLI `--lint` (exit 0, informatif) listant les manifestes sans `deployment.environments` non vide.

- [ ] **Step 1: Ajouter les tests conditionnels (rouges)**

Ajouter à `tests/brick/test_validate.py`:
```python
def test_empty_strategy_without_reason_fails():
    m = valid()
    m["backup"]["strategy"] = []
    assert any("disabled_reason" in e for e in errors_of(m))


def test_empty_strategy_with_reason_passes():
    m = valid()
    m["backup"]["strategy"] = []
    m["backup"]["disabled_reason"] = "stateless, état 100% en base déjà dumpée par la brique postgresql"
    assert errors_of(m) == []


def test_alerts_missing_restart_loop_fails():
    m = valid()
    m["monitoring"]["alerts"] = [{"kind": "service_down"}]
    assert any("restart_loop" in e for e in errors_of(m))


def test_alerts_missing_entirely_fails():
    m = valid()
    del m["monitoring"]["alerts"]
    assert any("service_down" in e and "restart_loop" in e for e in errors_of(m))


def test_http_5xx_without_vhost_fails():
    m = valid()
    del m["exposure"]
    assert any("http_5xx_rate" in e for e in errors_of(m))


def test_http_5xx_with_mode_none_fails():
    m = valid()
    m["exposure"]["vhost"]["mode"] = "none"
    assert any("http_5xx_rate" in e for e in errors_of(m))


def test_public_without_dns_proof_fails():
    m = valid()
    m["exposure"]["vhost"]["mode"] = "public"
    assert any("dns_proof" in e for e in errors_of(m))


def test_public_with_dns_proof_passes():
    m = valid()
    m["exposure"]["vhost"]["mode"] = "public"
    m["exposure"]["vhost"]["dns_proof"] = {
        "record_type": "A",
        "value": "203.0.113.10",
        "validated_at": "2026-08-05",
        "validated_by": "test",
    }
    assert errors_of(m) == []


def test_versions_yml_image_mismatch_fails():
    m = valid()
    versions = {"umami_image": "ghcr.io/umami-software/umami:postgresql-v2.19.0"}
    assert any("versions.yml" in e for e in errors_of(m, versions))


def test_versions_yml_image_match_passes():
    m = valid()
    versions = {"umami_image": "ghcr.io/umami-software/umami:postgresql-v2.20.0"}
    assert errors_of(m, versions) == []


def test_versions_yml_no_entry_is_ok():
    assert errors_of(valid(), {"other_image": "x:1"}) == []


def test_env_secret_key_as_literal_fails():
    m = valid()
    m["runtime"]["env"]["ADMIN_PASSWORD"] = "hunter2"
    assert any("vault_ref" in e for e in errors_of(m))


def test_env_secret_key_as_vault_ref_passes():
    m = valid()
    m["runtime"]["env"]["ADMIN_PASSWORD"] = {"vault_ref": "vault_umami_admin_password"}
    assert errors_of(m) == []
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 -m pytest tests/brick -q`
Expected: FAIL sur les 13 nouveaux tests (les assertions n'existent pas), les 12 anciens passent

- [ ] **Step 3: Implémenter les assertions dans `validate_manifest`**

Remplacer le commentaire stub de `validate_manifest` par :
```python
    # --- Assertions conditionnelles §5 (hors de portée de JSON Schema seul) ---
    # Garde de types (revue Codex 2026-08-05, HIGH TypeError) : sur un manifeste
    # structurellement invalide (backup = string, alerts = dict...), le schéma a
    # déjà produit les erreurs — les assertions ne doivent pas crasher par-dessus.
    def _dict(value):
        return value if isinstance(value, dict) else {}

    def _list(value):
        return value if isinstance(value, list) else []

    backup = _dict(manifest.get("backup"))
    if backup.get("strategy") == [] and not backup.get("disabled_reason"):
        errors.append(
            f"{path}: backup.strategy vide sans backup.disabled_reason — un commentaire "
            "YAML ne suffit pas (spec §5 #2, incident 2026-08-04)"
        )

    alert_kinds = {
        a.get("kind")
        for a in _list(_dict(manifest.get("monitoring")).get("alerts"))
        if isinstance(a, dict)
    }
    if _dict(manifest.get("runtime")).get("healthcheck") is not None:
        missing = {"service_down", "restart_loop"} - alert_kinds
        if missing:
            errors.append(
                f"{path}: monitoring.alerts doit couvrir service_down et restart_loop "
                f"(manquent : {', '.join(sorted(missing))}) — spec §5 #5"
            )

    vhost = _dict(_dict(manifest.get("exposure")).get("vhost"))
    vhost_mode = vhost.get("mode", "none")
    if "http_5xx_rate" in alert_kinds and vhost_mode == "none":
        errors.append(
            f"{path}: alerte http_5xx_rate déclarée sans exposition HTTP "
            "(exposure.vhost.mode absent ou none) — spec §5 #5"
        )
    if vhost_mode == "public" and "dns_proof" not in vhost:
        errors.append(
            f"{path}: exposure.vhost.mode public sans dns_proof structuré "
            "(record_type/value/validated_at/validated_by) — spec §5 #6"
        )

    # --- Secrets : une clé env au nom sensible ne peut être qu'un vault_ref (revue
    # Codex round 2 — la règle « jamais de secret en clair » doit être mécanique).
    # Marqueurs volontairement larges (KEY attrape API_KEY/ACCESS_KEY/PRIVATE_KEY,
    # PASS attrape PASSWORD/DB_PASS) : un faux positif se règle en passant par
    # vault_ref ou en renommant la variable — l'inverse (fuite) ne se règle pas.
    SECRET_KEY_MARKERS = ("SECRET", "PASS", "TOKEN", "KEY", "CREDENTIAL")
    for key, value in _dict(_dict(manifest.get("runtime")).get("env")).items():
        if any(marker in key.upper() for marker in SECRET_KEY_MARKERS) and not (
            isinstance(value, dict) and "vault_ref" in value
        ):
            errors.append(
                f"{path}: runtime.env.{key} ressemble à un secret et doit être un "
                "vault_ref, jamais un littéral"
            )

    # --- Cross-check versions.yml : tant que le générateur compose n'existe pas,
    # <name>_image dans versions.yml reste la source déployée ; le manifeste ne
    # doit jamais diverger d'elle (double déclaration assumée, dérive interdite).
    identity = _dict(manifest.get("identity"))
    name = identity.get("name")
    declared_image = identity.get("image")
    # tirets du nom de brique → underscores : convention des noms de vars Ansible
    # (ex. content-factory → content_factory_image)
    versions_image = versions.get(f"{name.replace('-', '_')}_image") if name else None
    if versions_image and declared_image and versions_image != declared_image:
        errors.append(
            f"{path}: identity.image ({declared_image}) diverge de {name}_image "
            f"dans versions.yml ({versions_image}) — mettre à jour LES DEUX"
        )
```
(La validation schéma en tête de fonction, déjà en place, reste inchangée. Quand le schéma
rejette déjà la structure — ex. `monitoring.alerts` absent n'est pas rejeté par le schéma
car optionnel — les assertions Python tournent toujours, sur ce que `manifest.get` trouve.)

- [ ] **Step 4: Ajouter `--lint` au CLI**

Dans `main()`, ajouter `parser.add_argument("--lint", action="store_true")` et :
```python
def cmd_lint(repo: Path) -> int:
    orphans = []
    for path in find_manifests(repo):
        try:
            manifest = load_manifest(path)
        except BrickError as exc:
            print(f"ERREUR: {exc}", file=sys.stderr)
            continue
        if not manifest.get("deployment", {}).get("environments"):
            orphans.append(path)
    if orphans:
        print("Manifestes orphelins (aucun environnement — jamais sélectionnés par --env) :")
        for path in orphans:
            print(f"  - {path}")
    else:
        print("Aucun manifeste orphelin.")
    return 0
```
et le brancher : `if args.lint: return cmd_lint(args.repo)` (après le bloc `--validate`).

- [ ] **Step 5: Vérifier que tout passe**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 -m pytest tests/brick -q`
Expected: `25 passed`

- [ ] **Step 6: Commit**

```bash
cd ~/work/infra/VPAI
git add scripts/brick_generate.py tests/brick/test_validate.py
git commit -m "feat(brick): assertions conditionnelles §5 + cross-check versions.yml + --lint

Refus durs : strategy vide sans disabled_reason (#2), alertes minimales
service_down+restart_loop (#5), public sans dns_proof (#6). Le cross-check
versions.yml borne la double déclaration d'image tant que le générateur
compose n'existe pas."
```

---

### Task 3: Générateur backup + `--check` (garde de dérive CI)

**Files:**
- Modify: `scripts/brick_generate.py`
- Test: `tests/brick/test_backup_generator.py`

**Interfaces:**
- Consumes: `find_manifests`, `load_manifest`, `validate_manifest` (le générateur refuse de produire si la validation échoue — spec §5 « avant toute génération »).
- Produces: `generate_backup_vars(manifests: list[tuple[Path, dict]], env: str) -> str` (texte YAML complet, déterministe ; lève `BrickError` sur doublon (brick, archive)) ; `backup_vars_path(env: str) -> str` retournant `roles/backup-config/vars/bricks_backup_<env>.yml` (**un fichier PAR environnement** — revue Codex 2026-08-05, HIGH env : un fichier unique généré pour sese serait chargé tel quel par un déploiement d'un autre environnement) ; CLI `--generate backup --env NOM [--check]`. Le fichier généré définit exactement deux variables : `brick_backup_pg_databases` (liste triée de noms de bases) et `brick_backup_tar_jobs` (liste de `{brick, archive, src, include}` triée par (brick, archive)).

- [ ] **Step 1: Écrire les tests (rouges)**

`tests/brick/test_backup_generator.py`:
```python
import copy
from pathlib import Path

import yaml

from tests.brick.test_validate import valid  # réutilise la fixture chargée

# Même préambule importlib que test_validate.py si scripts/ n'est pas un package :
from scripts.brick_generate import GENERATED_HEADER, generate_backup_vars


def manifests_fixture():
    umami = valid()  # postgres_dump umami, env sese
    trek = valid()
    trek["identity"]["name"] = "trek"
    trek["backup"]["strategy"] = [
        {"kind": "volume_tar", "archive": "uploads", "src": "{{ trek_uploads_dir }}"},
        {"kind": "volume_tar", "archive": "data", "src": "{{ trek_data_dir }}"},
    ]
    hetzner_only = valid()
    hetzner_only["identity"]["name"] = "zitadel"
    hetzner_only["deployment"]["environments"] = ["hetzner-hello-awa"]
    return [
        (Path("roles/umami/brick.yml"), umami),
        (Path("roles/trek/brick.yml"), trek),
        (Path("roles/zitadel/brick.yml"), hetzner_only),
    ]


def test_selects_only_env_bricks():
    out = yaml.safe_load(generate_backup_vars(manifests_fixture(), "sese"))
    bricks = {j["brick"] for j in out["brick_backup_tar_jobs"]}
    assert bricks == {"trek"}
    assert out["brick_backup_pg_databases"] == ["umami"]


def test_tar_jobs_sorted_and_default_include():
    out = yaml.safe_load(generate_backup_vars(manifests_fixture(), "sese"))
    jobs = out["brick_backup_tar_jobs"]
    assert [j["archive"] for j in jobs] == ["data", "uploads"]
    assert all(j["include"] == ["."] for j in jobs)


def test_deterministic():
    a = generate_backup_vars(manifests_fixture(), "sese")
    b = generate_backup_vars(manifests_fixture(), "sese")
    assert a == b


def test_header_present():
    text = generate_backup_vars(manifests_fixture(), "sese")
    assert GENERATED_HEADER.strip() in text
    assert "--env sese" in text


def test_empty_env_produces_empty_lists():
    out = yaml.safe_load(generate_backup_vars(manifests_fixture(), "nulle-part"))
    assert out == {"brick_backup_pg_databases": [], "brick_backup_tar_jobs": []}


def test_duplicate_brick_archive_pair_rejected():
    import pytest

    from scripts.brick_generate import BrickError

    fixtures = manifests_fixture()
    trek = fixtures[1][1]
    trek["backup"]["strategy"].append(
        {"kind": "volume_tar", "archive": "data", "src": "/autre/chemin"}
    )
    with pytest.raises(BrickError, match="trek.*data"):
        generate_backup_vars(fixtures, "sese")


def test_backup_vars_path_is_per_env():
    from scripts.brick_generate import backup_vars_path

    assert backup_vars_path("sese") == "roles/backup-config/vars/bricks_backup_sese.yml"


def test_cli_rejects_unsafe_env(tmp_path):
    from scripts.brick_generate import main

    assert main(["--generate", "backup", "--env", "../../etc", "--repo", str(tmp_path)]) == 1
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 -m pytest tests/brick/test_backup_generator.py -q`
Expected: FAIL — `generate_backup_vars` n'existe pas

- [ ] **Step 3: Implémenter le générateur + CLI**

Ajouter à `scripts/brick_generate.py`:
```python
def backup_vars_path(env: str) -> str:
    """Un fichier de vars PAR environnement : un déploiement d'un autre env ne
    doit jamais hériter des jobs de sese (revue Codex 2026-08-05, HIGH env)."""
    return f"roles/backup-config/vars/bricks_backup_{env}.yml"


def generate_backup_vars(manifests: list[tuple[Path, dict]], env: str) -> str:
    pg: set[str] = set()
    tar: list[dict] = []
    seen_archives: set[tuple[str, str]] = set()
    for _path, manifest in manifests:
        if env not in manifest.get("deployment", {}).get("environments", []):
            continue
        name = manifest["identity"]["name"]
        for entry in manifest["backup"]["strategy"]:
            if entry["kind"] == "postgres_dump":
                pg.add(entry["database"])
            elif entry["kind"] == "volume_tar":
                key = (name, entry["archive"])
                if key in seen_archives:
                    raise BrickError(
                        f"doublon volume_tar {name}/{entry['archive']} : deux jobs "
                        "écriraient la même archive horodatée"
                    )
                seen_archives.add(key)
                tar.append(
                    {
                        "brick": name,
                        "archive": entry["archive"],
                        "src": entry["src"],
                        "include": list(entry.get("include", ["."])),
                    }
                )
    tar.sort(key=lambda job: (job["brick"], job["archive"]))
    body = yaml.safe_dump(
        {"brick_backup_pg_databases": sorted(pg), "brick_backup_tar_jobs": tar},
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=120,
    )
    return (
        GENERATED_HEADER
        + f"# commande : python3 scripts/brick_generate.py --generate backup --env {env}\n"
        + f"# environnement : {env} — consommé par roles/backup-config (include_vars) : pre-backup.sh.j2 + backup-cleanup.sh.j2\n"
        + "---\n"
        + body
    )


def cmd_generate_backup(repo: Path, env: str, check: bool) -> int:
    # --env borné : interpolé dans un chemin de fichier ET dans le nom chargé par
    # include_vars — pas de séparateur, pas de traversée (revue Codex round 2, HIGH).
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", env):
        print(f"ERREUR: --env invalide ({env!r}) : motif attendu [a-z0-9][a-z0-9_-]*", file=sys.stderr)
        return 1
    manifests: list[tuple[Path, dict]] = []
    versions = load_versions(repo)
    errors: list[str] = []
    for path in find_manifests(repo):
        try:
            manifest = load_manifest(path)
        except BrickError as exc:
            errors.append(str(exc))
            continue
        errors.extend(validate_manifest(manifest, path, versions))
        manifests.append((path, manifest))
    if errors:
        for error in errors:
            print(f"ERREUR: {error}", file=sys.stderr)
        print("Génération refusée : manifestes invalides (spec §5).", file=sys.stderr)
        return 1

    try:
        rendered = generate_backup_vars(manifests, env)
    except BrickError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 1
    rel_path = backup_vars_path(env)
    target = repo / rel_path
    if check:
        current = target.read_text() if target.exists() else ""
        if current != rendered:
            print(
                f"DÉRIVE: {rel_path} ne correspond plus aux brick.yml — "
                f"régénérer avec : python3 scripts/brick_generate.py --generate backup --env {env}",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {rel_path} à jour.")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered)
    print(f"Écrit : {rel_path}")
    return 0
```
CLI dans `main()` :
```python
    parser.add_argument("--generate", choices=["backup"])
    parser.add_argument("--env")
    parser.add_argument("--check", action="store_true")
```
et le dispatch :
```python
    if args.generate == "backup":
        if not args.env:
            parser.error("--generate backup exige --env")
        return cmd_generate_backup(args.repo, args.env, args.check)
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 -m pytest tests/brick -q`
Expected: `33 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/work/infra/VPAI
git add scripts/brick_generate.py tests/brick/test_backup_generator.py
git commit -m "feat(brick): générateur backup → vars Ansible + --check anti-dérive

Produit roles/backup-config/vars/bricks_backup_<env>.yml (déterministe, en-tête
GÉNÉRÉ). --check échoue si le fichier committé diverge des manifestes —
la garde CI de la spec §4 contre l'édition manuelle."
```

---

### Task 4: Manifeste TREK (migration opportuniste) + première génération

**Files:**
- Create: `roles/trek/brick.yml`
- Create: `roles/backup-config/vars/bricks_backup_sese.yml` (généré, committé)

**Interfaces:**
- Consumes: CLI complet de Task 3.
- Produces: premier `brick.yml` réel du repo ; `bricks_backup_sese.yml` avec les 2 jobs tar TREK (`brick_backup_pg_databases: []`).

- [ ] **Step 1: Résoudre le digest réel de l'image TREK**

Run (waza — TOUJOURS `--context local`, sinon docker tape la prod Sese) :
```bash
docker --context local buildx imagetools inspect docker.io/mauriceboe/trek:3.0.22 2>/dev/null | grep -i '^Digest:'
```
Fallback si buildx indisponible : `skopeo inspect --format '{{.Digest}}' docker://docker.io/mauriceboe/trek:3.0.22`.
Expected: une ligne `Digest: sha256:<64 hex>` — noter la valeur pour Step 3.

- [ ] **Step 2: Vérifier le DNS public de TREK (dns_proof)**

Run: `dig +short trip.ewutelo.cloud A`
Expected: une IP publique (service public live) — noter la valeur pour Step 3.

- [ ] **Step 3: Écrire le manifeste**

`roles/trek/brick.yml` (remplacer `DIGEST_RESOLU` et `IP_DNS` par les valeurs des Steps 1-2) :
```yaml
apiVersion: optimus.brick/v1
kind: Brick

# Migration opportuniste (spec brick-manifest §7) : TREK a essuyé l'incident
# backup 2026-08-04 et son compose vit déjà dans le pattern central docker-stack
# (roles/docker-stack/templates/compose/apps-docs-misc.yml.j2). Seul le
# générateur BACKUP consomme ce manifeste pour l'instant ; compose/Caddy/alertes
# restent gérés comme avant (générateurs à venir, spec §8 étapes 3-4).

identity:
  name: trek
  version: "3.0.22"
  image: "mauriceboe/trek:3.0.22"
  digest: "DIGEST_RESOLU"
  phase: phase3
  category: apps

deployment:
  compose: generated
  environments: ["sese"]

runtime:
  # env volontairement absent : trek.env.j2 (secrets vaultés) reste la source
  # tant que le générateur compose n'existe pas.
  resources:
    memory_limit: "512M"
    memory_reservation: "192M"
    cpu_limit: "1.0"
  healthcheck:
    test: ["CMD", "wget", "-qO-", "http://localhost:3000/api/health"]
    interval: 30s
    timeout: 10s
    retries: 5
    start_period: 60s
  networks:
    - frontend
    - egress
  volumes:
    - "/opt/{{ project_name }}/data/trek:/app/data"
    - "/opt/{{ project_name }}/data/trek-uploads:/app/uploads"
    - "/opt/{{ project_name }}/configs/trek/public:/app/public:ro"

exposure:
  vhost:
    mode: public
    subdomain: "trip"
    upstream_port: 3000
    dns_proof:
      record_type: "A"
      value: "IP_DNS"
      validated_at: "2026-08-05"
      validated_by: "migration opportuniste — service déjà en prod, DNS vérifié par dig"

backup:
  # SQLite dans trek_data_dir + uploads : les deux archives que pre-backup.sh
  # produisait en dur avant ce manifeste (mêmes chemins de destination).
  strategy:
    - kind: volume_tar
      archive: data
      src: "{{ trek_data_dir }}"
    - kind: volume_tar
      archive: uploads
      src: "{{ trek_uploads_dir }}"
  retention: inherit

monitoring:
  scrape: true
  metrics_endpoint: null
  alerts:
    - kind: service_down
    - kind: restart_loop
    - kind: http_5xx_rate
      threshold: "5%"
      window: 5m

logging:
  driver: json-file
  max_size: "10m"
  max_file: "3"

dependencies: []
```

- [ ] **Step 4: Valider**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 scripts/brick_generate.py --validate && .venv/bin/python3 scripts/brick_generate.py --lint`
Expected: `1 manifeste(s), 0 erreur(s).` puis `Aucun manifeste orphelin.` — le cross-check versions.yml passe car `trek_image: "mauriceboe/trek:3.0.22"` (versions.yml:94) == identity.image.

- [ ] **Step 5: Générer le fichier de vars**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 scripts/brick_generate.py --generate backup --env sese && cat roles/backup-config/vars/bricks_backup_sese.yml`
Expected: fichier contenant `brick_backup_pg_databases: []` et 2 jobs (`data` puis `uploads`, `src` = `{{ trek_data_dir }}`/`{{ trek_uploads_dir }}`, `include: ['.']`).

- [ ] **Step 6: Vérifier la garde de dérive + yamllint**

Run:
```bash
cd ~/work/infra/VPAI
.venv/bin/python3 scripts/brick_generate.py --generate backup --env sese --check
.venv/bin/yamllint -c .yamllint.yml roles/trek/brick.yml roles/backup-config/vars/bricks_backup_sese.yml
```
Expected: `OK: roles/backup-config/vars/bricks_backup_sese.yml à jour.` puis yamllint exit 0

- [ ] **Step 7: Commit**

```bash
cd ~/work/infra/VPAI
git add roles/trek/brick.yml roles/backup-config/vars/bricks_backup_sese.yml
git commit -m "feat(trek): premier brick.yml réel + vars backup générées

Migration opportuniste (spec §7) : TREK, service public déjà victime de
l'incident backup 2026-08-04, devient la preuve du générateur. Digest résolu,
dns_proof rempli depuis le DNS live."
```

---

### Task 5: Câblage des templates backup sur les vars générées

**Files:**
- Modify: `roles/backup-config/tasks/main.yml` (assert + include_vars en tête)
- Modify: vars du groupe prod dans `inventory/group_vars/` (ajout `brick_backup_env: "sese"` — fichier exact découvert au Step 3)
- Modify: `roles/backup-config/templates/pre-backup.sh.j2` (lignes 60 et 180-188)
- Modify: `roles/backup-config/templates/backup-cleanup.sh.j2` (ligne 13)
- Modify: `roles/backup-config/defaults/main.yml` (retrait `backup_trek_dir`)
- Test: `tests/brick/test_prebackup_render.py`

**Interfaces:**
- Consumes: `bricks_backup_sese.yml` (Task 4) — variables `brick_backup_pg_databases`, `brick_backup_tar_jobs`.
- Produces: templates rendus dont les entrées backup dérivent du manifeste ; plus aucun bloc tar par-service codé en dur.

- [ ] **Step 1: Écrire le test de rendu (rouge)**

`tests/brick/test_prebackup_render.py`:
```python
"""Rend pre-backup.sh.j2 / backup-cleanup.sh.j2 avec des vars fixture et vérifie
que les jobs brick.yml y apparaissent et que le bash produit est syntaxiquement
valide (bash -n). Ne teste PAS la résolution Jinja imbriquée d'Ansible
({{ trek_data_dir }} dans les vars) : les src sont pré-résolus dans la fixture —
la résolution paresseuse est un comportement plateforme d'Ansible, prouvé au
déploiement (Task 7)."""
import subprocess
from pathlib import Path

import jinja2

REPO = Path(__file__).resolve().parents[2]

VARS = {
    "ansible_managed": "test",
    "project_display_name": "Test",
    "project_name": "testproj",
    "postgresql_password": "x",
    "redis_password": "x",
    "qdrant_api_key": "x",
    "grafana_admin_password": "x",
    "backup_base_dir": "/opt/testproj/backups",
    "backup_local_retention_days": 3,
    "backup_pre_script_cron_hour": "2",
    "backup_pre_script_cron_minute": "55",
    "backup_heartbeat_url": "",
    "postgresql_databases": [{"name": "n8n"}],
    "openclaw_volume_isolation": False,
    "brick_backup_pg_databases": ["umami"],
    "brick_backup_tar_jobs": [
        {"brick": "trek", "archive": "data", "src": "/opt/testproj/data/trek", "include": ["."]},
        {"brick": "trek", "archive": "uploads", "src": "/opt/testproj/data/trek-uploads", "include": ["."]},
        # src volontairement hostile : prouve que le filtre quote neutralise la
        # valeur RESOLUE (espace + $()), pas seulement la référence du manifeste.
        {"brick": "demo", "archive": "spaced", "src": "/opt/test proj/$(reboot)", "include": ["."]},
    ],
}


def _env() -> jinja2.Environment:
    import shlex

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(REPO / "roles/backup-config/templates"),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )
    env.filters["quote"] = shlex.quote  # équivalent du filtre Ansible `quote`
    return env


def render(template_name: str) -> str:
    return _env().get_template(template_name).render(**VARS)


def assert_bash_valid(script: str, tmp_path: Path, name: str):
    path = tmp_path / name
    path.write_text(script)
    subprocess.run(["bash", "-n", str(path)], check=True)


def test_prebackup_renders_brick_jobs(tmp_path):
    out = render("pre-backup.sh.j2")
    assert "trek/data-${TIMESTAMP}.tar.gz" in out
    assert "trek/uploads-${TIMESTAMP}.tar.gz" in out
    assert "-C /opt/testproj/data/trek ." in out  # chemin sain : quote no-op
    assert "-C '/opt/test proj/$(reboot)' ." in out  # chemin hostile : neutralisé
    assert "BRICK_TAR_FAILURES=$((BRICK_TAR_FAILURES + 1))" in out
    assert 'if [ "${BRICK_TAR_FAILURES}" -gt 0 ]' in out
    assert_bash_valid(out, tmp_path, "pre-backup.sh")


def test_prebackup_pg_includes_brick_databases(tmp_path):
    out = render("pre-backup.sh.j2")
    for_line = next(line for line in out.splitlines() if line.startswith("for DB in "))
    assert "umami" in for_line
    assert "prisme" in for_line  # la liste en dur historique reste
    covered_line = next(line for line in out.splitlines() if line.startswith("COVERED="))
    assert "umami" in covered_line  # la garde de dérive couvre aussi les bases brick


def test_prebackup_no_hardcoded_trek_block():
    out = render("pre-backup.sh.j2")
    assert "TREK data backup" not in out


def test_prebackup_without_brick_vars_still_renders(tmp_path):
    bare = {k: v for k, v in VARS.items() if not k.startswith("brick_backup_")}
    out = _env().get_template("pre-backup.sh.j2").render(**bare)
    assert_bash_valid(out, tmp_path, "pre-backup-bare.sh")


def test_cleanup_covers_brick_dirs(tmp_path):
    out = render("backup-cleanup.sh.j2")
    cleanup_line = next(line for line in out.splitlines() if line.startswith("for SUBDIR in "))
    assert " trek" in cleanup_line
    assert_bash_valid(out, tmp_path, "backup-cleanup.sh")
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `cd ~/work/infra/VPAI && .venv/bin/python3 -m pytest tests/brick/test_prebackup_render.py -q`
Expected: FAIL — `trek/data-${TIMESTAMP}` déjà présent (dur) mais `umami` absent du `for DB`, bloc `TREK data backup` encore présent

- [ ] **Step 3: Charger les vars générées dans le rôle**

Dans `roles/backup-config/tasks/main.yml`, insérer juste après le commentaire d'en-tête (avant `# === DIRECTORIES ===`) :
```yaml
# === VARS GÉNÉRÉES (brick.yml) ===

- name: Assert brick_backup_env is explicitly set
  ansible.builtin.assert:
    that:
      - brick_backup_env is defined
      - brick_backup_env is match('^[a-z0-9][a-z0-9_-]*$')
    fail_msg: >-
      brick_backup_env doit être défini dans l'inventaire de l'environnement cible
      (jamais un défaut de rôle : un défaut 'sese' ferait hériter silencieusement
      les jobs backup de sese à tout autre environnement — revue Codex 2026-08-05).

- name: Load generated brick backup vars
  ansible.builtin.include_vars:
    file: "bricks_backup_{{ brick_backup_env }}.yml"
```
**PAS de `brick_backup_env` dans `roles/backup-config/defaults/main.yml`** (revue Codex round 2, HIGH défaut). À la place, le définir dans l'inventaire du groupe prod. D'abord découvrir la structure :
```bash
ls ~/work/infra/VPAI/inventory/group_vars/
```
puis ajouter dans le fichier de vars du groupe prod existant (`inventory/group_vars/prod.yml` ou `inventory/group_vars/prod/main.yml` selon la structure constatée — si seul `all/` existe, créer `inventory/group_vars/prod/main.yml`) :
```yaml
# Environnement brick.yml : sélectionne roles/backup-config/vars/bricks_backup_<env>.yml
# (généré par scripts/brick_generate.py --generate backup --env <env>).
brick_backup_env: "sese"
```

- [ ] **Step 4: Modifier `pre-backup.sh.j2`**

Ligne 60, remplacer :
```jinja2
{% set backup_pg_databases = (postgresql_databases | default([]) | map(attribute='name') | list) + ['plane_production', 'content_factory', 'prisme', 'postiz'] %}
```
par :
```jinja2
{# Bases declarees par manifeste brick.yml (roles/*/brick.yml -> vars/bricks_backup_<env>.yml,
   genere par scripts/brick_generate.py). La liste en dur historique reste pour les
   roles non migres — toute NOUVELLE base passe par un brick.yml, plus par cette liste. #}
{% set backup_pg_databases = (postgresql_databases | default([]) | map(attribute='name') | list) + ['plane_production', 'content_factory', 'prisme', 'postiz'] + (brick_backup_pg_databases | default([])) %}
```
Puis remplacer intégralement le bloc TREK (lignes 180-188, de `# === TREK data backup ===` à `echo "[$(date)] TREK backup completed"`) par :
```jinja2
# === Backups tar declares par manifeste (roles/*/brick.yml) ===
{# Genere indirectement : brick_backup_tar_jobs vient de
   roles/backup-config/vars/bricks_backup_<env>.yml, produit par scripts/brick_generate.py.
   NE PAS rajouter de bloc tar par-service code en dur ici — c'est la liste statique
   qui a laisse TREK/OpenClaw sans backup (incident 2026-08-04, spec brick-manifest §1).
   src et include passent par le filtre Ansible `quote` (shlex.quote) : le schema
   borne la REFERENCE ecrite dans brick.yml, mais pas la valeur Ansible RESOLUE
   ({{ trek_data_dir }} peut contenir n'importe quoi) — seul un echappement shell a
   la resolution est fiable (revue Codex 2026-08-05 round 2). Un echec n'est plus
   avale par || true : compte, puis le heartbeat final est saute => alerte Uptime
   Kuma (dead-man). #}
BRICK_TAR_FAILURES=0
{% for job in brick_backup_tar_jobs | default([]) %}
echo "[$(date)] Backing up {{ job.brick }}/{{ job.archive }} (brick.yml)..."
backup_tar "{{ backup_base_dir }}/{{ job.brick }}/{{ job.archive }}-${TIMESTAMP}.tar.gz" \
  -C {{ job.src | quote }}{% for inc in job.include %} {{ inc | quote }}{% endfor %} \
  || BRICK_TAR_FAILURES=$((BRICK_TAR_FAILURES + 1))
{% endfor %}
```
Et en fin de script, remplacer la ligne `echo "[$(date)] Pre-backup completed successfully"` par :
```jinja2
if [ "${BRICK_TAR_FAILURES}" -gt 0 ]; then
  echo "[$(date)] ERREUR: ${BRICK_TAR_FAILURES} backup(s) brick.yml en echec — heartbeat NON envoye"
  exit 1
fi
echo "[$(date)] Pre-backup completed successfully"
```
(`exit 1` avant le bloc heartbeat : le push Uptime Kuma n'est pas envoyé → l'alerte
dead-man existante se déclenche. Les blocs historiques redis/qdrant/n8n gardent leur
politique WARNING — la durcir est hors périmètre de ce plan.)
Parité de chemins garantie : ancien dest = `{{ backup_trek_dir }}/data-…` avec `backup_trek_dir: "{{ backup_base_dir }}/trek"` (defaults) ; nouveau dest = `{{ backup_base_dir }}/trek/data-…` — identique. Le `mkdir -p` explicite disparaît : `backup_tar` fait déjà `sudo -n mkdir -p "$(dirname dest)"`.

- [ ] **Step 5: Modifier `backup-cleanup.sh.j2`**

Ligne 13, remplacer :
```bash
for SUBDIR in pg_dump redis qdrant n8n grafana trek; do
```
par :
```jinja2
{# Repertoires par-brique ajoutes depuis brick_backup_tar_jobs — meme raison que
   pre-backup.sh.j2 : la liste statique est le mode de panne (incident 2026-08-04). #}
for SUBDIR in pg_dump redis qdrant n8n grafana{% for b in brick_backup_tar_jobs | default([]) | map(attribute='brick') | unique %} {{ b }}{% endfor %}; do
```

- [ ] **Step 6: Retirer la variable morte**

Run: `cd ~/work/infra/VPAI && grep -rn backup_trek_dir . --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules`
(sans filtre d'extension — revue Codex : README/molecule/docs comptent aussi)
Expected: seule occurrence restante = `roles/backup-config/defaults/main.yml`. La supprimer :
retirer la ligne `backup_trek_dir: "{{ backup_base_dir }}/trek"` de `roles/backup-config/defaults/main.yml`.
(Si d'autres occurrences apparaissent — README, molecule — les traiter au même commit : README reformulé, molecule adapté.)

- [ ] **Step 7: Vérifier que les tests passent + lint Ansible**

Run:
```bash
cd ~/work/infra/VPAI && .venv/bin/python3 -m pytest tests/brick -q
source .venv/bin/activate && make lint
```
Expected: `38 passed` ; lint OK (yamllint + ansible-lint sur site.yml/workstation.yml)

- [ ] **Step 8: Commit**

```bash
cd ~/work/infra/VPAI
git add roles/backup-config/ tests/brick/test_prebackup_render.py inventory/group_vars/
git commit -m "feat(backup): pre-backup + cleanup consomment les vars brick.yml générées

Le bloc TREK codé en dur devient une boucle sur brick_backup_tar_jobs
(mêmes chemins de destination), la liste PG et la garde de dérive
absorbent brick_backup_pg_databases, cleanup couvre les répertoires
par-brique. no_log préservé sur le déploiement du script."
```

---

### Task 6: Branchement CI (Makefile + GitHub Actions + requirements)

**Files:**
- Modify: `requirements.txt`
- Modify: `Makefile` (cible `lint` + nouvelles cibles)
- Modify: `.github/workflows/ci.yml` (job lint + `paths`)

**Interfaces:**
- Consumes: CLI complet (`--validate`, `--generate backup --env sese --check`) + tests pytest.
- Produces: `make lint` et la CI échouent sur manifeste invalide OU dérive du fichier généré.

- [ ] **Step 1: Ajouter les dépendances CI**

Dans `requirements.txt`, ajouter à la fin :
```text
# brick_generate (scripts/brick_generate.py + tests/brick)
jsonschema>=4.26,<5.0
pytest>=9.0,<10.0
```
(PyYAML et Jinja2 arrivent déjà via ansible.)

- [ ] **Step 2: Cibles Makefile**

Après la cible `lint-yaml`, ajouter :
```makefile
.PHONY: lint-bricks
lint-bricks: ## Valider les manifestes brick.yml + dérive des fichiers générés (tous les envs committés)
	.venv/bin/python3 scripts/brick_generate.py --validate
	@for f in roles/backup-config/vars/bricks_backup_*.yml; do \
		[ -e "$$f" ] || continue; \
		env=$$(basename "$$f" .yml | sed 's/^bricks_backup_//'); \
		echo ">>> drift check env $$env"; \
		.venv/bin/python3 scripts/brick_generate.py --generate backup --env "$$env" --check || exit 1; \
	done

.PHONY: test-bricks
test-bricks: ## Tests unitaires du générateur brick
	.venv/bin/python3 -m pytest tests/brick -q
```
Et dans la cible `lint`, insérer avant la ligne finale `@echo "$(GREEN)>>> All linting passed$(NC)"` :
```makefile
	@echo "$(GREEN)>>> Running brick manifests validation...$(NC)"
	@$(MAKE) --no-print-directory lint-bricks
```

- [ ] **Step 3: Étapes CI**

Dans `.github/workflows/ci.yml`, job lint, après le step `Qdrant registry canonicalization`, ajouter :
```yaml
      - name: Brick manifests (validate + drift guard, tous les envs)
        run: |
          set -euo pipefail
          python scripts/brick_generate.py --validate
          for f in roles/backup-config/vars/bricks_backup_*.yml; do
            [ -e "$f" ] || continue
            env=$(basename "$f" .yml | sed 's/^bricks_backup_//')
            python scripts/brick_generate.py --generate backup --env "$env" --check
          done

      - name: Brick generator tests
        run: python -m pytest tests/brick -q
```
Dans le bloc `on: ... paths:` du même workflow (lignes ~9-22), ajouter les entrées :
```yaml
      - "roles/**/brick.yml"
      - "roles/backup-config/vars/bricks_backup_*.yml"
      - "scripts/brick_generate.py"
      - "scripts/brick.schema.json"
      - "tests/brick/**"
```
(Respecter l'indentation existante de la liste ; si le workflow n'a pas de filtre `paths`, ne rien ajouter — il tourne déjà sur tout push.)

- [ ] **Step 4: Vérifier localement**

Run: `cd ~/work/infra/VPAI && source .venv/bin/activate && make lint && make test-bricks`
Expected: lint complet vert (yamllint + ansible-lint + brick validate + drift OK), `38 passed`

- [ ] **Step 5: Test négatif de la garde (non committé)**

Run:
```bash
cd ~/work/infra/VPAI
git diff --quiet roles/trek/brick.yml || { echo "brick.yml a des modifs locales — test annulé"; exit 1; }
sed -i 's/archive: data/archive: sqlite/' roles/trek/brick.yml
make lint-bricks; echo "exit=$?"
git checkout -- roles/trek/brick.yml
```
(garde `git diff --quiet` d'abord : le `git checkout --` final ne doit jamais détruire une modif locale préexistante — revue Codex)
Expected: `DÉRIVE: roles/backup-config/vars/bricks_backup_sese.yml ...` et `exit=2` (make relaie l'échec) — puis restauration propre.

- [ ] **Step 6: Commit**

```bash
cd ~/work/infra/VPAI
git add requirements.txt Makefile .github/workflows/ci.yml
git commit -m "ci(brick): make lint-bricks + garde de dérive + tests dans le job lint

Un manifeste invalide ou un fichier généré édité à la main casse
make lint et la CI (spec brick-manifest §4/§5)."
```

---

### Task 7: Déploiement prod + preuve par run réel

**Files:**
- Aucun nouveau — déploiement du rôle `backup-config` sur Sese-AI et vérification.

**Interfaces:**
- Consumes: tout ce qui précède, committé sur `main`.
- Produces: `pre-backup.sh` et `backup-cleanup.sh` régénérés en prod depuis les vars brick.yml ; run réel produisant les archives TREK ; 2e run Ansible idempotent.

- [ ] **Step 1: Check-mode d'abord**

Run:
```bash
cd ~/work/infra/VPAI && source .venv/bin/activate
ansible-playbook playbooks/stacks/site.yml --tags backup-config --check -e prod_ip=100.64.0.14
```
Expected: `changed` uniquement sur les 2 tâches template (pre-backup, cleanup) — pas d'erreur `brick_backup_tar_jobs undefined` (l'include_vars tourne aussi en check mode). Le diff du pre-backup est masqué (`no_log`) — attendu, ne pas le retirer.

- [ ] **Step 2: Déployer**

Run: `make deploy-role ROLE=backup-config ENV=prod EXTRA_ARGS='-e prod_ip=100.64.0.14'`
Expected: play récap sans failed ; changed sur les templates.

- [ ] **Step 3: Résoudre le chemin exact du script en prod, puis le vérifier**

(pas de glob `/opt/*` dans une commande d'exécution — plusieurs projets sous `/opt` feraient exécuter le premier et passer les autres en arguments — revue Codex, HIGH glob)

Run:
```bash
SCRIPT=$(ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 'ls /opt/*/scripts/pre-backup.sh')
# arrêt DUR si zéro ou plusieurs candidats (une sortie vide n'est pas « une ligne »)
[ -n "${SCRIPT}" ] && [ "$(printf '%s\n' "${SCRIPT}" | wc -l)" -eq 1 ] \
  || { echo "zéro ou plusieurs pre-backup.sh sous /opt — résoudre manuellement, STOP"; exit 1; }
echo "${SCRIPT}"
PROJ_DIR=$(dirname "$(dirname "${SCRIPT}")")
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "grep -n '(brick.yml)' ${SCRIPT}; grep -n 'data/trek' ${SCRIPT}; grep -n 'for SUBDIR' ${PROJ_DIR}/scripts/backup-cleanup.sh"
```
Expected: 2 lignes `Backing up trek/... (brick.yml)`, les appels `backup_tar` avec chemins TREK résolus (`.../data/trek`, `.../data/trek-uploads`), cleanup listant `... grafana trek`.

- [ ] **Step 4: Run réel**

Run (réutilise `${SCRIPT}`/`${PROJ_DIR}` du Step 3 ; sortie dans un fichier pour ne pas
masquer le code retour derrière `tail`, marqueur temporel pour prouver que les archives
viennent de CE run — revue Codex round 2) :
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 "
  touch /tmp/prebackup.marker
  bash ${SCRIPT} > /tmp/prebackup.out 2>&1
  RC=\$?
  echo exit=\${RC}
  tail -30 /tmp/prebackup.out
  echo '--- archives de ce run :'
  find ${PROJ_DIR}/backups/trek -type f -newer /tmp/prebackup.marker -size +0 -exec ls -lh {} +
  exit \${RC}
"
echo "ssh exit=$?"   # doit être 0 — le code du backup est propagé, pas celui de tail/find
```
Expected: `exit=0`, `Backing up trek/data (brick.yml)...` + `trek/uploads`, aucun `WARNING`/`ERREUR` sur les archives trek, `Pre-backup completed successfully`, et exactement 2 archives `.tar.gz` non vides plus récentes que le marqueur.

- [ ] **Step 5: Idempotence (2e run Ansible = 0 changed)**

Run: `set -o pipefail; ansible-playbook playbooks/stacks/site.yml --tags backup-config -e prod_ip=100.64.0.14 | tail -5; echo "play exit=$?"`
Expected: `changed=0` au récap ET `play exit=0` (pipefail : un échec du play ne peut pas être masqué par `tail`).

- [ ] **Step 6: Pousser**

Run — en DEUX temps (revue Codex round 2 : inspection puis push, jamais enchaînés aveuglément) :
```bash
cd ~/work/infra/VPAI
[ "$(git remote get-url origin)" = "git@github-seko:Mobutoo/vpai.git" ] || { echo "remote origin inattendu — STOP"; exit 1; }
git log --oneline @{upstream}..HEAD
```
Lire la liste : elle doit contenir les commits de ce plan + la dette antérieure connue (~15 commits signalés en mémoire — vérifier la liste affichée, pas le chiffre). **Si un commit inattendu apparaît, STOP et remonter à l'opérateur.** Sinon :
```bash
git push origin main
```
Expected: push OK, la CI GitHub rejoue validate + drift + tests.

> **Finding Codex REJETÉ (à remonter au gate humain)** : le round 2 demandait « push
> sur branche/PR + CI verte AVANT tout déploiement prod ». Rejeté pour ce plan :
> repo mono-opérateur dont le flux établi déploie depuis le main local (historique
> constant du projet), les gates CI (validate + drift + pytest + lint) sont
> exécutés à l'identique en local aux Tasks 5-6 AVANT le déploiement, et la preuve
> décisive (run réel du backup, Step 4) n'est de toute façon pas couverte par la
> CI. Basculer le repo en flux PR est un changement de process hors périmètre.

---

## Self-Review (fait à la rédaction)

- **Couverture spec** : §8 étape 1 (schéma + validation → Tasks 1-2), étape 2 (générateur backup + assertion #2 + TREK → Tasks 3-5), garde CI §4 (→ Tasks 3/6). Assertions §5 : #1/#7 (schéma), #2/#5/#6 (Task 2), #8 (schéma). #3/#4 requis par le schéma. `--resolve-digest` (§5 #1 exception) = hors périmètre, séquencé avec la forge (§8 étape 5) — le digest TREK est résolu manuellement (Task 4 Step 1), conforme.
- **Générateurs alertes/compose/Caddy/tags/images** : hors périmètre de ce plan (étapes 3-5 du séquencement), plans suivants.
- **Cohérence types** : `brick_backup_tar_jobs = [{brick, archive, src, include}]` identique entre générateur (Task 3), fixture de rendu (Task 5) et templates (Task 5). `GENERATED_HEADER` partagé. `validate_manifest(manifest, path, versions)` stable de Task 1 à 3.
- **Pièges repo intégrés** : `no_log` préservé, `--context local` docker, `include: ['.']` défaut, parité chemins `backup_trek_dir`, cleanup statique corrigé, yamllint sur fichiers générés, `-e prod_ip=100.64.0.14` pour deploy local.
- **Revue Codex intégrée (2026-08-05, rapport `~/work/ops/loops/reviews/REVIEW-FILE-2026-08-05-brick-generate-p1-schema-backup-20260805-0955.md`, 5 HIGH confirmés + 8 MED + 1 LOW, tous traités)** : garde de types dans les assertions (HIGH TypeError) ; fichier de vars PAR environnement `bricks_backup_<env>.yml` + `brick_backup_env` (HIGH env) ; charset strict `src`/`include` au schéma + quoting par élément dans le template (HIGH injection) ; compteur `BRICK_TAR_FAILURES` + `exit 1` avant heartbeat → alerte dead-man Uptime Kuma (HIGH `|| true`) ; chemins prod résolus au lieu de globs `/opt/*` (HIGH glob) ; compteurs de tests recalculés 12/25/33/38, stratégie d'import unique (conftest + PEP 420), refus des doublons (brick, archive), grep `backup_trek_dir` sans filtre d'extension, commit Task 5 complet, paths CI incluant les vars générées, garde `git diff --quiet` au test négatif, contrôle `@{upstream}..HEAD` avant push.
- **Revue Codex round 2 intégrée (rapport `...-20260805-1002.md`, 7 HIGH / 4 MED / 1 LOW)** : `--env` borné `[a-z0-9][a-z0-9_-]*` (traversée de chemin) ; `brick_backup_env` SANS défaut de rôle — assert + définition explicite dans l'inventaire prod ; `| quote` (shlex) sur `src`/`include` résolus + job hostile dans le test de rendu ; arrêt dur si zéro/plusieurs `pre-backup.sh` sous `/opt` ; capture du code retour hors pipe `tail` + marqueur temporel prouvant les archives du run ; `git remote get-url origin` comparé exactement ; push en deux temps avec inspection ; clés env sensibles (SECRET/PASSWORD/TOKEN/API_KEY/PRIVATE_KEY) exigent `vault_ref` ; références résiduelles au fichier unique corrigées. **1 HIGH rejeté avec justification** (flux PR + CI verte avant déploiement — voir encadré Task 7 Step 6) : à trancher au gate humain.
- **Revue Codex round 3 intégrée (rapport `...-20260805-1011.md`, 2 HIGH / 5 MED / 1 LOW)** : refus des segments `..` dans `src`/`include` (schéma `not pattern` + test) ; marqueurs secrets élargis (SECRET/PASS/TOKEN/KEY/CREDENTIAL, faux positifs assumés) ; normalisation tirets→underscores pour le cross-check `versions.yml` ; garde de dérive CI bouclant sur TOUS les `bricks_backup_*.yml` committés ; code retour du run réel propagé via `exit ${RC}` en fin de commande ssh ; `pipefail` sur la vérification d'idempotence ; `OSError` convertie en `BrickError` dans `load_manifest`. Le 2e HIGH = re-remontée du finding PR/CI déjà rejeté au round 2 — **rejet maintenu** (règle d'arrêt convergence : pas de boucle sur un finding re-remonté), statut RESIDUAL_REJECTED à trancher au gate humain.
