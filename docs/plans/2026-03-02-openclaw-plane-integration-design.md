# Design — Phase 2 : Integration OpenClaw ↔ Plane + Purge Kaneo

**Date** : 2026-03-02
**Auteur** : Claude Opus 4.6
**Statut** : Approuve

---

## Contexte

Phase 1 (terminee) a mis a jour OpenClaw vers v2026.3.1. Phase 2 remplace entierement Kaneo par Plane comme backend de gestion de projet pour les agents OpenClaw.

- **Workspace Plane** : Ewutelo (`work.ewutelo.cloud`, slug `ewutelo`)
- **Workspace Javisi** : NE PAS TOUCHER (application separee)
- **Palais** : reste accessible pour memory/insights/budget (hors boucle taches)

## Decisions architecturales

1. **Purge totale Kaneo** — role, workflows, variables, MCP, Makefile, GitHub Action
2. **Messenger allege** — proxy curl vers Plane REST + Palais REST (double acces)
3. **n8n pour workflows lourds** — plan-dispatch, github-autofix recrits pour Plane
4. **10 comptes agents Plane** dans workspace Ewutelo (Mobutoo=admin, 9 autres=membres)
5. **Endpoints `/work-items/`** (pas `/issues/` — deprecie 31 mars 2026)
6. **Telegram customCommands** persistants dans `openclaw.json`
7. **Pas de montee en version OpenClaw** — attendre la prochaine release

## Plane API Reference

- Base : `http://plane-api:8000/api/v1/`
- Auth : `X-API-Key: <token>` (header)
- Rate limit : 60 req/min par cle
- Endpoints cles :
  - `GET/POST /workspaces/{slug}/projects/`
  - `GET/POST .../projects/{id}/work-items/`
  - `PATCH .../work-items/{id}/`
  - `POST .../work-items/{id}/comments/`
  - `GET/POST .../projects/{id}/labels/`
  - `GET /workspaces/{slug}/members/`
- Champs creation work-item : `name` (requis), `description_html`, `state` (UUID), `assignees` (array UUID), `priority` (none|urgent|high|medium|low), `labels` (array UUID), `parent` (UUID), `start_date`, `target_date`

## Streams d'execution

### Stream A — Purge Kaneo

**Fichiers a supprimer :**
- `roles/kaneo/` (role complet)
- `.github/workflows/kaneo-build.yml`
- `roles/palais/files/app/scripts/migrate-kaneo.ts`
- `roles/n8n-provision/files/workflows/plan-dispatch.json` (archive)

**Fichiers a nettoyer (retirer blocs/lignes Kaneo) :**
- `inventory/group_vars/all/docker.yml` (L80-83)
- `inventory/group_vars/all/main.yml` (L218-219, L234)
- `inventory/group_vars/all/versions.yml` (L45-47)
- `roles/n8n/templates/n8n.env.j2` (L93-108)
- `roles/openclaw/templates/openclaw.env.j2` (L44-51)
- `roles/openclaw/defaults/main.yml` (L70-71, L160, L188, L191)
- `roles/openclaw/templates/HEARTBEAT.md.j2` (L42 — update mention)
- `roles/claude-code/defaults/main.yml` (L36-39)
- `roles/claude-code/templates/settings.json.j2` (L5)
- `roles/claude-code/templates/CLAUDE.md.j2` (L22, L33-34)
- `roles/claude-code/templates/mcp.json.j2` (L9-24)
- `roles/caddy/defaults/main.yml` (L13-14)
- `roles/caddy/templates/Caddyfile.j2` (L241)
- `roles/smoke-tests/templates/smoke-test.sh.j2` (L53-54, L170-173, L208-209, L228)
- `roles/vpn-dns/defaults/main.yml` (L81-83)
- `roles/postgresql/defaults/main.yml` (L23)
- `roles/docker-stack/templates/docker-compose.yml.j2` (L142-143)
- `roles/n8n-provision/tasks/main.yml` (L242)
- `playbooks/site.yml` (L81-82)
- `Makefile` (L252-254)

**IMPORTANT : NE PAS supprimer** `openclaw.json.j2` L17 (`hq.domain`) — c'est Palais.

### Stream B — Provisioning Plane (Ewutelo)

