# Plan : Integration Kaneo-OpenClaw — Pipeline "Demande → Production"

> Date : 2026-02-23
> Statut : Valide, pret a implementer
> Prerequis : Plan valide par l'utilisateur apres 4 iterations d'audit

## Contexte

Le concierge (Mobutoo) commande les sous-agents mais ne cree pas de projets Kaneo, ne trace pas le temps, ne rattache pas les livrables. Ouvrir Kaneo doit montrer un **vrai tableau de bord de pilotage** : qui fait quoi, depuis combien de temps, quelles taches dependent des autres, ou en est chaque projet, et les livrables produits.

**Objectif** : Integration maximale Kaneo <-> OpenClaw. Chaque action d'un agent est tracee dans Kaneo. Chaque livrable y est rattache. Chaque minute y est comptee.

**Principe** : Le concierge orchestre. Les workflows n8n sont des outils d'execution. Kaneo est le miroir fidele de tout ce qui se passe.

---

## Contrainte technique cle : qui peut appeler l'API Kaneo ?

L'API Kaneo est interne Docker (`http://kaneo-api:1337`). `web_fetch` d'OpenClaw **bloque les hostnames internes**. Seul l'outil `exec` (curl) peut y acceder.

| Agent | `exec` ? | Peut appeler Kaneo directement ? |
|-------|----------|----------------------------------|
| Concierge | **NON** | Non |
| Builder | OUI | Oui, mais ce n'est pas son role |
| Maintainer | OUI | Oui, mais ce n'est pas son role |
| Writer | NON | Non |
| Explorer | NON | Non |
| Artist | NON | Non |
| CFO | NON | Non |

**Solution : Agent "Messenger"** — un agent dedie, ultra-leger, dont l'unique role est de faire le pont entre les agents OpenClaw et l'API Kaneo. Tout agent peut le spawner via `sessions_spawn` pour toute operation Kaneo.

---

## Agent Messenger — Design

### Identite
- **Nom** : `messenger` (variable `openclaw_agent_messenger_name`)
- **Persona** : Hermes — le messager des dieux. Rapide, precis, silencieux.
- **Modele** : `deepseek-v3` (ultra-low cost, suffisant pour du CRUD JSON)
- **Outils** : `exec` uniquement (curl vers Kaneo API). Pas de `fs`, pas de sandbox reseau externe.
- **Spawn depth** : N'importe quel agent peut le spawner (profondeur 1 suffit)

### Protocole
Le messenger recoit un message structure et execute l'operation Kaneo correspondante :

```
Action: create_project | create_task | update_status | start_timer | stop_timer |
        add_comment | add_link | add_label | get_tasks | get_project
Params: { ... }
```

Il retourne le resultat JSON brut au parent via `announce`.

### Securite du Messenger

Le Messenger a `exec` — il faut restreindre ce qu'il peut faire :

1. **Allowlist de commandes** : Dans son IDENTITY, il est instruit de n'executer QUE `curl` vers `http://kaneo-api:1337/api/*` et `redis-cli` vers `redis`. Toute autre commande = refus.
2. **Sandbox Docker** : Le Messenger tourne en sandbox `all` (comme Explorer) mais sur le reseau `backend` (pas `egress`). Il ne peut pas sortir vers Internet.
3. **Pas de `fs`** : `fs: { enabled: false }` — il ne peut ni lire ni ecrire de fichiers dans le workspace. Aucun acces aux secrets, configs, ou livrables.
4. **Timeout court** : `exec.timeoutSec: 15` — les appels Kaneo prennent <1s. Un timeout de 15s empeche tout abus.
5. **Pas d'`elevated`** : Aucun acces root, aucun acces Docker socket.
6. **Instructions de refus explicites** dans l'IDENTITY : "Tu refuses CATEGORIQUEMENT toute demande qui n'est pas un appel API Kaneo ou Redis. Tu ne fais PAS de SSH, tu ne telecharges PAS de fichiers, tu n'executes PAS de scripts."

