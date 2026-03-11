# PRD Flash Studio v5.0 — Document Final
## Sovereign IaaS — Studio de Production IA pour Entrepreneurs

> Mise à jour mars 2026 — Référence technique : `flash-infra/ARCHITECTURE.md`

---

## 1. Vision

Flash Studio est une plateforme IaaS fournissant à chaque client un VPS dédié
pré-configuré avec une stack complète d'outils IA, d'automatisation et de gestion
de données. Le client obtient son infrastructure souveraine, ses données, ses clés
API — hébergées en Europe, isolées par client, protégées par un VPN post-quantique.

**Positionnement :** Le facilitateur du Web 3.0 pour les entrepreneurs de l'ère IA.

**Prix :** 29€ à 149€/mois selon le plan. GPU et Bright Data refacturés avec marge.

**Cible :** Créateurs de contenu IA, gestionnaires UGC, studios musicaux,
dropshippers, traders, webmarketeurs — tout entrepreneur ayant besoin d'automatisation IA.

**Domaines :**
- `paultaffe.com` → Vitrine, support, dashboard client
- `paultaffe.net` → Infrastructure ops (SSO, VPN, monitoring)
- `paultaffe.fr` → Isolation per-client (`{client_id}.paultaffe.fr`)

---

## 2. Architecture globale

```
INFRA FLASH STUDIO (périmètre Flash Studio)
─────────────────────────────────────────────────────────────────

  ┌────────────┐   ┌─────────────┐   ┌────────────┐
  │  GATEWAY   │   │SERVICE DESK │   │   MASTER   │
  │ CX33 (8GB) │   │ CX33 (8GB) │   │ CX33 (8GB) │
  │            │   │             │   │            │
  │*.paultaffe │   │*.paultaffe  │   │*.paultaffe │
  │    .fr     │   │    .com     │   │    .net    │
  │registry.net│   │(help,app,   │   │(auth,vpn,  │
  │            │   │ terrasse,   │   │ monitor,   │
  │TLS On-Demand│  │ status,     │   │ n8n,admin) │
  │Catch-all   │   │ agence)     │   │            │
  └────────────┘   └─────────────┘   └────────────┘
         │                │                 │
         └────────────────┼─────────────────┘
                          │
                  NetBird VPN mesh
                  (WireGuard + Rosenpass post-quantique)
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
  │  Sovereign  │  │  Sovereign  │  │  Sovereign  │
  │ (per-client)│  │ (per-client)│  │ (per-client)│
  │  IP fixe    │  │  IP fixe    │  │  IP fixe    │
  │*.client.fr  │  │*.client.fr  │  │*.client.fr  │
  └──────┬──────┘  └─────────────┘  └─────────────┘
         │
  ┌──────▼──────┐
  │  Production │
  │ (destructib)│
  │ /mnt/data   │
  │ persiste    │
  └─────────────┘


INFRA CLIENT (leur VPS, leur propriété)

  VM Souveraine (CX33 — 4vCPU, 8GB, 80GB)
  ├── Caddy (reverse proxy, TLS auto, routes base + custom)
  ├── Flash-Agent Go (heartbeat, backup, exec, LUKS mount, Caddy manager)
  ├── NetBird client (self-hosted, mesh chiffré post-quantique)
  └── Services permanents (Grafana, n8n, Vaultwarden...)

  VM Production (CX33 + Volume persistant /mnt/data)
  └── Docker Compose modulaire (profiles par plan)
```

**5 types de VMs :**

| VM | Rôle | Coût |
|----|------|------|
| Gateway | TLS On-Demand, Docker Registry cache, catch-all parking | Fixe ~8€/mois |
| Service Desk | Dashboard, ticketing, forum, status, event-router | Fixe ~20€/mois |
| Master | Provisioning, billing, SSO (Zitadel), NetBird, monitoring | Fixe ~20€/mois |
| Sovereign (per-client) | Services permanents, IP fixe, DNS wildcard | ~8€/mois par client |
| Production (per-client) | Stack IA destructible + volume persistant | ~8-20€ par client |

---

## 3. Stack client — Docker Compose avec profiles

### Services Core (tous les plans)

| Service | Rôle | RAM limit |
|---------|------|-----------|
| Caddy | Reverse proxy, TLS auto | 64m |
| Flash-Agent | Agent local + MCPs + LUKS mount | 32m (process) |
| PostgreSQL | Base de données | 512m |
| NocoDB | Hub de données NoCode | 512m |

