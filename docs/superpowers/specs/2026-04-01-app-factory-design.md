# App Factory — Design Spec

> Workflow automatise pour coder, deployer et documenter des applications de A a Z.

**Date:** 2026-04-01
**Status:** Approved
**Approach:** Hybrid Command — GSD pilote, n8n automatise la glue

---

## 1. Vue d'ensemble

App Factory est un workflow repeatable qui transforme un PRD en application deployee sur Hetzner, avec documentation complete dans Plane (projet), NocoDB (metriques/decisions) et Qdrant (REX/patterns).

### Principes

- **GSD reste le driver** — phases, plans, execution, verification
- **n8n automatise le repetitif** — CI/CD, sync Plane, logs NocoDB, indexation Qdrant
- **Plane est la source de verite** pour l'etat projet
- **3 gates humaines** : design, deploy prod, rollback
- **Le reste est autonome** : scaffolding, code, tests, CI, docs

### Lifecycle

```
INTAKE → DESIGN (gate) → BUILD → CI → SHIP (gate) → OPERATE (gate si rollback) → LEARN
```

7 etapes, 3 gates humaines (design, deploy, rollback conditionnel).

| Etape | Acteur | Action | Outputs |
|-------|--------|--------|---------|
| Intake | Claude | Parse PRD, cree projet Plane + NocoDB + repo GitHub | Plane project, NocoDB row, GitHub repo |
| Design | Claude + Humain | Brainstorm, spec, plan | `docs/specs/*.md`, Plane work items |
| Build | Claude (GSD) | Code par phases, tests, lint | Code, commits lies aux Plane work items |
| CI | GitHub Actions | Build image, push GHCR | Image Docker tagguee |
| Ship | n8n | Webhook CI, Ansible deploy, smoke tests | App live sur Hetzner |
| Operate | n8n + Grafana | Health checks, alertes | Dashboards |
| Learn | n8n + Claude | REX extraits, patterns indexes | Qdrant vectors, NocoDB metriques |

---

## 2. Architecture Repo & Infra

### Deux repos par projet

**Repo app** (`github-seko:Mobutoo/<app>`) :

```
<app>/
├── src/                    # Code applicatif
├── tests/                  # Tests (unit + integration)
├── Dockerfile              # Multi-stage build
├── docker-compose.dev.yml  # Dev local
├── .github/
│   └── workflows/
│       └── ci.yml          # Lint → Test → Build → Push GHCR
├── docs/
│   └── specs/              # Specs de design
├── CLAUDE.md               # Conventions pour Claude Code
├── .env.example            # Variables documentees
└── README.md
```

**Role Ansible dans VPAI** (`roles/<app>/`) :

```
roles/<app>/
├── defaults/main.yml       # Variables overridable (ports, domaine, limites)
├── tasks/main.yml          # Create dirs, deploy templates, pull image, compose up
├── handlers/main.yml       # Restart stack handler
└── templates/
    ├── docker-compose.yml.j2   # Image pinnee depuis versions.yml
    ├── <app>.env.j2            # Secrets du vault
    └── Caddyfile.j2            # Reverse proxy (VPN-only ou public)
```

### Images Docker

- Registry : GHCR (`ghcr.io/mobutoo/<app>`)
- Tag : git SHA complet (`ghcr.io/mobutoo/<app>:a1b2c3d4e5f6...`) — `${{ github.sha }}` en CI
- Pin dans `inventory/group_vars/all/versions.yml`
- Jamais `:latest`

### Authentification GHCR sur Hetzner

Les repos GHCR sont prives. Pour que Hetzner puisse pull les images :

1. **Prerequis** : generer un GitHub PAT (scope `read:packages`) depuis le compte Mobutoo, puis ajouter au vault : `ansible-vault edit inventory/group_vars/all/secrets.yml` → `vault_ghcr_pull_token: "ghp_..."`
2. Le role `app-scaffold` deploie `/root/.docker/config.json` avec les credentials GHCR :
   ```json
   { "auths": { "ghcr.io": { "auth": "<base64(username:token)>" } } }
   ```
