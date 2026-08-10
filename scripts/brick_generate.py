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
  --generate alerts --env NOM   (ré)génère les règles d'alerte Grafana par brique
  ... --check                   ne réécrit pas : échoue (exit 1) si le fichier committé diffère
  --list-envs                   liste l'union des deployment.environments déclarés
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


class _FoldedStr(str):
    """Sous-classe marqueur : dumpée en style YAML replié (`>-`) pour que
    PyYAML rewrappe les expressions PromQL longues (une seule ligne sans
    espace exploitable en dessous de ~120c) au lieu d'émettre une ligne
    dépassant la limite yamllint (finding TV LOW : 167 > 160). Round-trip
    exact : le pli est réabsorbé en un unique espace par tout parseur YAML,
    et PromQL est insensible aux espaces/retours à la ligne."""


def _represent_folded_str(dumper: yaml.Dumper, data: "_FoldedStr") -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style=">")


yaml.SafeDumper.add_representer(_FoldedStr, _represent_folded_str)

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

    alert_kind_list = [
        a.get("kind")
        for a in _list(_dict(manifest.get("monitoring")).get("alerts"))
        if isinstance(a, dict)
    ]
    alert_kinds = set(alert_kind_list)
    duplicate_kinds = sorted({k for k in alert_kinds if alert_kind_list.count(k) > 1})
    if duplicate_kinds:
        errors.append(
            f"{path}: monitoring.alerts contient des kind dupliqués : "
            f"{', '.join(duplicate_kinds)} — deux règles au même uid (brick-<name>-<kind>) "
            "seraient générées, rejetées par Grafana"
        )
    if _dict(manifest.get("runtime")).get("healthcheck") is not None:
        missing = {"service_down", "restart_loop"} - alert_kinds
        if missing:
            errors.append(
                f"{path}: monitoring.alerts doit couvrir service_down et restart_loop "
                f"(manquent : {', '.join(sorted(missing))}) — spec §5 #5"
            )

    # --- Borne de window (finding TV LOW voisin du MEDIUM ci-dessus) : le
    # pattern JSON Schema ^[0-9]+[smhd]$ seul accepte `0m` (fenêtre nulle,
    # rate() PromQL indéfini) et `999999d` (fenêtre absurde). JSON Schema ne
    # sait pas convertir les unités pour borner numériquement une string —
    # assertion mécanique ici, dans la même veine que les autres §5. Portée
    # volontairement limitée à http_5xx_rate : c'est le seul kind où window
    # est honoré (cf. if/then du schéma juste au-dessus).
    for alert in _list(_dict(manifest.get("monitoring")).get("alerts")):
        if not isinstance(alert, dict):
            continue
        window = alert.get("window")
        if not (isinstance(window, str) and re.fullmatch(r"[0-9]+[smhd]", window)):
            continue  # motif déjà rejeté par le schéma — pas de double message
        seconds = _duration_seconds(window)
        if not (_WINDOW_MIN_SECONDS <= seconds <= _WINDOW_MAX_SECONDS):
            errors.append(
                f"{path}: monitoring.alerts[].window {window!r} hors bornes raisonnables "
                "(minimum 1m, maximum 7d)"
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
    # PASS attrape PASSWORD/DB_PASS, URL/URI/DSN/CONN attrapent DATABASE_URL/
    # SENTRY_DSN/CONNECTION_STRING, PW attrape DB_PW/ADMIN_PW, SALT/AUTH/SIGN
    # attrapent *_SALT/AUTH_TOKEN/HMAC_SIGN*, PRIVATE attrape *_PRIVATE_KEY
    # (5 derniers ajoutés revue finale de branche 2026-08-05) — souvent porteurs
    # de credentials embarqués) : un faux positif se règle en passant par
    # vault_ref ou en renommant la variable — l'inverse (fuite) ne se règle pas.
    SECRET_KEY_MARKERS = (
        "SECRET",
        "PASS",
        "TOKEN",
        "KEY",
        "CREDENTIAL",
        "URL",
        "URI",
        "DSN",
        "CONN",
        "PW",
        "SALT",
        "AUTH",
        "SIGN",
        "PRIVATE",
    )
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
    name = identity.get("name") if isinstance(identity.get("name"), str) else None
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


def _require_repo(repo: Path) -> str | None:
    if not repo.is_dir():
        return f"{repo} n'est pas un répertoire"
    return None


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
    error = _require_repo(repo)
    if error:
        print(f"ERREUR: {error}", file=sys.stderr)
        return 2
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
        current = target.read_text(encoding="utf-8") if target.exists() else ""
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
    target.write_text(rendered, encoding="utf-8")
    print(f"Écrit : {rel_path}")
    return 0


ALERT_KIND_ORDER = ["service_down", "restart_loop", "http_5xx_rate"]


def alerts_yaml_path(env: str) -> str:
    """Un fichier PAR environnement, même discipline que backup_vars_path :
    un déploiement d'un autre env ne doit jamais hériter des règles de sese."""
    return f"roles/monitoring/templates/grafana/provisioning/bricks/alerting-bricks-{env}.yaml"


# NON RELIÉ À UN DÉPLOIEMENT ANSIBLE (décision volontaire, cf. en-tête généré
# ci-dessous) : les producteurs des métriques utilisées ici sont documentés
# absents pour la stack actuelle — cAdvisor ne réassocie plus les cgroups aux
# conteneurs nommés depuis la migration socket-proxy (REX-77 2026-03-10,
# roles/monitoring/templates/grafana/provisioning/alerting.yaml.j2 en-tête) et
# rien ne scrape encore les métriques Caddy (roles/monitoring/templates/
# config.alloy.j2 ne déclare aucun job "caddy"). Câbler un déploiement
# maintenant reproduirait l'anti-pattern déjà purgé de alerting.yaml.j2 :
# des règles qui ne tirent jamais que DatasourceNoData.
#
# Label `server` (metric_reverse_proxy_http_requests_total{server=~...} —
# nom générique ici pour ne pas répéter le nom du reverse-proxy HTTP déjà cité
# plus haut) : convention PROVISOIRE, non vérifiée contre un job de scrape
# réel (aucun job dédié dans le rôle monitoring à ce jour) et non documentée
# ailleurs dans le repo. Épinglée ici et gelée par test
# (tests/brick/test_alerts_generator.py::test_http_5xx_rate_label_is_server)
# pour qu'un futur câblage du scrape la confirme ou la corrige explicitement
# plutôt que de la découvrir en prod (revue findings TV, MEDIUM label).
def _promql_syntax_errors(expr: str) -> list[str]:
    """Vérification STRUCTURELLE, pas un vrai parseur PromQL : promtool est
    absent de cet environnement (vérifié en session). Parenthèses/accolades/
    crochets équilibrés + jeu de caractères plausible. Documenté comme tel,
    pas présenté comme une validation `promtool check rules` complète."""
    errors: list[str] = []
    if not expr or not expr.strip():
        errors.append("expression PromQL vide")
        return errors
    pairs = {")": "(", "}": "{", "]": "["}
    stack: list[str] = []
    for ch in expr:
        if ch in "({[":
            stack.append(ch)
        elif ch in ")}]":
            if not stack or stack[-1] != pairs[ch]:
                errors.append(f"parenthèses/accolades déséquilibrées : {expr!r}")
                stack = []
                break
            stack.pop()
    else:
        if stack:
            errors.append(f"parenthèses/accolades non refermées : {expr!r}")
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        "_:{}()[],.=~!<>\"'*/+%-^$ "
    )
    bad_chars = sorted({ch for ch in expr if ch not in allowed})
    if bad_chars:
        errors.append(f"caractères inattendus dans l'expression PromQL : {bad_chars!r}")
    return errors


