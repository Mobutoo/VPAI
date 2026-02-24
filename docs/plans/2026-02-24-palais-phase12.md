# Palais Phase 12 — Integration n8n + OpenClaw

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Adapter les workflows n8n existants pour utiliser l'API Palais (remplacer Kaneo), creer les nouveaux workflows (standup, insight-alert), adapter le skill OpenClaw `palais-bridge` et l'identite Messenger.

**Architecture:** Les workflows n8n appellent l'API REST Palais via `X-API-Key`. Le skill `palais-bridge` utilise MCP JSON-RPC (ou HTTP fallback). Le Messenger (Concierge) route les commandes Telegram vers Palais.

**Tech Stack:** n8n webhooks, OpenClaw skills, Ansible templates Jinja2

**PRD Reference:** `docs/PRD-PALAIS.md` — Phase 12 (Integration n8n + OpenClaw)

---

## Task 1: Adapter workflow `code-review`

**Files:**
- Modify: `roles/n8n-provision/files/workflows/code-review.json`

Remplacer les appels Kaneo API par Palais API :
- `POST http://kaneo-api:1337/...` → `POST http://palais:3300/api/v1/tasks/:id/comments`
- Header: `X-API-Key: {{ vault_palais_api_key }}`
- Quand code-review termine : POST commentaire sur la tache avec le resultat
- Mettre a jour le statut tache si review OK (`PUT /api/v1/tasks/:id` → status `review`)

Commit: `fix(n8n): adapt code-review workflow to Palais API`

## Task 2: Adapter workflow `error-to-task`

**Files:**
- Modify: `roles/n8n-provision/files/workflows/error-to-task.json`

Remplacer la creation de tache Kaneo par :
1. `POST http://palais:3300/api/v1/projects/:id/tasks` — creer tache avec label `error`, priority `high`
2. `POST http://palais:3300/api/v1/memory/nodes` — creer noeud episodique Knowledge Graph avec l'erreur
3. Header: `X-API-Key` sur les deux appels

Commit: `fix(n8n): adapt error-to-task workflow to Palais API + Knowledge Graph`

## Task 3: Adapter workflow `project-status`

**Files:**
- Modify: `roles/n8n-provision/files/workflows/project-status.json`

Remplacer les appels Kaneo par :
- `GET http://palais:3300/api/v1/projects` — liste projets
- `GET http://palais:3300/api/v1/projects/:id/tasks` — taches par projet
- `GET http://palais:3300/api/v1/budget/summary` — budget du jour
- Formater le message Telegram avec les nouvelles donnees

Commit: `fix(n8n): adapt project-status workflow to Palais API`

## Task 4: Supprimer workflows Kaneo obsoletes

**Files:**
- Delete: `roles/n8n-provision/files/workflows/kaneo-agents-sync.json`
- Delete: `roles/n8n-provision/files/workflows/kaneo-sync.json`

Ces workflows synchronisaient Kaneo avec les agents OpenClaw. Plus necessaires car Palais gere nativement les agents.

Commit: `chore(n8n): remove obsolete kaneo-sync workflows`

## Task 5: Creer workflow `palais-standup`

**Files:**
- Create: `roles/n8n-provision/files/workflows/palais-standup.json`

Workflow cron :
1. Trigger: cron `0 8 * * *` (8h chaque matin, configurable)
2. HTTP Request: `GET http://palais:3300/api/v1/standup/latest` avec `X-API-Key`
3. Formatter le briefing pour Telegram (markdown)
4. Envoyer sur Telegram via bot API

Format message :
```
🏛️ *Briefing Matinal — Palais*

*Completees hier:*
{{ tasks_completed }}

*En cours:*
{{ tasks_in_progress }}

*Budget:* ${{ spent_yesterday }} hier | ${{ remaining_today }} restant

*Alertes:*
{{ insights }}
```

Commit: `feat(n8n): palais-standup workflow (daily briefing → Telegram)`

## Task 6: Creer workflow `palais-insight-alert`

**Files:**
- Create: `roles/n8n-provision/files/workflows/palais-insight-alert.json`

Workflow webhook :
1. Trigger: webhook `POST /webhook/palais-insight-alert`
2. Palais appelle ce webhook quand un insight `critical` est cree
3. Payload attendu: `{ type, severity, title, description, suggested_actions, entity_type, entity_id }`
4. Formatter alerte pour Telegram
5. Envoyer sur Telegram

Format message :
```
⚠️ *Alerte Palais — {{ severity }}*

*{{ title }}*
{{ description }}

*Actions suggerees:*
{{ suggested_actions }}
```