3. `docker compose pull` utilise automatiquement ce fichier
4. Le token est scope `read:packages` uniquement — pas de write depuis la VM

### Decision Hetzner (partage vs dedie)

Flag `app_dedicated_vm: false` dans le role defaults :

| Mode | Quand | Infra |
|------|-------|-------|
| Partage (defaut) | Apps legeres, internes | `app-prod` existant, Caddy mutualise |
| Dedie | Perf, isolation, client externe | `provision-hetzner.yml` cree une VM CX22, stack isolee |

Quand `app_dedicated_vm: true` :
- `provision-hetzner.yml` cree une VM CX22 dediee
- Un playbook `playbooks/app-<name>.yml` est cree
- Le role deploie Docker + Caddy + app

### Playbook `app-prod.yml`

```yaml
# playbooks/app-prod.yml
- hosts: "{{ target_env | default('app_prod') }}"
  roles:
    - role: common
      tags: [common, phase1]
    - role: docker
      tags: [docker, phase1]
    - role: app-scaffold
      tags: [app-scaffold, phase1]
    # Per-app roles included dynamically via --tags
```

Chaque role d'app est ajoute a ce playbook quand il est cree. `--tags <app>` cible uniquement ce role.

### Limites ressources par defaut

Chaque app container sur Hetzner CX22 (4GB RAM, 2 vCPU) utilise ces limites par defaut dans `defaults/main.yml` :

```yaml
app_memory_limit: "512M"
app_cpu_limit: "0.5"
```

Overridable par app. Le `docker-compose.yml.j2` template les applique via `deploy.resources.limits`.

### Reseaux Docker Hetzner

Le serveur `app-prod` utilise 2 reseaux :
- `frontend` : Caddy + apps avec routes publiques
- `backend` (internal) : apps + leurs bases de donnees

### GitHub Secrets requis pour `deploy-app.yml`

| Secret | Description |
|--------|-------------|
| `APP_PROD_SSH_KEY` | Cle privee SSH pour le serveur Hetzner |
| `APP_PROD_SERVER_IP` | IP Tailscale du serveur Hetzner (VPN-only SSH) |
| `ANSIBLE_VAULT_PASSWORD` | Password Ansible Vault (meme secret que les autres workflows) |

---

## 3. Workflows n8n

5 nouveaux workflows dans la base `app-factory`.

**Authentification webhooks** : tous les webhooks n8n exigent un header `X-AF-Secret: {{ vault_af_webhook_secret }}`. Le secret est stocke dans Ansible Vault et injecte dans les appels Claude via variable d'environnement. Les webhooks n8n valident ce header dans un noeud `IF` avant tout traitement. n8n est derriere Caddy VPN-only, donc seuls les peers Tailscale peuvent y acceder.

### 3.1 `af-intake` — Bootstrap projet

**Trigger:** webhook manuel (appele par Claude)

**Input:**
```json
{
  "project_name": "MonApp",
  "repo_name": "mon-app",
  "stack": "next.js + postgresql",
  "prd_summary": "...",
  "plane_module_dates": { "start": "2026-04-01", "end": "2026-04-15" }
}
```

**Actions:**
1. GitHub API : create repo `Mobutoo/<repo_name>` (private)
2. Push scaffold : CLAUDE.md, Dockerfile, ci.yml
3. Plane API : create project + 1er module + work items depuis PRD
4. NocoDB API : insert row dans `projects`

**Output:** `{ repo_url, plane_project_id, nocodb_project_id }`

### 3.2 `af-ci-hook` — Chaque push GitHub

**Trigger:** webhook GitHub (push + check_suite events)