### Cache de session via Redis

Redis est deja deploye dans la stack. Le Messenger l'utilise pour :

1. **Cookie de session Kaneo** : Au lieu de s'authentifier a chaque spawn, stocker le cookie dans Redis avec un TTL. Le Messenger verifie Redis d'abord, s'authentifie seulement si le cookie a expire.
   ```
   redis-cli -h redis GET kaneo:session:cookie
   redis-cli -h redis SETEX kaneo:session:cookie 3600 "<cookie>"
   ```
2. **Cache d'IDs** : Stocker les IDs de projets/taches recents pour eviter des GET inutiles.
   ```
   redis-cli -h redis HSET kaneo:projects "<project_name>" "<project_id>"
   redis-cli -h redis HGET kaneo:projects "<project_name>"
   ```
3. **Compteur de corrections** : `correction_depth` par tache pour eviter les boucles infinies.
   ```
   redis-cli -h redis INCR kaneo:corrections:<task_id>
   redis-cli -h redis GET kaneo:corrections:<task_id>  # si > 2, stop
   ```

Le Messenger a acces au reseau `backend` ou Redis est deja connecte.

### Pourquoi un agent dedie et pas un outil custom ?
1. **Pas besoin de plugin TypeScript** — on reste dans le paradigme `sessions_spawn` natif
2. **Chaque agent garde ses outils propres** — pas de pollution de toolset
3. **Isolation maximale** — sandbox Docker, pas de fs, pas d'internet, timeout court
4. **Budget** — deepseek-v3 coute quasi rien pour parser JSON + exec curl
5. **Simplicite** — n'importe quel agent peut l'appeler, meme ceux sans `exec`
6. **Redis** — session cache + project/task ID cache + correction depth tracking

### Impact sur la hierarchie des agents
```
Concierge (Mobutoo)
  |-- Builder (Imhotep)        -> code, infra
  |     \-- Messenger (Hermes) -> log time, attach PR, update status
  |-- Writer (Thot)            -> contenu
  |     \-- Messenger (Hermes) -> log time, attach doc
  |-- Explorer (R2D2)          -> recherche web
  |     \-- Messenger (Hermes) -> log sources
  |-- Artist (Basquiat)        -> visuel
  |     \-- Messenger (Hermes) -> log time, attach image
  |-- Maintainer               -> ops, sante stack
  |     \-- Messenger (Hermes) -> sync agents, health data
  |-- CFO                      -> budget
  \-- Messenger (Hermes)       -> creer projets, structurer taches, lire etat
```

**Regle subagents** : Tous les agents ont `allowAgents: ["messenger"]` dans leur config. Le concierge garde aussi ses agents habituels.

---

## API Kaneo native (aucune modification fork pour le CRUD)

| Module | Endpoints | Utilite |
|--------|-----------|---------|
| **Project** | `POST/GET/PUT/DELETE /api/project` | CRUD projets |
| **Task** | `POST /api/task/:projectId`, `GET /api/task/tasks/:projectId`, `PUT /api/task/status/:id`, `/assignee/:id`, `/priority/:id`, `/due-date/:id`, `/title/:id`, `/description/:id` | CRUD + updates granulaires |
| **Column** | `GET/POST /api/column/:projectId`, `PUT /api/column/reorder/:projectId` | Colonnes Kanban |
| **Label** | `GET /api/label/task/:taskId`, `GET /api/label/workspace/:wId`, `POST/PUT/DELETE /api/label` | Tags colores |
| **Time Entry** | `GET /api/time-entry/task/:taskId`, `POST /api/time-entry`, `PUT /api/time-entry/:id` | Suivi temps |
| **External Link** | `GET /api/external-link/task/:taskId`, `POST /api/external-link` | Liens PR, fichiers, docs |
| **Activity** | `GET /api/activity/:taskId`, `POST /api/activity/comment` | Commentaires + historique |
| **GitHub Integration** | `POST /api/github-integration/project/:projectId`, webhook handler | Sync issues <-> taches |
| **Search** | `GET /api/search` | Recherche cross-projet |

