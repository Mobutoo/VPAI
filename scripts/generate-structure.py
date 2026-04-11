#!/usr/bin/env python3
"""
generate-structure.py — Génère docs/STRUCTURE.md depuis platform.yaml.

Usage:
    python scripts/generate-structure.py
    python scripts/generate-structure.py --check   # exit 1 si STRUCTURE.md serait modifié

Source de vérité: platform.yaml (racine du repo)
Sortie: docs/STRUCTURE.md
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML requis: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Descriptions des roles (à maintenir ici quand on ajoute un role)
# ---------------------------------------------------------------------------
ROLE_DESCRIPTIONS = {
    # core
    "common":              "Paquets système, utilisateur déploiement, dépôts Debian",
    "docker":              "Docker CE + Docker Compose V2, daemon.json, log rotation",
    "hardening":           "SSH durcissement, UFW, Fail2ban, CrowdSec",
    # platform
    "postgresql":          "PostgreSQL 18.3, init.sql, migrations",
    "redis":               "Redis 8.4.0",
    "qdrant":              "Qdrant v1.16.3 — base vectorielle",
    "caddy":               "Reverse proxy TLS auto, ACL VPN",
    "headscale-node":      "Client Tailscale, join réseau Headscale",
    "docker-stack":        "docker-compose-infra.yml + docker-compose.yml",
    "app-scaffold":        "Infrastructure Hetzner App Factory (réseaux Docker, GHCR)",
    # apps
    "n8n":                 "n8n 2.7.3 — orchestration workflows",
    "litellm":             "LiteLLM v1.81.3 — proxy modèles IA",
    "openclaw":            "OpenClaw 2026.3.13-1 — agent IA",
    "nocodb":              "NocoDB 0.301.3 — base de données no-code",
    "plane":               "Plane v1.2.2 — gestion de projet",
    "kitsu":               "Kitsu 1.0.19 — production management",
    "firefly":             "Firefly III 6.5.3 — finances personnelles",
    "zimboo":              "Zimboo v1.14.0",
    "mealie":              "Mealie v3.12.0 — gestion recettes",
    "grocy":               "Grocy 4.6.0 — gestion stocks",
    "koodia":              "Koodia v0.1.0",
    "palais":              "Dashboard mission control + MCP",
    "flash-suite":         "Flash Suite — stack créative auto-contenue",
    "story-engine":        "StoryEngine — pipeline narration IA",
    "typebot":             "Typebot 3.16+ — chatbots",
    "penpot":              "Penpot — design collaboratif (VPS éphémère)",
    "metube":              "MeTube — téléchargement vidéo (aussi sur Waza)",
    "carbone":             "Carbone — génération documents",
    "gotenberg":           "Gotenberg — conversion PDF",
    "webhook-relay":       "Relay webhooks (n8n ↔ services)",
    "llamaindex-memory":   "LlamaIndex memory worker (Sese-AI)",
    "obsidian":            "Obsidian sync server",
    # provision
    "n8n-provision":              "Création compte owner n8n via API",
    "plane-provision":            "Bucket MinIO Plane",
    "kitsu-provision":            "Init DB Kitsu/Zou, admin user",
    "app-factory-provision":      "Tables NocoDB + collections Qdrant App Factory",
    "content-factory-provision":  "Tables NocoDB + collections Qdrant Content Factory",
    # monitoring
    "monitoring":          "VictoriaMetrics, Loki, Grafana Alloy, Grafana",
    "diun":                "DIUN 4.31.0 — alertes nouvelles versions images",
    "uptime-config":       "Configuration uptime monitoring",
    "obsidian-collector":  "Collecte notes Obsidian (Sese-AI)",
    "smoke-tests":         "Tests post-déploiement (tag `always`)",
    # workstation
    "workstation-common":        "Base Ubuntu, Docker, Tailscale",
    "workstation-caddy":         "Caddy local (proxy outils créatifs)",
    "workstation-monitoring":    "Monitoring local Pi",
    "claude-code":               "Claude Code CLI",
    "codex-cli":                 "Codex CLI (OpenAI)",
    "gemini-cli":                "Gemini CLI (Google)",
    "opencode":                  "OpenCode 1.2.15",
    "comfyui":                   "ComfyUI ARM64 CPU-only + MCP studio",
    "remotion":                  "Remotion — vidéo programmatique",
    "opencut":                   "OpenCut — montage vidéo",
    "openpencil":                "OpenPencil — dessin vectoriel",
    "videoref-engine":           "VideoRef Engine — référence vidéo",
    "metube_ws":                 "MeTube local (téléchargement vidéo)",
    "n8n-mcp":                   "n8n-docs MCP server (documentation n8n locale)",
    "llamaindex-memory-worker":  "Worker mémoire IA (Qdrant ingestion)",
    "obsidian-collector-pi":     "Collecte notes Obsidian (Pi)",
    # ops
    "backup-config":  "Configuration backup Zerobyte",
    "vpn-dns":        "Mise à jour extra_records.json Headscale (split DNS)",
}

# Pour workstation/metube (distinct de apps/metube)
WORKSTATION_ROLE_DESCRIPTIONS = dict(ROLE_DESCRIPTIONS)
WORKSTATION_ROLE_DESCRIPTIONS["metube"] = "MeTube local (téléchargement vidéo)"

# ---------------------------------------------------------------------------
# Sections statiques
# ---------------------------------------------------------------------------
PLAYBOOKS_SECTION = """\
## Structure `playbooks/`