Commit: `feat(n8n): palais-insight-alert workflow (critical insights → Telegram)`

## Task 7: Creer skill OpenClaw `palais-bridge`

**Files:**
- Create: `roles/openclaw/templates/skills/palais-bridge/SKILL.md.j2`

Remplace `kaneo-bridge`. Contenu du SKILL.md :

```markdown
# palais-bridge

Skill pour interagir avec Palais — le hub de gestion de projet et orchestration IA.

## Connexion
- **URL**: `http://palais:3300`
- **Auth**: Header `X-API-Key: {{ vault_palais_api_key }}`

## Endpoints disponibles

### Taches
- `GET /api/v1/projects` — Liste les projets
- `GET /api/v1/projects/:id/tasks` — Taches d'un projet
- `POST /api/v1/projects/:id/tasks` — Creer une tache
- `PUT /api/v1/tasks/:id` — Modifier une tache (status, assignee, description)
- `POST /api/v1/tasks/:id/comments` — Ajouter un commentaire

### Budget
- `GET /api/v1/budget/summary` — Budget du jour (spent, remaining)
- `GET /api/v1/budget/by-agent` — Depenses par agent

### Memoire
- `POST /api/v1/memory/search` — Recherche semantique (body: { query })
- `POST /api/v1/memory/nodes` — Stocker un souvenir

### Agents
- `GET /api/v1/agents` — Liste des agents avec statut

## Exemples d'utilisation

### Creer une tache
```bash
curl -X POST http://palais:3300/api/v1/projects/1/tasks \
  -H "X-API-Key: {{ vault_palais_api_key }}" \
  -H "Content-Type: application/json" \
  -d '{"title": "...", "assignee_agent_id": "...", "priority": "high"}'
```

### Rechercher dans la memoire
```bash
curl -X POST http://palais:3300/api/v1/memory/search \
  -H "X-API-Key: {{ vault_palais_api_key }}" \
  -H "Content-Type: application/json" \
  -d '{"query": "Caddy 403 error resolution"}'
```
```

Commit: `feat(openclaw): palais-bridge skill replacing kaneo-bridge`

## Task 8: Supprimer ancien skill `kaneo-bridge`

**Files:**
- Delete: `roles/openclaw/templates/skills/kaneo-bridge/`

Supprimer le repertoire complet du skill kaneo-bridge.

Commit: `chore(openclaw): remove obsolete kaneo-bridge skill`

## Task 9: Adapter IDENTITY.md du Messenger

**Files:**
- Modify: `roles/openclaw/templates/agents/messenger/IDENTITY.md.j2`

Remplacer toutes les references Kaneo par Palais :
- URL API : `http://kaneo-api:1337` → `http://palais:3300`
- Auth : cookie BetterAuth → `X-API-Key: {{ vault_palais_api_key }}`
- Endpoints : adapter les chemins API
- Ajouter les nouvelles capacites : recherche memoire, budget check, insights

Le Messenger doit pouvoir :
1. Creer/modifier des taches via Palais API
2. Consulter le budget (`/budget`)
3. Rechercher dans la memoire (`/memory <query>`)
4. Lister les insights actifs (`/insights`)

Commit: `fix(openclaw): update Messenger IDENTITY.md for Palais API`

## Task 10: Test E2E Telegram → Palais

Test manuel de bout en bout :
1. Envoyer "cree un projet test-e2e" sur Telegram
2. Verifier : Concierge interprete → appelle palais-bridge → POST /projects
3. Verifier : projet visible dans le dashboard Palais
4. Envoyer "ajoute une tache 'hello world' au projet test-e2e"
5. Verifier : tache creee avec le bon projet

Commit: `test(e2e): Telegram → Concierge → Palais round-trip verified`

---

## Verification Checklist

- [ ] Workflow `code-review` utilise Palais API
- [ ] Workflow `error-to-task` cree tache Palais + noeud memoire
- [ ] Workflow `project-status` lit depuis Palais API
- [ ] Workflows `kaneo-sync` supprimes
- [ ] Workflow `palais-standup` envoie briefing matinal sur Telegram
- [ ] Workflow `palais-insight-alert` envoie alertes critiques sur Telegram
- [ ] Skill `palais-bridge` deploye et fonctionnel
- [ ] Skill `kaneo-bridge` supprime
- [ ] IDENTITY.md Messenger adapte pour Palais
- [ ] Test E2E : Telegram → Concierge → Palais → tache visible