_DURATION_FACTORS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_WINDOW_MIN_SECONDS = 60  # 1m — en dessous, rate() PromQL sur une fenêtre nulle/quasi-nulle
_WINDOW_MAX_SECONDS = 7 * 86400  # 7d — au-delà, fenêtre d'évaluation déraisonnable


def _duration_seconds(duration: str) -> int:
    """Convertit une durée `^[0-9]+[smhd]$` (déjà garantie par le schéma pour
    monitoring.alerts[].window) en secondes. Pas de fallback silencieux : une
    valeur hors motif est un bug de schéma, pas un cas à absorber ici."""
    match = re.fullmatch(r"([0-9]+)([smhd])", duration)
    if not match:
        raise BrickError(f"durée invalide (motif attendu [0-9]+[smhd]) : {duration!r}")
    value, unit = match.groups()
    return int(value) * _DURATION_FACTORS[unit]


def _alert_rule(brick: str, alert: dict) -> dict:
    """Construit une règle d'alerte unified-alerting (schéma identique à
    alerting-prisme.yaml.j2) à partir d'un item monitoring.alerts[] du
    manifeste. Nom de conteneur apparié par regex `.*_<brick>$` — pas de
    project_name interpolé : l'artefact reste autonome quel que soit
    l'environnement (project_name diffère déjà : javisi vs mediahall).

    `range_seconds` peuple `data[0].relativeTimeRange.from` (fenêtre
    d'évaluation Grafana) — dérivé de `window` pour http_5xx_rate (>= 2x la
    fenêtre du rate, pour ne jamais évaluer sur moins de données que le rate
    lui-même ne couvre), fixe (900s) pour les deux autres kinds dont
    l'expression ne dépend pas de `window`. `for` (durée de pending avant
    passage en Alerting) reste une constante par kind : ce n'est PAS la même
    grandeur que la fenêtre du rate et ne doit pas être dérivée de `window`
    (revue findings TV, HIGH)."""
    kind = alert["kind"]
    container_pat = f".*_{brick}$"
    range_seconds = 900
    if kind == "service_down":
        expr = f'(absent(container_last_seen{{name=~"{container_pat}"}}) or vector(0))'
        threshold, operator, for_, severity = 0, "gt", "5m", "critical"
        title = f"{brick}: service down"
    elif kind == "restart_loop":
        expr = f'(changes(container_start_time_seconds{{name=~"{container_pat}"}}[10m]) or vector(0))'
        threshold, operator, for_, severity = 3, "gt", "1m", "warning"
        title = f"{brick}: restart loop (> 3 redémarrages / 10 min)"
    elif kind == "http_5xx_rate":
        threshold_raw = alert.get("threshold", "5%")
        try:
            threshold = float(str(threshold_raw).rstrip("%"))
        except ValueError as exc:
            raise BrickError(f"{brick}: threshold http_5xx_rate invalide : {threshold_raw!r}") from exc
        window = alert.get("window", "5m")
        window_seconds = _duration_seconds(window)
        range_seconds = max(2 * window_seconds, 900)
        expr = (
            f"((sum(rate(caddy_http_requests_total{{server=~\"{container_pat}\", code=~\"5..\"}}[{window}])) "
            f"or vector(0)) / (sum(rate(caddy_http_requests_total{{server=~\"{container_pat}\"}}[{window}])) "
            f"or vector(1))) * 100"
        )
        operator, for_, severity = "gt", "5m", "warning"
        title = f"{brick}: taux d'erreurs HTTP 5xx > {threshold_raw}"
    else:
        raise BrickError(f"{brick}: kind d'alerte inconnu : {kind!r}")
    return {
        "uid": f"brick-{brick}-{kind}",
        "title": title,
        "expr": expr,
        "threshold": threshold,
        "operator": operator,
        "for": for_,
        "range_seconds": range_seconds,
        "severity": severity,
    }


