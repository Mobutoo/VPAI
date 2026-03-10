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
├── Caddy (reverse proxy, auto-TLS, routes base + custom)
│   ├── /etc/caddy/Caddyfile           — Base (Ansible, read-only)
│   └── /mnt/data/caddy/custom/*.caddy — Custom (client, via dashboard)
└── flash-agent (Go binary)
    ├── Heartbeat → flash-master
    ├── Métriques → Prometheus
    ├── Auto-update compose
    ├── Backup trigger
    ├── Exec remote
    └── Caddy route manager (API pour le dashboard)
```

### DNS par client (créés au provisioning par Master API via OVH)

```
# Exemple pour le client "acme42" (IP Sovereign = 1.2.3.4)
acme42.paultaffe.fr      A    1.2.3.4    # base domain → direct Sovereign
*.acme42.paultaffe.fr    A    1.2.3.4    # wildcard sub-subdomains → direct Sovereign
```

Le trafic client va **directement** vers la VM Sovereign (pas via Gateway).
Le wildcard `*.paultaffe.fr` sur la Gateway = catch-all parking page uniquement.

### Domaines custom (gérés par le client via dashboard)

Le client peut ajouter son propre nom de domaine (ex: `api.mycorp.com`)
via le dashboard (`app.paultaffe.com` → section "Domaines").

```
1. Client ajoute "api.mycorp.com" dans le dashboard
2. Dashboard → Master API → flash-agent (via NetBird)
3. flash-agent écrit /mnt/data/caddy/custom/mycorp.caddy
4. Caddy reload → certificat TLS auto-provisionné (Let's Encrypt)
5. Le client configure son DNS : api.mycorp.com A <IP_SOVEREIGN>
```

### Ports exposés (via Caddy)

| Service | Sous-domaine | Port interne |
|---------|-------------|-------------|
| Activepieces | `flow.{client_id}.paultaffe.fr` | 8080 |
| OpenClaw | `agent.{client_id}.paultaffe.fr` | 3000 |
| LiteLLM | `llm.{client_id}.paultaffe.fr` | 4000 |
| Firefly III | `finance.{client_id}.paultaffe.fr` | 8082 |
| Vaultwarden | `vault.{client_id}.paultaffe.fr` | 8081 |
| Grafana | `monitor.{client_id}.paultaffe.fr` | 3001 |

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
| VPN | NetBird **self-hosted** (WireGuard + **Rosenpass post-quantique**, zero-trust, mesh, controller sur Master) — section 16 |
| Chiffrement disque | **LUKS2 AES-256-XTS** sur `/mnt/data` (clé gérée par Master, délivrée via NetBird) — section 19.2 |
| TLS | Caddy auto-renew Let's Encrypt (TLS 1.3) |
| Firewall | Hetzner Cloud Firewall API + **nftables** egress filtering — section 19.5 |
| SSH | User `studio` (pas root), clé ED25519 uniquement, no password |
| Fichiers critiques | `chattr +i` (immutable) + AppArmor (MAC) — section 17 |
| Runtime | **Tetragon eBPF** (détection + kill kernel-level, container-aware) — section 19.1 |
| Docker | Non-root containers, read-only rootfs, **réseaux isolés** (frontend/backend/monitoring) — section 19.5 |
| Identité | Zitadel SSO + MFA + **Posture Checks NetBird** (vérification continue device) — section 19.3 |
| Supply chain | **Cosign keyless** (binaires signés Sigstore) + **SBOM** (SPDX) — section 19.4 |
| Backups | Restic (chiffré AES-256, dédupliqué, versionné) |
| OS | Debian 13 (Trixie), unattended-upgrades |
| Audit | Tetragon events + `auditd` → flash-agent → Event Router |

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
│       ├── common/                # base Debian, users, SSH, nftables, cosign
│       ├── docker/                # Docker Engine + compose
│       ├── netbird-client/        # NetBird VPN + Rosenpass
│       ├── caddy/                 # reverse proxy + TLS
│       ├── postgres/              # PostgreSQL 16
│       ├── tetragon/              # eBPF runtime security + policies
│       ├── sovereign-compose/     # docker-compose sovereign (réseaux isolés)
│       ├── studio-compose/        # docker-compose production (réseaux isolés)
│       ├── grafana/               # monitoring stack
│       ├── vaultwarden/           # gestionnaire mdp
│       ├── backup/                # Restic + S3 + cron
│       └── hetzner-volume/        # montage volume persistant + LUKS
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
Webhook Stripe → Master API
        │
        ├─► 1. Zitadel : créer user client (SSO)
        ├─► 2. Hetzner API : créer VM Souveraine (IP fixe)
        ├─► 3. Hetzner API : créer VM Production + Volume
        ├─► 4. OVH DNS API :
        │       acme42.paultaffe.fr      A  <IP_SOVEREIGN>
        │       *.acme42.paultaffe.fr    A  <IP_SOVEREIGN>
        ├─► 5. NetBird Management API :
        │       POST /api/groups      → Group "client-acme42"
        │       POST /api/policies    → client-acme42 ↔ infra (ALLOW, posture check)
        │       POST /api/policies    → client-acme42 ↔ client-acme42 (ALLOW, posture check)
        │       POST /api/setup-keys  → Setup key (single-use, 24h, auto-group)
        │       PUT  /api/users/{id}  → User auto-groups = ["client-acme42"]
        │       POST /api/posture-checks → Baseline (OS version, NetBird version)
        │
        ▼
Ansible playbook (déclenché par Master)
        │
        ├─► Role common (SSH, users, nftables, cosign install)
        ├─► Role docker
        ├─► Role hetzner-volume (LUKS2 format + mount chiffré)
        ├─► Role netbird-client (setup key + Rosenpass)
        ├─► Role tetragon (eBPF policies : protect files, block reverse shell)
        ├─► Role caddy (Caddyfile base + import custom/*.caddy)
        ├─► Role flash-agent (cosign verify + deploy signé + LUKS mount service)
        ├─► Role sovereign-compose (docker-compose up, réseaux isolés)
        ├─► Role studio-compose (docker-compose up --profile=base,{plan})
        ├─► Role grafana
        ├─► Role backup
        │
        ▼
Post-deploy
        │
        ├─► Email client : accès, URLs, install NetBird (devices perso), guide démarrage
        ├─► NocoDB : création entrée client
        ├─► Grafana : dashboard client activé
        ├─► OpenClaw : message bienvenue Telegram/Discord
        └─► Monitoring : alertes activées
```

**Temps total : < 30 minutes, zéro intervention humaine.**
Le client a immédiatement accès à `acme42.paultaffe.fr` + tous les sub-subdomains.
Il peut ajouter des domaines custom depuis son dashboard (`app.paultaffe.com`).

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

### Post-Quantum Cryptography (Rosenpass)

NetBird intègre nativement **Rosenpass**, un protocole post-quantique qui génère un
pre-shared key (PSK) toutes les 2 minutes via **Classic McEliece + Kyber**, injecté
dans le slot PSK de WireGuard. Le protocole WireGuard lui-même n'est pas modifié.

```
Sans Rosenpass :                       Avec Rosenpass :
WireGuard (Curve25519)                 WireGuard (Curve25519)
  → Vulnérable "harvest now,            + PSK post-quantique (Rosenpass)
    decrypt later"                       → Résistant aux ordinateurs quantiques
```

**Menace :** un attaquant enregistre le trafic WireGuard chiffré aujourd'hui et le
déchiffre quand les ordinateurs quantiques seront viables ("harvest now, decrypt later").
Rosenpass élimine ce risque en ajoutant une couche de chiffrement post-quantique.

**Activation :**

```bash
# Sur chaque peer — cloud-init du VPS client :
netbird up --setup-key <key> --enable-rosenpass --rosenpass-permissive

# Sur les VMs infra (Master, SD, Gateway) — via Ansible :
netbird up --enable-rosenpass --rosenpass-permissive
```

Le flag `--rosenpass-permissive` permet un rollout progressif : les peers avec
Rosenpass utilisent le PSK post-quantique entre eux, les peers sans Rosenpass
continuent à fonctionner normalement (WireGuard classique). Aucune coupure.

**Rôle Ansible (update) :**

```yaml
# roles/netbird-client/tasks/main.yml
- name: Start NetBird with Rosenpass
  ansible.builtin.command:
    cmd: >
      netbird up
      --setup-key {{ netbird_setup_key }}
      --management-url https://vpn.paultaffe.net
      --enable-rosenpass
      --rosenpass-permissive
```

---

## 17. Accès client — SSH, Console KVM, Rescue

### Principe IaaS

Flash Studio est un IaaS : le client a accès à son infrastructure. Il peut SSH,
ouvrir une console KVM, et utiliser le mode Rescue. Mais le plan de gestion
Flash Studio (flash-agent, NetBird, Caddy base, kernel) doit rester intègre.

**Philosophie : le client peut tout casser chez lui, mais pas ce qui nous permet de le gérer.**

### 3 modes d'accès

```
┌─────────────────────────────────────────────────────────────────┐
│ Mode 1 : SSH (usage quotidien)                                   │
│   User: studio (pas root)                                        │
│   Via: NetBird VPN (IP privée) ou IP publique Sovereign          │
│   Peut: docker, custom caddy, /mnt/data, apt install             │
│   Ne peut pas: modifier flash-agent, netbird, caddy base, kernel │
│                                                                   │
│ Mode 2 : Console KVM (urgence)                                   │
│   Via: Dashboard → Hetzner API → WebSocket VNC                   │
│   Peut: tout ce que SSH fait + recovery si SSH cassé             │
│   Même restrictions user studio (login console = user studio)    │
│                                                                   │
│ Mode 3 : Rescue (disaster recovery)                              │
│   Via: Dashboard → Hetzner API → reboot rescue                   │
│   Peut: accès disque complet, réparer boot, fsck                 │
│   Risque: peut toucher les fichiers protégés (accès physique)    │
│   Mitigation: détection par absence de heartbeat → alerte auto   │
└─────────────────────────────────────────────────────────────────┘
```

### Mode 1 : SSH — User `studio`

#### Permissions

```
User: studio
Groups: docker, studio
Shell: /bin/bash
Home: /home/studio
SSH: clé ED25519 uniquement (pas de mot de passe)
```

| Action | Autorisé | Comment |
|--------|----------|---------|
| Gérer ses containers | ✅ | `docker compose up/down/logs/exec` |
| Installer des paquets | ✅ | `sudo apt install` (via sudoers whitelist) |
| Lire/écrire ses données | ✅ | `/mnt/data/` (volume persistant) |
| Configurer Caddy custom | ✅ | `/mnt/data/caddy/custom/*.caddy` |
| Redémarrer un service Docker | ✅ | `sudo systemctl restart docker` |
| Recharger Caddy | ✅ | `sudo systemctl reload caddy` |
| Consulter les logs système | ✅ | `journalctl` (lecture) |
| Modifier flash-agent | ❌ | Immutable (`chattr +i`) |
| Modifier NetBird config | ❌ | Immutable (`chattr +i`) |
| Modifier Caddy base | ❌ | Immutable (`chattr +i`) |
| Modifier sshd_config | ❌ | Immutable (`chattr +i`) |
| Stopper flash-agent | ❌ | AppArmor + systemd protection |
| Devenir root | ❌ | Pas dans sudoers (sudo limité) |

#### Sudoers whitelist (`/etc/sudoers.d/studio`)

```
# Commandes autorisées sans mot de passe
studio ALL=(ALL) NOPASSWD: /usr/bin/apt, /usr/bin/apt-get
studio ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/bin/docker-compose
studio ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart docker
studio ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload caddy
studio ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart caddy
studio ALL=(ALL) NOPASSWD: /usr/bin/journalctl

# Explicitement interdit
studio ALL=(ALL) !ALL
```

### Mode 2 : Console KVM (Hetzner VNC)

Accessible depuis le dashboard client (`app.paultaffe.com` → section "Console").

```
Client clique "Console" dans le dashboard
  │
  ├─► Dashboard → Master API (POST /api/studios/{id}/console)
  ├─► Master → Hetzner API (POST /servers/{hetzner_id}/request_console)
  │     → Retourne : wss_url (WebSocket VNC, valide 1 min)
  │     → Retourne : password (pour le login VNC)
  │
  ├─► Dashboard ouvre un iframe noVNC avec le wss_url
  └─► Client voit la console de son serveur (comme devant l'écran)
```

**Cas d'usage :**
- SSH cassé (mauvaise config réseau, firewall bloqué)
- Boot qui ne finit pas (kernel panic, fsck interactif)
- Reset mot de passe user studio (oublié sa clé SSH → recovery)

**Sécurité :** la console ouvre un login standard → user `studio`. Le client
n'a pas le mot de passe root. Les mêmes restrictions `chattr +i` s'appliquent.

### Mode 3 : Rescue (Hetzner Rescue System)

Le mode Rescue boot un Debian live en RAM. Le client peut monter les disques
et réparer son système. C'est l'équivalent d'un CD de recovery.

```
Client clique "Rescue" dans le dashboard
  │
  ├─► Dashboard affiche un avertissement :
  │   "Le mode Rescue donne un accès complet au disque.
  │    Les services seront arrêtés pendant la durée du rescue.
  │    Le monitoring sera suspendu."
  │
  ├─► Client confirme → Master API (POST /api/studios/{id}/rescue)
  ├─► Master → Hetzner API :
  │     POST /servers/{id}/actions/enable_rescue (ssh_keys: [client_key])
  │     POST /servers/{id}/actions/reset (reboot)
  │
  ├─► Le serveur boot en rescue (Debian live, RAM)
  ├─► Client SSH vers IP Sovereign → rescue@... (root dans le rescue)
  │
  │   # Monter le disque
  │   mount /dev/sda1 /mnt
  │   # Réparer
  │   chroot /mnt
  │   ...
  │
  └─► Client clique "Quitter Rescue" → Master reboot en mode normal
      → flash-agent reprend → heartbeat → monitoring reprend
```

**Cas d'usage :**
- Filesystem corrompu (fsck requis)
- Kernel cassé (grub repair)
- Récupération de données après mauvaise manipulation
- Réinstallation de paquets systèmes cassés

**Risque :** en rescue, le client a un accès root au disque. Il PEUT :
- Retirer les flags `chattr +i` et modifier les fichiers protégés
- Lire les credentials NetBird (setup key expirée, mais config locale)
- Modifier le flash-agent

**Mitigations :**

| Risque | Mitigation |
|--------|-----------|
| Client modifie flash-agent | Heartbeat cesse → alerte auto → ticket auto "Agent tampered" |
| Client casse NetBird | VPN down → Master le détecte (peer offline) → alerte |
| Client modifie Caddy base | Ansible re-déploie au prochain update → écrase les modifications |
| Client lit des secrets | Les secrets sensibles (Master JWT) sont en mémoire, pas sur disque |
| Abus prolongé du rescue | Timeout rescue configurable (4h max) → reboot auto en mode normal |

**Acceptation du risque :** le rescue mode est un accès physique virtuel.
Comme tout IaaS (AWS, Hetzner, OVH), on accepte que le client a le contrôle
ultime sur sa machine. Notre protection est basée sur la **détection**, pas
l'empêchement absolu. Si le client sabote son agent, il perd son monitoring
et son support — c'est un problème pour lui, pas pour nous.

### Protection des fichiers Flash Studio

#### Couche 1 : Immutable flags (`chattr +i`)

```bash
# Appliqué par Ansible au déploiement (rôle common)
chattr +i /usr/local/bin/flash-agent
chattr +i /etc/systemd/system/flash-agent.service
chattr +i /etc/netbird/config.json
chattr +i /etc/caddy/Caddyfile
chattr +i /etc/ssh/sshd_config
chattr +i /etc/sudoers.d/studio
chattr +i /etc/apparmor.d/flash-agent

# Les logs sont append-only (chattr +a)
chattr +a /var/log/flash-agent.log
```

**Effet :** même root ne peut pas modifier ces fichiers sans d'abord
exécuter `chattr -i`, ce qui est :
- Impossible pour le user `studio` (pas dans sudoers pour chattr)
- Détectable par `auditd` (règle sur les appels chattr)
- Possible uniquement en rescue mode (risque accepté)

#### Couche 2 : AppArmor (Mandatory Access Control)

```
# /etc/apparmor.d/flash-agent — profil AppArmor
profile flash-agent /usr/local/bin/flash-agent {
    # Réseau : peut contacter Master + Event Router via NetBird
    network inet stream,
    network inet dgram,

    # Lecture système
    /etc/flash-agent/** r,
    /etc/netbird/config.json r,
    /proc/stat r,
    /proc/meminfo r,
    /proc/diskstats r,
    /sys/class/net/** r,

    # Écriture limitée
    /var/log/flash-agent.log a,          # append-only
    /mnt/data/caddy/custom/** rw,        # gestion routes Caddy
    /tmp/flash-agent-* rw,               # fichiers temporaires

    # Docker socket (pour health checks containers)
    /var/run/docker.sock rw,

    # Deny explicite
    deny /etc/shadow r,
    deny /etc/sudoers* rw,
    deny /root/** rwx,
    deny /home/studio/.ssh/** rw,
}
```

**Effet :** flash-agent ne peut accéder qu'à ce qui est listé. Si le binaire
est compromis (supply chain attack), il ne peut pas lire les clés SSH client,
les mots de passe, ou escalader ses privilèges.

#### Couche 3 : systemd hardening

```ini
# /etc/systemd/system/flash-agent.service (extrait)
[Service]
ExecStart=/usr/local/bin/flash-agent
User=flash-agent
Group=flash-agent
Restart=always
RestartSec=5

# Hardening
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
RestrictSUIDSGID=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
LockPersonality=yes
RestrictRealtime=yes
MemoryDenyWriteExecute=yes

# Le service ne peut PAS être arrêté par le user studio
# (systemctl stop flash-agent → access denied)
```

#### Couche 4 : Audit trail (`auditd`)

```bash
# /etc/audit/rules.d/flash-studio.rules

# Surveiller les tentatives de modification des fichiers protégés
-w /usr/local/bin/flash-agent -p wa -k flash-agent-tamper
-w /etc/netbird/ -p wa -k netbird-tamper
-w /etc/caddy/Caddyfile -p wa -k caddy-base-tamper
-w /etc/ssh/sshd_config -p wa -k sshd-tamper

# Surveiller l'usage de chattr (tentative de retirer immutable)
-a always,exit -F arch=b64 -S ioctl -F a1=0x40086602 -k chattr-change

# Les logs audit → flash-agent → Event Router → alerte Telegram
```

**Effet :** toute tentative de toucher aux fichiers protégés (même échouée)
génère un événement audit → flash-agent le capte → Event Router → ticket auto.

### Arbre de décision des accès

```
Client veut faire X
  │
  ├─► X = gérer ses containers ? → SSH (studio) ✅
  ├─► X = ajouter un domaine ?   → Dashboard ✅
  ├─► X = installer un paquet ?  → SSH (sudo apt) ✅
  ├─► X = voir les logs ?        → SSH (journalctl) ou Dashboard ✅
  ├─► X = SSH cassé ?            → Console KVM (Dashboard) ✅
  ├─► X = boot cassé ?           → Rescue (Dashboard) ✅
  ├─► X = accès root ?           → ❌ Non fourni (sécurité plan de gestion)
  ├─► X = modifier flash-agent ? → ❌ Immutable + AppArmor
  └─► X = modifier NetBird ?     → ❌ Immutable
```

### Dashboard — Section "Accès serveur"

```
app.paultaffe.com → Dashboard client → "Mon serveur"

┌─────────────────────────────────────────────────────┐
│  Mon serveur — acme42                               │
│                                                      │
│  IP publique : 1.2.3.4                               │
│  IP NetBird : 100.64.x.x                            │
│  Status : ● En ligne                                 │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ SSH      │  │ Console  │  │ Rescue   │          │
│  │ Clés SSH │  │   KVM    │  │  Mode    │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│                                                      │
│  Clés SSH autorisées :                               │
│  ┌──────────────────────────────────────────┐       │
│  │ 🔑 macbook-pro (ed25519, ajouté 10/03)  │ [×]  │
│  │ 🔑 desktop-pc (ed25519, ajouté 12/03)   │ [×]  │
│  │              [+ Ajouter une clé]          │       │
│  └──────────────────────────────────────────┘       │
│                                                      │
│  Domaines configurés :                               │
│  ┌──────────────────────────────────────────┐       │
│  │ acme42.paultaffe.fr      ● TLS OK       │       │
│  │ api.acme42.paultaffe.fr  ● TLS OK       │ [×]  │
│  │ api.mycorp.com           ● TLS OK       │ [×]  │
│  │              [+ Ajouter un domaine]       │       │
│  └──────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────┘
```

### Rôle Ansible correspondant

| Rôle | Contenu |
|------|---------|
| `common` | User `studio`, sudoers whitelist, `chattr +i` sur fichiers protégés, AppArmor profiles, auditd rules, fail2ban |
| `flash-agent` | Binaire, systemd unit hardened, AppArmor profil dédié |
| `netbird-client` | Config + immutable flag post-enrollment |

### Résumé de la protection

```
                    ┌─────────────────────────┐
                    │   Fichiers Flash Studio  │
                    └───────────┬──────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                  │
         chattr +i         AppArmor          auditd
         (filesystem)       (kernel MAC)      (détection)
              │                 │                  │
              └─────────────────┼─────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
        User studio      flash-agent          Event Router
        ne peut pas      ne peut pas          alerte si
        modifier         être tué/modifié     tentative détectée
```

**Defense in depth :** 3 couches indépendantes. Chaque couche seule est contournable
(root peut chattr, rescue peut tout). Mais les 3 ensemble créent un modèle où
toute action malveillante est **détectée et alertée** avant de causer des dommages.

---

## 18. Vie privée client — DNS privé et Exit Node

### Problème

Le VPN NetBird protège le **plan de gestion** (communication inter-infra), mais
le client reste exposé sur le **plan web** :

| Fuite | Détail |
|-------|--------|
| DNS résolution | L'ISP du client voit **tous les domaines** visités (requêtes DNS en clair) |
| Trafic sortant (devices) | Le laptop/PC du client sort via son ISP → IP résidentielle visible |
| Trafic sortant (VPS) | Le VPS fait du scraping/API → IP publique Hetzner traçable |

NetBird est un **mesh VPN** (accès aux ressources), pas un **full-tunnel VPN**.
Les devices du client accèdent au VPS et à l'infra Flash Studio via NetBird,
mais leur navigation web sort en direct par l'ISP.

### Brique 1 : DNS privé self-hosted

Un resolver DNS privé hébergé sur le Master, accessible **uniquement via NetBird**.

```
Client device (laptop, PC, phone)
  │
  ├─► NetBird tunnel (WireGuard)
  │     │
  │     └─► AdGuard Home (Master, port 53 sur IP NetBird uniquement)
  │           │
  │           ├─► Filtrage publicité + trackers (listes communautaires)
  │           ├─► Logs par client (audit, debugging)
  │           ├─► Blocage domaines malveillants (sécurité)
  │           │
  │           └─► Upstream chiffré :
  │                 DoH → https://dns.quad9.net/dns-query
  │                 DoT → tls://dns.quad9.net (fallback)
  │
  └─► ISP du client ne voit AUCUNE requête DNS
```

**Configuration via NetBird DNS Management :**

NetBird permet de définir un **DNS nameserver** par Group. Au provisioning,
le Master configure automatiquement le resolver DNS pour le group `client-{id}` :

```
NetBird Management API :
  PUT /api/dns/nameservers
    → nameserver: IP NetBird du Master
    → groups: ["client-{id}"]
    → domains: [] (match-all = toutes les requêtes DNS)
    → primary: true
```

Résultat : dès qu'un device rejoint le group via NetBird, **toutes ses requêtes
DNS passent automatiquement par AdGuard Home** sur le Master. Zéro config côté client.

**Pourquoi AdGuard Home :**

| Critère | AdGuard Home | Pi-hole | Unbound |
|---------|-------------|---------|---------|
| Interface web | ✅ Intégrée | ✅ Intégrée | ❌ CLI only |
| DoH/DoT upstream | ✅ Natif | ❌ Nécessite cloudflared | ✅ Natif |
| Filtrage trackers | ✅ Built-in | ✅ Built-in | ❌ Pas de filtrage |
| API REST | ✅ Complète | ⚠️ Limitée | ❌ Aucune |
| Multi-client (logs séparés) | ✅ Par IP | ⚠️ Limité | ❌ Non |
| Ressources | ~50 MB RAM | ~80 MB RAM | ~30 MB RAM |

L'API REST d'AdGuard Home permet au Master de configurer les règles par client
(blocklists personnalisées, domaines autorisés, etc.) depuis le dashboard.

**Docker Compose sur Master :**

```yaml
adguard-home:
  image: adguardteam/adguardhome:latest
  container_name: adguard-home
  restart: unless-stopped
  volumes:
    - adguard-work:/opt/adguardhome/work
    - adguard-conf:/opt/adguardhome/conf
  ports:
    - "100.64.x.x:53:53/tcp"    # DNS — IP NetBird uniquement
    - "100.64.x.x:53:53/udp"    # DNS — IP NetBird uniquement
    - "127.0.0.1:3000:3000"     # Admin UI — localhost only (proxied par Caddy)
  networks:
    - backend
```

**Important :** Le port 53 est bindé sur l'**IP NetBird du Master uniquement**.
Pas d'exposition sur l'IP publique. Seuls les peers NetBird peuvent résoudre.

### Brique 2 : Exit Node (full-tunnel VPN)

Le VPS du client devient sa **porte de sortie internet**. Tout le trafic web
des devices du client sort par le VPS au lieu de l'ISP.

```
Sans Exit Node :                    Avec Exit Node :
─────────────────                   ──────────────────

Laptop ──► ISP ──► Internet          Laptop ──► NetBird tunnel ──► VPS ──► Internet
│                                    │                              │
├ DNS : ISP voit tout                ├ DNS : AdGuard (brique 1)
├ IP : résidentielle du client       ├ IP : IP publique du VPS Hetzner
├ ISP : voit domaines + contenus     ├ ISP : voit UNIQUEMENT du WireGuard chiffré
└ Traçable → identité client         └ Traçable → IP VPS (pas le client)
```

**Configuration NetBird Exit Node :**

Le VPS du client est configuré comme Exit Node via le provisioning :

```
# Sur le VPS client (cloud-init) :
netbird up --setup-key <key>

# Via NetBird Management API (Master) :
POST /api/routes
  → network: 0.0.0.0/0        (tout le trafic)
  → peer: <peer_id du VPS>    (le VPS est la gateway)
  → groups: ["client-{id}"]   (seulement les devices de ce client)
  → enabled: true
  → masquerade: true           (NAT : trafic sort avec l'IP du VPS)
```

**Ce que voit chaque acteur :**

| Acteur | Sans Exit Node | Avec Exit Node |
|--------|---------------|----------------|
| ISP du client | Domaines visités, IPs contactées, volume | Tunnel WireGuard chiffré vers 1 IP (VPS) |
| Sites web visités | IP résidentielle du client | IP Hetzner du VPS |
| Hetzner | Trafic VPS uniquement | Trafic VPS + trafic sortant des devices |
| Flash Studio | Rien (pas notre trafic) | Rien (trafic P2P client↔VPS) |

**Activable par le client :** les deux briques (DNS privé et Exit Node) sont
**optionnelles** et contrôlables depuis le dashboard. Désactivées par défaut,
le client les active en 1 clic selon ses besoins.

```
Dashboard → "Mon serveur" → "Vie privée"
  ┌─────────────────────────────────────────────────┐
  │  Vie privée                                      │
  │                                                   │
  │  DNS privé        [○ OFF] / [● ON]               │
  │  "Requêtes DNS chiffrées + filtrage trackers"     │
  │  ✅ ISP ne voit plus vos sites visités            │
  │  ✅ Publicités et trackers bloqués                │
  │  Bloqué ce mois : 12 847 requêtes                │
  │                                                   │
  │  ──────────────────────────────────              │
  │                                                   │
  │  Exit Node         [○ OFF] / [● ON]              │
  │  "Tout mon trafic internet passe par mon VPS"     │
  │  ✅ Sites voient l'IP de votre VPS, pas la vôtre  │
  │  ✅ ISP ne voit que du trafic chiffré             │
  │  ⚠ Augmente la latence (~10-30ms)                │
  └─────────────────────────────────────────────────┘
```

**Actions dashboard → Master API → NetBird Management API :**

| Action client | Appel Master API | Appel NetBird API |
|---------------|-----------------|-------------------|
| Active DNS privé | `POST /api/studios/{id}/dns` `{"enabled": true}` | `PUT /api/dns/nameservers` → ajoute le nameserver AdGuard pour le group |
| Désactive DNS privé | `POST /api/studios/{id}/dns` `{"enabled": false}` | `PUT /api/dns/nameservers` → retire le nameserver pour le group |
| Active Exit Node | `POST /api/studios/{id}/exit-node` `{"enabled": true}` | `PUT /api/routes/{route_id}` `{"enabled": true}` |
| Désactive Exit Node | `POST /api/studios/{id}/exit-node` `{"enabled": false}` | `PUT /api/routes/{route_id}` `{"enabled": false}` |

### Résultat combiné

```
                    Avant                 Après (DNS privé + Exit Node)
                    ─────                 ───────────────────────────────
DNS résolution      ISP en clair          AdGuard Home via NetBird (chiffré)
Navigation web      IP résidentielle      IP VPS Hetzner (full-tunnel)
ISP voit            Tout                  Tunnel WireGuard opaque
Tracking/pubs       Passent               Bloqués par AdGuard
Scraping VPS        IP Hetzner directe    Idem (inchangé, déjà via VPS)
```

### Provisioning automatique

Au provisioning d'un nouveau client, le Master ajoute automatiquement :

```
POST /api/studios (Master API)
  │
  ├─► ... (étapes existantes 1-5) ...
  │
  ├─► 6. NetBird DNS (pré-provisionné, désactivé) :
  │       PUT /api/dns/nameservers
  │         → nameserver: IP NetBird Master (AdGuard Home)
  │         → groups: ["client-{id}"]
  │         → enabled: false  (activable par le client via dashboard)
  │
  ├─► 7. NetBird Exit Node (pré-provisionné, désactivé) :
  │       POST /api/routes
  │         → network: 0.0.0.0/0
  │         → peer: <peer_id du VPS>
  │         → groups: ["client-{id}"]
  │         → enabled: false  (activable par le client via dashboard)
  │         → masquerade: true
  │
  └─► DNS privé et Exit Node pré-configurés, prêts en 1 clic
      Le client active/désactive depuis Dashboard → "Vie privée"
```

### Rôles Ansible

| Rôle | Machine | Contenu |
|------|---------|---------|
| `adguard-home` | Master | Docker Compose, config AdGuard (upstream DoH Quad9, listes filtrage), bind sur IP NetBird |
| `netbird-server` (update) | Master | Ajouter DNS nameserver + route Exit Node dans le flux de provisioning |

### Limites connues

| Limite | Explication | Mitigation |
|--------|------------|------------|
| Exit Node = latence | +10-30ms sur toute la navigation | Optionnel, désactivable |
| VPS down = pas d'internet | Si le VPS crash et Exit Node actif, devices perdent l'accès | NetBird auto-reconnect + alerte Event Router |
| AdGuard down = pas de DNS | Résolution bloquée pour tous les clients | Failover : DNS secondaire configuré dans NetBird (ex: Quad9 direct) |
| Bande passante VPS | Le trafic des devices consomme la BP du VPS | Monitoring Gatus + alertes seuils |

---

## 19. Hardening V1 — Sécurité avancée

6 améliorations sécuritaires implémentées en V1, classées par priorité.

### 19.1 Tetragon — eBPF Runtime Security

Tetragon (CNCF, par les créateurs de Cilium) fait de la **détection + enforcement
directement dans le kernel Linux via eBPF**, remplaçant auditd pour la détection
runtime et complétant AppArmor pour l'enforcement.

```
             Avant (section 17)              Après (Tetragon)
             ──────────────────              ─────────────────
Détection    auditd (fichiers seuls)         eBPF kernel-level (fichiers + réseau + process)
Enforcement  AppArmor (profils statiques)    AppArmor + Tetragon (kill en temps réel)
Overhead     ~2-5% (auditd user-space)       < 1% (eBPF in-kernel)
Containers   Non-aware                       Container-aware (namespace, cgroup)
Exfiltration Invisible                       Détecté (process → IP inconnue)
```

**Cas concret :** un container Docker compromis tente un reverse shell.
- **Avant :** auditd ne voit rien (pas de fichier touché). AppArmor bloque si profil.
- **Après :** Tetragon détecte le `connect()` syscall vers une IP externe non-whitelistée
  et **kill le process avant que la connexion ne s'établisse**.

**Déploiement sur chaque VM (Sovereign + Production) :**

```yaml
# Docker Compose — ajouté à la stack Sovereign
tetragon:
  image: quay.io/cilium/tetragon:v1.3
  container_name: tetragon
  restart: unless-stopped
  pid: host
  privileged: true
  volumes:
    - /sys/kernel/btf:/sys/kernel/btf:ro
    - /sys/kernel/security:/sys/kernel/security
    - /sys/fs/bpf:/sys/fs/bpf
    - tetragon-policies:/etc/tetragon/tetragon.tp.d
  command:
    - --export-stdout
    - --export-filename /var/log/tetragon/events.log
  networks:
    - backend
```

**Policies Tetragon (YAML) :**

```yaml
# /etc/tetragon/tetragon.tp.d/01-protect-critical-files.yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: protect-flash-studio-files
spec:
  kprobes:
    - call: sys_openat
      syscall: true
      args:
        - index: 1
          type: string
      selectors:
        - matchArgs:
            - index: 1
              operator: Prefix
              values:
                - /usr/local/bin/flash-agent
                - /etc/netbird/
                - /etc/caddy/Caddyfile
                - /etc/ssh/sshd_config
          matchActions:
            - action: Sigkill    # Kill le process immédiatement
            - action: NotifyEnforcer
```

```yaml
# /etc/tetragon/tetragon.tp.d/02-block-reverse-shell.yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: block-reverse-shell
spec:
  kprobes:
    - call: sys_connect
      syscall: true
      args:
        - index: 1
          type: sockaddr
      selectors:
        - matchBinaries:
            - operator: NotIn
              values:
                - /usr/local/bin/flash-agent
                - /usr/bin/caddy
                - /usr/bin/netbird
                - /usr/bin/docker
          matchActions:
            - action: NotifyEnforcer
            # Log + alerte (pas kill — trop de faux positifs réseau)
```

**Intégration Event Router :**

```
Tetragon (events.log) → flash-agent (tail + parse) → Event Router
  → Alerte Telegram : "ALERT: process /bin/bash (PID 4521, container n8n)
     tenté d'ouvrir /etc/netbird/config.json — KILLED"
```

**Rôle Ansible :** `tetragon` — install binaire ou container, policies YAML, logrotate.

### 19.2 LUKS — Chiffrement disque au repos

Les VPS Hetzner n'ont **pas de chiffrement disque par défaut**. Si un attaquant
accède au stockage physique (ou Hetzner est compromis), tout est lisible :
base de données, tokens API, clés NetBird, modèles ComfyUI.

Hetzner ne supporte pas AMD SEV / Intel TDX (Confidential Computing). LUKS2
est la meilleure option disponible pour le chiffrement at-rest.

```
                  Sans LUKS                   Avec LUKS
                  ─────────                   ──────────
/mnt/data         Clair sur disque            Chiffré AES-256-XTS (LUKS2)
Accès physique    Tout lisible                Chiffré, illisible sans clé
Performance       Baseline                    ~2-5% overhead (AES-NI hardware)
Rescue mode       Montage direct              Nécessite la clé LUKS
```

**Architecture :**

```
VM boot
  │
  ├─► systemd unit : flash-luks-mount.service (Before=docker.service)
  │     │
  │     ├─► 1. Récupère la clé LUKS via NetBird :
  │     │       curl -s https://master.netbird.selfhosted/api/internal/luks-key \
  │     │         -H "Authorization: Bearer ${FLASH_AGENT_TOKEN}"
  │     │
  │     ├─► 2. cryptsetup luksOpen /dev/sdb1 data_crypt --key-file=-
  │     │
  │     ├─► 3. mount /dev/mapper/data_crypt /mnt/data
  │     │
  │     └─► 4. Efface la clé de la mémoire (shred)
  │
  └─► Docker démarre → monte /mnt/data/* pour les volumes
```

**Clé LUKS :**
- Générée au provisioning par le Master (256 bits, random)
- Stockée dans la base Master (chiffrée SOPS)
- Délivrée au VPS via NetBird (API interne, TLS, authentifié par token flash-agent)
- Jamais écrite sur disque du VPS (in-memory only, shred après mount)
- Le client n'a **pas accès** à la clé LUKS (protection plan de gestion)

**Provisioning (ajout au flux existant) :**

```
Ansible playbook
  │
  ├─► Role hetzner-volume (existant)
  │     ├─► Créer volume Hetzner
  │     ├─► Partitionner (GPT)
  │     ├─► cryptsetup luksFormat /dev/sdb1 --key-file=<clé_master>
  │     ├─► cryptsetup luksOpen → mount /mnt/data
  │     └─► mkfs.ext4 /dev/mapper/data_crypt
  │
  ├─► Role flash-agent
  │     └─► flash-luks-mount.service (systemd, Before=docker)
  │
  └─► Master API : stocker la clé LUKS associée au client
```

**Impact Rescue mode :** en mode Rescue, le client ne peut **pas** monter
`/mnt/data` sans la clé LUKS. C'est une protection supplémentaire : même avec
un accès Rescue, les données restent chiffrées. Le client doit contacter le
support pour un unlock assisté (vérification identité → clé temporaire).

**Rôle Ansible :** `hetzner-volume` (update) + `flash-agent` (update pour le mount service).

### 19.3 Posture Checks — Authentification continue

Le Zero Trust classique vérifie l'identité **une seule fois** (au login). En 2026,
le standard est la **vérification continue** : identité + état du device + contexte.

NetBird supporte les **Posture Checks** nativement. Ils sont évalués **à chaque
connexion** et **périodiquement** pour les peers déjà connectés.

```
Peer tente de se connecter
  │
  ├─► 1. Authentification Zitadel (SSO) ✅
  │
  ├─► 2. Posture Checks NetBird :
  │     ├─► OS version ≥ minimum ? (ex: macOS 14+, Windows 11 23H2+, Ubuntu 22.04+)
  │     ├─► NetBird client ≥ version minimum ? (ex: v0.35+)
  │     ├─► Peer approuvé ? (pas en quarantaine)
  │     │
  │     ├─► ✅ Tout OK → connexion autorisée
  │     └─► ❌ Check échoué → connexion REFUSÉE + notification client
  │
  └─► 3. Re-évaluation périodique (toutes les heures)
        → Si le device ne passe plus → déconnexion automatique
```

**Configuration via NetBird Management API (au provisioning) :**

```
POST /api/posture-checks
{
  "name": "flash-studio-baseline",
  "checks": {
    "nb_version_check": {
      "min_version": "0.35.0"
    },
    "os_version_check": {
      "linux": { "min_kernel_version": "5.15" },
      "darwin": { "min_version": "14.0" },
      "windows": { "min_kernel_version": "10.0.22631" }
    },
    "peer_network_range_check": {
      "action": "allow",
      "ranges": ["0.0.0.0/0"]
    }
  }
}
```

Les posture checks sont associés aux **Policies**. Un peer qui ne passe pas
le check perd l'accès aux ressources de la policy correspondante.

**Zitadel — Session re-evaluation :**

En complément, Zitadel (SSO) est configuré pour :
- **Session lifetime** : 8h (après : re-auth obligatoire)
- **Idle timeout** : 1h (inactivité : re-auth)
- **MFA obligatoire** : TOTP ou WebAuthn pour le dashboard (`app.paultaffe.com`)

**Rôle Ansible :** `netbird-server` (update) — posture checks créés au provisioning.

### 19.4 Cosign + SBOM — Supply Chain Security

Tous les binaires Flash Studio (flash-agent, event-router, support-agent) sont
buildés dans GitHub Actions puis déployés via Ansible. Sans vérification de
signature, un binaire compromis pourrait être injecté à n'importe quelle étape.

```
                Avant                           Après
                ─────                           ─────
Build     go build → binaire                  go build → binaire → cosign sign
Deploy    scp binaire → serveur               scp binaire + sig → cosign verify → deploy
SBOM      Aucun                               syft → SBOM (SPDX) → attestation cosign
Confiance "On fait confiance au CI"           Vérification cryptographique à chaque deploy
```

**Pipeline CI/CD (GitHub Actions) :**

```yaml
# .github/workflows/build.yml
jobs:
  build:
    steps:
      - uses: actions/checkout@v4

      - name: Build binary
        run: CGO_ENABLED=0 go build -o flash-agent ./cmd/agent

      - name: Generate SBOM
        uses: anchore/sbom-action@v0
        with:
          artifact-name: flash-agent.spdx.json

      - name: Sign binary with Cosign (keyless / Sigstore)
        uses: sigstore/cosign-installer@v3
      - run: cosign sign-blob --yes flash-agent --bundle flash-agent.bundle

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: flash-agent-signed
          path: |
            flash-agent
            flash-agent.bundle
            flash-agent.spdx.json
```

**Vérification au déploiement (Ansible) :**

```yaml
# roles/flash-agent/tasks/main.yml
- name: Download signed binary from release
  ansible.builtin.get_url:
    url: "{{ flash_agent_release_url }}"
    dest: /tmp/flash-agent
    checksum: "sha256:{{ flash_agent_sha256 }}"

- name: Download signature bundle
  ansible.builtin.get_url:
    url: "{{ flash_agent_bundle_url }}"
    dest: /tmp/flash-agent.bundle

- name: Verify Cosign signature
  ansible.builtin.command:
    cmd: >
      cosign verify-blob /tmp/flash-agent
      --bundle /tmp/flash-agent.bundle
      --certificate-identity-regexp "github.com/Mobutoo/flash-infra"
      --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
  register: cosign_verify
  failed_when: cosign_verify.rc != 0

- name: Deploy verified binary
  ansible.builtin.copy:
    src: /tmp/flash-agent
    dest: /usr/local/bin/flash-agent
    mode: "0755"
    remote_src: true
  when: cosign_verify.rc == 0

- name: Set immutable flag
  ansible.builtin.command:
    cmd: chattr +i /usr/local/bin/flash-agent
```

**Cosign keyless (Sigstore) :** pas de clé privée à gérer. L'identité du signataire
est liée au workflow GitHub Actions via OIDC. Impossible de signer depuis un laptop
compromis — seul le CI peut signer.

**SBOM :** inventaire complet des dépendances Go (modules + versions). Utile pour :
- Réponse rapide si une CVE touche une dépendance
- Audit de conformité
- Transparence client (disponible dans le dashboard si demandé)

### 19.5 Micro-segmentation Docker (nftables)

Par défaut, Docker crée un bridge `docker0` où **tous les containers peuvent
communiquer entre eux**. Un container compromis peut scanner et attaquer les autres.

```
Sans micro-segmentation :          Avec micro-segmentation :

┌─────────────────────┐            ┌─────────────────────┐
│     docker0 bridge  │            │  Réseau "frontend"  │
│                     │            │  ┌──────┐  ┌──────┐ │
│ n8n ↔ ComfyUI ↔ PG │            │  │ n8n  │  │Caddy │ │
│  ↔ Caddy ↔ Grafana  │            │  └──┬───┘  └──────┘ │
│                     │            │     │                │
│ TOUT communique     │            ├─────┼────────────────┤
│ avec TOUT           │            │  Réseau "backend"   │
└─────────────────────┘            │  ┌──────┐  ┌──────┐ │
                                   │  │  PG  │  │Qdrant│ │
                                   │  └──────┘  └──────┘ │
                                   └─────────────────────┘
                                   n8n → PG ✅  (backend)
                                   Caddy → n8n ✅ (frontend)
                                   ComfyUI → PG ❌ (pas même réseau)
```

**Docker Compose — réseaux isolés :**

```yaml
# docker-compose.yml (Sovereign / Production)
networks:
  frontend:
    driver: bridge
    internal: false    # accès internet (Caddy, n8n pour webhooks)
  backend:
    driver: bridge
    internal: true     # PAS d'accès internet (BDD, services internes)
  monitoring:
    driver: bridge
    internal: true     # Isolé (Prometheus, Grafana interne)

services:
  caddy:
    networks: [frontend]

  n8n:
    networks: [frontend, backend]   # Accès web + accès BDD

  postgres:
    networks: [backend]             # Isolé, pas d'accès internet

  qdrant:
    networks: [backend]

  comfyui:
    networks: [frontend]            # Accès web pour l'UI, pas de BDD

  grafana:
    networks: [monitoring, frontend]  # UI accessible + métriques internes

  prometheus:
    networks: [monitoring]          # Isolé

  tetragon:
    network_mode: host              # Nécessaire pour eBPF
```

**nftables — Egress filtering sur la VM :**

```bash
#!/usr/sbin/nft -f
# /etc/nftables.conf — Sovereign VM

table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    iif lo accept
    tcp dport { 22, 80, 443 } accept        # SSH + HTTP/S
    ip saddr 100.64.0.0/10 accept            # NetBird mesh
    drop
  }

  chain forward {
    type filter hook forward priority 0; policy drop;
    # Docker gère ses propres règles via iptables/nftables
    ct state established,related accept
    # Interdire le forwarding inter-containers sauf via Docker networks
    iifname "docker0" oifname "docker0" drop
  }

  chain output {
    type filter hook output priority 0; policy accept;
    # Log les connexions sortantes inattendues (debug)
    # En production : restreindre aux IPs connues si nécessaire
  }
}
```

**Rôle Ansible :** `common` (update) — nftables rules + Docker network config.
`sovereign-compose` et `studio-compose` (update) — réseaux isolés dans les Compose files.

### Résumé Hardening V1

```
┌──────────────────────────────────────────────────────────────────┐
│                  FLASH STUDIO — Security Stack V1                │
│                                                                  │
│  ┌─ Couche 1 : Chiffrement ──────────────────────────────────┐  │
│  │  WireGuard + Rosenpass (post-quantique)   [section 16]    │  │
│  │  LUKS2 AES-256-XTS (disque at-rest)       [section 19.2]  │  │
│  │  SOPS + age (secrets Ansible)             [section 6]     │  │
│  │  TLS 1.3 (Caddy, auto-renew)             [section 6]     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ Couche 2 : Identité & Accès ─────────────────────────────┐  │
│  │  Zitadel SSO + MFA (TOTP/WebAuthn)        [section 6]     │  │
│  │  NetBird Posture Checks (device state)    [section 19.3]  │  │
│  │  Session re-evaluation continue           [section 19.3]  │  │
│  │  User studio (sudoers whitelist)          [section 17]    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ Couche 3 : Runtime Protection ───────────────────────────┐  │
│  │  Tetragon eBPF (détection + kill kernel)  [section 19.1]  │  │
│  │  AppArmor (MAC statique)                  [section 17]    │  │
│  │  systemd hardening (ProtectSystem=strict)  [section 17]   │  │
│  │  chattr +i (fichiers immutables)          [section 17]    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ Couche 4 : Réseau ───────────────────────────────────────┐  │
│  │  NetBird Groups + deny-by-default         [section 16]    │  │
│  │  Docker networks isolés (frontend/backend) [section 19.5] │  │
│  │  nftables egress filtering                [section 19.5]  │  │
│  │  AdGuard Home DNS privé                   [section 18]    │  │
│  │  Exit Node full-tunnel (optionnel)        [section 18]    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ Couche 5 : Supply Chain ─────────────────────────────────┐  │
│  │  Cosign keyless (Sigstore) — binaires signés [section 19.4]│ │
│  │  SBOM (SPDX) — inventaire dépendances     [section 19.4]  │  │
│  │  Verify at deploy — Ansible reject si !sig [section 19.4] │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ Couche 6 : Détection & Réponse ──────────────────────────┐  │
│  │  Tetragon events → flash-agent → Event Router [section 19.1]│ │
│  │  auditd → flash-agent → Event Router      [section 17]    │  │
│  │  Gatus health checks + alertes             [section 11]   │  │
│  │  Alertes Telegram (temps réel)             [section 11]   │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Nouveaux rôles Ansible (récapitulatif)

| Rôle | Machine | Contenu |
|------|---------|---------|
| `tetragon` | Sovereign, Production | Container Tetragon, policies YAML (protect files, block reverse shell), logrotate |
| `hetzner-volume` (update) | Sovereign, Production | LUKS2 format + cryptsetup au provisioning |
| `flash-agent` (update) | Sovereign, Production | Service systemd `flash-luks-mount` (unlock au boot via Master API) |
| `netbird-server` (update) | Master | Posture checks baseline, Rosenpass config |
| `netbird-client` (update) | Toutes les VMs | `--enable-rosenpass --rosenpass-permissive` |
| `common` (update) | Toutes les VMs | nftables rules, cosign install |
| `sovereign-compose` (update) | Sovereign | Docker networks isolés (frontend/backend/monitoring) |
| `studio-compose` (update) | Production | Docker networks isolés |

### Provisioning (étapes ajoutées au flux section 9)

```
Ansible playbook (après les étapes existantes)
  │
  ├─► Role hetzner-volume : LUKS format + mount
  ├─► Role netbird-client : --enable-rosenpass --rosenpass-permissive
  ├─► Role tetragon : install + policies
  ├─► Role common : nftables + cosign
  ├─► Role flash-agent : cosign verify + deploy signé + LUKS mount service
  ├─► Role sovereign-compose : Docker networks isolés
  │
  └─► Master API (NetBird) :
        POST /api/posture-checks → baseline (OS version, NetBird version)
        Associer les posture checks aux policies du client
```