**Actions:**
1. Parse commit messages pour `[PLANE-xxx]` references
2. Plane API : update work item status → "In Progress"
3. NocoDB API : insert row dans `commits`
4. Si CI success : Plane label "build-ok"
5. Si CI failure : Plane label "ci-fail" + comment error summary

### 3.3 `af-deploy` — Deploiement orchestre

**Trigger:** GitHub Actions `workflow_dispatch` (appele par Claude apres gate humaine)

Le deploiement tourne dans GitHub Actions (runner ubuntu-latest), pas via n8n SSH. Cela garantit :
- Acces natif au repo VPAI (git push versions.yml)
- Secrets GitHub (SSH key, vault password) deja configures
- Logs de deploy auditable dans GitHub

**Input (workflow_dispatch):**
```json
{
  "repo": "mon-app",
  "image_tag": "a1b2c3d4e5f6...",
  "target_env": "app_prod",
  "plane_project_id": "..."
}
```

**Actions:**
1. GitHub Actions : checkout VPAI, update `versions.yml` (pin new image tag), commit + push
2. GitHub Actions : `ansible-playbook playbooks/app-prod.yml --tags <app> -e target_env=app_prod`
3. GitHub Actions : smoke tests (healthcheck HTTP + container status via SSH)
4. GitHub Actions appelle un webhook n8n (endpoint integre dans `af-ci-hook`, event `deploy_complete`) : NocoDB insert row dans `deployments`
5. Si smoke OK : Plane work items → label "Deployed", fermer cycle
6. Si smoke FAIL : Plane work item label "deploy-fail", Telegram alerte

### 3.3b Rollback

Si smoke fail ou probleme en prod :

1. L'utilisateur confirme "rollback" (gate humaine)
2. Claude revert `versions.yml` au tag precedent (git revert ou edit direct)
3. Re-trigger `af-deploy` avec l'ancien `image_tag`
4. Si l'ancien tag n'est plus dans GHCR → l'utilisateur decide "fix forward"
5. NocoDB : insert row `deployments` avec `smoke_result: "rollback"`

### 3.4 `af-phase-complete` — Fin de phase GSD

**Trigger:** webhook (appele par Claude a chaque fin de phase)

**Input:**
```json
{
  "project_name": "MonApp",
  "phase_number": 2,
  "phase_name": "API Layer",
  "summary": "...",
  "duration_min": 12,
  "files_changed": 8,
  "decisions": [
    { "context": "...", "options": ["A", "B"], "choice": "A", "reason": "..." }
  ]
}
```

**Actions:**
1. Plane API : mark phase work items as Complete
2. NocoDB : insert `phase_logs` row
3. NocoDB : insert `decisions` rows (1 par decision technique)
4. Trigger `af-rex-indexer`

### 3.5 `af-rex-indexer` — Memoire longue Qdrant

**Trigger:** appele par `af-phase-complete` ou manuellement

**Actions:**
1. LiteLLM : embed summary → vector 1536d (model_name `embedding` via proxy, routed par LiteLLM pour budget/fallback)
2. Qdrant : upsert dans `app-factory-rex`
   - payload: `{ project, phase, type: "rex", text, timestamp }`
3. Pour chaque pattern detecte :
   - LiteLLM : embed pattern
   - Qdrant : upsert dans `app-factory-patterns`
   - payload: `{ project, stack, context, code_snippet, timestamp }`
4. NocoDB : update `projects` row avec metrics agregees

---

## 4. Data Model

### NocoDB — Base `app-factory`

| Table | Colonnes cles | Alimentee par |
|-------|--------------|---------------|
| `projects` | name, repo, stack, plane_id, status, started_at, phases_completed, total_duration, total_commits, last_rex_at | af-intake, af-phase-complete |
| `commits` | hash, repo, message, plane_work_item, files_changed, timestamp | af-ci-hook |
| `phase_logs` | project, phase, phase_name, duration_min, files_count, decisions_count, timestamp | af-phase-complete |
| `decisions` | project, phase, context, options, choice, reason, timestamp | af-phase-complete |
| `deployments` | repo, version, env, duration_sec, smoke_result, ansible_rc, timestamp | af-deploy |
| `error_logs` | workflow, error_message, error_node, project, timestamp, resolved_at | Error Trigger (tous workflows) |