def generate_alerts_yaml(manifests: list[tuple[Path, dict]], env: str) -> str:
    entries: list[tuple[str, str, dict]] = []
    syntax_errors: list[str] = []
    for _path, manifest in manifests:
        if env not in manifest.get("deployment", {}).get("environments", []):
            continue
        name = manifest["identity"]["name"]
        alerts = manifest.get("monitoring", {}).get("alerts") or []
        for alert in alerts:
            rule = _alert_rule(name, alert)
            syntax_errors.extend(
                f"{name}/{alert['kind']}: {err}" for err in _promql_syntax_errors(rule["expr"])
            )
            entries.append((name, alert["kind"], rule))
    if syntax_errors:
        raise BrickError("syntaxe PromQL invalide — " + "; ".join(syntax_errors))
    entries.sort(key=lambda e: (e[0], ALERT_KIND_ORDER.index(e[1])))

    rules = [
        {
            "uid": rule["uid"],
            "title": rule["title"],
            "condition": "C",
            "data": [
                {
                    "refId": "A",
                    "relativeTimeRange": {"from": rule["range_seconds"], "to": 0},
                    "datasourceUid": "VictoriaMetrics",
                    "model": {
                        "expr": _FoldedStr(rule["expr"]),
                        "intervalMs": 30000,
                        "maxDataPoints": 43200,
                    },
                },
                {
                    "refId": "B",
                    "datasourceUid": "__expr__",
                    "model": {"type": "reduce", "expression": "A", "reducer": "last"},
                },
                {
                    "refId": "C",
                    "datasourceUid": "__expr__",
                    "model": {
                        "type": "threshold",
                        "expression": "B",
                        "conditions": [
                            {"evaluator": {"type": rule["operator"], "params": [rule["threshold"]]}}
                        ],
                    },
                },
            ],
            "for": rule["for"],
            "noDataState": "Alerting",
            "execErrState": "Error",
            "annotations": {"summary": rule["title"]},
            "labels": {"severity": rule["severity"], "brick": name},
        }
        for name, _kind, rule in entries
    ]
    doc = {
        "apiVersion": 1,
        "groups": (
            [
                {
                    "orgId": 1,
                    "name": f"Bricks générées — {env}",
                    "folder": "Bricks",
                    "interval": "1m",
                    "rules": rules,
                }
            ]
            if rules
            else []
        ),
    }
    body = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False, width=80)
    return (
        GENERATED_HEADER
        + f"# commande : python3 scripts/brick_generate.py --generate alerts --env {env}\n"
        + f"# environnement : {env} — règles d'alerte unified-alerting dérivées de monitoring.alerts.\n"
        + "# NON RELIÉ à un déploiement Ansible : producteurs absents pour cette stack\n"
        + "# (cAdvisor par-conteneur cassé depuis la migration socket-proxy, REX-77\n"
        + "# 2026-03-10 — cf. alerting.yaml.j2 en-tête ; aucun job Caddy dans\n"
        + "# config.alloy.j2 pour http_5xx_rate). Câbler un déploiement recréerait\n"
        + "# l'anti-pattern DatasourceNoData déjà purgé de alerting.yaml.j2 : ne PAS\n"
        + "# ajouter de tâche de déploiement avant que ces producteurs existent.\n"
        + "---\n"
        + body
    )


