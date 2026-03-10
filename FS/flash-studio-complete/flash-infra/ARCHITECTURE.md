# ARCHITECTURE.md — Flash Studio v2

> Document de référence technique pour le repo `flash-infra`.
> Dernière mise à jour : Mars 2026

---

## 1. Vue d'ensemble

Flash Studio est une plateforme IaaS automatisée fournissant des stacks IA pré-configurées sur VPS dédiés.

### 3 piliers d'infrastructure

```
                         Internet
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
     ┌─────────────┐ ┌───────────┐ ┌────────────┐
     │   GATEWAY    │ │  SERVICE  │ │   MASTER   │
     │ 46.225.224.189│ │   DESK   │ │178.104.31.134│
     │              │ │142.132...│ │             │
     │ *.paultaffe.fr│ │*.paultaffe│ │*.paultaffe │
     │ registry.net │ │   .com   │ │    .net    │
     └──────┬───────┘ └─────┬────┘ └──────┬─────┘
            │               │             │
            └───────────────┼─────────────┘
                            │
                    NetBird VPN (mesh)
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
     ┌─────────────┐ ┌───────────┐ ┌────────────┐
     │  Sovereign   │ │Production │ │   Agents   │
     │  (per-client)│ │(destruct.)│ │ flash-agent │
     └─────────────┘ └───────────┘ └────────────┘
```

| Pilier | Rôle | Domaines | Exposition |
|--------|------|----------|-----------|
| **Gateway** | Portier public, TLS On-Demand, proxy clients, Docker Registry | `*.paultaffe.fr`, `registry.paultaffe.net` | Public (trafic client) |
| **Service Desk** | Support, ticketing, forum, status, dashboard, event-router, **site vitrine** | `*.paultaffe.com` (help, terrasse, agence, status, app) | Public (trafic prospect + client) |
| **Master** | Source de vérité, provisioning, billing, SSO, monitoring, agent tokens | `*.paultaffe.net` (auth, vpn, monitor, chat, n8n, admin) | Privé (VPN + Gateway proxy pour SSO/Stripe) |

### Domaines (source: domain-strategy.md)

```
paultaffe.com  → Client-facing (vitrine, support, dashboard)  → Service Desk
paultaffe.net  → Infrastructure ops (auth, vpn, monitor)       → Master (via Gateway proxy)
paultaffe.fr   → Per-client isolation (agents, webhooks, SEO)  → Gateway → Sovereign
```

**Principes fondamentaux :**
- La VM Souveraine (per-client) est permanente, l'IP fixe sert de point d'entrée DNS
- La VM Production (per-client) est destructible/reconstructible en 30 min via Ansible
- Le volume persistant `/mnt/data` survit à la destruction de la VM Production
- NetBird VPN connecte toutes les machines en mesh privé
- Le Master n'a PAS d'IP publique dans les DNS — la Gateway proxie les endpoints publics
- SOPS + age pour le chiffrement de tous les secrets

---

## 2. Infrastructure Provider

### Hetzner Cloud — CX33 (5,49€/mois)

| Spec | Valeur |
|------|--------|
| vCPU | 4 (shared) |
| RAM | 8 GB |
| Stockage | 80 GB NVMe |
| Bande passante | 20 TB inclus |
| API | Complète, Terraform provider |
| Billing | Horaire |
| Provision | ~10 secondes |

**Choix validé vs alternatives :**
- Netcup, Contabo : pas d'API, pas Terraform, pas volumes détachables
- OVH : API complexe, plus cher
- Hetzner : API complète, Terraform provider, hourly billing, volumes, snapshots, firewall API

**Provider-agnostic :** Migration VM souveraine vers autre provider = changer 3 lignes de config Ansible, downtime 15-20 min.

### S3 Object Storage

| Provider | Prix/Go | Usage |
|----------|---------|-------|
| Hetzner | 0,0065€ | Défaut |
| Wasabi | $0,0069 | Alternative |
| Backblaze B2 | $0,005 | Alternative |
| Scaleway | 0,008€ | Alternative EU |

Swappable via variable Ansible `s3_endpoint`.

---

