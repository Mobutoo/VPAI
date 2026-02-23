# Taches d'implementation — Integration Kaneo-OpenClaw

> Plan de reference : `docs/PLAN-KANEO-OPENCLAW.md`
> Decoupage pour Sonnet 4.6 — chaque tache est autonome et peut etre executee independamment (sauf dependances notees)

---

## Lot A — Agent Messenger + Config de base (pas de dependances)

### TASK-A1 : Creer l'agent Messenger — IDENTITY.md.j2

**Fichier** : `roles/openclaw/templates/agents/messenger/IDENTITY.md.j2` (NOUVEAU)

**Instructions** :
1. Lire le plan `docs/PLAN-KANEO-OPENCLAW.md` sections "Agent Messenger — Design" et "API Kaneo native"
2. Lire les IDENTITY existantes pour le pattern : `roles/openclaw/templates/agents/builder/IDENTITY.md.j2`, `roles/openclaw/templates/agents/maintainer/IDENTITY.md.j2`
3. Creer le fichier IDENTITY du Messenger avec :
   - Persona : Hermes — le messager. Rapide, precis, silencieux.
   - **Section Securite** (CRITIQUE) :
     - N'executer QUE `curl` vers `http://kaneo-api:1337/api/*` et `redis-cli -h redis`
     - Refus categorique de toute autre commande (SSH, wget, scripts, etc.)
     - Instructions de refus explicites et fermes
   - **Section Auth** :
     - Verifier Redis d'abord : `redis-cli -h redis GET kaneo:session:cookie`
     - Si nil : `curl -s -c - -X POST http://kaneo-api:1337/api/auth/sign-in -H 'Content-Type: application/json' -d '{"email":"{{ kaneo_agent_email }}","password":"{{ kaneo_agent_password }}"}'`
     - Stocker le cookie : `redis-cli -h redis SETEX kaneo:session:cookie 3600 "<cookie>"`
   - **Section Commandes** — templates curl pour chaque operation :
     - `create_project` : POST /api/project
     - `create_task` : POST /api/task/:projectId
     - `update_status` : PUT /api/task/status/:id
     - `update_description` : PUT /api/task/description/:id
     - `set_priority` : PUT /api/task/priority/:id
     - `set_due_date` : PUT /api/task/due-date/:id
     - `start_timer` : POST /api/time-entry (body: taskId, startTime=now)
     - `stop_timer` : PUT /api/time-entry/:id (body: endTime=now)
     - `add_comment` : POST /api/activity/comment
     - `add_link` : POST /api/external-link
     - `add_label` : POST /api/label
     - `get_tasks` : GET /api/task/tasks/:projectId
     - `get_project` : GET /api/project (ou GET /api/project/:id)
     - `create_columns` : POST /api/column/:projectId (x4 : Backlog, In Progress, Review, Done)
     - `search` : GET /api/search?q=...
   - **Section Redis Cache** :
     - Cache IDs projets : `redis-cli -h redis HSET kaneo:projects "name" "id"`
     - Compteur corrections : `redis-cli -h redis INCR kaneo:corrections:<task_id>` (max 2)
   - **Section Format de reponse** : Toujours retourner le JSON brut de Kaneo API

**Variables Jinja2 a utiliser** : `{{ kaneo_agent_email }}`, `{{ kaneo_agent_password }}`, `{{ kaneo_subdomain_override | default('hq') }}`, `{{ domain_name }}`

---

### TASK-A2 : Ajouter le Messenger dans openclaw.json.j2

**Fichier** : `roles/openclaw/templates/openclaw.json.j2` (MODIFIER)