---

## Ce qui MANQUE dans le fork Kaneo (Phase 2 — non-bloquant)

### A. Dependances entre taches

Ajouter au schema `task` :
```typescript
dependsOn: text('depends_on'),  // JSON array of task IDs ["task-123", "task-456"]
```

+ Endpoints `PUT/GET /api/task/dependencies/:id`

### B. Vue Timeline/Gantt (frontend)

Composant affichant les taches sur un axe temporel avec fleches de dependances, couleurs par agent (label `agent:*`), chemin critique surligne.

### C. Vue Calendrier (frontend)

Composant calendrier mensuel/hebdomadaire avec les taches par date de deadline.

### D. Assignation agent

V1 via **labels** (`agent:builder`, `agent:writer`, etc.) — pas de modif fork.
V2 : champ `assignedAgent` dedie au schema.

---

## Architecture du Pipeline

```
Telegram -> Concierge (Mobutoo)
  | Detecte demande longue (>30min, multi-etapes, multi-agents)
  | Reformule (protocole standard)
  |
  | STRUCTURATION (via Messenger) :
  |   sessions_spawn(messenger, "create_project + create_tasks + labels + deadlines")
  |   -> Messenger execute :
  |      POST /api/project -> projet Kaneo
  |      POST /api/column/:projectId x 4 -> Backlog, In Progress, Review, Done
  |      POST /api/task/:projectId x N -> taches
  |      POST /api/label (agent:<id>, type:<type>) par tache
  |      PUT /api/task/due-date/:id -> deadlines
  |   -> Retourne project_id + task_ids au concierge
  |
  | DISPATCH (via sessions_spawn) :
  |   Pour chaque tache :
  |     -> sessions_spawn(agentId, message avec task_id + project_id + instructions)
  |     -> Le sous-agent recoit le contexte complet
  |
  | CHAQUE SOUS-AGENT (Builder, Writer, Explorer, etc.) :
  |   1. sessions_spawn(messenger, "start_timer task_id=...")
  |   2. Execute la tache (code, contenu, recherche, etc.)
  |   3. sessions_spawn(messenger, "update_status task_id=... status=in-progress")
  |   4. sessions_spawn(messenger, "add_comment task_id=... text=progres")
  |   5. Quand termine :
  |      - sessions_spawn(messenger, "stop_timer + add_link + update_status=done")
  |   6. Rapporte au concierge (announce OpenClaw)
  |
  | CONCIERGE recoit le rapport :
  |   Si code -> sessions_spawn(builder, "code-review via delegate-n8n")
  |     -> Builder cree une sous-tache Kaneo via Messenger
  |     -> Builder appelle delegate-n8n pour la review SSH Pi
  |     -> Builder logge le resultat via Messenger (commentaire + statut)
  |   Si review KO -> sessions_spawn(builder, "correction")
  |     -> Builder cree une sous-tache correction via Messenger
  |   Si erreur -> sessions_spawn(maintainer, "error-to-task via delegate-n8n")
  |     -> Maintainer cree la tache de correction via Messenger
  |   Si toutes taches done :
  |     -> sessions_spawn(messenger, "update project status")
  |     -> Telegram notification recap
  |
  | HEARTBEAT (30min) :
  |   Concierge -> sessions_spawn(messenger, "get all active projects + tasks")
  |   Analyse : taches in-progress > 2h -> alerter
  |   Projets termines non notifies -> recap Telegram
  |
  | CRON QUOTIDIEN "project-digest" (9h) :
      Concierge fait le point via Messenger -> annonce Telegram
```

---

## Phase 1 — VPAI : Agent Messenger + Config OpenClaw + Skills + Identites

