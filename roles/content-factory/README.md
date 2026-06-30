# content-factory — Ansible role

Deploys **Content Factory v2 (M0)** on **Hetzner app-prod (CX22, 2 vCPU / 4 GB)** via
Docker Compose, build-on-host. Calqué sur le rôle `story-engine`.

## Stack (5 services, ~2.5 GB)

| Service | Image | Rôle | mem_limit |
|---------|-------|------|-----------|
| `cf-postgres` | `{{ postgresql_image }}` (PG18) | 1 instance, 3 bases : `content_factory` (domaine) + `temporal` + `temporal_visibility` | 1g |
| `cf-temporal` | `{{ temporal_auto_setup_image }}` | serveur Temporal + auto-setup (crée les 2 bases + le namespace `content-factory`) | 512m |
| `cf-api` | build `apps/api/Dockerfile` (ctx `apps/api`) | FastAPI `app.main:app` :8000 | 512m |
| `cf-conductor` | build `services/conductor/Dockerfile` (ctx `services/`) | worker Temporal (import frère `plane-adapter`) | 384m |
| `cf-caddy` | `{{ caddy_image }}` | reverse proxy VPN-only `cf.<domain>`, TLS HTTP-01 | 128m |

Réseaux : `app_frontend` (external, app-scaffold) + `cf_backend` (bridge, **non** `internal`
car le conductor a besoin d'un egress vers Plane).

## Secrets vault à créer AVANT déploiement (gate humain)

À ajouter dans `inventory/group_vars/all/secrets.yml` (`ansible-vault edit`) :

| Variable vault | Requis | Défaut si absent | Rôle |
|----------------|--------|------------------|------|
| `vault_plane_admin_api_token` | **oui** | `''` | header `X-Api-Key` adapter Plane |
| `vault_cf_plane_project_id` | **oui** | `''` | UUID projet Plane CF |
| `vault_plane_base_url` | non | `https://work.<domain>` | base API Plane |
| `vault_plane_workspace_slug` | non | `ewutelo` | slug workspace Plane |

Déjà présents (réutilisés, pas à créer) : `vault_postgresql_password` (mot de passe PG
**partagé**), `vault_ghcr_pull_token` (clone repo privé), `vault_domain_name`,
`vault_notification_email`.

## Prérequis déploiement

1. **DNS public** : enregistrement A `cf.<domain>` → IP publique app-prod (requis pour TLS HTTP-01).
2. **Repo poussé** : `github.com/Mobutoo/content-factory` accessible via `ghcr_pull_token`.
3. **`apps/api/Dockerfile`** présent dans le repo (écrit côté repo source — voir « Écarts »).
4. Réseau `app_frontend` créé (rôle `app-scaffold`, phase1).

## Déploiement

```bash
source .venv/bin/activate
ansible-playbook playbooks/hosts/app-prod.yml -e "target_env=app_prod" --tags content-factory
```

## Écarts / pièges connus

- **Contrat de routing** : l'API expose ses routes à la **racine** (`/health`, `/brands`,
  `/productions/*`, `/events/stream`) + `/compat/*`. Il n'y a **pas** de préfixe `/api/*`
  (hypothèse du brief invalidée par `apps/api/app/main.py`). → Caddy fait un **catch-all**
  vers `cf-api:8000`.
- **`apps/api/Dockerfile` absent** au moment de l'écriture du rôle (seul
  `services/conductor/Dockerfile` existe). Le build `cf-api` échouera tant que ce
  Dockerfile n'est pas committé dans le repo source.
- **Image Temporal dépréciée** : `temporalio/auto-setup` est marqué deprecated (builds
  migrés vers `temporalio/server`). Conservé pour M0 (auto-setup = chemin standard
  compose). Combo Temporal 1.29 × PG18 à confirmer au déploiement.
- **`cf-temporal` sans healthcheck** (auto-setup n'en fournit pas) → `cf-conductor` utilise
  `depends_on: condition: service_started` + `restart: unless-stopped` (retry connexion).