**Instructions** :
1. Lire le fichier actuel : `roles/openclaw/templates/openclaw.json.j2`
2. Lire `roles/openclaw/defaults/main.yml` pour les noms de variables
3. Dans la section `agents.list`, ajouter l'agent messenger **apres** l'agent maintainer :
```json
{
  "id": "{{ openclaw_agent_messenger_name }}",
  "model": {
    "primary": "{{ openclaw_messenger_model }}"
  },
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
4. Pour CHAQUE agent existant qui a une section `subagents.allowAgents`, ajouter `"{{ openclaw_agent_messenger_name }}"` dans la liste
5. Pour les agents qui N'ONT PAS de section `subagents`, en ajouter une :
```json
"subagents": {
  "allowAgents": ["{{ openclaw_agent_messenger_name }}"]
}
```
   Concernes : builder, writer, artist, tutor, explorer, marketer, cfo, maintainer
6. Le concierge a deja `allowAgents` — ajouter messenger a sa liste existante

---

### TASK-A3 : Ajouter les variables Messenger dans defaults/main.yml

**Fichier** : `roles/openclaw/defaults/main.yml` (MODIFIER)

**Instructions** :
1. Lire le fichier actuel
2. Ajouter dans la section "Agent names" :
```yaml
openclaw_agent_messenger_name: "messenger"
```
3. Ajouter dans la section "Model assignments" :
```yaml
openclaw_messenger_model: "custom-litellm/deepseek-v3"
```
4. Ajouter dans `openclaw_agents_list` (apres maintainer) :
```yaml
  - id: "{{ openclaw_agent_messenger_name }}"
    name: "Hermes"
    type: "messenger"
    model: "{{ openclaw_messenger_model }}"
```
5. Dans `openclaw_skills`, remplacer `task-management` par `project-management`
6. Ajouter `code-review` dans `openclaw_skills`
7. Ajouter dans `openclaw_n8n_workflows` :
```yaml
  - name: code-review
    path: code-review
    description: "Review automatique de code via SSH RPi + LiteLLM"
  - name: error-to-task
    path: error-to-task
    description: "Creer une tache de correction a partir d'une erreur"
  - name: project-status
    path: project-status
    description: "Rapport d'avancement projet (temps, livrables, blocages)"