### Qdrant — Collections

| Collection | Dims | Distance | Contenu |
|------------|------|----------|---------|
| `app-factory-rex` | 1536 | Cosine | REX par phase (pieges, solutions, lecons) |
| `app-factory-patterns` | 1536 | Cosine | Patterns de code reutilisables (snippets, archi, conventions) |

### Plane — Structure par projet

```
Projet "<app>"
  └── Module "Phase N: <nom>"
       ├── Work Item: "feat: <description>" [Backlog → In Progress → Complete]
       ├── Work Item: "feat: <description>"
       └── ...
```

**Etats** : utilise les etats Plane par defaut (`Backlog`, `In Progress`, `Complete`).
Le label `deployed` est ajoute aux work items deployes (pas un etat custom).
Le label `build-ok` indique que le CI est vert.
Le label `ci-fail` indique un echec CI.
Le label `deploy-fail` indique un echec de deploiement.

---

## 5. Protocole de commit & tracabilite

### Convention

```
<type>(<scope>): <description> [PLANE-<id>]
```

- `PLANE-<id>` = 8 premiers chars de l'UUID du work item Plane
- `af-ci-hook` parse ce pattern sur chaque push

### Types

| Type | Usage | Plane transition |
|------|-------|-----------------|
| `feat` | Nouvelle fonctionnalite | Work item → "In Progress" |
| `fix` | Bug fix | Work item → "In Progress" |
| `test` | Ajout/modif tests | Aucune |
| `chore` | CI, deps, config | Aucune |
| `docs` | Documentation | Aucune |
| `deploy` | Version pinnee dans VPAI | Work item → label "deployed" |

### Flux d'un work item

```
Backlog → (1er commit [PLANE-xxx]) → In Progress → (CI green) → label "build-ok"
        → (phase GSD done) → Complete → (deploy confirme) → label "deployed"
```

---

## 6. Protocole operationnel

### Gates humaines

| Gate | Moment | Action utilisateur | Timeout |
|------|--------|-------------------|---------|
| Design | Apres brainstorm + spec | "go" ou feedback | Aucun — Claude attend |
| Deploy | Code termine, CI vert | "deploy" ou "attends" | Aucun — Claude attend |
| Rollback | Si smoke fail en prod | "rollback" ou "fix forward" | Alerte Telegram |

### Sequence complete

**Intake:**
1. Utilisateur fournit PRD (contenu ou chemin fichier)
2. Claude parse, appelle `af-intake`, scaffold le repo
3. Claude lance le brainstorm

**Design (gate):**
4. Questions une par une → spec
5. Propose 2-3 approches → recommandation
6. Presente le design → utilisateur valide
7. Ecrit spec dans repo, cree plan GSD, cree work items Plane
8. Utilisateur dit "go"

**Build (autonome):**
9. Pour chaque phase GSD :
   - Execute les plans (code, tests, lint)
   - Commits avec `[PLANE-xxx]`
   - Push → CI tourne → `af-ci-hook` sync Plane/NocoDB
   - Phase terminee → `af-phase-complete` sync + REX
10. Si bloque : consulte Qdrant (REX similaires), sinon notifie l'utilisateur

**Ship (gate):**
11. Claude presente le resume (phases OK, CI vert, image buildee, target)
12. Utilisateur confirme "deploy"
13. Claude commit dans VPAI (pin image + role), appelle `af-deploy`
14. GitHub Actions : Ansible → Hetzner → smoke tests → webhook n8n → NocoDB/Plane MAJ
15. Si smoke fail → Telegram alerte, utilisateur decide