### Profile: ai (plans Créateur+)

| Service | Rôle | RAM limit |
|---------|------|-----------|
| LiteLLM | Proxy LLM multi-provider (BYOK) | 256m |
| Qdrant | Base vectorielle (RAG) | 1g |

### Profile: ai-gateway (optionnel)

| Service | Rôle | RAM limit |
|---------|------|-----------|
| OpenClaw (ou PicoClaw) | AI Gateway MCP | 512m |

### Profile: knowledge (plans Créateur+)

| Service | Rôle | RAM limit |
|---------|------|-----------|
| CouchDB (Obsidian LiveSync) | Second Cerveau | 256m |

### Profile: tools (plans Créateur+)

| Service | Rôle | RAM limit |
|---------|------|-----------|
| Browserless | Chrome headless | 1g |
| Flash-Review | App de validation livrables | 256m |
| Flash-Tools | Terminal web (Claude Code, Gemini CLI) | 256m |

### Profile: scraping (plans Business+)

| Service | Rôle | RAM limit |
|---------|------|-----------|
| Bright Data Proxy Manager | Scraping résidentiel | 256m |

### Profile: trading (plan Illimité)

| Service | Rôle | RAM limit |
|---------|------|-----------|
| Freqtrade | Bot de trading + FreqUI | 512m |

### GPU (externe, à la demande)

ComfyUI, Remotion, Whisper, fine-tuning LoRA → lancés sur RunPod via SkyPilot,
déclenchés par le client, résultats transférés via S3.

---

## 4. Plans et tarification

| | Socle | Créateur | Business | Illimité |
|---|---|---|---|---|
| Prix | 29€/mois | 49€/mois | 79€/mois | 149€/mois |
| VPS | CX21 (4 Go) | CX31 (8 Go) | CX31 (8 Go) | CX41 (16 Go) |
| Volume | 20 Go | 40 Go | 40 Go | 80 Go |
| Profiles | core | core+ai+knowledge+tools | +scraping | +trading |
| GPU simultanés | 1 | 3 | 5 | 10 |
| Mode 24/7 | Non | Non | Oui | Oui |

**Add-ons :** GPU RunPod (coût + 25%), Bright Data forfaits (coût + 30%),
volume supplémentaire (2€/10 Go).

**LLM :** BYOK (Bring Your Own Key). Le client fournit ses clés API.
Flash Studio ne touche pas aux tokens.

**Incentive GPU :** Le client qui éteint son VPS accumule des crédits GPU
(0,005€/heure éteinte).

---

## 5. Cycle de vie d'un Studio

### START — Provisioning automatique (< 30 min)

```
Client paie (Stripe Checkout)
  │
  ▼
Webhook Stripe → Master API
  │
  ├─► 1. Zitadel : créer user client (SSO, MFA activé)
  ├─► 2. Hetzner API : créer VM Souveraine (IP fixe)
  ├─► 3. Hetzner API : créer VM Production + Volume (LUKS2 formaté)
  ├─► 4. OVH DNS API :
  │       {client_id}.paultaffe.fr      A  <IP_SOVEREIGN>
  │       *.{client_id}.paultaffe.fr    A  <IP_SOVEREIGN>
  ├─► 5. NetBird Management API :
  │       Group "client-{id}" + Policies (ALLOW ↔ infra + intra-client)
  │       Setup key (single-use, 24h) + Posture checks baseline
  │       DNS nameserver AdGuard (pré-configuré, désactivé)
  │       Route Exit Node 0.0.0.0/0 (pré-configurée, désactivée)
  │
  ▼
Ansible playbook (déclenché par Master)
  │
  ├─► common (SSH, users, nftables, cosign)
  ├─► hetzner-volume (LUKS2 mount chiffré)
  ├─► netbird-client (setup key + Rosenpass post-quantique)
  ├─► tetragon (eBPF runtime security)
  ├─► caddy (Caddyfile base + import custom/*.caddy)
  ├─► flash-agent (cosign verify + deploy signé + LUKS mount service)
  ├─► sovereign-compose (services permanents, réseaux isolés)
  ├─► studio-compose (stack IA, profil selon plan)
  └─► grafana + backup
  │
  ▼
Post-deploy
  ├─► Email client : accès, URLs, guide install NetBird (devices perso)
  ├─► NocoDB : entrée client créée
  ├─► Grafana : dashboard client activé
  └─► Monitoring : alertes activées

Temps total : < 30 minutes, zéro intervention humaine.
```

