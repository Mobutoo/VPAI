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
        _schema_validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    return _schema_validator


def find_manifests(repo: Path = REPO) -> list[Path]:
    return sorted(repo.glob("roles/*/brick.yml"))


def load_manifest(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
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
    return yaml.safe_load(versions_path.read_text(encoding="utf-8")) or {}


def validate_manifest(manifest: dict, path: Path, versions: dict) -> list[str]:
    errors: list[str] = []
    for err in sorted(
        _validator().iter_errors(manifest),
        key=lambda e: ([(type(p).__name__, str(p)) for p in e.absolute_path], e.message),
    ):
        where = ".".join(str(p) for p in err.absolute_path) or "<racine>"
        errors.append(f"{path}: [{where}] {err.message}")
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
        if (
            isinstance(key, str)
            and any(marker in key.upper() for marker in SECRET_KEY_MARKERS)
            and not (isinstance(value, dict) and "vault_ref" in value)
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
    return errors


def cmd_validate(repo: Path) -> int:
    if not repo.is_dir():
        print(f"ERREUR: {repo} n'est pas un répertoire", file=sys.stderr)
        return 2
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--lint", action="store_true")
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args(argv)
    if args.validate:
        return cmd_validate(args.repo)
    if args.lint:
        return cmd_lint(args.repo)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