**Learn (automatique):**
16. `af-rex-indexer` : REX finaux + patterns indexes dans Qdrant
17. NocoDB : metriques finales
18. Plane : projet marque "Complete"

### Commande de lancement

```
"Nouveau projet. PRD: [contenu ou chemin]"
```

---

## 7. CI/CD Pipeline — Repo app

### `.github/workflows/ci.yml`

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup
        # Stack-specific (Node, Python, Go, etc.)
      - name: Lint
      - name: Test

  build-push:
    needs: lint-test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Login GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build & Push
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/mobutoo/${{ github.event.repository.name }}:${{ github.sha }}
      - name: Notify n8n
        run: |
          curl -sf -X POST "${{ secrets.N8N_DEPLOY_WEBHOOK }}" \
            -H "Content-Type: application/json" \
            -H "X-AF-Secret: ${{ secrets.AF_WEBHOOK_SECRET }}" \
            -d '{"repo":"${{ github.event.repository.name }}","image_tag":"${{ github.sha }}","event":"image_pushed"}'
```

Le webhook `N8N_DEPLOY_WEBHOOK` notifie n8n qu'une image est prete. Le deploy attend la gate humaine — n8n ne deploie pas automatiquement sur push.

---

## 8. Gestion d'erreurs

Chaque workflow n8n a un noeud `Error Trigger` qui :
1. Log l'erreur dans NocoDB (`error_logs` table, ajoutee a la base `app-factory`)
2. Envoie une alerte Telegram avec : workflow name, error message, timestamp
3. Set le label Plane correspondant (`ci-fail`, `deploy-fail`)

| Workflow | Erreur typique | Action |
|----------|---------------|--------|
| `af-intake` | GitHub API rate limit, Plane API down | Retry 3x (backoff 30s), puis Telegram alerte |
| `af-ci-hook` | Commit sans `[PLANE-xxx]`, Plane work item introuvable | Log warning, skip Plane update, continue |
| `af-deploy` | Ansible fail, smoke fail, SSH timeout | Telegram alerte immediate, label "deploy-fail", attente gate humaine |
| `af-phase-complete` | NocoDB write fail | Retry 3x, queue les decisions en memoire, retry au prochain trigger |
| `af-rex-indexer` | LiteLLM embed fail, Qdrant down | Retry 3x, log dans NocoDB, pas bloquant pour le projet |

---

## 9. Composants a construire

| Composant | Ou | Effort |
|-----------|----|--------|
| 5 workflows n8n (af-*) | Sese-AI n8n | Medium |
| NocoDB base `app-factory` (6 tables incl. error_logs) | Sese-AI NocoDB | Light |
| 2 collections Qdrant | Sese-AI Qdrant | Light |
| Role Ansible template `app-scaffold` | VPAI roles/ | Medium |
| `playbooks/app-prod.yml` | VPAI playbooks/ | Light |
| GitHub Actions `deploy-app.yml` workflow | VPAI .github/workflows/ | Medium |
| CI template `.github/workflows/ci.yml` | Template dans af-intake | Light |
| CLAUDE.md template | Template dans af-intake | Light |
| Dockerfile template (multi-stack) | Template dans af-intake | Light |
| GHCR pull auth (docker config.json) | Role app-scaffold | Light |
| Hook GSD → af-phase-complete | VPAI .claude/ settings | Light |

---

## 10. Contraintes

- **Budget IA** : $5/jour hard cap LiteLLM — les embeddings REX consomment peu (~$0.01/phase)
- **Hetzner CX22** : 4GB RAM, 2 vCPU — limiter a ~4 apps par VM partagee
- **GHCR** : images privees, necessitent `GITHUB_TOKEN` dans CI + pull secret sur Hetzner
- **SSH Sese-AI** : Tailscale IP `100.64.0.14:804` (IP publique timeout)
- **Conventions VPAI** : FQCN Ansible, images pinnees, `changed_when` explicite, secrets en vault