## 3. VM Souveraine — Stack complète

**Rôle :** Point d'entrée permanent, IP fixe, DNS wildcard, services 24/7.

```
VM Souveraine (CX33 — 4vCPU, 8GB, 80GB)
├── Caddy (reverse proxy, auto-TLS, wildcard *.domaine.tld)
├── PostgreSQL 16 (base partagée)
├── Docker Engine
│   ├── activepieces        (MIT)     — Workflows + ~400 MCPs
│   ├── openclaw            (MIT)     — Agent IA multi-canal 24/7
│   │   ├── WhatsApp, Telegram, Slack, Discord
│   │   ├── Heartbeat monitoring
│   │   └── Skills système (fichiers, recherche, mémoire)
│   ├── litellm             (MIT)     — Proxy multi-LLM BYOK
│   │   ├── Claude (Anthropic)
│   │   ├── GPT (OpenAI)
│   │   ├── Gemini (Google)
│   │   ├── Mistral
│   │   └── Modèles locaux (Ollama)
│   ├── firefly-iii         (AGPL)    — Finances perso + compta
│   │   └── MCP server (connexion Activepieces)
│   ├── vaultwarden         (AGPL)    — Gestionnaire mots de passe
│   ├── grafana             (AGPL)    — Dashboards monitoring
│   ├── prometheus                     — Métriques
│   ├── node-exporter                  — Métriques système
│   ├── cadvisor                       — Métriques containers
│   └── restic              (BSD)     — Backups → S3
├── NetBird client (free tier)
├── SOPS + age (secrets chiffrés)
└── flash-agent (Go binary)
    ├── Heartbeat → flash-master
    ├── Métriques → Prometheus
    ├── Auto-update compose
    ├── Backup trigger
    └── Exec remote
```

### Ports exposés (via Caddy)

| Service | Sous-domaine | Port interne |
|---------|-------------|-------------|
| Activepieces | `flow.domaine.tld` | 8080 |
| OpenClaw | `agent.domaine.tld` | 3000 |
| LiteLLM | `llm.domaine.tld` | 4000 |
| Firefly III | `finance.domaine.tld` | 8082 |
| Vaultwarden | `vault.domaine.tld` | 8081 |
| Grafana | `monitor.domaine.tld` | 3001 |

---

## 4. VM Production — Stack modulaire

**Rôle :** Environnement de travail destructible. Le volume `/mnt/data` persiste.

```
VM Production (CX33 — 4vCPU, 8GB, 80GB + Volume persistant)
├── Caddy (reverse proxy)
├── PostgreSQL 16
├── Docker Engine
│   │
│   ├── [BASE — tous les plans Studio+]
│   │   ├── claude-code-cli          — CLI dev IA
│   │   ├── opencode                 — Alternative OSS
│   │   ├── gemini-cli               — CLI Google
│   │   ├── qdrant            (Apache) — RAG vectoriel
│   │   ├── nocodb            (AGPL)   — Base no-code
│   │   ├── couchdb           (Apache) — Obsidian LiveSync
│   │   └── postgresql                 — Base locale
│   │
│   ├── [MODULES À LA CARTE]
│   │   ├── n8n               (SUL)    — Client installe lui-même
│   │   ├── browserless                — Headless Chrome
│   │   ├── bright-data                — Proxy scraping
│   │   └── bigcapital        (AGPL)   — Compta avancée
│   │
│   ├── [PROFIL CRÉATION — plan Création uniquement]
│   │   ├── comfyui                    — Génération images/vidéo IA
│   │   ├── remotion                   — Rendu vidéo programmatique
│   │   └── skypilot                   — GPU à la demande (RunPod)
│   │
│   └── [PROFIL TRADING — plan Trading uniquement]
│       ├── freqtrade                  — Bot trading
│       ├── grafana-trading            — Dashboards PnL
│       └── telegram-alerts            — Alertes temps réel
│
├── Volume persistant /mnt/data
│   ├── /mnt/data/postgres
│   ├── /mnt/data/qdrant
│   ├── /mnt/data/nocodb
│   ├── /mnt/data/comfyui/models
│   ├── /mnt/data/comfyui/outputs
│   ├── /mnt/data/freqtrade
│   └── /mnt/data/backups
│
├── NetBird client
└── flash-agent (Go binary)
```

