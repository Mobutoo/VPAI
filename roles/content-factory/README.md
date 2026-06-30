# content-factory — Ansible role (variante Sese-AI, FRUGAL)

Co-localise **Content Factory v2 (M0)** sur **Sese-AI** (OVH VPS prod, 12 Go, déjà chargé)
en **réutilisant l'infra existante** au lieu d'une box dédiée :

- **Postgres prod** `javisi_postgresql` (PG 18.4) — pas de PG dédié
- **réseaux docker externes** `javisi_backend` (172.20.2.0/24) + `javisi_frontend` (172.20.1.0/24)
- **routing** via `javisi_caddy` (vhost ajouté au Caddyfile prod **hors de ce rôle**)
- **source** = sync du repo **local** `/home/mobuone/work/saas/content-factory` (le repo n'a pas de remote GitHub)

## Stack (3 services, ~1.4 Go)

| Service | Image / build | Rôle | mem_limit | Réseaux |
|---------|---------------|------|-----------|---------|
| `cf-temporal` | `{{ temporal_auto_setup_image }}` | Temporal + auto-setup : crée `temporal` + `temporal_visibility` + namespace `content-factory` **dans javisi_postgresql** | 512m | javisi_backend |
| `cf-api` | build `apps/api/Dockerfile` (ctx `apps/api`) | FastAPI `app.main:app` :8000, `/health` | 512m | javisi_backend + javisi_frontend |
| `cf-conductor` | build `services/conductor/Dockerfile` (ctx `services/`) | worker Temporal (importe le frère `plane-adapter`) | 384m | javisi_backend |

Pas de service `postgres`, pas de service `caddy`.

## Postgres prod réutilisé

- Superuser confirmé (SSH) : **`postgres`**, authentifié par le mot de passe **partagé** `{{ postgresql_password }}` (règle CLAUDE.md — jamais de variante par service).
- Le rôle provisionne `content_factory` (base domaine) si absente, applique `packages/domain/schema.sql` une seule fois (garde sentinelle, transaction unique).
- `temporal` / `temporal_visibility` sont créées par **auto-setup au démarrage** (ne pas pré-créer).
- **À SURVEILLER** : Temporal écrit ses 2 bases dans le **Postgres prod** partagé (charge + sauvegardes restic à étendre à `temporal`/`temporal_visibility`).

## Secrets vault à créer AVANT déploiement (gate humain)

À ajouter dans `inventory/group_vars/all/secrets.yml` (`ansible-vault edit`) :

| Variable vault | Requis | Défaut si absent | Rôle |
|----------------|--------|------------------|------|
| `vault_cf_plane_project_id` | **oui** | `e0cb95f0-0ea5-41b8-a3e3-aec45e8cc37e` | UUID projet Plane CF |
| `vault_plane_admin_api_token` | **oui** | `''` | header `X-Api-Key` adapter Plane |
| `vault_plane_base_url` | non | `https://work.<domain>` | base API Plane |
| `vault_plane_workspace_slug` | non | `ewutelo` | slug workspace Plane |

Déjà présents (réutilisés) : `vault_postgresql_password` (mot de passe PG **partagé**),
`vault_domain_name`.

## Prérequis

1. `javisi_postgresql`, `javisi_backend`, `javisi_frontend`, `javisi_caddy` actifs sur Sese (infra prod).
2. Repo local présent : `/home/mobuone/work/saas/content-factory` avec `apps/api/Dockerfile` + `services/conductor/Dockerfile` (présents).
3. **Vhost Caddy ajouté** au Caddyfile prod (cf. ci-dessous) — géré par l'orchestrateur, **pas** par ce rôle.
4. **Rôle non câblé dans `playbooks/`** : l'orchestrateur doit l'ajouter au play du groupe `prod` (le brief interdit de toucher `playbooks/`).

## Bloc vhost Caddy à AJOUTER (par l'orchestrateur, dans `roles/caddy/templates/Caddyfile.j2`)

VPN-only, réutilise les snippets existants `vpn_only` / `vpn_error_page` du Caddyfile prod
(CIDRs `100.64.0.0/10` Tailscale + `172.20.1.0/24` gateway docker frontend, DNS-01 OVH déjà
configuré dans le bloc global → pas de port 80). `cf-api` est joignable car il partage
`javisi_frontend` avec `javisi_caddy`.

```caddy
{{ cf_domain }} {
    import vpn_only
    import vpn_error_page
    reverse_proxy cf-api:8000
}
```

> Note : l'API expose ses routes à la **racine** (`/health`, `/brands`, `/productions/*`,
> `/events/stream`, `/compat/*`) — **pas** de préfixe `/api/*` → `reverse_proxy` catch-all.

## Déploiement (cible Sese = groupe `prod`)

```bash
source .venv/bin/activate
# Déploiement local via Tailscale (R7 : jamais l'IP publique 137.74.114.167)
ansible-playbook playbooks/stacks/site.yml -e "target_env=prod" -e "prod_ip=100.64.0.14" \
  --tags content-factory
# (ou via make une fois le rôle câblé dans le play prod)
```

## Écarts / pièges connus

- **Idempotence schema.sql** : `CREATE TYPE ... AS ENUM` n'accepte pas `IF NOT EXISTS`. Le rôle
  n'altère pas `schema.sql` (source de vérité) : il applique en **transaction unique**
  (`psql --single-transaction -v ON_ERROR_STOP=1`) sous **garde sentinelle** `to_regclass('public.brand')`.
  Échec → ROLLBACK total → sentinelle reste NULL → rejeu propre (jamais d'état partiel).
- **`synchronize`** écrit dans `{{ cf_src_dir }}` (propriété `prod_user`, sans `become`) ;
  les opérations docker/psql tournent en `become` (docker requiert sudo sur Sese).
- **Image Temporal dépréciée** : `temporalio/auto-setup:1.29.7` (builds migrés vers
  `temporalio/server`), conservée pour M0 (chemin standard compose). Combo Temporal 1.29 × PG18
  à confirmer au 1er run.
- **`cf-temporal` sans healthcheck** → `cf-conductor` utilise `depends_on: service_started`
  + `restart: unless-stopped` (retry connexion).
- **Secret PG** : passé via `environment: PGPASSWORD` (jamais dans la commande) + `no_log: true`.