```
playbooks/
├── stacks/
│   ├── site.yml              # Déploiement complet Sese-AI (prod/preprod)
│   └── seed-preprod.yml      # Initialisation preprod depuis prod
├── hosts/
│   ├── workstation.yml       # Déploiement Waza (Raspberry Pi 5)
│   └── app-prod.yml          # Déploiement serveur Prod Apps (Hetzner)
├── apps/
│   ├── flash-suite.yml       # Déploiement Flash Suite standalone
│   └── story-engine.yml      # Déploiement StoryEngine standalone
├── bootstrap/
│   ├── provision-hetzner.yml # Provisioning CX22 via hcloud API
│   ├── penpot-up.yml         # Déployer Penpot (VPS éphémère)
│   └── penpot-down.yml       # Détruire Penpot (VPS éphémère)
├── ops/
│   ├── backup-restore.yml    # Restauration depuis backup
│   ├── rollback.yml          # Rollback d'un service
│   ├── rotate-secrets.yml    # Rotation des secrets Vault
│   └── safety-check.yml      # Vérification pré-déploiement
└── utils/
    ├── vpn-toggle.yml        # Activer/désactiver VPN-only Caddy
    ├── vpn-dns.yml           # Mise à jour DNS VPN (Headscale)
    ├── obsidian.yml          # Synchronisation Obsidian
    ├── openclaw-oauth.yml    # Configuration OAuth OpenClaw
    └── ovh-dns-add.yml       # Ajout entrée DNS OVH
```"""

TAGS_SECTION = """\
## Utilisation des tags pour déploiement ciblé

### Par catégorie
```bash
# Toute l'infrastructure
ansible-playbook playbooks/stacks/site.yml --tags platform

# Toutes les applications
ansible-playbook playbooks/stacks/site.yml --tags apps

# Tout le monitoring
ansible-playbook playbooks/stacks/site.yml --tags monitoring

# Tout le provisioning
ansible-playbook playbooks/stacks/site.yml --tags provision
```

### Par phase
```bash
ansible-playbook playbooks/stacks/site.yml --tags phase1   # fondations
ansible-playbook playbooks/stacks/site.yml --tags phase2   # données & proxy
ansible-playbook playbooks/stacks/site.yml --tags phase3   # toutes les apps
```

### Par rôle spécifique
```bash
ansible-playbook playbooks/stacks/site.yml --tags n8n
ansible-playbook playbooks/stacks/site.yml --tags litellm,nocodb
ansible-playbook playbooks/stacks/site.yml --tags "apps,phase3"
```

### Workstation Pi
```bash
ansible-playbook playbooks/hosts/workstation.yml --tags workstation   # tout le Pi
ansible-playbook playbooks/hosts/workstation.yml --tags tools         # CLI tools
ansible-playbook playbooks/hosts/workstation.yml --tags creative      # stack créative
ansible-playbook playbooks/hosts/workstation.yml --tags services      # services locaux
ansible-playbook playbooks/hosts/workstation.yml --tags claude-code   # un outil précis
```"""

FOOTER_SECTION = """\
## Référence machine-readable