```

---

### TASK-A4 : Ajouter heartbeat + cron dans openclaw.json.j2

**Fichier** : `roles/openclaw/templates/openclaw.json.j2` (MODIFIER)

**Depend de** : TASK-A2 (le messenger doit exister dans la config)

**Instructions** :
1. Lire le fichier actuel
2. Ajouter une section `"heartbeat"` au niveau racine (apres `"agents"`) :
```json
"heartbeat": {
  "intervalMinutes": 30,
  "activeHours": { "start": 8, "end": 22 }
}
```
3. Ajouter une section `"cron"` au niveau racine :
```json
"cron": [
  {
    "id": "project-digest",
    "schedule": "0 9 * * *",
    "agentId": "{{ openclaw_agent_concierge_name }}",
    "message": "Fais le point sur tous les projets Kaneo actifs via le messenger. Resume par projet : taches done/total, temps passe, livrables produits, blocages. Envoie le resume sur Telegram.",
    "mode": "main-session",
    "delivery": "announce"
  }
]
```

---

## Lot B — Skills (pas de dependances)

### TASK-B1 : Creer le skill project-management

**Fichier** : `roles/openclaw/templates/skills/project-management/SKILL.md.j2` (NOUVEAU)

**Instructions** :
1. Lire le plan `docs/PLAN-KANEO-OPENCLAW.md` sections "Architecture du Pipeline" et "Phase 1.2"
2. Lire les skills existants pour le pattern : `roles/openclaw/templates/skills/delegate-n8n/SKILL.md.j2`, `roles/openclaw/templates/skills/task-management/SKILL.md.j2`
3. Creer le fichier avec le frontmatter YAML :
```yaml
---
name: project-management
description: Full project lifecycle in Kaneo via Messenger agent. Create projects, manage tasks, track time, attach deliverables.
metadata: { "openclaw": { "emoji": "📊", "always": true } }
---
```
4. Sections du skill :

   **1. Protocole Messenger** — Comment utiliser le Messenger pour TOUTE operation Kaneo :
   ```
   sessions_spawn(messenger, "<instructions structurees>")
   ```
   Le messenger est un sous-agent dedie. Il execute des appels curl vers l'API Kaneo et retourne le JSON brut.

   **2. Creer un projet complet** — Sequence complete :
   - sessions_spawn(messenger, "Cree un projet Kaneo : name=<nom>, description=<desc>")
   - sessions_spawn(messenger, "Cree 4 colonnes pour projectId=<id> : Backlog, In Progress, Review, Done")
   - Pour chaque tache : sessions_spawn(messenger, "Cree une tache : projectId=<id>, title=<titre>, description=<desc>")
   - Pour chaque tache : sessions_spawn(messenger, "Ajoute les labels : taskId=<id>, labels=[agent:<agentId>, type:<type>]")
   - Pour chaque tache : sessions_spawn(messenger, "Met la deadline : taskId=<id>, dueDate=<date>")

   **3. Gerer les taches en cours** — Operations courantes :
   - Demarrer timer : sessions_spawn(messenger, "start_timer taskId=<id>")
   - Arreter timer : sessions_spawn(messenger, "stop_timer timeEntryId=<id>")
   - Ajouter commentaire : sessions_spawn(messenger, "add_comment taskId=<id> text=<progres>")
   - Attacher livrable : sessions_spawn(messenger, "add_link taskId=<id> url=<url> title=<titre>")
   - Changer statut : sessions_spawn(messenger, "update_status taskId=<id> status=<done|in-progress>")

   **4. Conventions labels** :
   - `agent:<agentId>` — agent:builder, agent:writer, agent:explorer, agent:artist, agent:maintainer
   - `type:<deliverable>` — type:code, type:content, type:research, type:visual, type:ops
   - `correction` — tache de correction issue d'une review
   - `blocked` — tache bloquee par une dependance

   **5. Protocole Demande Longue** (pour le concierge) :
   - Detecter : demande multi-etapes, multi-agents, >30min
   - Reformuler en objectif strategique
   - Creer projet Kaneo complet (sequence ci-dessus)
   - Dispatcher via sessions_spawn avec contexte complet (task_id, project_id, instructions)
   - A chaque rapport : evaluer, review si code, corriger si erreur, notifier
   - Quand tout done : fermer projet + recap Telegram

   **6. Protocole Sous-Agent** — Ce que chaque sous-agent fait quand il recoit une tache avec task_id :
   - AU DEBUT : sessions_spawn(messenger, "start_timer + update_status in-progress")
   - PENDANT : sessions_spawn(messenger, "add_comment progres") periodiquement
   - A LA FIN : sessions_spawn(messenger, "stop_timer + add_link livrable + update_status done")

   **7. Delegation n8n** — Pour les operations qui necessitent n8n :
   - Code review : delegate-n8n vers /webhook/code-review
   - Error to task : delegate-n8n vers /webhook/error-to-task
   - Project status : delegate-n8n vers /webhook/project-status

5. Supprimer l'ancien skill : `roles/openclaw/templates/skills/task-management/` (tout le dossier)

---

### TASK-B2 : Creer le skill code-review

**Fichier** : `roles/openclaw/templates/skills/code-review/SKILL.md.j2` (NOUVEAU)

**Instructions** :
1. Lire `docs/PLAN-KANEO-OPENCLAW.md` section 1.3
2. Lire `CLAUDE.md` pour les criteres VPAI (conventions Ansible, Docker, Jinja2, securite)
3. Creer le fichier avec frontmatter :
```yaml
---
name: code-review
description: Automated code review against VPAI standards. Used by Builder after code deliverables.
metadata: { "openclaw": { "emoji": "🔍", "always": false } }
---
```
4. Contenu :
   - **Quand** : apres chaque livrable code (PR, commit, fichier modifie)
   - **Qui** : le Builder (delegue par le concierge)
   - **Comment** : delegate-n8n vers le workflow `code-review` (SSH Pi + LiteLLM)
   - **Criteres VPAI** (extraits de CLAUDE.md) :
     - FQCN obligatoire (ansible.builtin.apt, jamais apt seul)
     - changed_when/failed_when explicites sur command/shell
     - set -euo pipefail + executable: /bin/bash sur shell
     - Pas de :latest ni :stable — images pinnees
     - cap_drop: ALL + cap_add minimal
     - Healthchecks sur chaque service
     - Variables Jinja2, pas de hardcode
     - Secrets dans vault, jamais en clair
   - **Format rapport** : OK/KO + liste des problemes + suggestions
   - **Tracabilite Kaneo** :
     - Le Builder cree une sous-tache Kaneo "Review: <titre>" via Messenger
     - Labels : `type:review`, `agent:builder`
     - Commentaire avec le rapport complet
     - Statut done si OK, blocked si KO

---

## Lot C — MAJ Identites Agents (depend de Lot A et B)

### TASK-C1 : MAJ IDENTITY Concierge — Protocole Demande Longue

**Fichiers** :
- `roles/openclaw/templates/agents/concierge/IDENTITY.md.j2` (MODIFIER)
- `roles/openclaw/templates/agents/main/IDENTITY.md.j2` (MODIFIER — meme contenu)

**Instructions** :
1. Lire les fichiers actuels
2. Lire le plan section "Phase 1.4 — Concierge"
3. Ajouter le Messenger dans le tableau des sous-agents :
```
| {{ openclaw_agent_messenger_name }} | Hermes | Interface Kaneo — projets, taches, temps, livrables |
```
4. Ajouter les lignes de routing :
```
| demande longue, projet, implementation, multi-etapes | messenger + agents | Protocole Demande Longue |
| statut projet, ou en est, avancement, kaneo | messenger | sessions_spawn(messenger, "get_project") |
| review code, verifier PR, qualite | builder | sessions_spawn(builder, "code-review") |
```
5. Ajouter une section **## Protocole Demande Longue** avec les 6 etapes du plan
6. Augmenter le nombre de sous-agents dans la description : de 7 a 8 (+ Messenger)

---

### TASK-C2 : MAJ IDENTITY Builder — Protocole tache Kaneo

**Fichier** : `roles/openclaw/templates/agents/builder/IDENTITY.md.j2` (MODIFIER)

**Instructions** :
1. Lire le fichier actuel
2. Ajouter une section **## Protocole tache Kaneo** :
   - "Quand tu recois une tache avec un `task_id` et `project_id`, tu DOIS :"
   - AU DEBUT : sessions_spawn(messenger, "start_timer taskId=<task_id>") + sessions_spawn(messenger, "update_status taskId=<task_id> status=in-progress")
   - PENDANT : sessions_spawn(messenger, "add_comment taskId=<task_id> text=<description du progres>") toutes les 15-20 minutes de travail effectif
   - A LA FIN : sessions_spawn(messenger, "stop_timer timeEntryId=<id>") + sessions_spawn(messenger, "add_link taskId=<task_id> url=<PR_ou_fichier> title=<description>") + sessions_spawn(messenger, "update_status taskId=<task_id> status=done")
   - SI REVIEW DEMANDEE : creer une sous-tache via Messenger, appeler delegate-n8n /webhook/code-review, loguer le resultat en commentaire via Messenger

---

### TASK-C3 : MAJ IDENTITY Writer + Explorer + Maintainer

**Fichiers** :
- `roles/openclaw/templates/agents/writer/IDENTITY.md.j2` (MODIFIER)
- `roles/openclaw/templates/agents/explorer/IDENTITY.md.j2` (MODIFIER)
- `roles/openclaw/templates/agents/maintainer/IDENTITY.md.j2` (MODIFIER)

**Instructions** :
1. Lire chaque fichier actuel
2. **Writer** : Ajouter section "## Protocole tache Kaneo" identique a Builder mais adapte :
   - Livrables = fichiers texte/docs dans workspace -> external-link vers le chemin du fichier
   - Writer n'a PAS exec donc il doit TOUJOURS passer par sessions_spawn(messenger)
3. **Explorer** : Ajouter section "## Protocole tache Kaneo" adapte :
   - Timer + rapport de recherche dans description via Messenger
   - External-links vers les sources trouvees
   - Explorer n'a PAS exec donc il doit TOUJOURS passer par sessions_spawn(messenger)
4. **Maintainer** : Ajouter section "## Protocole tache Kaneo" + :
   - Peut creer des taches de correction via Messenger (quand une erreur est detectee)
   - Sync agents -> Kaneo via Messenger
   - Maintainer A exec mais doit utiliser Messenger pour Kaneo (separation des responsabilites)

---

### TASK-C4 : MAJ HEARTBEAT.md.j2

**Fichier** : `roles/openclaw/templates/HEARTBEAT.md.j2` (MODIFIER)

**Instructions** :
1. Lire le fichier actuel
2. Ajouter une section :
```markdown
## Suivi projets Kaneo