- Modifier `roles/plane-provision/defaults/main.yml` : `plane_workspace_slug: "ewutelo"`
- Reecrire `provision-plane.sh.j2` pour workspace Ewutelo :
  - Creer 10 users (email `<agent>@ewutelo.local`)
  - Mobutoo=admin, 9 autres=member
  - Generer API tokens par agent
  - Afficher tokens (vault manuelle apres)
- Ajouter `plane_admin_memory_limit`/`plane_admin_cpu_limit` dans defaults (manquants)

### Stream C — Messenger + customCommands Telegram

- Reecrire `roles/openclaw/templates/agents/messenger/IDENTITY.md.j2` :
  - Ajouter section Plane (en plus de Palais existante)
  - Auth par agent : `PLANE_TOKEN_<AGENT>` env vars
  - Commandes : create_project, list_projects, create_task, update_task, assign_task, add_comment, list_tasks
  - Endpoints `/work-items/` (pas `/issues/`)

- Ajouter dans `openclaw.json.j2` :
  ```json
  "customCommands": [
    { "command": "tasks", "description": "Lister mes taches en cours" },
    { "command": "status", "description": "Statut de la stack" },
    { "command": "budget", "description": "Budget IA 24h" },
    { "command": "approve", "description": "Approuver une idee en attente" },
    { "command": "reject", "description": "Refuser une idee en attente" },
    { "command": "projects", "description": "Lister les projets actifs" }
  ]
  ```

- Ajouter dans `openclaw.env.j2` : `PLANE_TOKEN_CONCIERGE`, `PLANE_TOKEN_BUILDER`, etc.

### Stream D — Skills (5 fichiers)

1. **project-management/SKILL.md.j2** — rewrite complet :
   - Remplacer Kaneo par Plane work-items API
   - Colonnes → etats Plane (state UUIDs)
   - Timer → commentaires horodates (Plane n'a pas de timer natif)
   - Labels : meme convention `agent:<id>` via Plane labels API
   - Deliverables : commentaires avec prefix `[DELIVERABLE]`

2. **idea-planning/SKILL.md.j2** — rewrite :
   - Plan JSON dans `description_html` du work-item
   - Delimiteurs `---IDEA-PLAN-V*---` dans description
   - Callbacks approve/reject via Telegram inline buttons
   - Dispatch cree un projet Plane (plus Kaneo)

3. **code-fix-github/SKILL.md.j2** — mise a jour :
   - Remplacer `POST http://kaneo-api:1337/api/tasks` par Plane work-items
   - Auth via `X-API-Key` au lieu de BetterAuth

4. **code-review/SKILL.md.j2** — mise a jour :
   - Sous-taches → work-items enfants (champ `parent`)
   - Labels via Plane labels API
   - Redis counter : `plane:corrections:<task_id>` (rename key)

5. **infra-maintain/SKILL.md.j2** — mise a jour :
   - Retirer `GET http://kaneo-api:1337/api/health` de la table

### Stream E — Agent Personas (8 fichiers)

Remplacer `## Protocole tache Kaneo` par `## Protocole tache Plane` dans :
- `main/IDENTITY.md.j2` — routing table
- `concierge/IDENTITY.md.j2` — routing table + etape structuration
- `builder/IDENTITY.md.j2` — protocole complet
- `maintainer/IDENTITY.md.j2` — healthcheck + protocole + sync
- `cfo/IDENTITY.md.j2` — tracking taches IA
- `explorer/IDENTITY.md.j2` — protocole
- `marketer/IDENTITY.md.j2` — protocole
- `writer/IDENTITY.md.j2` — protocole

Pattern commun : les agents appellent `sessions_spawn(messenger, "plane: <commande> agent=<self>")`.

### Stream F — n8n Workflows (3 fichiers)

1. **plan-dispatch.json.j2** — reecrire auth + endpoints pour Plane
2. **github-autofix.json** — remplacer les 20+ refs kaneo-api par Plane
3. **asset-register.json** — remplacer creation tache Kaneo par Plane work-item
4. **stack-health.json** — retirer healthcheck kaneo-api

## Rollback

Git revert du commit. Aucune donnee Plane n'est perdue (les agents n'ont pas encore de comptes).