Pour l'outillage CI/CD, la génération de matrices dynamiques et la documentation automatique :

```yaml
# platform.yaml — source canonique de la taxonomie
# Voir /platform.yaml à la racine du repo
```

Utilisé par :
- `.github/workflows/ci.yml` — matrix lint/test par catégorie
- `Makefile` — cibles `deploy-*` par tag
- `scripts/generate-structure.py` — régénération de ce fichier

> **Ne pas modifier ce fichier manuellement.**
> Mettre à jour `platform.yaml` puis relancer `python scripts/generate-structure.py`."""


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------

def role_table(roles: list, descriptions: dict) -> str:
    lines = ["| Rôle | Description |", "|------|-------------|"]
    for role in roles:
        desc = descriptions.get(role, "")
        lines.append(f"| `{role}` | {desc} |")
    return "\n".join(lines)


def generate(platform: dict) -> str:
    parts = [
        "# STRUCTURE.md — Taxonomie du repo VPAI",
        "",
        "Index humain-readable de l'organisation du repo, des playbooks et des rôles.",
        "Pour le contrat machine-readable, voir [`platform.yaml`](../platform.yaml).",
        "",
        "> **Fichier généré automatiquement** par `scripts/generate-structure.py`.",
        "> Ne pas modifier manuellement — toute modification sera écrasée.",
        "",
        "---",
        "",
        PLAYBOOKS_SECTION,
        "",
        "---",
        "",
        "## Structure `roles/` — Taxonomie logique",
        "",
    ]

    categories = platform.get("categories", {})

    for cat_name, cat in categories.items():
        desc = cat.get("description", "")
        phase = cat.get("phase", "")
        roles = cat.get("roles", [])
        subcategories = cat.get("subcategories", {})

        # En-tête catégorie
        parts.append(f"### {cat_name} — {desc} (Phase {phase})")

        if cat_name == "workstation":
            parts.append(f"Tags: `{cat_name}` + sous-catégorie")
        else:
            parts.append(f"Tags: `{cat_name}`, `phase{phase}`")

        parts.append("")

        if subcategories:
            subcat_labels = {
                "infra":       "Infrastructure Pi",
                "tools":       "CLI IA",
                "creative":    "Outils créatifs",
                "services":    "Services locaux",
                "monitoring":  "Monitoring Pi",
            }
            for subcat_name, subcat_roles in subcategories.items():
                label = subcat_labels.get(subcat_name, subcat_name.capitalize())
                parts.append(f"#### {subcat_name} — {label}")
                parts.append(f"Tags: `{cat_name}`, `{subcat_name}`")
                parts.append("")
                parts.append(role_table(subcat_roles, WORKSTATION_ROLE_DESCRIPTIONS))
                parts.append("")
        elif roles:
            parts.append(role_table(roles, ROLE_DESCRIPTIONS))
            parts.append("")

        parts.append("---")
        parts.append("")

    parts += [
        TAGS_SECTION,
        "",
        "---",
        "",
        FOOTER_SECTION,
        "",
    ]

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Génère docs/STRUCTURE.md depuis platform.yaml")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 si STRUCTURE.md serait modifié (mode CI)")
    args = parser.parse_args()

    platform_path = REPO_ROOT / "platform.yaml"
    structure_path = REPO_ROOT / "docs" / "STRUCTURE.md"

    if not platform_path.exists():
        print(f"Erreur: {platform_path} introuvable", file=sys.stderr)
        sys.exit(1)

    with open(platform_path, encoding="utf-8") as f:
        # Ignorer les lignes de commentaires YAML en tête (PyYAML les ignore nativement)
        platform = yaml.safe_load(f)

    new_content = generate(platform)

    if args.check:
        if structure_path.exists():
            current = structure_path.read_text(encoding="utf-8")
            if current == new_content:
                print("OK: docs/STRUCTURE.md est à jour.")
                sys.exit(0)
            else:
                print("DIFF: docs/STRUCTURE.md est désynchronisé de platform.yaml.")
                print("Relancer: python scripts/generate-structure.py")
                sys.exit(1)
        else:
            print("MISSING: docs/STRUCTURE.md n'existe pas.")
            sys.exit(1)

    structure_path.write_text(new_content, encoding="utf-8")
    print(f"Généré: {structure_path}")


if __name__ == "__main__":
    main()
