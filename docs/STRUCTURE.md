# STRUCTURE.md — Taxonomie du repo VPAI

Index humain-readable de l'organisation du repo, des playbooks et des rôles.
Pour le contrat machine-readable, voir [`platform.yaml`](../platform.yaml).

> **Fichier généré automatiquement** par `scripts/generate-structure.py`.
> Ne pas modifier manuellement — toute modification sera écrasée.

---

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
```

---

## Structure `roles/` — Taxonomie logique

### core — Fondations obligatoires — déployées en premier (Phase 1)
Tags: `core`, `phase1`

| Rôle | Description |
|------|-------------|
| `common` | Paquets système, utilisateur déploiement, dépôts Debian |
| `docker` | Docker CE + Docker Compose V2, daemon.json, log rotation |
| `hardening` | SSH durcissement, UFW, Fail2ban, CrowdSec |

---

### platform — Infrastructure et middleware — données, proxy, VPN (Phase 2)
Tags: `platform`, `phase2`

| Rôle | Description |
|------|-------------|
| `postgresql` | PostgreSQL 18.3, init.sql, migrations |
| `redis` | Redis 8.4.0 |
| `qdrant` | Qdrant v1.16.3 — base vectorielle |
| `caddy` | Reverse proxy TLS auto, ACL VPN |
| `headscale-node` | Client Tailscale, join réseau Headscale |
| `docker-stack` | docker-compose-infra.yml + docker-compose.yml |
| `app-scaffold` | Infrastructure Hetzner App Factory (réseaux Docker, GHCR) |

---

### apps — Applications métier — services déployés sur Sese-AI (Phase 3)
Tags: `apps`, `phase3`

| Rôle | Description |
|------|-------------|
| `n8n` | n8n 2.7.3 — orchestration workflows |
| `litellm` | LiteLLM v1.81.3 — proxy modèles IA |
| `openclaw` | OpenClaw 2026.3.13-1 — agent IA |
| `nocodb` | NocoDB 0.301.3 — base de données no-code |
| `plane` | Plane v1.2.2 — gestion de projet |
| `kitsu` | Kitsu 1.0.19 — production management |
| `firefly` | Firefly III 6.5.3 — finances personnelles |
| `zimboo` | Zimboo v1.14.0 |
| `mealie` | Mealie v3.12.0 — gestion recettes |
| `grocy` | Grocy 4.6.0 — gestion stocks |
| `koodia` | Koodia v0.1.0 |
| `palais` | Dashboard mission control + MCP |
| `flash-suite` | Flash Suite — stack créative auto-contenue |
| `story-engine` | StoryEngine — pipeline narration IA |
| `typebot` | Typebot 3.16+ — chatbots |
| `penpot` | Penpot — design collaboratif (VPS éphémère) |
| `metube` | MeTube — téléchargement vidéo (aussi sur Waza) |
| `carbone` | Carbone — génération documents |
| `gotenberg` | Gotenberg — conversion PDF |
| `webhook-relay` | Relay webhooks (n8n ↔ services) |
| `llamaindex-memory` | LlamaIndex memory worker (Sese-AI) |
| `obsidian` | Obsidian sync server |

---

### provision — Provisioning post-deploy — setup initial des applications (Phase 4.6)
Tags: `provision`, `phase4.6`

| Rôle | Description |
|------|-------------|
| `n8n-provision` | Création compte owner n8n via API |
| `plane-provision` | Bucket MinIO Plane |
| `kitsu-provision` | Init DB Kitsu/Zou, admin user |
| `app-factory-provision` | Tables NocoDB + collections Qdrant App Factory |
| `content-factory-provision` | Tables NocoDB + collections Qdrant Content Factory |

---

### monitoring — Observabilité — métriques, logs, alertes, smoke tests (Phase 4)
Tags: `monitoring`, `phase4`

| Rôle | Description |
|------|-------------|
| `monitoring` | VictoriaMetrics, Loki, Grafana Alloy, Grafana |
| `diun` | DIUN 4.31.0 — alertes nouvelles versions images |
| `uptime-config` | Configuration uptime monitoring |
| `obsidian-collector` | Collecte notes Obsidian (Sese-AI) |
| `smoke-tests` | Tests post-déploiement (tag `always`) |

---

### workstation — Waza (Raspberry Pi 5) — outils locaux Mission Control (Phase waza)
Tags: `workstation` + sous-catégorie

#### infra — Infrastructure Pi
Tags: `workstation`, `infra`

| Rôle | Description |
|------|-------------|
| `workstation-common` | Base Ubuntu, Docker, Tailscale |
| `workstation-caddy` | Caddy local (proxy outils créatifs) |
| `workstation-monitoring` | Monitoring local Pi |

#### tools — CLI IA
Tags: `workstation`, `tools`

| Rôle | Description |
|------|-------------|
| `claude-code` | Claude Code CLI |
| `codex-cli` | Codex CLI (OpenAI) |
| `gemini-cli` | Gemini CLI (Google) |
| `opencode` | OpenCode 1.2.15 |

#### creative — Outils créatifs
Tags: `workstation`, `creative`

| Rôle | Description |
|------|-------------|
| `comfyui` | ComfyUI ARM64 CPU-only + MCP studio |
| `remotion` | Remotion — vidéo programmatique |
| `opencut` | OpenCut — montage vidéo |
| `openpencil` | OpenPencil — dessin vectoriel |
| `videoref-engine` | VideoRef Engine — référence vidéo |

#### services — Services locaux
Tags: `workstation`, `services`

| Rôle | Description |
|------|-------------|
| `metube` | MeTube local (téléchargement vidéo) |
| `n8n-mcp` | n8n-docs MCP server (documentation n8n locale) |
| `llamaindex-memory-worker` | Worker mémoire IA (Qdrant ingestion) |

#### monitoring — Monitoring Pi
Tags: `workstation`, `monitoring`

| Rôle | Description |
|------|-------------|
| `obsidian-collector-pi` | Collecte notes Obsidian (Pi) |

---

### ops — Opérations ponctuelles — backup, secrets, DNS (Phase adhoc)
Tags: `ops`, `phaseadhoc`

| Rôle | Description |
|------|-------------|
| `backup-config` | Configuration backup Zerobyte |
| `vpn-dns` | Mise à jour extra_records.json Headscale (split DNS) |

---

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
```

---

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
> Mettre à jour `platform.yaml` puis relancer `python scripts/generate-structure.py`.