### STOP — Destruction VM Production (données préservées)

```
1. Agent : docker compose stop (arrêt gracieux)
2. Agent : resticprofile backup → S3 Hetzner
3. Agent : signal "ready to destroy" → Master
4. Master : Hetzner API → detach volume
5. Master : Hetzner API → delete VM Production
6. VM Souveraine reste active (DNS, NetBird, accès client inchangés)
7. Master : update status → SLEEPING
```

### DUNNING — Gestion des impayés

```
Stripe webhook invoice.payment_failed
  │
  ├─► Jour 0 : Couper IMMÉDIATEMENT services surfacturés
  │     (GPU RunPod, Bright Data) — VM principale : INTACT
  │     Email client : "7 jours pour régulariser"
  │
  ├─► Stripe retry automatique J+3, J+5, J+7
  │
  ├─► Jour 7 (si toujours impayé) : VM suspendue (poweroff)
  │     Données préservées 30 jours — Email + ticket Zammad
  │
  └─► Jour 37 : Offboarding complet (voir ci-dessous)

Régularisation à tout moment → réactivation automatique (Stripe invoice.paid)
```

### OFFBOARDING — Annulation ou impayé

```
Annulation confirmée (ou J+37 impayé)
  │
  ├─► Immédiat : docker stop + mode "lecture seule + export"
  ├─► 30 jours : export ZIP disponible (pg_dump + Qdrant JSON + /mnt/data)
  │     Lien S3 signé (valide 24h) envoyé par email
  │
  └─► J+30 : Suppression totale
        VM Sovereign + VM Production + Volume
        DNS OVH + peer NetBird + user Zitadel
        Email confirmation RGPD Art.17
```

### Garde-fous

- Mutex par studio_id (pas de double START/STOP)
- Volume et VPS doivent être dans la même zone Hetzner
- Si detach échoue → retry 3x avant alerte
- Si mount LUKS échoue → alerte ops (clé via Master API)
- Si agent ne heartbeat pas dans les 5 min après boot → alerte admin

---

## 6. Flash-Agent Go

**Rôle :** Interface unique entre le Master et le VPS client.

### Modules

| Module | Fonction | Lignes estimées |
|--------|---------|----------------|
| core | Heartbeat (60s), auth JWT, config sync | ~200 |
| health | Docker stats, RAM, CPU, disk | ~150 |
| backup | Pilotage resticprofile (backup, check, forget) | ~200 |
| exec | Exécution de commandes du Master | ~100 |
| meter | Métriques d'usage pour facturation | ~150 |
| update | Auto-update binaire signé (Cosign keyless) | ~100 |
| luks | Mount /mnt/data via clé Master API au boot | ~80 |
| caddy | Gestion routes Caddyfile custom (dashboard) | ~120 |
| security | Relay events Tetragon + auditd → Event Router | ~100 |
| mcps | Serveur MCP + implémentations | ~1500 |

**Total :** ~2700 lignes Go. Binaire statique signé (Cosign/Sigstore). CGO_ENABLED=0.

### MCPs intégrés

Exposés sur `/var/run/flash-mcp.sock`. Consommables par tout agent IA compatible MCP.

