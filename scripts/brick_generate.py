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