### Docker Compose Profiles

```yaml
# docker-compose.yml
services:
  # Base services (toujours actifs)
  claude-code:
    profiles: ["base"]
  qdrant:
    profiles: ["base"]
  nocodb:
    profiles: ["base"]

  # Modules à la carte
  browserless:
    profiles: ["scraping"]
  bright-data:
    profiles: ["scraping"]

  # Profil Création
  comfyui:
    profiles: ["creation"]
  remotion:
    profiles: ["creation"]

  # Profil Trading
  freqtrade:
    profiles: ["trading"]
  grafana-trading:
    profiles: ["trading"]
```

Activation : `COMPOSE_PROFILES=base,creation docker compose up -d`

---

## 5. Réseau

```
                    Internet
                       │
                       ▼
              ┌────────────────┐
              │   Caddy (TLS)  │
              │  VM Souveraine │
              │  IP: fixe      │
              └───────┬────────┘
                      │
            ┌─────────┴─────────┐
            │   NetBird VPN     │
            │   (mesh WireGuard)│
            └─────────┬─────────┘
                      │
          ┌───────────┼───────────┐
          │           │           │
    ┌─────▼─────┐ ┌───▼───┐ ┌────▼────┐
    │ Raspberry │ │  VM   │ │   VM    │
    │    Pi     │ │ Souv. │ │  Prod.  │
    │  @home    │ │       │ │         │
    └───────────┘ └───────┘ └─────────┘

Subnet : 100.64.0.0/10 (NetBird)
DNS interne : *.netbird.cloud
```