def cmd_generate_alerts(repo: Path, env: str, check: bool) -> int:
    error = _require_repo(repo)
    if error:
        print(f"ERREUR: {error}", file=sys.stderr)
        return 2
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
        rendered = generate_alerts_yaml(manifests, env)
    except BrickError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 1
    rel_path = alerts_yaml_path(env)
    target = repo / rel_path
    if check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != rendered:
            print(
                f"DÉRIVE: {rel_path} ne correspond plus aux brick.yml — "
                f"régénérer avec : python3 scripts/brick_generate.py --generate alerts --env {env}",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {rel_path} à jour.")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"Écrit : {rel_path}")
    return 0


def declared_environments(repo: Path = REPO) -> list[str]:
    """Union des `deployment.environments` de tous les manifestes valides —
    source de vérité pour piloter les boucles de dérive CI (Makefile), plutôt
    qu'un glob des fichiers générés déjà présents (un artefact supprimé à la
    main échapperait sinon à la garde, spec §4/§5)."""
    envs: set[str] = set()
    for path in find_manifests(repo):
        try:
            manifest = load_manifest(path)
        except BrickError:
            continue
        deployment = manifest.get("deployment")
        if isinstance(deployment, dict):
            for env in deployment.get("environments") or []:
                if isinstance(env, str):
                    envs.add(env)
    return sorted(envs)


_BACKUP_ARTIFACT_RE = re.compile(r"^bricks_backup_(?P<env>.+)\.yml$")
_ALERTS_ARTIFACT_RE = re.compile(r"^alerting-bricks-(?P<env>.+)\.yaml$")


def backup_artifact_environments(repo: Path = REPO) -> set[str]:
    """Envs déduits des `roles/backup-config/vars/bricks_backup_<env>.yml`
    présents sur disque. Un env d'inventaire réel (ex. preprod) peut
    légitimement précéder tout brick.yml qui le déclare : le fichier est
    consommé inconditionnellement par roles/backup-config (include_vars, pas
    de défaut) — ce n'est PAS un artefact orphelin, mais son contenu doit
    quand même être gardé contre la dérive manuelle (spec §4/§5, finding TV
    HIGH couverture)."""
    backup_dir = repo / "roles/backup-config/vars"
    if not backup_dir.is_dir():
        return set()
    envs: set[str] = set()
    for candidate in backup_dir.glob("bricks_backup_*.yml"):
        match = _BACKUP_ARTIFACT_RE.match(candidate.name)
        if match:
            envs.add(match.group("env"))
    return envs


def alerts_artifact_environments(repo: Path = REPO) -> set[str]:
    """Envs déduits des `alerting-bricks-<env>.yaml` présents sur disque.
    Contrairement au backup, ce générateur n'est câblé nulle part dans les
    rôles (cf. en-tête généré) : un env sans manifeste qui le déclare est ici
    toujours un artefact mort (cf. cmd_lint)."""
    alerts_dir = repo / "roles/monitoring/templates/grafana/provisioning/bricks"
    if not alerts_dir.is_dir():
        return set()
    envs: set[str] = set()
    for candidate in alerts_dir.glob("alerting-bricks-*.yaml"):
        match = _ALERTS_ARTIFACT_RE.match(candidate.name)
        if match:
            envs.add(match.group("env"))
    return envs


def cmd_list_envs(repo: Path, generator: str | None = None) -> int:
    error = _require_repo(repo)
    if error:
        print(f"ERREUR: {error}", file=sys.stderr)
        return 2
    envs = set(declared_environments(repo))
    # --generator étend l'union aux envs déduits des artefacts déjà présents
    # sur disque pour CE générateur, afin que le pilotage des boucles de
    # dérive (Makefile) ne dépende plus uniquement des manifestes déclarés
    # (finding TV HIGH : preprod backup n'était plus gardé).
    if generator == "backup":
        envs |= backup_artifact_environments(repo)
    elif generator == "alerts":
        envs |= alerts_artifact_environments(repo)
    for env in sorted(envs):
        print(env)
    return 0


def cmd_validate(repo: Path) -> int:
    error = _require_repo(repo)
    if error:
        print(f"ERREUR: {error}", file=sys.stderr)
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
    error = _require_repo(repo)
    if error:
        print(f"ERREUR: {error}", file=sys.stderr)
        return 2
    orphans = []
    for path in find_manifests(repo):
        try:
            manifest = load_manifest(path)
        except BrickError as exc:
            print(f"ERREUR: {exc}", file=sys.stderr)
            continue
        deployment = manifest.get("deployment")
        if not (isinstance(deployment, dict) and deployment.get("environments")):
            orphans.append(path)
    if orphans:
        print("Manifestes orphelins (aucun environnement — jamais sélectionnés par --env) :")
        for path in orphans:
            print(f"  - {path}")
    else:
        print("Aucun manifeste orphelin.")

    # Orphelins d'ARTEFACTS d'alertes : contrairement à bricks_backup_<env>.yml
    # (consommé inconditionnellement par roles/backup-config via include_vars —
    # un env d'inventaire réel peut légitimement précéder tout brick.yml qui le
    # déclare, cf. inventory/group_vars/preprod), alerting-bricks-<env>.yaml
    # n'est câblé nulle part dans les rôles (grep vide, en-tête généré
    # "NON RELIÉ à un déploiement Ansible") : un fichier pour un env qu'aucun
    # manifeste ne déclare est donc toujours un artefact mort, jamais un
    # scaffold légitime — à la différence des vars de backup.
    declared = set(declared_environments(repo))
    alerts_dir = (repo / alerts_yaml_path("_")).parent
    alert_artifact_orphans: list[Path] = [
        alerts_dir / f"alerting-bricks-{env}.yaml"
        for env in sorted(alerts_artifact_environments(repo) - declared)
    ]
    if alert_artifact_orphans:
        print(
            "Artefacts d'alertes orphelins (env non déclaré par aucun brick.yml, "
            "non câblés à un déploiement) :"
        )
        for path in alert_artifact_orphans:
            print(f"  - {path}")
        orphans.extend(alert_artifact_orphans)
    return 1 if orphans else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--lint", action="store_true")
    parser.add_argument("--generate", choices=["backup", "alerts"])
    parser.add_argument("--env")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--list-envs", action="store_true")
    parser.add_argument(
        "--generator",
        choices=["backup", "alerts"],
        help=(
            "avec --list-envs : étend l'union aux envs déduits des artefacts déjà "
            "présents pour ce générateur (pas seulement declared_environments)"
        ),
    )
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args(argv)
    if args.list_envs:
        return cmd_list_envs(args.repo, args.generator)
    if args.generate == "backup":
        if not args.env:
            parser.error("--generate backup exige --env")
        return cmd_generate_backup(args.repo, args.env, args.check)
    if args.generate == "alerts":
        if not args.env:
            parser.error("--generate alerts exige --env")
        return cmd_generate_alerts(args.repo, args.env, args.check)
    if args.validate and args.lint:
        rc_validate = cmd_validate(args.repo)
        rc_lint = cmd_lint(args.repo)
        return rc_validate or rc_lint
    if args.validate:
        return cmd_validate(args.repo)
    if args.lint:
        return cmd_lint(args.repo)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