> Phase 1 est entierement dans le repo VPAI. Aucune modification du fork Kaneo.

### 1.1 — Agent Messenger (NOUVEAU)

**Fichiers** :
```
roles/openclaw/templates/agents/messenger/IDENTITY.md.j2     <- NOUVEAU
```

**Contenu IDENTITY** :
- Persona : Hermes — rapide, precis, silencieux
- Unique role : interfacer avec l'API Kaneo via `exec` (curl)
- Recoit des instructions structurees, retourne le JSON brut
- Documente toutes les commandes Kaneo supportees (create_project, create_task, update_status, start_timer, stop_timer, add_comment, add_link, add_label, get_tasks, get_project, search)
- Inclut les templates curl pour chaque operation avec les bons endpoints
- Gere l'auth BetterAuth via Redis cache (cookie de session)
- Instructions de securite explicites (refus de tout ce qui n'est pas curl kaneo-api / redis-cli)

**Config dans `openclaw.json.j2`** (nouvel agent) :
```json
{
  "id": "{{ openclaw_agent_messenger_name }}",
  "model": { "primary": "{{ openclaw_messenger_model }}" },
  "workspace": "/home/node/.openclaw/workspace",
  "sandbox": {
    "mode": "all",
    "docker": {
      "network": "{{ project_name }}_backend",
      "readOnlyRoot": true,
      "capDrop": ["ALL"],
      "memory": "256m",
      "cpus": 0.5
    }
  },
  "tools": {
    "exec": { "timeoutSec": 15 },
    "fs": { "enabled": false },
    "elevated": { "enabled": false }
  }
}
```

**Config dans `defaults/main.yml`** :
```yaml
openclaw_agent_messenger_name: "messenger"
openclaw_messenger_model: "custom-litellm/deepseek-v3"
```

+ Ajout dans `openclaw_agents_list` :
```yaml
- id: "{{ openclaw_agent_messenger_name }}"
  name: "Hermes"
  type: "messenger"
  model: "{{ openclaw_messenger_model }}"
```

**Config subagents** : Ajouter `messenger` dans `allowAgents` de TOUS les agents (concierge, builder, writer, artist, explorer, maintainer, cfo, tutor, marketer).

### 1.2 — Skill `project-management` (remplace `task-management`)

**Fichier** : `roles/openclaw/templates/skills/project-management/SKILL.md.j2`

Ce skill documente le protocole complet pour piloter Kaneo. Il est lu par le concierge ET les sous-agents.

**Sections** :

1. **Protocole Messenger** — Comment spawner le messenger et quelles commandes lui envoyer
2. **Creer un projet complet** — Sequence messenger pour creer projet + colonnes + taches + labels + deadlines
3. **Gerer les taches en cours** — Sequence messenger pour timer + commentaires + livrables + statut
4. **Conventions labels** :
   - `agent:<agentId>` (agent:builder, agent:writer, etc.)
   - `type:<deliverable>` (type:code, type:content, type:research, type:visual)
   - `correction` (tache de correction issue d'une review)
   - `blocked` (tache bloquee par une dependance)
5. **Protocole Demande Longue** (pour le concierge) — Analyse, decomposition, structuration, dispatch, suivi
6. **Protocole Sous-Agent** — Ce que chaque sous-agent doit faire au debut et a la fin de sa tache
7. **Delegation n8n** — Comment les sous-agents utilisent delegate-n8n pour des operations specifiques (code-review, error-to-task)

**Supprimer** : `roles/openclaw/templates/skills/task-management/`

**MAJ `openclaw_skills`** dans defaults : remplacer `task-management` par `project-management`, ajouter `code-review`

### 1.3 — Skill `code-review` (NOUVEAU)

**Fichier** : `roles/openclaw/templates/skills/code-review/SKILL.md.j2`

**Contenu** :
- Quand : apres chaque livrable code (PR, commit, fichier modifie)
- Qui : le Builder (delegue par le concierge)
- Comment : delegate-n8n vers le workflow `code-review` (SSH Pi + LiteLLM)
- Criteres VPAI : FQCN, changed_when, pas de hardcode, secrets vault, idempotence
- Format rapport : OK/KO, liste des problemes, suggestions
- Tracabilite : le Builder cree une sous-tache Kaneo "Review" via Messenger, logue le resultat en commentaire

### 1.4 — MAJ Identites Agents

#### Concierge (`IDENTITY.md.j2`)

Ajout du **Protocole Demande Longue** :
1. Detecter demande longue (>30min, multi-etapes, multi-agents)
2. Reformuler en objectif strategique
3. `sessions_spawn(messenger)` -> creer projet Kaneo complet
4. `sessions_spawn(agentId)` x N -> dispatcher les taches avec contexte (task_id, project_id)
5. A chaque rapport de sous-agent :
   - Si code -> `sessions_spawn(builder, "review ce code")` -> Builder cree sous-tache Kaneo + delegate-n8n
   - Si erreur -> `sessions_spawn(maintainer, "corriger cette erreur")` -> Maintainer cree sous-tache Kaneo
   - Si OK -> `sessions_spawn(messenger, "update status done")`
   - Telegram notification
6. Quand toutes taches done -> `sessions_spawn(messenger, "close project")` + recap Telegram

Ajout dans le **tableau de routing** :
```
| demande longue, projet, multi-etapes, implementation | messenger + agents | Protocole Demande Longue |
| statut projet, ou en est, avancement | messenger | sessions_spawn(messenger, "get_project") |
| review code, verifier PR | builder | sessions_spawn(builder, "code-review") |
```

Ajout du **Messenger dans les sous-agents** :
```
| messenger | Hermes | Interface Kaneo — projets, taches, temps, livrables |
```

#### Builder (`IDENTITY.md.j2`)

Ajout du **Protocole tache Kaneo** :
- Au debut : `sessions_spawn(messenger, "start_timer task_id=... + update_status in-progress")`
- Pendant : `sessions_spawn(messenger, "add_comment task_id=... text=progres")`
- A la fin : `sessions_spawn(messenger, "stop_timer + add_link url=... + update_status done")`
- Si review demandee : creer sous-tache via Messenger, appeler delegate-n8n, loguer resultat

#### Writer (`IDENTITY.md.j2`)

Ajout du meme protocole, adapte :
- Livrables = fichiers texte dans workspace -> external-link vers le chemin

#### Explorer (`IDENTITY.md.j2`)

Ajout :
- Timer + rapport de recherche dans description via Messenger
- External-links vers les sources trouvees

#### Maintainer (`IDENTITY.md.j2`)

Ajout :
- Peut creer des taches de correction via Messenger (error-to-task)
- Sync agents -> Kaneo via Messenger (remplace le workflow n8n existant si pertinent)

### 1.5 — HEARTBEAT.md + Cron

**`HEARTBEAT.md.j2`** (ajout section) :
```markdown
## Suivi projets Kaneo
- sessions_spawn(messenger, "get all active projects")
- Pour chaque projet avec taches : analyser l'etat
- Taches in-progress > 2h sans commentaire recent -> alerter Telegram
- Projets avec toutes taches done -> notifier recap Telegram
- Taches avec label "blocked" -> escalader
```

**Config heartbeat dans `openclaw.json.j2`** (section a ajouter) :
```json
"heartbeat": {
  "intervalMinutes": 30,
  "activeHours": { "start": 8, "end": 22 }
}
```

**Config cron dans `openclaw.json.j2`** (section a ajouter) :
```json
"cron": [
  {
    "id": "project-digest",
    "schedule": "0 9 * * *",
    "agentId": "concierge",
    "message": "Fais le point sur tous les projets Kaneo actifs. Resume par projet : taches done/total, temps passe, livrables produits, blocages. Envoie le resume sur Telegram.",
    "mode": "main-session",
    "delivery": "announce"
  }
]
```

### 1.6 — MAJ `defaults/main.yml`

- Ajouter `openclaw_agent_messenger_name: "messenger"`
- Ajouter `openclaw_messenger_model: "custom-litellm/deepseek-v3"`
- Ajouter messenger a `openclaw_agents_list`
- Remplacer `task-management` par `project-management` dans `openclaw_skills`
- Ajouter `code-review` dans `openclaw_skills`
- Ajouter les nouveaux workflows dans `openclaw_n8n_workflows` :
  - code-review, error-to-task, project-status

### 1.7 — MAJ `openclaw.json.j2`

- Ajouter l'agent `messenger` dans la liste `agents.list`
- Ajouter `"messenger"` dans `allowAgents` de TOUS les agents existants
- Ajouter la section `heartbeat`
- Ajouter la section `cron`

---

## Phase 2 — Fork Kaneo : dependances + vues Timeline/Calendrier

> Phase separee, dans le repo Mobutoo/kaneo. Non-bloquante pour Phase 1.

### 2.1 — Champ `dependsOn` (API)

```
packages/database/src/schema.ts              <- ajouter dependsOn au task schema
apps/api/src/task/index.ts                   <- ajouter PUT/GET /dependencies/:id
packages/database/drizzle/                   <- migration SQL
```

### 2.2 — Vue Timeline/Gantt (Frontend)

```
apps/web/src/components/timeline-view/       <- NOUVEAU (index, task-bar, dependency-arrow, critical-path)
apps/web/src/routes/.../project.$projectId.timeline.tsx  <- NOUVEAU route
```

### 2.3 — Vue Calendrier (Frontend)

```
apps/web/src/components/calendar-view/       <- NOUVEAU (index, day-cell, task-chip)
apps/web/src/routes/.../project.$projectId.calendar.tsx  <- NOUVEAU route
```

### 2.4 — Rebuild + push images

```bash
cd kaneo && docker build -t ghcr.io/mobutoo/api:sha-XXXXXXX apps/api
docker push ghcr.io/mobutoo/api:sha-XXXXXXX
docker build -t ghcr.io/mobutoo/web:sha-XXXXXXX apps/web
docker push ghcr.io/mobutoo/web:sha-XXXXXXX
# MAJ inventory/group_vars/all/versions.yml
```

---

## Phase 3 — Realigner workflows n8n existants

Les 2 workflows existants utilisent des endpoints Kaneo **incorrects** (`POST /api/tasks` avec `tags`/`metadata`). Realigner vers la vraie API.

### 3.1 — `kaneo-agents-sync.json`

- Remplacer `POST /api/tasks` -> `POST /api/task/:projectId` (project "OpenClaw Agents")
- Remplacer `tags` -> creer des labels via `POST /api/label`
- Utiliser les vrais champs : title, description, status (via column), priority
- Auth : BetterAuth cookie ou token API

### 3.2 — `github-autofix.json`

- Meme realignement API
- Ajouter : time-entry au debut/fin, external-link pour la PR, commentaire d'activite

### Fichiers
```
roles/n8n-provision/files/workflows/kaneo-agents-sync.json   <- MODIFIER
roles/n8n-provision/files/workflows/github-autofix.json      <- MODIFIER
```

---

## Phase 4 — Workflows n8n auxiliaires (3 nouveaux)

### 4.1 — `code-review.json` (webhook `/webhook/code-review`)

- Input : repo_url, branch, task_id, project_id
- SSH vers RPi -> execute review LiteLLM (gpt-codex ou glm-5)
- Output : rapport review (OK/KO, liste problemes)
- Appel Kaneo API : commentaire d'activite sur la tache avec le resultat

### 4.2 — `error-to-task.json` (webhook `/webhook/error-to-task`)

- Input : error_message, source_task_id, project_id, agent_id
- Cree une tache de correction dans Kaneo (POST /api/task/:projectId)
- Ajoute label `correction` + `agent:<agent_id>`
- Cree external-link sur la tache source pointant vers la correction

### 4.3 — `project-status.json` (webhook `/webhook/project-status`)

- Input : project_id
- GET /api/task/tasks/:projectId -> toutes les taches
- GET /api/time-entry/task/:taskId -> temps par tache
- Calcul : temps total, temps par agent (label `agent:*`), livrables (external-links)
- Output : rapport JSON structure

### Fichiers + deploiement
```
roles/n8n-provision/files/workflows/code-review.json       <- NOUVEAU
roles/n8n-provision/files/workflows/error-to-task.json     <- NOUVEAU
roles/n8n-provision/files/workflows/project-status.json    <- NOUVEAU
roles/n8n-provision/tasks/main.yml                         <- ajouter aux 4 listes
roles/n8n/templates/n8n.env.j2                             <- KANEO_WORKSPACE_ID, KANEO_API_URL
```

---

## Tous les fichiers VPAI (Phase 1 + 3 + 4)

```
# Agent Messenger
roles/openclaw/templates/agents/messenger/IDENTITY.md.j2     <- NOUVEAU

# Skills
roles/openclaw/templates/skills/project-management/SKILL.md.j2  <- NOUVEAU
roles/openclaw/templates/skills/code-review/SKILL.md.j2         <- NOUVEAU
roles/openclaw/templates/skills/task-management/                 <- SUPPRIMER

# Agents (MAJ)
roles/openclaw/templates/agents/concierge/IDENTITY.md.j2  <- MAJ (protocole demande longue + messenger)
roles/openclaw/templates/agents/main/IDENTITY.md.j2       <- MAJ (idem)
roles/openclaw/templates/agents/builder/IDENTITY.md.j2    <- MAJ (protocole tache Kaneo)
roles/openclaw/templates/agents/writer/IDENTITY.md.j2     <- MAJ (protocole tache Kaneo)
roles/openclaw/templates/agents/explorer/IDENTITY.md.j2   <- MAJ (protocole tache Kaneo)
roles/openclaw/templates/agents/maintainer/IDENTITY.md.j2 <- MAJ (error-to-task + messenger)

# Config OpenClaw
roles/openclaw/templates/openclaw.json.j2     <- MAJ (agent messenger + heartbeat + cron + subagents)
roles/openclaw/defaults/main.yml              <- MAJ (messenger vars + skills + workflows)

# Heartbeat
roles/openclaw/templates/HEARTBEAT.md.j2      <- MAJ (section suivi projets)

# n8n workflows
roles/n8n-provision/files/workflows/code-review.json       <- NOUVEAU
roles/n8n-provision/files/workflows/error-to-task.json     <- NOUVEAU
roles/n8n-provision/files/workflows/project-status.json    <- NOUVEAU
roles/n8n-provision/files/workflows/kaneo-agents-sync.json <- MODIFIER
roles/n8n-provision/files/workflows/github-autofix.json    <- MODIFIER

# n8n deployment
roles/n8n-provision/tasks/main.yml            <- ajouter 3 workflows aux 4 listes
roles/n8n/templates/n8n.env.j2                <- KANEO_WORKSPACE_ID, KANEO_API_URL
```

---

## Ordre d'implementation

| Etape | Quoi | Depend de | Effort |
|-------|------|-----------|--------|
| **1** | Agent Messenger : IDENTITY + config openclaw.json.j2 + defaults | — | ~1h |
| **2** | Skill `project-management` (remplace task-management) | — | ~1.5h |
| **3** | Skill `code-review` | — | ~30min |
| **4** | MAJ IDENTITY concierge + main (protocole demande longue) | Etape 1, 2 | ~1.5h |
| **5** | MAJ IDENTITY builder + writer + explorer + maintainer | Etape 1, 2 | ~1.5h |
| **6** | Heartbeat + cron dans openclaw.json.j2 | Etape 1 | ~30min |
| **7** | Realigner `kaneo-agents-sync` + `github-autofix` | — | ~2h |
| **8** | Workflows n8n (code-review, error-to-task, project-status) | — | ~3h |
| **9** | MAJ n8n-provision/tasks + n8n.env.j2 | Etape 7, 8 | ~30min |
| **10** | Deploy + test end-to-end via Telegram | Tout | ~1h |

> Etapes 1-3 parallelisables.
> Etapes 4-6 dependent de 1+2 mais parallelisables entre elles.
> Etapes 7-8 parallelisables entre elles et avec 4-6.
> **Total Phase 1 VPAI : ~12h** (2 sessions)
> **Phase 2 fork Kaneo : ~8h** (1-2 sessions, non-bloquant)

---

## Auth Kaneo pour le Messenger

L'API Kaneo utilise BetterAuth. Approche retenue :

**Session cookie + Redis cache** : Le messenger verifie Redis (`kaneo:session:cookie`). Si present, l'utilise. Sinon, `POST /api/auth/sign-in`, stocke le cookie dans Redis avec TTL (1h).

Creer un user Kaneo `agent@internal` via le setup initial (provisioning Ansible). Le messenger verifie Redis d'abord, s'authentifie seulement si necessaire.

Variables dans `secrets.yml` :
```yaml
kaneo_agent_email: "agent@internal.{{ domain_name }}"
kaneo_agent_password: "{{ vault_kaneo_agent_password }}"
```

Le provisioning Kaneo (role `kaneo`) doit creer ce user au premier deploiement via l'API BetterAuth `POST /api/auth/sign-up`.

---

## Verification End-to-End

1. **Kaneo UI** : ouvrir `hq.ewutelo.cloud`
   - Vue Kanban -> taches avec labels `agent:builder`, `type:code`, colonnes Backlog/InProgress/Review/Done
   - Detail tache -> time-entries (duree), external-links (PRs, fichiers), historique activite (commentaires agents)
   - Filtre par label -> voir toutes les taches d'un agent
2. **Pipeline** : Telegram -> "Implemente un systeme de notification push"
   - Projet cree dans Kaneo avec 5+ taches
   - Agents assignes via labels
   - Timers demarres quand les agents travaillent
   - PRs / docs rattaches comme external-links
   - Commentaires d'activite en cours de route
   - Review auto du code -> sous-tache review + commentaire resultat
3. **Heartbeat** : projets actifs surveilles toutes les 30min
4. **Cron digest** : resume 9h avec temps passe par agent et avancement par projet
5. **Phase 2** (post fork) : vues Timeline + Calendrier avec dependances et chemin critique

---

## Risques et Mitigations

| Risque | Mitigation |
|--------|------------|
| Auth BetterAuth cookie expire | Redis cache avec TTL + re-auth automatique |
| Messenger spawne trop souvent -> cout | deepseek-v3 ultra-low cost + messages courts (JSON CRUD) |
| Boucle error->task->error | `correction_depth` max 2 (compteur Redis) |
| Agents oublient de spawner Messenger | Instructions explicites dans IDENTITY + heartbeat verifie les taches sans timer |
| subagent depth limit (5) | Messenger est profondeur 1 depuis n'importe quel agent -> OK meme si Builder est deja depth 1 depuis Concierge |
| Budget IA avec reviews + structuration | deepseek-v3 pour Messenger, haiku pour review rapide, sonnet pour review code uniquement |
| Concierge overwhelmed | Max 3 projets actifs simultanes (verifie par heartbeat) |
| Fork Kaneo diverge d'upstream | Phase 2 : changements minimaux (1 champ DB + 2 vues frontend) |
| Securite Messenger | Sandbox backend-only, pas de fs, timeout 15s, allowlist curl/redis-cli only |