1. `sessions_spawn(messenger, "Liste tous les projets actifs")` -> GET /api/project
2. Pour chaque projet avec des taches non terminees :
   - `sessions_spawn(messenger, "get_tasks projectId=<id>")` -> GET /api/task/tasks/:projectId
   - Analyser l'etat :
     - Taches in-progress depuis > 2h sans commentaire recent -> **alerter** sur Telegram
     - Toutes taches done -> **notifier recap** sur Telegram
     - Taches avec label "blocked" -> **escalader** sur Telegram
3. Max 3 projets actifs simultanement. Si > 3, le plus ancien non-urgent passe en attente.
```

---

## Lot D — Workflows n8n (pas de dependances directes)

### TASK-D1 : Realigner kaneo-agents-sync.json

**Fichier** : `roles/n8n-provision/files/workflows/kaneo-agents-sync.json` (MODIFIER)

**Instructions** :
1. Lire le fichier actuel
2. Lire la section "API Kaneo native" du plan pour les bons endpoints
3. **Probleme** : le workflow utilise `POST /api/tasks` (fictif). La vraie API est `POST /api/task/:projectId`
4. Modifier le workflow pour :
   - D'abord s'authentifier via BetterAuth (`POST /api/auth/sign-in`)
   - Chercher ou creer le projet "OpenClaw Agents" (`GET /api/project` ou `POST /api/project`)
   - Pour chaque agent dans la liste : creer/mettre a jour une tache (`POST /api/task/:projectId`)
   - Creer des labels (`POST /api/label`) au lieu de `tags`
   - Utiliser les vrais champs : title, description, priority (via `PUT /api/task/priority/:id`)
5. Auth via env vars : `KANEO_AGENT_EMAIL`, `KANEO_AGENT_PASSWORD`

---

### TASK-D2 : Realigner github-autofix.json

**Fichier** : `roles/n8n-provision/files/workflows/github-autofix.json` (MODIFIER)

**Instructions** :
1. Lire le fichier actuel
2. Meme realignement API que TASK-D1
3. Ajouter les operations Kaneo enrichies :
   - Au debut : `POST /api/time-entry` (startTime = now)
   - Quand la PR est creee : `POST /api/external-link` (lien vers la PR)
   - A la fin : `PUT /api/time-entry/:id` (endTime = now) + `POST /api/activity/comment` (resultat)
   - Ajouter les labels : `agent:builder`, `type:code`, `auto-fix`

---

### TASK-D3 : Creer le workflow code-review.json

**Fichier** : `roles/n8n-provision/files/workflows/code-review.json` (NOUVEAU)

**Instructions** :
1. Lire un workflow existant pour le pattern : `roles/n8n-provision/files/workflows/github-autofix.json`
2. Creer un workflow n8n avec :
   - **Trigger** : Webhook POST `/webhook/code-review`
   - **Input** : `{ repo_url, branch, task_id, project_id, secret }`
   - **Validation** : verifier le secret (X-Webhook-Secret header ET body.secret)
   - **Execution** : SSH vers RPi -> cloner/pull le repo -> executer une review via LiteLLM (modele gpt-codex ou glm-5)
   - **Criteres review** : extraits de CLAUDE.md (FQCN, changed_when, pas de hardcode, secrets vault, idempotence, images pinnees, healthchecks)
   - **Output Kaneo** : `POST /api/activity/comment` sur la tache avec le rapport review
   - **Reponse** : `{ status: "ok|ko", issues: [...], suggestions: [...] }`

---

### TASK-D4 : Creer le workflow error-to-task.json

**Fichier** : `roles/n8n-provision/files/workflows/error-to-task.json` (NOUVEAU)

**Instructions** :
1. Creer un workflow n8n avec :
   - **Trigger** : Webhook POST `/webhook/error-to-task`
   - **Input** : `{ error_message, source_task_id, project_id, agent_id, secret }`
   - **Execution** :
     - `POST /api/task/:projectId` -> creer tache de correction
     - `POST /api/label` -> labels `correction` + `agent:<agent_id>`
     - `POST /api/external-link` -> lien sur la tache source vers la correction
   - **Compteur Redis** : `INCR kaneo:corrections:<source_task_id>` -> si > 2, retourner erreur (boucle detectee)
   - **Reponse** : `{ status: "created", correction_task_id: "..." }`

---

### TASK-D5 : Creer le workflow project-status.json

**Fichier** : `roles/n8n-provision/files/workflows/project-status.json` (NOUVEAU)

**Instructions** :
1. Creer un workflow n8n avec :
   - **Trigger** : Webhook POST `/webhook/project-status`
   - **Input** : `{ project_id, secret }`
   - **Execution** :
     - `GET /api/task/tasks/:projectId` -> toutes les taches
     - Pour chaque tache : `GET /api/time-entry/task/:taskId` -> temps passe
     - Pour chaque tache : `GET /api/label/task/:taskId` -> labels (agent, type)
     - Pour chaque tache : `GET /api/external-link/task/:taskId` -> livrables
   - **Calculs** : temps total, temps par agent (group by label `agent:*`), nb livrables, nb taches done/total
   - **Reponse** : rapport JSON structure

---

### TASK-D6 : MAJ n8n-provision pour les 3 nouveaux workflows

**Fichiers** :
- `roles/n8n-provision/tasks/main.yml` (MODIFIER)
- `roles/n8n/templates/n8n.env.j2` (MODIFIER)

**Depend de** : TASK-D3, D4, D5

**Instructions** :
1. Lire `roles/n8n-provision/tasks/main.yml`
2. Ajouter les 3 nouveaux workflows dans les 4 listes du fichier :
   - Liste de copie des fichiers JSON
   - Liste des checksums
   - Liste d'import
   - Liste de publication
3. Noms : `code-review`, `error-to-task`, `project-status`
4. Dans `roles/n8n/templates/n8n.env.j2`, ajouter :
```
KANEO_API_URL=http://kaneo-api:1337
KANEO_AGENT_EMAIL={{ kaneo_agent_email }}
KANEO_AGENT_PASSWORD={{ kaneo_agent_password }}
```

---

## Lot E — Kaneo provisioning auth

### TASK-E1 : Ajouter les secrets Kaneo agent + provisioning

**Fichiers** :
- `inventory/group_vars/all/secrets.yml` (MODIFIER via ansible-vault)
- `roles/kaneo/defaults/main.yml` (MODIFIER)

**Instructions** :
1. `ansible-vault edit inventory/group_vars/all/secrets.yml`
2. Ajouter :
```yaml
vault_kaneo_agent_password: "<generer un mot de passe aleatoire fort>"
```
3. Dans `roles/kaneo/defaults/main.yml`, ajouter :
```yaml
kaneo_agent_email: "agent@internal.{{ domain_name }}"
kaneo_agent_password: "{{ vault_kaneo_agent_password }}"
```
4. Optionnel : ajouter une tache de provisioning dans `roles/kaneo/tasks/main.yml` pour creer le user agent via `POST /api/auth/sign-up` au premier deploiement (avec un flag `kaneo_agent_provisioned` dans un fichier sur le serveur pour ne pas recreer a chaque deploy)

---

## Lot F — Lint + Verification (apres tous les lots)

### TASK-F1 : Lint + dry run

**Instructions** :
1. `source .venv/bin/activate && make lint`
2. Corriger tous les warnings
3. `ansible-playbook playbooks/site.yml --check --diff --tags openclaw`
4. Verifier que les templates Jinja2 se rendent correctement

---

## Resume des dependances

```
Lot A (A1-A4) ──┐
                 ├──> Lot C (C1-C4) ──> Lot F
Lot B (B1-B2) ──┘

Lot D (D1-D6) ────────────────────────> Lot F

Lot E (E1) ────────────────────────────> Lot F
```

Lots A, B, D, E sont independants et parallelisables.
Lot C depend de A et B.
Lot F depend de tout.