**Flux :**
1. Client accède à `flow.domaine.tld` → Caddy (VM Souveraine) → Activepieces
2. Raspberry Pi SSH via NetBird → VM Souveraine (pas d'IP publique exposée)
3. VM Souveraine → VM Production via NetBird (communication inter-VM)
4. Backups : VM → Restic → S3 Hetzner (chiffré, hors VPN)

---

## 6. Sécurité

| Couche | Mécanisme |
|--------|-----------|
| Secrets | SOPS + age (chiffrés au repos, déchiffrés au deploy) |
| Mots de passe | Vaultwarden (auto-hébergé, E2E chiffré) |
| VPN | NetBird (WireGuard, zero-trust, mesh) |
| TLS | Caddy auto-renew Let's Encrypt |
| Firewall | Hetzner Cloud Firewall API (22, 80, 443 only) |
| SSH | Clé ED25519 uniquement, no password |
| Docker | Non-root containers, read-only rootfs quand possible |
| Backups | Restic (chiffré AES-256, dédupliqué, versionné) |
| OS | Debian 13 (Trixie), unattended-upgrades |

---

## 7. Repo `flash-infra`

```
flash-infra/
├── ansible/
│   ├── inventory/
│   │   └── hosts.yml              # sovereign + studio, variables par client
│   ├── playbooks/
│   │   ├── site.yml               # déploiement complet
│   │   ├── sovereign.yml          # VM Souveraine uniquement
│   │   ├── studio.yml             # VM Production uniquement
│   │   ├── destroy-studio.yml     # destruction VM Production
│   │   ├── rebuild-studio.yml     # reconstruction depuis volume
│   │   ├── backup.yml             # backup on-demand
│   │   └── update-stack.yml       # mise à jour compose
│   └── roles/
│       ├── common/                # base Debian, users, SSH, ufw
│       ├── docker/                # Docker Engine + compose
│       ├── netbird-client/        # NetBird VPN
│       ├── caddy/                 # reverse proxy + TLS
│       ├── postgres/              # PostgreSQL 16
│       ├── sovereign-compose/     # docker-compose sovereign
│       ├── studio-compose/        # docker-compose production
│       ├── grafana/               # monitoring stack
│       ├── vaultwarden/           # gestionnaire mdp
│       ├── backup/                # Restic + S3 + cron
│       └── hetzner-volume/        # montage volume persistant
│
├── docker/
│   ├── sovereign/
│   │   └── docker-compose.yml     # Stack souveraine
│   └── studio/
│       └── docker-compose.yml     # Stack production (profiles)
│
├── marketplace/
│   ├── n8n/                       # Instructions install client
│   ├── comfyui/                   # Config + modèles
│   ├── remotion/                  # Templates vidéo
│   ├── freqtrade/                 # Stratégies trading
│   ├── claude-code/               # Config + prompts
│   ├── opencode/                  # Config
│   ├── gemini-cli/                # Config
│   ├── browserless/               # Config
│   ├── bigcapital/                # Config compta
│   └── bright-data/               # Config proxy
│
├── packs/                         # Templates vendus (Flash Packs)
│   ├── ugc-factory/               # Workflows ComfyUI UGC
│   ├── manga-pipeline/            # SD + Remotion manga
│   ├── shortform-video/           # Templates Remotion TikTok
│   ├── rag-business/              # Qdrant + prompts métier
│   └── trading-starter/           # Stratégies Freqtrade
│
├── configs/
│   ├── caddy/Caddyfile.j2        # Template Jinja2
│   ├── grafana/dashboards/        # JSON dashboards
│   ├── prometheus/prometheus.yml   # Config monitoring
│   └── restic/backup.conf         # Config backup
│
├── secrets/
│   └── secrets.enc.yaml           # SOPS + age (chiffré)
│
├── scripts/
│   ├── flash-daemon.sh            # Daemon Claude Code
│   ├── flash-ctl.sh               # CLI admin
│   └── flash-tmux.sh              # Lanceur sessions tmux
│
├── CLAUDE.md                      # Contexte pour daemon IA
├── ARCHITECTURE.md                # Ce document
└── README.md                      # Guide démarrage
```

### Conventions

| Règle | Détail |
|-------|--------|
| OS | Debian 13 (Trixie) partout |
| Ansible | `ansible.builtin` uniquement |
| Playbooks | Idempotents (re-run safe) |
| Secrets | SOPS + age |
| Git | trunk-based (`main` + `feat/*` + `fix/*`) |
| Commits | `type(scope): message` (conventional commits) |
| Docker | Compose v2, profiles pour variantes |
| Tests | `ansible-lint`, `yamllint`, CI GitHub Actions |

---

## 8. Licences

| Licence | Logiciel | Redistribution |
|---------|----------|---------------|
| MIT | Activepieces, OpenClaw, LiteLLM | ✅ Libre |
| Apache 2.0 | Qdrant, CouchDB, NetBird, Caddy | ✅ Libre |
| AGPL 3.0 | Firefly III, Grafana, Vaultwarden, NocoDB, Bigcapital | ✅ OK (SaaS, code non modifié) |
| BSD | Restic, PostgreSQL | ✅ Libre |
| SUL | n8n | ❌ Client installe lui-même |

**n8n (Sustainable Use License) :** Interdit la revente hébergée. Le client installe n8n sur son infra via notre doc. Flash Studio ne fournit pas n8n pré-installé.

---

## 9. Flux de provisioning automatisé

```
Client paie (Stripe Checkout)
        │
        ▼
Webhook Stripe → Activepieces workflow
        │
        ├─► Hetzner API : créer VM Souveraine
        ├─► Hetzner API : créer VM Production + Volume
        ├─► DNS API : créer wildcard *.client.flash-studio.io
        │
        ▼
Ansible playbook (déclenché par webhook)
        │
        ├─► Role common (SSH, users, firewall)
        ├─► Role docker
        ├─► Role netbird-client
        ├─► Role caddy
        ├─► Role sovereign-compose (docker-compose up)
        ├─► Role studio-compose (docker-compose up --profile=base,{plan})
        ├─► Role grafana
        ├─► Role backup
        │
        ▼
Post-deploy
        │
        ├─► Email client : accès, URLs, guide démarrage
        ├─► NocoDB : création entrée client
        ├─► Grafana : dashboard client activé
        ├─► OpenClaw : message bienvenue Telegram/Discord
        └─► Monitoring : alertes activées
```

**Temps total : < 30 minutes, zéro intervention humaine.**

---

## 10. Destruction / Reconstruction

```
# Destruction VM Production (données préservées)
ansible-playbook destroy-studio.yml -e client=xxx
  → Hetzner API : supprimer VM
  → Volume /mnt/data : PRÉSERVÉ
  → DNS : inchangé (pointe vers souveraine)

# Reconstruction (30 min)
ansible-playbook rebuild-studio.yml -e client=xxx
  → Hetzner API : créer nouvelle VM
  → Attacher volume existant
  → Ansible : redéployer stack
  → Données intactes (Postgres, Qdrant, ComfyUI models...)
```

---

## 11. Monitoring & Alertes

```
┌─────────────┐     ┌────────────┐     ┌──────────┐
│ node-exporter│────►│ Prometheus │────►│ Grafana  │
│ cadvisor     │     │            │     │          │
│ flash-agent  │     └────────────┘     └─────┬────┘
└─────────────┘                               │
                                              ▼
                                     Alertmanager
                                         │
                                    ┌────┴────┐
                                    │Telegram │
                                    │ alerts  │
                                    └─────────┘
```

**Alertes configurées :**
- CPU > 80% pendant 5 min
- RAM > 90%
- Disque > 85%
- Container down > 2 min
- Backup échoué
- Certificat TLS expire < 7 jours
- flash-agent heartbeat manqué > 5 min

---

## 12. Backups

| Paramètre | Valeur |
|-----------|--------|
| Outil | Restic |
| Destination | S3 Hetzner Object Storage |
| Chiffrement | AES-256 (clé Restic) |
| Fréquence | Toutes les 6h (cron) |
| Rétention défaut | 30 jours |
| Rétention 90j | +2€/mois |
| Rétention 365j | +5€/mois |
| Déduplication | Oui (Restic natif) |
| Restauration | `flash-ctl restore --client xxx --date 2026-01-15` |

**Données sauvegardées :**
- PostgreSQL (dump + WAL)
- Volume /mnt/data complet
- Configs Docker Compose
- Secrets SOPS (chiffrés)
- Caddyfile

---

## 13. Flux de trafic — Parcours prospect et client

### Parcours d'acquisition (prospect)

```
1. DÉCOUVERTE
   Google/Social/IA → paultaffe.com          → Service Desk (site vitrine)
   Google.fr        → paultaffe.fr            → Gateway (landing SEO France)
   Bouche-à-oreille → terrasse.paultaffe.com  → Service Desk (forum public)

2. ÉVALUATION
   Prospect → terrasse.paultaffe.com (forum communauté)    → Service Desk
   Prospect → agence.paultaffe.com (marketplace, tutos)    → Service Desk [Phase 3]
   Prospect → status.paultaffe.com (uptime, transparence)  → Service Desk
   Prospect → help.paultaffe.com (FAQ publique)             → Service Desk

3. INSCRIPTION
   Prospect → app.paultaffe.com (dashboard, "Créer un compte")  → Service Desk
   Sign-up  → auth.paultaffe.net (Zitadel SSO, OAuth)           → Gateway → Master

4. PAIEMENT
   Client → Stripe Checkout (hébergé par Stripe)       → Stripe
   Stripe webhook → Gateway → Master                   → Provisioning Hetzner

5. UTILISATION POST-PAIEMENT
   Client → app.paultaffe.com (dashboard)              → Service Desk
   Client → help.paultaffe.com (tickets support)       → Service Desk
   Agent  → Master (heartbeat, config) via NetBird VPN → Master (direct, privé)
   Agent  → Event Router (events, tickets) via NetBird → Service Desk (direct, privé)
```

**Point clé :** Le trafic d'acquisition et d'utilisation quotidienne arrive sur le
**Service Desk** (paultaffe.com), jamais directement sur le Master. Le Master
n'intervient que pour le SSO (via Gateway proxy) et le provisioning (webhook Stripe).

### Matrice de trafic par VM

| Source | Destination | Route | Volume | Fréquence |
|--------|-------------|-------|--------|-----------|
| Prospects (web) | Service Desk | Internet direct | Variable | Continu |
| Prospects (SEO FR) | Gateway | Internet direct | Variable | Continu |
| Clients (dashboard) | Service Desk | Internet direct | Moyen | Continu |
| Clients (SSO login) | Gateway → Master | Internet → proxy VPN | Faible | Login seul |
| Stripe webhooks | Gateway → Master | Internet → proxy VPN | Très faible | ~qqs/jour |
| Flash agents | Master | NetBird VPN direct | N × 1/min | Continu |
| Flash agents | Event Router | NetBird VPN direct | Variable | Events |
| Admin ops | Master | NetBird VPN direct | Très faible | Manuel |

---

## 14. Gateway comme proxy unique — Protection du Master

### Pourquoi pas de VPS frontend dédié devant le Master

Le Master est la source de vérité (config, billing, provisioning), mais il reçoit
très peu de trafic public. Un VPS frontend dédié serait du sur-engineering.

**La Gateway fait déjà le travail :**

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  GATEWAY (Caddy TLS On-Demand)                          │
│  46.225.224.189                                          │
│                                                          │
│  Route 1 : *.paultaffe.fr    → Sovereign (via NetBird)  │
│  Route 2 : registry.paultaffe.net → local Docker Registry│
│  Route 3 : auth.paultaffe.net → Master (via NetBird)    │  ← SSO public
│  Route 4 : api.paultaffe.com  → Master (via NetBird)    │  ← API Phase 3
│  Route 5 : stripe-webhook     → Master (via NetBird)    │  ← Webhook only
└──────────┬──────────────────────────────────────────────┘
           │ NetBird VPN
           ▼
┌──────────────────┐
│  MASTER           │
│  178.104.31.134   │
│  IP non publiée   │
│  Firewall :       │
│   ACCEPT 100.64.0.0/10 (NetBird)  │
│   ACCEPT <IP_GATEWAY>             │
│   DROP   tout le reste            │
└──────────────────┘
```

### Règles de la Gateway pour le Master

```
# Caddyfile sur la Gateway (extrait)

# SSO — endpoint public (login navigateur)
auth.paultaffe.net {
    reverse_proxy <MASTER_NETBIRD_IP>:8080
    rate_limit {
        zone sso_zone {
            key    {remote_host}
            events 30
            window 1m
        }
    }
}

# API publique provisioning (Phase 3)
api.paultaffe.com {
    reverse_proxy <MASTER_NETBIRD_IP>:3000
    rate_limit {
        zone api_zone {
            key    {remote_host}
            events 60
            window 1m
        }
    }
}

# Stripe webhook (IP whitelistées Stripe + rate limit strict)
api.paultaffe.com/api/billing/webhook {
    reverse_proxy <MASTER_NETBIRD_IP>:3000
}
```

### Firewall Master (Hetzner Cloud Firewall)

| Règle | Source | Port | Action |
|-------|--------|------|--------|
| NetBird VPN | 100.64.0.0/10 | ALL | ACCEPT |
| Gateway proxy | 46.225.224.189/32 | 3000, 8080 | ACCEPT |
| SSH admin | IP admin fixe | 22 | ACCEPT |
| Tout le reste | 0.0.0.0/0 | ALL | DROP |

Le Master n'apparaît dans aucun record DNS public. Son IP (178.104.31.134)
n'est jamais exposée. Un attaquant ne peut pas le cibler directement.

### Résilience Master (disaster recovery)

Le Master est critique car c'est la source de vérité. Protection :

| Mesure | Coût | RPO | RTO |
|--------|------|-----|-----|
| Snapshot volume Hetzner (auto, 6h) | ~1€/mois | 6h | 15 min (attach à nouveau VPS) |
| Restic → S3 (PostgreSQL dump, 6h) | inclus | 6h | 30 min (rebuild Ansible) |
| Config versionnée dans Git (flash-infra) | 0€ | 0 | 30 min (ansible-playbook) |

```bash
# Reconstruction Master après crash
ansible-playbook playbooks/master.yml -e target=new_vps_ip
# → Redéploie la stack complète, restaure le dump PostgreSQL depuis S3
# → Les agents se reconnectent automatiquement via NetBird (IP VPN stable)
```
