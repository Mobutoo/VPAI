# Plane — Operational Intelligence pour Agents IA

## What This Is

Une intégration de **Plane** (plateforme open-source de gestion de projet) comme hub opérationnel central pour la stack IA VPAI. Plane devient le cerveau visible de l'orchestration : les agents OpenClaw y détectent leurs tâches, y mettent à jour leur progression, et l'humain (via Concierge sur Telegram) y pilote projets et sprints. Remplace l'anti-pattern Kaneo + simplification majeure de l'architecture.

Déployé sur `work.ewutelo.cloud` (Sese-AI), intégré dans l'écosystème Ansible/Docker existant avec PostgreSQL et Redis partagés.

## Core Value

**Le Concierge crée et orchestre les projets via Telegram → Plane, et les agents OpenClaw exécutent et synchronisent automatiquement leur progression.** Synchronisation bidirectionnelle : Plane détecte les nouvelles tâches, agents mettent à jour statuts/temps/livrables, notifications temps-réel vers Telegram.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Plane déployé sur `work.ewutelo.cloud` via Docker Compose (Sese-AI)
- [ ] PostgreSQL partagé (DB `plane_production`, utilisateur `plane`, schéma isolé)
- [ ] Redis partagé (namespace `plane:*` pour éviter collisions)
- [ ] Concierge = compte admin Plane (créé au provisioning)
- [ ] Auth hybride : Email/password humain + API tokens agents
- [ ] OpenClaw agents : détection bidirectionnelle tâches (polling API Plane)
- [ ] Agents mettent à jour : statut, progression, temps passé, commentaires
- [ ] Caddy reverse proxy : `work.ewutelo.cloud` → VPN-only (ACL standard)
- [ ] Webhooks publics : endpoint `/webhooks/*` accessible sans VPN (pour n8n)
- [ ] Notifications Telegram : via n8n (events Plane → webhook → Telegram)
- [ ] Backup Zerobyte : DB Plane incluse dans dump PostgreSQL quotidien
- [ ] Healthcheck Plane : endpoint `/api/health` (monitored via stack monitoring)
- [ ] Provisioning initial : workspace, premier projet, API tokens agents
- [ ] Documentation : guide OpenClaw skill `plane-bridge` (remplace `kaneo-bridge`)

### Out of Scope

- **Palais custom build** — Plane **devient** l'operational intelligence, pas un interim
- **SSO/OAuth** — Email/password suffit (VPN-only, solo user)
- **Mobile app Plane** — Web-only pour v1
- **Multi-tenancy** — Un seul workspace (javisi)
- **Custom Plane plugins** — Utiliser API REST standard uniquement
- **PostgreSQL dédié** — Instance partagée obligatoire (contrainte infra)
- **Real-time WebSocket UI** — Polling API suffit pour agents, SSE pour humain OK
- **Plane self-hosted complex features** — Activer uniquement modules essentiels (issues, projects, cycles, modules)

## Context

**Écosystème existant VPAI :**
- Serveur **Sese-AI** (OVH VPS 8GB, production) déjà déployé avec 20+ services Docker
- **OpenClaw** : 10 agents IA (Concierge, Imhotep, Thot, Basquiat, R2D2, Shuri, Piccolo, etc.)
- **Concierge** : agent orchestrateur, interface Telegram avec l'humain
- **PostgreSQL 18.1** : instance partagée (n8n, litellm, nocodb, openclaw déjà présents)
- **Redis 8.0** : instance partagée (cache + queues)
- **n8n** : orchestration workflows (notifications, automatisations)
- **Caddy** : reverse proxy avec ACL VPN (Headscale mesh)
- **Zerobyte** : backup quotidien PostgreSQL → serveur VPN distant
- **Monitoring stack** : Grafana + VictoriaMetrics + Loki