| MCP | API backend |
|-----|------------|
| mcp-n8n | localhost:5678 |
| mcp-nocodb | localhost:8080 |
| mcp-postgresql | localhost:5432 (lecture seule) |
| mcp-qdrant | localhost:6333 |
| mcp-obsidian | filesystem /mnt/data/obsidian/vault/ |
| mcp-gpu | proxy vers Master /api/gpu/* |
| mcp-flash | proxy vers Master /api/* |
| mcp-docs | Qdrant collection "flash-docs" |
| mcp-marketplace | Qdrant collection "flash-intel" |
| mcp-review | API flash-review localhost |
| mcp-freqtrade | localhost:8081 (si profil trading) |
| mcp-brightdata | API Bright Data (si profil scraping) |

---

## 7. Master Flash Studio

**Stack :** Next.js 14+ (App Router) + TypeScript + Prisma + PostgreSQL + Redis

### API Routes

```
/api/auth/*                   NextAuth (login, register, sessions)
/api/studios                  CRUD studios
/api/studios/[id]/start       Séquence START (provisioning)
/api/studios/[id]/stop        Séquence STOP
/api/studios/[id]/isolate     Isolation NetBird (incident sécurité)
/api/studios/[id]/console     KVM console → Hetzner request_console → noVNC
/api/studios/[id]/dns         Activer/désactiver DNS privé (AdGuard)
/api/studios/[id]/exit-node   Activer/désactiver Exit Node full-tunnel
/api/config/[id]              Config push vers les agents
/api/heartbeat                Réception heartbeats
/api/tickets                  Service Desk
/api/gpu/launch               Lancer instance RunPod via SkyPilot
/api/gpu/status               Statut jobs GPU
/api/gpu/stop                 Arrêter instance
/api/library/packs            Bibliothèque de Solution Packs
/api/library/install          Installer un pack sur un studio
/api/billing/*                Webhooks Stripe (provisioning, dunning, offboarding)
/api/dns/*                    Gestion dynamique OVH DNS API
/api/internal/luks-key        Clé LUKS → flash-agent (NetBird only, auth token)
```

### Dashboard Admin

```
/admin/fleet          Vue de tous les studios (statut, RAM, disk, alertes)
/admin/alerts         Heartbeats manquants, backups échoués, disques pleins
/admin/billing        MRR, coûts, marge par client
/admin/tickets        Service Desk (tickets pré-diagnostiqués)
/admin/rollout        Gestion des versions agent (fenêtre ven→sam 02h-04h)
/admin/incidents      Incidents P1/P2 en cours, historique post-mortems
```

### Dashboard Client

```
/dashboard              Vue du studio (services, RAM, CPU, disk)
/dashboard/services     Activer/désactiver services
/dashboard/backups      Historique, restore, backup manuel
/dashboard/ai-keys      OAuth Google + saisie clés API (Anthropic, OpenAI, etc.)
/dashboard/gpu          Crédits, lancer instance, historique jobs
/dashboard/library      Bibliothèque de Solution Packs
/dashboard/creations    Historique des outputs (images, vidéos, posts)
/dashboard/billing      Factures, crédits GPU, forfait Bright Data
/dashboard/settings     Plan, SSH keys, reset studio
/dashboard/server       SSH keys, Console KVM (noVNC), Rescue mode
/dashboard/domains      Sous-domaines + domaines custom (Caddyfile via flash-agent)
/dashboard/privacy      DNS privé (AdGuard) + Exit Node full-tunnel (on/off)
```

---

## 8. Infrastructure Flash Studio

### Gateway (CX33 — 8GB)

| Composant | Rôle |
|-----------|------|
| Caddy | TLS On-Demand (`*.paultaffe.fr`), catch-all parking "Studio en sommeil" |
| Docker Registry Cache | Mirror Docker Hub local (accélère les pulls) |

> Le Gateway n'est **pas** le point de passage du trafic client actif.
> Le trafic va directement vers la VM Souveraine du client (DNS `*.{client}.paultaffe.fr`).
> Le Gateway est le catch-all pour les clients inconnus ou en sommeil.

### Service Desk (CX33 → CX43 au palier 50 clients)

| Composant | Rôle |
|-----------|------|
| Zammad | Ticketing support (`help.paultaffe.com`) |
| Discourse | Forum communauté "La Terrasse" (`terrasse.paultaffe.com`) |
| Discourse (phase 3) | Marketplace "L'Agence" (`agence.paultaffe.com`) |
| Gatus | Status page (`status.paultaffe.com`) |
| Dashboard client | App web (`app.paultaffe.com`) |
| Event Router | Routeur d'événements (webhooks, tickets automatiques) |

### Master (CX33)

| Composant | Rôle |
|-----------|------|
| Master API (Next.js) | Provisioning, billing, config push |
| Zitadel | SSO + MFA (`auth.paultaffe.net`) |
| NetBird Management | VPN mesh controller (`vpn.paultaffe.net`) — self-hosted |
| AdGuard Home | DNS privé per-client (IP NetBird uniquement) |
| Grafana | Monitoring centralisé (`monitor.paultaffe.net`) |
| n8n | Automation ops (`n8n.paultaffe.net`) |
| PostgreSQL | Base Master (clients, billing, config) |

---

## 9. Backup — Stratégie Zero-Loss

| Élément | Outil | Stockage | Fréquence |
|---------|-------|---------|-----------|
| PostgreSQL client | pg_dump → restic | S3 Hetzner | Cron 2h + avant STOP |
| Qdrant client | Snapshot API → restic | S3 Hetzner | Cron 2h + avant STOP |
| Volume /mnt/data | resticprofile | S3 Hetzner | Cron 2h + avant STOP |
| Obsidian vault | rclone sync | S3 client | Cron 6h |
| Master PostgreSQL | pg_dump → restic | S3 Hetzner | Cron quotidien |
| Master configs | restic | S3 Hetzner | Cron 2h |

Rétention : 7 jours quotidien, 4 semaines hebdomadaire.
Déduplication au bloc via restic. Intégrité : `restic check` hebdomadaire.
Disque chiffré LUKS2 AES-256-XTS (clé gérée par Master, délivrée via NetBird).

---

## 10. Sécurité — Stack 6 couches

| Couche | Mécanisme |
|--------|-----------|
| **Chiffrement transit** | WireGuard + **Rosenpass post-quantique** (PSK renouvelé toutes les 2min) |
| **Chiffrement at-rest** | **LUKS2 AES-256-XTS** sur `/mnt/data` (clé via Master API, jamais sur disque) |
| **Identité continue** | Zitadel SSO + MFA + **NetBird Posture Checks** (OS version, client version) |
| **Runtime protection** | **Tetragon eBPF** (détection + kill kernel-level, container-aware) + AppArmor + systemd hardening |
| **Réseau** | NetBird deny-by-default (Groups + Policies) + Docker networks isolés + nftables egress |
| **Supply chain** | **Cosign keyless** (Sigstore) — binaires vérifiés à chaque déploiement + SBOM (SPDX) |
| SSH | User `studio` (pas root), ED25519 uniquement, sudoers whitelist |
| Fichiers critiques | `chattr +i` (immutable filesystem) |
| Audit & détection | Tetragon events + auditd → flash-agent → Event Router → alerte Telegram |
| Secrets | SOPS + age (chiffrés dans git), BYOK pour les clés LLM |
| TLS | Caddy auto-renew Let's Encrypt (TLS 1.3) |
| Firewall | Hetzner Cloud Firewall + nftables egress filtering |

### Accès client

| Mode | Description |
|------|-------------|
| **SSH** | User `studio` via IP NetBird (ou IP publique). Docker, apt, journalctl autorisés. |
| **Console KVM** | Dashboard → Hetzner API `request_console` → WebSocket VNC → noVNC iframe |
| **Rescue** | Dashboard → Hetzner API `enable_rescue` → Debian live RAM (recovery disque) |

### Vie privée client (opt-in)

| Feature | Description |
|---------|-------------|
| **DNS privé** | AdGuard Home sur Master via NetBird. Requêtes chiffrées (DoH Quad9), filtrage trackers/pubs. |
| **Exit Node** | VPS du client = porte de sortie internet. ISP ne voit que du WireGuard chiffré. |

---

## 11. Scalabilité (paliers confirmés)

| Clients | Action |
|---------|--------|
| 1-10 | Focus fiabilité backup S3 |
| 50 | Négociation quotas Hetzner + upgrade Service Desk CX43 |
| 150 | 2ème Gateway + Load Balancer + Master V2 (snapshots Hetzner 15min) |
| 300+ | Queues Redis, architecture asynchrone |
| 500+ | Support automatisé via Service Desk, bouton reset, Master V3 (hot standby) |

---

## 12. Opérations

### Maintenance & Updates

| Type | Fenêtre | Notification |
|------|---------|-------------|
| Patch OS | Continu (unattended-upgrades) | Aucune |
| Update containers | **Ven→Sam 02h-04h** | Email J-48h |
| Update flash-agent | **Ven→Sam 02h-04h** | Email J-48h |
| Update majeure | **Ven→Sam 02h-04h** | Email J-7j + J-48h |
| Patch sécurité critique | Hors fenêtre (< 4h) | Email immédiat |

Rolling Ansible (1 VM à la fois) + snapshot Hetzner avant update + rollback automatique.

### Incident Response

| Niveau | Définition | SLA |
|--------|-----------|-----|
| P1 — Critical | Plateforme down ou compromission confirmée | < 15 min |
| P2 — High | VM client down ou > 10 clients impactés | < 1h |
| P3 — Medium | VM individuelle avec problème | < 4h |
| P4 — Low | Anomalie mineure, no impact | < 24h |

**VM compromise :** isolation NetBird DENY all + snapshot forensique + email client + ticket P1.

### Master Disaster Recovery

| Version | RTO | RPO | Mécanisme |
|---------|-----|-----|-----------|
| V1 (actuel) | 4h | 2h | Rebuild Ansible depuis backup S3 |
| V2 (50 clients) | 1h | 15min | Snapshots Hetzner automatiques |
| V3 (150+ clients) | 15min | ~0 | Hot standby (PostgreSQL streaming replication) |

### Abuse Policy

Détection auto (CPU > 90% > 1h, pattern stratum mining, 10k+ connexions/min)
→ warning client 24h → suspension si pas de réponse.
Réponse plainte Hetzner < 4h.

---

## 13. RGPD & Légal

| Rôle | Flash Studio est... |
|------|---------------------|
| Données clients Flash Studio | **Responsable de traitement** |
| Données des clients des clients (sur VMs) | **Sous-traitant** |

**Sous-traitants déclarés :** Hetzner (Allemagne), Stripe (USA — SCCs), Brevo (France), OVH (France).

**Durées de conservation :**
- Données client actif : durée abonnement
- Post-offboarding : 30 jours (window export), puis suppression totale
- Factures : 10 ans (obligation légale)
- Logs techniques : 90 jours

**Droits RGPD :**
- Art.15 (accès) : export sur demande via hello@paultaffe.com (30j)
- Art.17 (effacement) : offboarding immédiat déclenché → suppression J+30
- Art.20 (portabilité) : ZIP (pg_dump + Qdrant JSON + /mnt/data) depuis dashboard

---

## 14. Roadmap de développement

### Phase 1 — Socle infra (Semaines 1-3)
- Ansible playbooks complets (roles : common, docker, netbird, caddy, flash-agent, LUKS, tetragon)
- Flash-Agent Go v1 (heartbeat + backup + config + LUKS mount + Cosign auto-update)
- API Master (CRUD studios, START/STOP, config push, dunning Stripe, LUKS key)
- DNS OVH API (provisioning + offboarding)
- NetBird Management API (groups, policies, posture checks, Rosenpass)

### Phase 2 — Dashboards (Semaines 4-5)
- Dashboard Admin (fleet, alertes, billing, incidents, rollout)
- Dashboard Client (services, backups, OAuth, GPU, billing)
- Dashboard Client — Server (SSH keys, Console KVM noVNC, Rescue)
- Dashboard Client — Domains (sous-domaines + custom)
- Dashboard Client — Privacy (DNS privé + Exit Node on/off)

### Phase 3 — Killer Features (Semaines 6-8)
- App de Review (PWA swipe)
- MCPs dans le Flash-Agent
- Skills Claude Code / CONTEXT.md
- Intégration GPU (SkyPilot + RunPod)
- Transfert résultats GPU → S3 → VPS

### Phase 4 — Intelligence (Semaines 9-10)
- Knowledge Engine (docs dans Qdrant)
- Pipeline de veille (RSS → LLM → embed → Qdrant)
- Obsidian vault intégré
- Bibliothèque + Solution Packs (5 packs initiaux)
- Forum Discourse (terrasse.paultaffe.com)

### Phase 5 — Marketplace & Scale (Semaines 11-12)
- Marketplace "L'Agence" (agence.paultaffe.com)
- API publique documentée (OpenAPI spec)
- Tests E2E complets (provisioning, dunning, offboarding)
- Master DR V2 (snapshots Hetzner 15min)
- SLA 99.5% validé

---

## 15. Repos et infra de développement

| Repo | Stack | Contenu |
|------|-------|---------|
| flash-agent | Go 1.22+ | Agent + MCPs + LUKS + Cosign + security relay |
| flash-master | Next.js + Prisma + PostgreSQL | API + Dashboards |
| flash-review | React + TypeScript | PWA de validation |
| flash-infra | Ansible + Docker + YAML | Playbooks, compose, skills, templates |

**Branching :** Trunk-based (main + feat/* + fix/*).
**CI/CD :** GitHub Actions (test + lint + build + release).
**Images :** Binaires signés Cosign en GitHub Releases, images Docker sur ghcr.io.
**Secrets :** SOPS + age.
**DNS :** `paultaffe.com/net/fr` via OVH DNS API (plugin `caddy-dns/ovh`).
**VPN :** NetBird self-hosted + Rosenpass (controller sur le Master, `vpn.paultaffe.net`).
**Développement :** Raspberry Pi 5 (Debian 13) + Claude Code CLI + OpenCode + Context7.
