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
- NetBird VPN **self-hosted** connecte toutes les machines en mesh privé (controller sur le Master)
- Le Master n'a PAS d'IP publique dans les DNS **sauf** `vpn.paultaffe.net` (bootstrap NetBird) — la Gateway proxie les autres endpoints publics
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
├── NetBird client (self-hosted, enrollment SSO ou setup key)
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
├── NetBird client (self-hosted, auto-enrollment via setup key)
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
DNS interne : *.netbird.selfhosted (via NetBird Management, résolu par le client NetBird)
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
| VPN | NetBird **self-hosted** (WireGuard, zero-trust, mesh, controller sur Master) |
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
| Gateway proxy | 46.225.224.189/32 | TCP 3000, 8080 | ACCEPT |
| NetBird bootstrap | 0.0.0.0/0 | TCP 443 | ACCEPT |
| NetBird STUN | 0.0.0.0/0 | UDP 3478 | ACCEPT |
| SSH admin | IP admin fixe | TCP 22 | ACCEPT |
| Tout le reste | 0.0.0.0/0 | ALL | DROP |

Le Master apparaît dans **un seul** record DNS public : `vpn.paultaffe.net`
(bootstrap NetBird — les clients doivent le joindre AVANT d'être sur le VPN).
TCP 443 sert uniquement les services NetBird (Management, Signal, Relay).
Les services Master (API, Zitadel) restent derrière Gateway proxy.

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

---

## 15. Capacité Service Desk — Plan de scaling

Le Service Desk héberge 20 containers sur une seule VM. Le plan de scaling est
progressif : CX33 au lancement, CX43 quand les clients arrivent, puis split en
2 VMs quand le trafic le justifie.

### Inventaire des containers (mars 2026, idle)

```
Catégorie          Containers                              RAM idle   RAM load
─────────────────────────────────────────────────────────────────────────────
Zammad (ticketing) rails, scheduler, websocket,            ~2.3 GB    ~3.5 GB
                   nginx, memcached, backup
Elasticsearch      elasticsearch (ES_JAVA_OPTS 512m)       ~1.1 GB    ~1.5 GB
Discourse (forum)  discourse, discourse-sidekiq             ~1.3 GB    ~2.5 GB
PostgreSQL         pgvector/pgvector (shared)               ~200 MB    ~500 MB
Redis              redis (maxmemory 256m)                   ~15 MB     ~256 MB
AI / Intelligence  qdrant, typesense, embedding-worker,     ~860 MB    ~1.5 GB
                   reranker, support-agent
Experience         portail (Next.js), gatus                 ~70 MB     ~200 MB
Core               caddy, event-router (Go)                 ~40 MB     ~80 MB
─────────────────────────────────────────────────────────────────────────────
TOTAL                                                      ~5.9 GB    ~10 GB
OS + buffers                                               ~800 MB    ~1 GB
─────────────────────────────────────────────────────────────────────────────
BESOIN TOTAL                                               ~6.7 GB    ~11 GB
```

### Étape 1 — Lancement (CX33, 8 GB RAM, 5.49€/mois)

Le CX33 suffit pour le lancement (0-10 clients, trafic faible).
La RAM idle (6.7 GB / 8 GB = 84%) est serrée mais fonctionnelle.
Pas de vitrine dédiée au lancement — la landing page est servie par le portail
ou une page statique dans Caddy (~0 MB supplémentaire).

**Optimisations appliquées :**
- Elasticsearch : `ES_JAVA_OPTS=-Xms512m -Xmx512m` (déjà en place)
- Redis : `maxmemory 256mb` (déjà en place)
- Memcached : `memcached -m 256M` (déjà en place)
- Profils Docker Compose : intelligence/experience/proactive activés à la demande

**Alerte déclencheur pour upgrade :**
- RAM > 90% pendant 10 min (Gatus/Telegram)
- Swap activé (signe de saturation, pas de swap configuré volontairement)
- Temps de réponse Zammad/Discourse > 2s

### Étape 2 — Croissance (CX43, 16 GB RAM, 10.49€/mois)

Upgrade quand les premiers clients actifs arrivent (~10-50 clients).
Un seul `hcloud server change-type sd-prod cx43` — resize en place, downtime <2 min.

```
CX43 : 8 vCPU, 16 GB RAM, 160 GB NVMe
Budget RAM : ~11 GB utilisé / 16 GB = 69% → confortable
Marge : ~5 GB pour absorber les pics de trafic
Suffisant pour ~100-200 utilisateurs actifs simultanés
```

### Étape 3 — Scale (split 2 VMs, ~11€/mois total)

Split quand une catégorie de containers impacte les autres (ex: Elasticsearch
OOM tue Discourse, ou le reranker sature le CPU et ralentit Zammad).

```
VM "sd-core" (CX33 — 8 GB)              VM "sd-edge" (CX33 — 8 GB)
┌────────────────────────────┐          ┌────────────────────────────┐
│ PostgreSQL (shared)         │          │ Portail (Next.js)          │
│ Redis (shared)              │          │ Event Router (Go)          │
│ Elasticsearch               │◄─────── │ Support Agent (Python)     │
│ Zammad (5 containers)       │  réseau │ Reranker                   │
│ Discourse (2 containers)    │ backend │ Embedding Worker           │
│ Memcached                   │          │ Qdrant                     │
│ Caddy (reverse proxy)       │          │ Typesense                  │
│                              │          │ Gatus                      │
│ RAM: ~5.4 GB idle            │          │ Caddy (reverse proxy)      │
│ → Confortable sur 8 GB      │          │ Vitrine (statique)         │
│ → Les apps lourdes ont de   │          │                             │
│   la marge pour les pics     │          │ RAM: ~1.5 GB idle           │
└────────────────────────────┘          │ → Très confortable sur 8 GB │
                                         │ → Marge pour scaling AI     │
Domaine : *.paultaffe.com               └────────────────────────────┘
(help, terrasse)
                                         Domaine : *.paultaffe.com
                                         (app, status, agence)
                                         + API internes (event-router)
```

**Avantages du split :**
- Isolation des pannes : si le reranker OOM, Zammad/Discourse ne tombent pas
- Scaling indépendant : upgrade sd-edge seul si l'AI stack grossit
- Maintenance sans interruption : restart sd-edge sans couper le ticketing

**Migration :**
```bash
# 1. Créer la VM sd-edge
hcloud server create --name sd-edge --type cx33 --image debian-13

# 2. Déployer le sous-ensemble de containers
ansible-playbook playbooks/service-desk-edge.yml

# 3. Caddy sd-core reverse_proxy les routes edge vers sd-edge (NetBird)
# 4. OU DNS split : app/status/agence → sd-edge IP, help/terrasse → sd-core IP

# 5. Couper les containers edge sur sd-core
docker compose --profile intelligence --profile experience down
```

### Résumé du plan

```
Étape   Trigger                  VM         RAM    Coût       Durée
──────────────────────────────────────────────────────────────────────
  1     Lancement                CX33       8 GB   5.49€/mois  0-10 clients
  2     RAM > 90% ou clients    CX43       16 GB  10.49€/mois 10-50 clients
        actifs
  3     Isolation nécessaire    2×CX33     2×8 GB ~11€/mois   50+ clients
        (OOM, latence)
──────────────────────────────────────────────────────────────────────
```

Pas de Cloudflare, pas de CDN externe. Tout est auto-hébergé, monitoré par
Gatus, alerté par Telegram. Le scaling est déclenché par des métriques
observées, pas par des projections.

---

## 16. NetBird VPN — Architecture self-hosted

### Principe : 0 dépendance externe

Flash Studio héberge **son propre contrôleur NetBird** sur le Master.
Aucun appel à `api.netbird.io`. Zitadel (déjà sur le Master) sert de fournisseur
d'identité OIDC. Le client NetBird sur chaque machine établit des tunnels
WireGuard P2P chiffrés bout-en-bout.

### Composants du contrôleur (sur le Master)

```
vpn.paultaffe.net (A → <IP_MASTER>)
        │
        ▼ TCP 443 + UDP 3478
┌─────────────────────────────────────────────┐
│  MASTER — NetBird Stack (Docker Compose)     │
│                                              │
│  ┌──────────────────┐  ┌─────────────────┐  │
│  │ Management Server │  │  Signal Server  │  │  ← TCP 443 (HTTP/2 mux)
│  │ • Peers, groupes  │  │  • Signalisation│  │
│  │ • Policies, ACL   │  │  • WebRTC nego  │  │
│  │ • Setup keys      │  │                 │  │
│  │ • API REST        │  └─────────────────┘  │
│  └──────┬───────────┘                        │
│         │ OIDC                                │
│  ┌──────▼───────────┐  ┌─────────────────┐  │
│  │ Zitadel (IDP)     │  │  Relay Server   │  │  ← TCP 443 (WebSocket/QUIC)
│  │ auth.paultaffe.net│  │  • Fallback P2P │  │
│  │ (déjà déployé)    │  │  • STUN intégré │  │
│  └──────────────────┘  └─────────────────┘  │
│                                              │
│  ┌──────────────────┐  ┌─────────────────┐  │
│  │ Dashboard (React) │  │  Coturn (STUN)  │  │  ← UDP 3478
│  │ vpn.paultaffe.net │  │  • NAT traversal│  │
│  │ /admin            │  │  • Host network │  │
│  └──────────────────┘  └─────────────────┘  │
│                                              │
│  Caddy (reverse proxy, déjà présent)         │
│  → Route vpn.paultaffe.net vers les services │
└─────────────────────────────────────────────┘
```

**Ports ouverts au public (Master) :**
- TCP 443 : Management + Signal + Relay + Dashboard (muxés derrière Caddy)
- UDP 3478 : STUN/Coturn (accès direct, host network — Caddy ne proxy pas l'UDP)

**Pourquoi le Master :**
- Control plane centralisé (VPN = contrôle, pas data plane)
- Zitadel OIDC sur la même machine (intégration directe, 0 latence)
- PostgreSQL partageable (Management stocke peers/groups/policies)
- Le provisioning Master crée le studio + le group NetBird + la setup key en une seule transaction
- `vpn.paultaffe.net` → Master IP (seul record DNS public du Master)

### Modèle d'isolation — Multi-tenant, multi-device

Chaque client a **son propre réseau privé** dans le mesh. Les devices du client
(VPS, laptop, PC, téléphone) se voient entre eux et voient l'infra Flash Studio.
Aucun client ne voit un autre client.

```
┌──────────────────────────────────────────────────────────────┐
│              NetBird Mesh (100.64.0.0/10)                     │
│                                                               │
│  ┌─── Group: infra ───────────────────────────┐              │
│  │  Master       100.64.0.1                    │              │
│  │  Service Desk 100.64.0.2                    │              │
│  │  Gateway      100.64.0.3                    │              │
│  └─────────────────────────────────────────────┘              │
│       ▲               ▲               ▲                       │
│       │ ALLOW          │ ALLOW          │ ALLOW                │
│       ▼               ▼               ▼                       │
│  ┌─ client-42 ─┐ ┌─ client-43 ─┐ ┌─ client-44 ─┐           │
│  │ VPS  100.64.│ │ VPS  100.64.│ │ VPS  100.64.│           │
│  │ 💻  100.64.│ │ 💻  100.64.│ │              │           │
│  │ 📱  100.64.│ │              │ │              │           │
│  └─── ALLOW ───┘ └─── ALLOW ───┘ └──────────────┘           │
│       intra-client    intra-client                            │
│                                                               │
│  client-42 ✖ client-43  (DENY — pas de policy)              │
│  client-42 ✖ client-44  (DENY — pas de policy)              │
│  client-43 ✖ client-44  (DENY — pas de policy)              │
└──────────────────────────────────────────────────────────────┘
```

**Policies NetBird (deny-by-default après suppression de la Default Policy) :**

| Policy | Source | Destination | Direction | Ports |
|--------|--------|-------------|-----------|-------|
| `infra-to-self` | `infra` | `infra` | Bidirectionnelle | ALL |
| `client-{id}-internal` | `client-{id}` | `client-{id}` | Bidirectionnelle | ALL |
| `client-{id}-to-infra` | `client-{id}` | `infra` | Bidirectionnelle | ALL |

**Pas de policy inter-clients = DENY total.** Un client ne peut pas scanner,
pinger, ni même savoir que d'autres clients existent sur le mesh.

### Enrollment des devices — 2 mécanismes

#### 1. VPS client (automatique, au provisioning)

```
Master API (POST /api/studios)
  │
  ├─► Hetzner API : créer VPS
  ├─► NetBird Management API :
  │     1. Créer Group "client-{id}"
  │     2. Créer Policy "client-{id}" ↔ "infra" = ALLOW
  │     3. Créer Policy "client-{id}" ↔ "client-{id}" = ALLOW
  │     4. Générer Setup Key (usage unique, expire 24h, auto-group "client-{id}")
  │
  ├─► Cloud-init du VPS :
  │     curl -fsSL https://pkgs.netbird.io/install.sh | sh
  │     netbird up --setup-key <SETUP_KEY> --management-url https://vpn.paultaffe.net
  │
  └─► VPS rejoint automatiquement le group "client-{id}"
      → Tunnel WireGuard P2P vers Master + Service Desk
      → flash-agent démarre, heartbeat via 100.64.x.x
```

**La setup key est à usage unique et expire en 24h.** Si le VPS ne s'enregistre
pas dans ce délai, le Master en génère une nouvelle au prochain boot.

#### 2. Devices personnels du client (SSO via Zitadel)

```
Client installe NetBird sur son laptop/PC/téléphone
  │
  ├─► netbird up --management-url https://vpn.paultaffe.net
  │     → Ouvre le navigateur → auth.paultaffe.net (Zitadel SSO)
  │     → Client se connecte avec ses identifiants Flash Studio
  │
  ├─► NetBird Management reçoit le token OIDC
  │     → Identifie le user Zitadel → client-{id}
  │     → Auto-assign le peer au Group "client-{id}" (User Auto-Groups)
  │
  └─► Device rejoint le mesh
      → Voit le VPS du client (même group)
      → Voit les autres devices du client (même group)
      → Voit l'infra Flash Studio (policy client ↔ infra)
      → Ne voit RIEN d'autre
```

**User Auto-Groups :** Au provisioning, le Master configure dans NetBird Management
que tous les peers authentifiés avec l'email `user@client-{id}` sont automatiquement
ajoutés au group `client-{id}`. Aucune action admin requise quand le client ajoute
un device.

### Ce que voit chaque machine

| Machine | Voit son VPS | Voit ses devices perso | Voit Flash Studio infra | Voit autres clients |
|---------|-------------|----------------------|------------------------|-------------------|
| VPS client-42 | — | ✅ laptop, PC, phone | ✅ Master, SD, Gateway | ❌ |
| Laptop client-42 | ✅ | ✅ PC, phone | ✅ Master, SD, Gateway | ❌ |
| PC client-42 | ✅ | ✅ laptop, phone | ✅ Master, SD, Gateway | ❌ |
| VPS client-43 | — | ✅ (ses propres devices) | ✅ Master, SD, Gateway | ❌ |
| Master | ✅ tous les VPS | ✅ tous les devices | ✅ | — |

### Cas d'usage client multi-device

Le client peut :
- **SSH vers son VPS** depuis son laptop via IP NetBird (pas d'IP publique nécessaire)
- **Accéder à n8n, Grafana, LiteLLM** sur son VPS via IP privée (sans exposer publiquement)
- **Utiliser Claude Code CLI** sur son laptop, connecté à LiteLLM du VPS via tunnel WireGuard
- **Partager des fichiers** entre son PC et son VPS via le tunnel privé
- **Monitorer son VPS** depuis son téléphone (Grafana via IP NetBird)

Le tout sans exposer de port public sur le VPS au-delà de ce que Caddy sert.

### Rôles Ansible

| Rôle | Machine cible | Contenu |
|------|--------------|---------|
| `netbird-server` | Master uniquement | Docker Compose (management, signal, relay, coturn, dashboard), config Zitadel OIDC, initialisation PostgreSQL |
| `netbird-client` | Service Desk, Gateway, chaque VPS client | Install client NetBird, registration (setup key ou SSO) |

### Provisioning NetBird dans le flux Master

```
POST /api/studios (Master API)
  │
  ├─► 1. Créer user Zitadel (email: user@flash-studio.io)
  ├─► 2. Créer VPS Hetzner
  ├─► 3. NetBird Management API :
  │       POST /api/groups       → Group "client-{id}"
  │       POST /api/policies     → client-{id} ↔ infra (ALLOW)
  │       POST /api/policies     → client-{id} ↔ client-{id} (ALLOW)
  │       POST /api/setup-keys   → Setup key (single-use, 24h, auto-group)
  │       PUT  /api/users/{id}   → User auto-groups = ["client-{id}"]
  │
  ├─► 4. Cloud-init avec setup key → VPS s'enregistre automatiquement
  ├─► 5. Email client : identifiants + lien install NetBird pour devices perso
  │
  └─► Résultat : client-{id} a son réseau privé opérationnel en < 5 min
```

### Résilience NetBird

| Scénario | Impact | Recovery |
|----------|--------|----------|
| Master down | Tunnels P2P existants **restent actifs** (WireGuard kernel) — seuls les nouveaux peers ne peuvent pas s'enregistrer | Rebuild Master → NetBird Management reprend depuis PostgreSQL |
| Signal down | Nouveaux tunnels P2P impossibles, existants restent | Restart container |
| Relay down | Peers derrière NAT strict perdent la connexion → fallback P2P direct si possible | Restart container |
| Client reboot | `netbird up` au boot (systemd) → reconnexion automatique | Automatique |

**Point critique :** les tunnels WireGuard P2P survivent à un crash du Management.
Le Management est nécessaire uniquement pour les changements (ajout peer, modification
policy). Le data plane est entièrement décentralisé.