**Problème Kaneo actuel (REX) :**
- 6 points de défaillance par requête (agent → Messenger → Kaneo API → BetterAuth → Redis → DB)
- Auth cookie fragile (TTL 40min, regeneration aléatoire)
- Pas de temps-réel (polling manuel)
- API limitée (pas de budget, pas de mémoire, pas de confiance)
- Outil PM humain détourné pour backend IA

**PRD Palais comme référence :**
Le document `docs/PRD-PALAIS.md` décrit les workflows idéaux (agent cockpit, knowledge graph, mission launcher, budget tracking). Ces fonctionnalités seront **implémentées via l'API Plane** plutôt que via une plateforme custom :
- Task management IA-natif → Issues Plane + custom fields (cost_estimate, confidence_score, agent_id)
- Observabilité → Commentaires automatiques des agents sur progression
- Knowledge Graph → Peut être ajouté plus tard (Qdrant séparé) ou rester dans TROUBLESHOOTING.md
- Budget tracking → Custom fields Plane ou tableau n8n séparé
- Mission Launcher → Workflow Concierge via Telegram → création projet/tâches Plane

**Flux typique attendu :**
1. Humain discute avec Concierge via Telegram : "Je veux ajouter feature X"
2. Concierge analyse, pose questions, confirme scope
3. Concierge crée projet Plane + issues + assigne agents OpenClaw
4. Agents OpenClaw (polling API Plane toutes les 5min) détectent nouvelles tâches
5. Agents exécutent, commentent progression dans Plane
6. Plane webhook → n8n → Telegram (notifications à l'humain)
7. Humain consulte Plane UI ou demande status via Telegram
8. Projet complété → Concierge résume via Telegram

## Constraints

- **Tech stack** : Docker Compose uniquement (pattern VPAI), pas de Kubernetes
- **PostgreSQL** : Instance partagée obligatoire (pas de DB dédiée), schéma isolé `plane.*`
- **Redis** : Instance partagée, namespace `plane:*` pour éviter conflits
- **Serveur** : Sese-AI uniquement (pas de multi-node)
- **Réseau** : VPN-only via Caddy (sauf webhooks publics `/webhooks/*`)
- **Backup** : Intégré dans Zerobyte existant (dump PostgreSQL quotidien)
- **Versions** : Images Docker pinnées dans `inventory/group_vars/all/versions.yml`
- **Limites ressources** : Max 512MB RAM, 0.5 CPU (contrainte VPS 8GB partagé)
- **Healthcheck** : Obligatoire pour monitoring stack (Grafana alerting)
- **Logs** : Rotation 10MB/3 fichiers (daemon.json Docker)
- **Timeline** : Déploiement v1 sous 2 semaines (constraint budget IA, besoin opérationnel urgent)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| **Plane au lieu de Palais custom** | Mature, API riche, communauté active, pas besoin de réécrire tout de zéro. PRD Palais = cahier des charges, implémentation via Plane API. | — Pending (validation post-déploiement) |
| **PostgreSQL partagé** | Simplification infra, backup unifié, pas de surcharge mémoire VPS 8GB. Isolation via schéma `plane.*`. | — Pending |
| **Redis partagé + namespace** | Plane nécessite Redis pour queues. Partager l'instance existante avec namespace évite second container. | — Pending |
| **Auth hybride (email + API tokens)** | Humain = email/password Plane natif. Agents = API tokens (pas de cookies fragiles comme Kaneo). | — Pending |
| **Bidirectional sync agents** | Agents détectent ET mettent à jour (vs push-only). Nécessaire pour workflows complexes (sprints, dépendances). | — Pending |
| **VPN-only + webhooks publics** | UI Plane = VPN sécurisé. Webhooks `/webhooks/*` publics pour n8n (authentifiés par secret). Pattern standard VPAI. | — Pending |
| **Concierge = orchestrateur** | Un seul agent responsable création projets/tâches. Évite chaos multi-agents créant tasks en parallèle. | — Pending |
| **Zerobyte backup** | Données critiques (projets, tasks, progression agents). Dump PostgreSQL quotidien suffit. | — Pending |

---
*Last updated: 2026-02-28 after initialization*
