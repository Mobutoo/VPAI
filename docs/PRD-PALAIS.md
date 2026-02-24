# PRD — Palais v2.0

## Plateforme d'Intelligence Operationnelle pour Agents IA

---

## Context

L'integration Kaneo + OpenClaw est un anti-pattern : un outil de PM humain utilise comme backend d'orchestration IA, avec un agent-pont (Messenger/Hermes) comme seule interface. 6 points de defaillance par requete, auth cookie BetterAuth fragile via Redis, pas de temps-reel, API limitee. 50+ REX documentes.

**Palais** n'est pas un remplacement de Kaneo. C'est une nouvelle categorie : un **jumeau numerique de l'operation IA** — un cockpit qui voit, comprend, se souvient, et agit. Son nom evoque le QG d'un royaume technologique — un centre de commandement ou chaque agent a sa place, sa mission, et sa memoire.

---

## Vision

> Palais est le systeme nerveux central de la stack IA. Il ne se contente pas d'afficher des donnees — il les comprend, les correle, et alerte proactivement. Les agents IA ne sont pas des outils qu'on surveille : ce sont des coequipiers dont Palais gere la charge de travail, la memoire, et la performance.

### Les 7 piliers

| Pilier | Description |
|--------|-------------|
| **Task Management IA-natif** | Chaque tache a un cout estime, un score de confiance, une trace d'execution, un lien memoire, et un time tracking |
| **Observabilite LLM** | Traces d'execution (spans), couts par span, qualite scoree, correlation infra |
| **Knowledge Graph Temporel** | Memoire persistante — chaque action, erreur, resolution est un noeud requetable par les agents |
| **Intelligence Budgetaire** | Scheduling budget-aware + tracking des appels directs providers (hors LiteLLM) |
| **MCP-First** | Palais est un outil que les agents utilisent, pas juste un ecran qu'un humain regarde |
| **Time Tracking & Analytics** | Temps passe par tache/projet, iterations, ressources consommees, post-mortem automatique |
| **Livrables & Assets** | Fichiers attaches aux taches/projets, stockes localement, liens de telechargement |

---

## Utilisateur & Canaux

- **Solo** : un seul utilisateur principal
- **Multi-canal** : Telegram = conversationnel rapide. Palais = hub visuel. Les agents commandes depuis les deux
- **Digital Standup** : briefing matinal auto-genere → Telegram chaque matin

---

## Direction Design : Afrofuturisme — Le QG de Wakanda

### Philosophie

Palais s'inspire du laboratoire de Shuri et du QG de Black Panther : un centre de commandement technologique impregnee de culture africaine. Pas de smileys generiques — chaque element visuel est intentionnel, regal, et distinctif.

### Palette de couleurs

| Token | Couleur | Usage |
|-------|---------|-------|
| `--palais-bg` | `#0A0A0F` | Fond principal (noir profond, presque spatial) |
| `--palais-surface` | `#111118` | Cartes, panneaux, surfaces elevees |
| `--palais-surface-hover` | `#1A1A24` | Hover states |
| `--palais-border` | `#2A2A3A` | Bordures subtiles |
| `--palais-gold` | `#D4A843` | Accents primaires (vibranium/or), boutons, liens actifs |
| `--palais-gold-glow` | `#D4A843/20%` | Glow effect autour des elements actifs |
| `--palais-amber` | `#E8833A` | Alertes, warnings, elements urgents |
| `--palais-cyan` | `#4FC3F7` | Donnees, metriques, informations secondaires |
| `--palais-green` | `#4CAF50` | Succes, healthy, completed |
| `--palais-red` | `#E53935` | Erreurs, critical, chemin critique |
| `--palais-text` | `#E8E6E3` | Texte principal (blanc chaud, pas froid) |
| `--palais-text-muted` | `#8A8A9A` | Texte secondaire |

### Typographie

- **Titres / Navigation** : Police geometrique inspiree Wakanda (ex: **Orbitron**, **Exo 2**, ou font custom basee sur l'alphabet Wakanda). Caracteres angulaires, formes triangulaires
- **Corps de texte** : **Inter** ou **Plus Jakarta Sans** — lisible, moderne, sans serif
- **Code / Donnees** : **JetBrains Mono** — monospace pour traces, logs, metriques
- **Chiffres dashboard** : **Tabular nums** (chiffres alignes pour les metriques)

### Motifs & Elements visuels

- **Motifs Kuba** : Utilises en subtil sur les fonds de cartes, en bordures decoratives, comme separateurs de sections. Pas en plein ecran — en finition, comme un textile precieux
- **Symboles Adinkra** : Utilises comme icones de navigation au lieu de Lucide generique :
  - `Gye Nyame` (omnipotence) → Dashboard / Home
  - `Dwennimmen` (force humble) → Agents
  - `Nkyinkyim` (adaptabilite) → Projets (chemin sinueux = workflow)
  - `Sankofa` (apprendre du passe) → Knowledge Graph / Memoire
  - `Aya` (endurance) → Budget
  - `Akoma` (patience) → Boite a Idees
  - `Fawohodie` (liberte) → Missions
  - `Ananse Ntontan` (toile d'araignee, sagesse) → Insights
- **Hexagones** : Motif de fond subtil (comme les murs du labo de Shuri). Grille hexagonale en filigrane sur le dashboard
- **Effet glow** : Les elements actifs/selectionnes ont un glow dore subtil (comme le vibranium)
- **Cartes** : Bordure fine doree, coin legerement arrondis, ombre subtile avec teinte or

### Avatars des Agents

**Pas d'emoji. Pas de smiley.** Chaque agent a un **portrait genere** dans le style de l'image Black Panther :
- Style : masque/portrait regal, fond sombre, accents or
- Traits : inspires de la persona (Imhotep = egyptien ancien, Thot = ibis stylise, Basquiat = neo-expressionniste, R2D2 = cyberpunk, Piccolo = guerrier, etc.)
- Format : 256x256px, generes via l'agent Artist (Basquiat) + Seedream/DALL-E
- Stockes dans `{{ palais_assets_dir }}/avatars/`
- Fallback : initiales stylisees en or sur fond Kuba pattern

### Composants UI specifiques

- **Agent Card** : Fond sombre + bordure or animee quand l'agent est `busy` (pulse subtil). Avatar a gauche, statut + tache en cours a droite. Motif Kuba en filigrane
- **Boutons de controle** : Inspires du HUD holographique — bordure doree fine, fond transparent, texte or. Hover = glow ambre. Active = fill or avec texte noir
- **Jauges/Gauges** : Arcs circulaires avec motifs Adinkra integres. Remplissage dore anime
- **Timeline Gantt** : Barres dorees sur fond noir. Fleches de dependance en cyan. Chemin critique en rouge lumineux
- **Kanban** : Colonnes avec header orne d'un motif Kuba subtil. Cartes avec accent or a gauche (priorite)

---

## Stack Technique

| Couche | Technologie | Justification |
|--------|-------------|---------------|
| Framework | **SvelteKit 5** (runes `$state/$derived`) | Plus leger (~50MB), SSR natif, WebSocket dans `+server.ts` |
| ORM | **Drizzle ORM** | Type-safe, migrations SQL, PostgreSQL natif |
| DB relationnelle | **PostgreSQL** (instance partagee, DB `palais`) | Deja deploye |
| DB vectorielle | **Qdrant** (instance partagee, collection `palais_memory`) | Deja deploye — Knowledge Graph embeddings |
| UI | **shadcn-svelte** (customise theme Palais) + **Tailwind CSS 4** | Design system custom, accessible |
| Icons | **Symboles Adinkra custom SVG** + Lucide en fallback | Identite visuelle unique |
| Rich Text | **TipTap** | Descriptions, commentaires, briefings |
| Temps-reel | **WebSocket** → OpenClaw + **SSE** → Browser | Connexion directe sans intermediaire |
| Timeline | **Custom SVG** (d3-scale pour les axes) | Controle total, minimal deps |
| Embeddings | **LiteLLM** (text-embedding-3-small via API) | Pour le Knowledge Graph |
| Container | **Node.js 22 Alpine** | Single process, ~128MB max |
| Auth | **Cookie signe** (solo user, VPN-only) | Zero complexite |
| Protocole agents | **MCP Server** integre (JSON-RPC over stdio/SSE) | Les agents interrogent Palais comme un tool |

---

## Architecture

```
                    ┌──────────────────────────────────────┐
                    │              PALAIS                    │
                    │           (SvelteKit 5)               │
                    │                                       │
 Browser ◄──SSE───►│  Server                               │
                    │    │                                  │
                    │    ├── WebSocket ──► OpenClaw Gateway  │
                    │    ├── HTTP ──────► LiteLLM            │
                    │    ├── HTTP ──────► n8n (webhooks)     │
                    │    ├── TCP ───────► PostgreSQL          │
                    │    ├── HTTP ──────► Qdrant              │
                    │    └── MCP Server ◄── Agents (tools)   │
                    └──────────────────────────────────────┘
```

### Connexions

| Source → Destination | Protocole | Usage |
|---------------------|-----------|-------|
| Palais → OpenClaw Gateway (18789) | WebSocket | Statut agents, events sessions, dispatch |
| Palais → LiteLLM (4000) | HTTP | Brainstorming IA, embeddings, budget API |
| Palais → PostgreSQL (5432) | TCP/Drizzle | Donnees Palais + lecture sessions OpenClaw |
| Palais → Qdrant (6333) | HTTP | Knowledge Graph : store/query memoire |
| Palais → n8n (5678) | HTTP webhooks | Orchestration complexe |
| Palais → Browser | SSE | Push temps-reel (agent status, events) |
| Agents → Palais | MCP (JSON-RPC) | Query tasks, memory, budget, context |
| Caddy → Palais (3300) | HTTP reverse_proxy | `palais.<domain>` VPN-only |

---

## Modules

### Module 1 — Agent Cockpit (temps-reel + presence)

**But** : Voir en live ce que chaque agent fait, avec le niveau de detail d'un debugger.

**Fonctionnalites** :
- Grille 10 agents : carte avec statut live (`idle`/`busy`/`error`/`offline`), tache en cours, modele, tokens consommes
- **Presence agent** : les agents ont un "curseur" sur la tache qu'ils travaillent (comme Figma) — visuellement sur le Kanban, la carte pulse quand l'agent ecrit
- Feed d'activite live (scrollable, filtrable par agent)
- **Trace depliable** : clic sur une session → arbre de spans (chaque appel LLM, chaque tool call, chaque decision). Inspire Langfuse. Cout par span, latence, tokens
- Detail agent : historique sessions, performance (tokens/$ par tache), config modele, score qualite moyen

**Integration** :
- WebSocket → OpenClaw Gateway : events `session.*`, `agent.*`
- SSE → Browser : push statut + events
- PostgreSQL : table `agent_sessions`, `agent_spans`

**Donnees** :
```sql
agents
  id, name, persona, emoji, model, status, current_task_id
  total_tokens_30d, total_spend_30d, avg_quality_score
  last_seen_at, created_at

agent_sessions
  id, agent_id, task_id (nullable), mission_id (nullable)
  started_at, ended_at, status (running|completed|failed|timeout)
  total_tokens, total_cost, model, summary
  confidence_score (0.0-1.0, nullable)

agent_spans (observabilite LLM)
  id, session_id, parent_span_id (nullable, arbre)
  type (llm_call|tool_call|decision|delegation)
  name, input (JSONB), output (JSONB)
  model, tokens_in, tokens_out, cost
  started_at, ended_at, duration_ms
  error (JSONB, nullable)
```

---

### Module 2 — Knowledge Graph Temporel (memoire persistante)

**But** : Les agents et le systeme se souviennent de tout. Chaque action, erreur, resolution, decision humaine est un noeud requetable. Remplace TROUBLESHOOTING.md par une memoire vivante.

**Architecture** : Pattern hybride Zep + A-MEM
- **Noeuds episodiques** : evenements bruts (erreur Caddy 403, deploiement reussi, decision humaine)
- **Noeuds semantiques** : faits extraits (Caddy 403 = CIDR Docker manquant, Redis 8.0 = plus de rename-command)
- **Aretes temporelles** : chaque relation a un timestamp (validite temporelle)
- **Embeddings** : stockes dans Qdrant (collection `palais_memory`, 1536 dims)
- **Full-text** : index GIN PostgreSQL pour recherche textuelle

**Fonctionnalites** :
- **Ingestion automatique** : chaque evenement systeme (erreur, deploiement, completion de tache, commentaire) cree un noeud
- **Extraction semantique** : LLM extrait les triplets (sujet, relation, objet) des noeuds episodiques
- **Requete contextuelle** : "Qu'est-ce qui s'est passe la derniere fois que Caddy a donne un 403 ?" → traversee du graphe + recherche vectorielle
- **Enrichissement retroactif** : quand un nouveau noeud est ajoute, les liens avec les noeuds existants sont recalcules (pattern A-MEM)
- **UI** : page `/memory` — recherche semantique, graphe visuel interactif, timeline d'evenements
- **API MCP** : les agents interrogent la memoire avant d'agir (`memory.search`, `memory.recall`)

**Donnees** :
```sql
memory_nodes
  id, type (episodic|semantic|procedural)
  content, summary
  entity_type (agent|service|task|error|deployment|decision)
  entity_id (nullable)
  tags[], metadata (JSONB)
  embedding_id (ref Qdrant point ID)
  valid_from, valid_until (nullable — temporalite)
  created_at, created_by (user|agent|system)

memory_edges
  id, source_node_id, target_node_id
  relation (caused_by|resolved_by|related_to|learned_from|supersedes)
  weight (0.0-1.0, force de la relation)
  created_at

-- Qdrant collection
palais_memory:
  vectors: 1536 dims (text-embedding-3-small)
  payload: { node_id, type, entity_type, tags, valid_from }
```

---

### Module 3 — Boite a Idees (versioning de plans)

**But** : Pipeline d'ideation avec versioning. Les idees murissent dans le temps : Draft → Brainstorming → Plan v1/v2/vN → Approved → Dispatched → Archived.

**Fonctionnalites** :
- CRUD idees : titre + description rich text + tags + priorite + liens entre idees
- **Historique de versions** : chaque idee a N versions. Chaque version = snapshot complet (description, taches proposees, agents assignes, estimations couts)
- **Brainstorming assiste** : transition Draft → Brainstorming declenche le Mission Launcher
- **Diff entre versions** : voir ce qui a change entre v1 et v2
- **Lien memoire** : le brainstorming injecte le contexte du Knowledge Graph (projets similaires passes, REX pertinents)
- Approved → Dispatched cree automatiquement projet + taches + dispatch agents

**Donnees** :
```sql
ideas
  id, title, description, status (draft|brainstorming|planned|approved|dispatched|archived)
  priority, tags[], created_at, updated_at

idea_versions
  id, idea_id, version_number
  content_snapshot (JSONB)
  task_breakdown (JSONB: [{title, agent_id, description, depends_on[], cost_estimate, confidence}])
  brainstorming_log (JSONB: [{role, content, timestamp}])
  memory_context (JSONB: [node_ids injected from Knowledge Graph])
  created_at, created_by (user|ai)

idea_links
  id, source_idea_id, target_idea_id, link_type (related|blocks|inspires)
```

---

### Module 4 — Mission Launcher (co-planning + execution)

**But** : Flow brainstorming → plan → co-editing → dispatch → suivi. Pattern Magentic-UI : l'humain et l'IA co-editent le plan.

**Flow** :
1. **Brief** : texte libre ou selection depuis Boite a Idees
2. **Context injection** : Palais interroge le Knowledge Graph pour les projets similaires, les REX pertinents, les patterns connus
3. **Brainstorming** : LiteLLM pose des questions (1 a la fois), reponses utilisateur, conversation sauvegardee
4. **Plan** : Decomposition auto en taches avec :
   - Agent assigne propose (base sur personas + charge actuelle + budget restant)
   - Dependances identifiees
   - **Cout estime** par tache (base sur historique agent + modele)
   - **Score de confiance** (l'IA evalue sa propre certitude)
5. **Co-editing** : L'humain modifie le plan inline — reordonne taches, change agents, ajuste estimations, ajoute dependances. **Pas juste approve/reject.**
6. **Dispatch** : Taches creees, agents notifies via OpenClaw
7. **Suivi live** : Progression dans le cockpit, statuts mis a jour en temps-reel
8. **Post-mortem** : Mission completee → resume auto → noeud Knowledge Graph

**Donnees** :
```sql
missions
  id, title, idea_id (nullable), project_id
  status (briefing|brainstorming|planning|co_editing|approved|executing|review|completed|failed)
  brief_text, plan_snapshot (JSONB), total_estimated_cost
  created_at, completed_at, actual_cost

mission_conversations
  id, mission_id, role (user|assistant|system), content
  memory_refs (JSONB: [node_ids referenced]), created_at
```

---

### Module 5 — Project Board (Kanban + Timeline + Dependances)

**Toutes les fonctionnalites Kaneo + au-dela.**

#### Vue Kanban (inspiree Kaneo + Linear)
- Colonnes drag & drop : Backlog → Planning → Assigned → In Progress → Review → Done
- Colonnes personnalisables par projet
- **Presence agents** : la carte pulse si un agent y travaille (curseur Figma-like)
- **Badge confiance** : score de confiance IA affiche (vert > 0.8, orange 0.5-0.8, rouge < 0.5)
- **Badge cout** : cout reel vs estime sur chaque carte
- Actions rapides : statut, assignee, label, priorite

#### Vue Timeline / Gantt
- Barres taches (start_date → end_date) avec fleches dependances
- **Chemin critique** surligne en rouge
- Zoom jour/semaine/mois, drag pour modifier dates
- **Prediction duree** : basee sur l'historique de l'agent assigne (moy. temps par complexite)

#### Vue Liste
- Tableau filtrable/triable
- Filtres : agent, statut, priorite, label, projet, confiance, cout
- Selection multiple + bulk actions

#### Dependances
- Types : `finish-to-start` (defaut), `start-to-start`, `finish-to-finish`
- Validation anti-cycles (DFS)
- Blocage auto : tache bloquee si dependances non resolues
- **Cascade** : quand une tache critique glisse, les dependantes sont recalculees

#### Chemin Critique
- Algo : tri topologique + plus long chemin O(V+E), calcule on-demand, cache
- Rouge sur timeline + badge sur Kanban
- **Alerte** : si une tache du chemin critique est en retard → notification proactive

**Donnees** :
```sql
projects
  id, workspace_id, name, slug, icon, description, created_at, updated_at

columns
  id, project_id, name, position, is_final, color

tasks
  id, project_id, column_id, title, description (rich text)
  status, priority (none|low|medium|high|urgent)
  assignee_agent_id (FK agents), creator (user|agent|system)
  start_date, end_date, due_date, position
  estimated_cost, actual_cost, confidence_score
  mission_id (nullable), session_id (nullable — lien vers la trace d'execution)
  created_at, updated_at

task_dependencies
  id, task_id, depends_on_task_id
  dependency_type (finish-to-start|start-to-start|finish-to-finish)
  UNIQUE(task_id, depends_on_task_id)

labels
  id, workspace_id, name, color

task_labels
  task_id, label_id — PK composite

comments
  id, task_id, author_type (user|agent|system), author_agent_id (nullable)
  content (rich text), created_at

activity_log
  id, entity_type (task|project|idea|mission|agent), entity_id
  actor_type (user|agent|system), actor_agent_id (nullable)
  action, old_value, new_value, created_at
```

---

### Module 6 — Time Tracking & Analytics (post-mortem)

**But** : Mesurer le temps passe, les ressources consommees, et les iterations pour chaque tache et projet. Analyse retrospective automatique.

**Fonctionnalites** :
- **Timer automatique** : demarre quand un agent commence une tache (status → `in-progress`), s'arrete a `review`/`done`
- **Timer manuel** : l'utilisateur peut start/stop/pause un timer sur n'importe quelle tache
- **Temps par agent** : combien de temps chaque agent a passe sur le projet
- **Iterations** : compteur de re-ouvertures (tache passee de `done` a `in-progress` = 1 iteration)
- **Vue projet analytics** (`/projects/[id]/analytics`) :
  - Temps total du projet (somme des taches)
  - Temps par phase (Kanban column durations)
  - Nombre d'iterations avant livraison correcte
  - Cout total (LLM tokens + providers directs)
  - Graphique : temps estime vs temps reel
  - Top 3 taches les plus couteuses (temps + argent)
  - Ratio cout/iteration : combien coute chaque "re-do"
- **Post-mortem auto** : quand un projet passe en `Done`, Palais genere un rapport :
  - Resume du projet
  - Statistiques : duree, cout, iterations, agents impliques
  - Comparaison avec l'estimation initiale
  - Lecons apprises (injectees dans le Knowledge Graph)
  - Envoye sur Telegram + stocke comme noeud memoire

**Donnees** :
```sql
time_entries
  id, task_id, agent_id (nullable — null = timer manuel user)
  started_at, ended_at, duration_seconds
  type (auto|manual), notes (nullable)

task_iterations
  id, task_id, iteration_number
  reopened_at, reason (nullable)
  resolved_at (nullable)

project_analytics (vue materialisee ou cache)
  project_id, total_duration_seconds, total_cost
  total_iterations, avg_iteration_cost
  tasks_completed, tasks_failed
  agents_involved[], phases_duration (JSONB: {column_name: seconds})
  computed_at
```

---

### Module 7 — Livrables & Assets

**But** : Attacher des fichiers/livrables aux taches et projets. Stockage local sur le VPS, liens de telechargement via Caddy.

**Architecture stockage** : Utilise le repertoire workspace OpenClaw existant
```
{{ palais_data_dir }}/deliverables/
  ├── projects/
  │   └── <project_slug>/
  │       └── <task_id>/
  │           ├── rapport-final.pdf
  │           ├── design-v2.png
  │           └── code-review.md
  └── missions/
      └── <mission_id>/
          └── brief-approved.md
```

**Fonctionnalites** :
- Upload depuis l'UI (drag & drop sur une tache/projet)
- Upload depuis un agent (via API ou MCP tool `palais.deliverables.upload`)
- Lien de telechargement genere automatiquement (`https://palais.<domain>/dl/<token>`)
- Preview inline pour images/PDF/markdown
- Liste des livrables par tache et par projet
- Taille max par fichier : 50MB (configurable)
- Nettoyage : livrables des projets archives supprimes apres 90j (configurable)

**Integration** :
- Caddy sert les fichiers statiques via un handler dedie (`/dl/` route)
- Les agents deposent via `palais.deliverables.upload` (MCP) — le fichier est copie depuis le workspace OpenClaw
- Les workflows n8n (code-review, creative-pipeline) deposent le resultat comme livrable

**Donnees** :
```sql
deliverables
  id, entity_type (task|project|mission), entity_id
  filename, mime_type, size_bytes
  storage_path (chemin relatif dans palais_data_dir/deliverables/)
  download_token (UUID unique pour le lien public)
  uploaded_by_type (user|agent|system), uploaded_by_agent_id (nullable)
  created_at

-- Index sur download_token pour lookup rapide
```

---

### Module 8 — Budget Intelligence

**Pas juste un dashboard — un scheduler budget-aware avec tracking des appels directs.**

**Probleme** : LiteLLM gere son propre budget, mais les agents OpenClaw font des appels **directs** aux providers (OpenAI `gpt-4o-mini` en bypass LiteLLM quand les credits sont epuises). Ces couts sont invisibles.

**Solution** : Double source de donnees budget.

**Fonctionnalites** :
- Jauge budget jour ($5/jour), repartition par provider et par agent
- Historique 30 jours (graphique ligne)
- Alertes visuelles (vert/orange/rouge) + seuils configurables
- Toggle eco mode (webhook n8n `budget-control`)
- **Scheduling budget-aware** :
  - "Il reste $2.40. 5 taches en attente couteraient ~$3.80."
  - Classement par ratio priorite/cout
  - Suggestion : "Executer taches 1, 3, 5 maintenant ($2.10). Reporter 2, 4 a demain."
  - Option : switch auto vers eco models si budget < 20%
- **Prediction burn rate** : "Au rythme actuel, budget epuise a 16:45"
- **Cout par projet/mission** : agregation des couts de toutes les taches
- **Tracking appels directs providers** :
  - OpenAI : `GET /v1/organization/usage/completions` (API usage endpoint)
  - Anthropic : `GET /v1/messages/usage` (si disponible) ou scraping dashboard
  - OpenRouter : `GET /api/v1/auth/key` (retourne credits restants + usage)
  - Cron 1h : Palais pull les couts reels depuis chaque provider API
  - Delta = cout provider - cout LiteLLM = **appels directs non traces**
  - Affichage separe : "Via LiteLLM: $3.20 | Direct: $0.80 | Total: $4.00"

**Integration** :
- LiteLLM : `GET /global/spend/report`, `GET /spend/logs`
- Provider APIs : OpenAI Usage, OpenRouter Credits, Anthropic Usage
- Refresh toutes les 15min (LiteLLM) + 1h (providers directs)

**Donnees** :
```sql
budget_snapshots
  id, date, source (litellm|openai_direct|anthropic_direct|openrouter_direct)
  provider, agent_id (nullable)
  spend_amount, token_count, request_count
  captured_at

budget_forecasts
  id, date, predicted_spend, predicted_exhaustion_time
  remaining_budget, computed_at
```

---

### Module 9 — Proactive Intelligence (Digital Standup + Insights)

**But** : Palais ne se contente pas d'afficher — il comprend et alerte proactivement.

#### Digital Standup
- Chaque matin a 8h (configurable), Palais genere un briefing structure :
  - Taches completees depuis hier (avec cout et qualite)
  - Taches echouees (avec root cause si disponible dans le Knowledge Graph)
  - Budget : depense hier, restant aujourd'hui, prediction
  - Anomalies detectees (agent stuck, service down, pattern d'erreur recurrent)
  - **Priorites recommandees** pour la journee (basees sur dependances, chemin critique, budget)
- Envoye sur Telegram via n8n webhook
- Aussi affiche sur le dashboard `/` au login

#### Insights Proactifs
- **Agent stuck** : "Builder travaille sur tache X depuis 2h. Root cause probable : OpenRouter 402. Action : [switch eco model] [restart] [escalate]"
- **Pattern d'erreur** : "3eme erreur 403 Caddy cette semaine. Cause connue : CIDR Docker. [Voir resolution]" (lien Knowledge Graph)
- **Budget warning** : "Budget a 85%. 3 taches high-priority en queue. Suggestion : reporter les taches low-priority"
- **Dependance critique** : "Tache Y (chemin critique) bloquee par tache X (assignee a Agent Z qui est offline). [Reassigner] [Notifier]"
- UI : banniere en haut du dashboard + section insights sur la page d'accueil

**Donnees** :
```sql
insights
  id, type (agent_stuck|budget_warning|error_pattern|dependency_blocked|standup)
  severity (info|warning|critical)
  title, description, suggested_actions (JSONB: [{label, action_type, params}])
  entity_type, entity_id (lien vers tache/agent/projet concerne)
  memory_refs (JSONB: [node_ids du Knowledge Graph])
  acknowledged (boolean), created_at
```

---

### Module 10 — MCP Server (Palais comme tool pour les agents)

**But** : Les agents IA interrogent Palais comme un outil, pas juste les humains via le browser.

**Protocole** : MCP (Model Context Protocol) — JSON-RPC over SSE (transport HTTP standard)

**Tools exposes** :
```
palais.tasks.list         → Lister taches (filtres: project, status, agent, priority)
palais.tasks.create       → Creer tache
palais.tasks.update       → Modifier statut, assignee, description
palais.tasks.comment      → Ajouter commentaire
palais.tasks.start_timer  → Demarrer timer sur une tache
palais.tasks.stop_timer   → Arreter timer sur une tache
palais.projects.list      → Lister projets
palais.projects.create    → Creer projet
palais.projects.analytics → Statistiques projet (temps, cout, iterations)
palais.agents.status      → Statut de tous les agents
palais.agents.available   → Agents disponibles (idle + budget suffisant)
palais.budget.remaining   → Budget restant aujourd'hui
palais.budget.estimate    → Estimer cout d'une tache
palais.deliverables.upload → Uploader un livrable vers une tache/projet
palais.deliverables.list   → Lister les livrables d'une tache/projet
palais.memory.search      → Recherche semantique dans le Knowledge Graph
palais.memory.recall      → Rappeler un noeud specifique
palais.memory.store       → Stocker un nouveau noeud memoire
palais.insights.active    → Insights non-acquittes
palais.standup.latest     → Dernier briefing genere
```

**Usage** : Le skill OpenClaw `palais-bridge` utilise ces MCP tools au lieu de curl brut. N'importe quel agent peut interroger Palais pour du contexte avant d'agir.

**Integration Ansible** : Le MCP server est expose sur un port interne (ex: 3301) accessible uniquement sur le reseau `backend`.

---

### Module 11 — Multi-Node Health + VPN Topology

**But** : Surveiller l'ensemble de l'infrastructure repartie, pas juste le VPS.

**3 noeuds surveilles** :
- **Sese-AI (VPS)** : OpenClaw, LiteLLM, n8n, PostgreSQL, Redis, Qdrant, Caddy, monitoring
- **RPi5 (Workstation)** : ComfyUI, Remotion, OpenCode, Claude Code, Caddy workstation
- **Seko-VPN** : Headscale, Zerobyte, webhook relay

**Fonctionnalites** :
- Carte reseau VPN visuelle (topologie Headscale — qui est connecte, latence entre noeuds)
- Statuts par noeud : services up/down, CPU/RAM/temp (Pi), uptime
- **Correlation** : "LLM quality dropped at 14:30" + "OpenRouter latency spike at 14:28" → alerte
- **Backup status** : dernier backup Zerobyte, prochain schedule, espace restant
- Lien direct Grafana pour le detail
- Alertes visuelles si noeud deconnecte ou service down

**Integration** :
- Headscale API (`/api/v1/machine`) : liste noeuds, IPs, derniere connexion
- n8n `stack-health` workflow : health check 6+ services (existant)
- SSH vers Pi pour metriques locales (ou agent leger heartbeat)
- Zerobyte API ou fichier status pour backup info

**Donnees** :
```sql
nodes
  id, name (sese-ai|rpi5|seko-vpn), tailscale_ip
  status (online|offline), last_seen_at
  cpu_percent, ram_percent, disk_percent, temperature (nullable)

health_checks
  id, node_id, service_name, status, response_time_ms
  checked_at, details (JSONB)

backup_status
  id, node_id (seko-vpn), last_backup_at, next_backup_at
  size_bytes, status (ok|failed|running), details (JSONB)
```

---

### Module 12 — Atelier Creatif (Pipeline ComfyUI + Remotion)

**But** : Dashboard natif pour le pipeline creatif reparti sur le Pi.

**Fonctionnalites** :
- **Queue ComfyUI** : taches de generation d'images en cours, en attente, terminees
  - Preview temps-reel de l'image en cours de generation
  - Historique des generations avec thumbnails
  - One-click "genere une image" avec prompt → envoye au Pi via VPN
- **Remotion render** : videos en cours de rendu, progression, preview
  - Declenchement depuis une tache Palais → n8n `creative-pipeline` → Pi
- **Galerie d'assets** : tous les assets generes, filtrables par type/date/projet
  - Attaches automatiquement comme livrables aux taches source
- **Modeles/Workflows ComfyUI** : liste des workflows disponibles, selection rapide

**Integration** :
- ComfyUI API : `http://{{ workstation_pi_tailscale_ip }}:8188/` (via VPN)
  - `/system_stats` : status, queue, GPU
  - `/prompt` : soumettre un workflow
  - `/history` : resultats
- Remotion : via n8n workflow `creative-pipeline`
- Assets stockes dans `{{ palais_data_dir }}/deliverables/creative/`

---

### Module 13 — Integration Claude Code (MCP bidirectionnel)

**But** : Claude Code sur le Pi et Palais se parlent nativement via MCP.

**Direction 1 : Claude Code → Palais (Claude Code consomme Palais MCP)**
- Quand tu codes sur le Pi, Claude Code peut interroger Palais :
  - "Quelles taches sont en cours pour le projet X ?"
  - "Quel est le dernier REX lie a Caddy ?" (Knowledge Graph)
  - "Quel agent travaille sur quoi en ce moment ?"
- Config MCP dans `~/.claude/servers/palais.json` sur le Pi :
  ```json
  { "url": "https://palais.<domain>/api/mcp/sse", "headers": {"X-API-Key": "..."} }
  ```

**Direction 2 : Palais → Claude Code (declenchement de sessions)**
- Depuis une tache Palais : "Implementer feature X" → bouton [Lancer Claude Code]
- Palais trigger via SSH ou n8n workflow :
  - SSH vers Pi → `claude-code --task "..." --context-from palais`
  - Claude Code execute, cree un commit/PR
  - n8n `code-review` workflow valide
  - Resultat → livrable attache a la tache, statut mis a jour
- Boucle complete : **Tache Palais → Claude Code → PR → Review → Deploy → Done**

**Integration** :
- SSH vers Pi (cle deploye par Ansible, deja en place pour n8n workflows)
- MCP SSE transport (Palais expose deja le serveur MCP)
- n8n `github-autofix` workflow (existant, a adapter)

---

### Module 14 — War Room (mode mission majeure)

**But** : Vue immersive pour les missions complexes qui mobilisent plusieurs noeuds et agents simultanement.

**Declenchement** : Quand une mission a 5+ taches paralleles ou implique le Pi + VPS.

**Layout War Room** :
```
┌──────────────────────────────────────────────────────────┐
│  WAR ROOM — Mission "Campagne Marketing Q1"              │
├────────────────────┬─────────────────────────────────────┤
│  AGENTS VPS        │  OUTILS PI                          │
│  ┌──────────────┐  │  ┌────────────────────┐             │
│  │ Builder [■■░] │  │  │ ComfyUI: 3/5 images│             │
│  │ Writer  [■░░] │  │  │ Remotion: rendering│             │
│  │ Artist  [■■■] │  │  │ Claude Code: idle  │             │
│  └──────────────┘  │  └────────────────────┘             │
├────────────────────┴─────────────────────────────────────┤
│  TIMELINE LIVE                                            │
│  ═══■═══════░░░░░░░░  42% complete  Budget: $1.80/$5.00  │
├──────────────────────────────────────────────────────────┤
│  FEED TEMPS-REEL                                          │
│  14:32 Artist genera image hero banner [preview]          │
│  14:31 Writer complete le script video                    │
│  14:28 Builder commit feature-auth PR #47                 │
└──────────────────────────────────────────────────────────┘
```

**Fonctionnalites** :
- Vue split : agents VPS a gauche, outils Pi a droite
- Timeline live de la mission avec progression par tache
- Budget en temps reel qui se decompte
- Feed d'activite temps-reel agrege (tous noeuds)
- Alertes si un noeud decroche ou un agent est stuck
- Boutons d'action rapide : [Pause mission] [Reassigner] [Eco mode] [Escaler]

---

### Module 15 — Backup Intelligent (Zerobyte)

**But** : Integrer Zerobyte dans le cycle de vie des projets.

**Fonctionnalites** :
- Statut backup visible dans Health dashboard (dernier, prochain, espace)
- **Backup post-projet** : quand un projet passe en "Done", Palais declenche un backup incremental
- **Restauration livrables** : si un fichier est supprime, restaurer depuis Zerobyte
- Alerte si dernier backup > 24h
- Historique backups avec taille et duree

**Integration** :
- Zerobyte API ou SSH vers Seko-VPN pour trigger/status
- n8n workflow dedie (ou appel direct SSH depuis Palais via VPN)

---

## Routes SvelteKit

```
/                            → Dashboard (agents grid + insights + budget gauge + standup)
/ideas                       → Boite a Idees (pipeline visuel)
/ideas/[id]                  → Detail idee + versions + brainstorming
/missions                    → Missions actives + historique
/missions/new                → Nouveau brief (ou depuis idee)
/missions/[id]               → Flow co-planning → execution → resultats
/projects                    → Liste projets
/projects/[id]               → Kanban (defaut) + toggle Timeline / Liste
/projects/[id]/timeline      → Gantt + dependances + chemin critique
/projects/[id]/list          → Liste filtrable
/projects/[id]/analytics     → Post-mortem : temps, cout, iterations, performance
/projects/[id]/deliverables  → Livrables du projet (galerie fichiers)
/agents                      → Cockpit (grille temps-reel)
/agents/[id]                 → Detail agent (sessions, traces, perf, qualite)
/agents/[id]/traces/[sid]    → Trace detaillee (arbre de spans)
/budget                      → Dashboard budget + scheduler + predictions + tracking direct
/memory                      → Knowledge Graph (recherche + graphe visuel + timeline)
/health                      → Stack health + correlation
/insights                    → Centre d'insights proactifs
/settings                    → Config (agents, modeles, budgets, colonnes, standup, avatars)
```

---

## API REST (palais-bridge + n8n)

```
# Health
GET    /api/health

# Agents
GET    /api/v1/agents
GET    /api/v1/agents/:id
GET    /api/v1/agents/:id/sessions
GET    /api/v1/agents/:id/sessions/:sid/spans

# Projects
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/:id/tasks
POST   /api/v1/projects/:id/tasks
GET    /api/v1/projects/:id/critical-path

# Tasks
PUT    /api/v1/tasks/:id
POST   /api/v1/tasks/:id/comments
POST   /api/v1/tasks/:id/dependencies
DELETE /api/v1/tasks/:id/dependencies/:depId

# Time Tracking
POST   /api/v1/tasks/:id/timer/start
POST   /api/v1/tasks/:id/timer/stop
GET    /api/v1/tasks/:id/time-entries
GET    /api/v1/projects/:id/analytics

# Deliverables
GET    /api/v1/tasks/:id/deliverables
POST   /api/v1/tasks/:id/deliverables       (multipart)
GET    /api/v1/projects/:id/deliverables
GET    /dl/:token                            (public, token-based)

# Ideas
GET    /api/v1/ideas
POST   /api/v1/ideas
PUT    /api/v1/ideas/:id
POST   /api/v1/ideas/:id/versions

# Missions
GET    /api/v1/missions
POST   /api/v1/missions
PUT    /api/v1/missions/:id

# Budget
GET    /api/v1/budget/summary
GET    /api/v1/budget/by-agent
GET    /api/v1/budget/by-provider
GET    /api/v1/budget/forecast
POST   /api/v1/budget/schedule

# Memory (Knowledge Graph)
POST   /api/v1/memory/search
GET    /api/v1/memory/nodes/:id
POST   /api/v1/memory/nodes
GET    /api/v1/memory/graph/:entityId

# Insights
GET    /api/v1/insights
PUT    /api/v1/insights/:id/acknowledge
GET    /api/v1/standup/latest

# MCP (JSON-RPC over SSE)
POST   /api/mcp
GET    /api/mcp/sse
```

Auth : `X-API-Key` header pour machine (n8n, OpenClaw skill). Cookie signe pour browser.

---

## Workflows n8n

| Workflow | Action |
|----------|--------|
| `budget-monitor` | **Conserve** + webhook Palais pour refresh |
| `budget-control` | **Conserve** — Telegram /budget |
| `stack-health` | **Conserve** + webhook Palais pour refresh |
| `code-review` | **Adapte** → Palais API |
| `error-to-task` | **Adapte** → Palais API + cree noeud Knowledge Graph |
| `creative-pipeline` | **Conserve** — Palais declenche via webhook |
| `plan-dispatch` | **Remplace** — Palais dispatch directement |
| `kaneo-agents-sync` | **Supprime** |
| `kaneo-sync` | **Supprime** |
| `project-status` | **Adapte** → Palais API |
| **NOUVEAU** `palais-standup` | Cron 8h → Palais `/api/v1/standup/latest` → Telegram |
| **NOUVEAU** `palais-insight-alert` | Webhook Palais (insight critical) → Telegram |
| Autres (ai-*, cve-*, ig-*, email-*) | **Conserves** tels quels |

---

## Skill OpenClaw : `palais-bridge`

Remplace `kaneo-bridge`. Differences majeures :

| Aspect | kaneo-bridge (ancien) | palais-bridge (nouveau) |
|--------|----------------------|---------------------|
| Auth | Cookie BetterAuth + Redis TTL 40min | API key statique `X-API-Key` |
| Transport | curl HTTP | MCP JSON-RPC (ou HTTP fallback) |
| Endpoint | `http://kaneo-api:1337` | `http://palais:3300/api/mcp` |
| Memoire | Aucune | `palais.memory.search` + `palais.memory.store` |
| Budget | Aucun | `palais.budget.remaining` + `palais.budget.estimate` |
| Confiance | Aucune | Score confiance retourne avec chaque completion |

---

## Ansible Role : `roles/palais/`

```
roles/palais/
├── defaults/main.yml           # port, subdomain, agents list, DB, Qdrant collection, standup_hour
├── vars/main.yml
├── tasks/main.yml              # Dirs, build Docker, env, DB+Qdrant init, seed agents, Caddy
├── handlers/main.yml           # Restart container
├── templates/
│   ├── palais.env.j2           # Toutes les connexions services
│   ├── Dockerfile.j2           # Multi-stage: install → build → runtime Node.js 22 Alpine
│   └── palais-bridge/SKILL.md.j2   # Skill OpenClaw pour le Messenger
└── files/
    └── app/                    # Code source SvelteKit
```

### Docker Compose (Phase B)

```yaml
palais:
  build:
    context: "{{ palais_app_dir }}"
    dockerfile: Dockerfile
  container_name: "{{ project_name }}_palais"
  restart: unless-stopped
  networks: [frontend, backend]
  volumes:
    - "{{ palais_data_dir }}/deliverables:/data/deliverables"
    - "{{ palais_data_dir }}/avatars:/data/avatars"
  environment:
    DATABASE_URL: "postgresql://{{ palais_db_user }}:{{ palais_db_password }}@postgresql:5432/{{ palais_db_name }}"
    OPENCLAW_WS_URL: "ws://openclaw:18789"
    LITELLM_URL: "http://litellm:4000"
    LITELLM_KEY: "{{ litellm_master_key }}"
    QDRANT_URL: "http://qdrant:6333"
    QDRANT_COLLECTION: "palais_memory"
    N8N_WEBHOOK_BASE: "http://n8n:5678/webhook"
    PALAIS_API_KEY: "{{ vault_palais_api_key }}"
    ORIGIN: "https://{{ palais_subdomain }}.{{ domain_name }}"
    STANDUP_HOUR: "{{ palais_standup_hour | default('08') }}"
  mem_limit: 192m
  cpus: "0.75"
  cap_drop: [ALL]
  cap_add: [CHOWN, SETGID, SETUID]
  security_opt: ["no-new-privileges:true"]
  healthcheck:
    test: ["CMD", "node", "-e", "fetch('http://localhost:3300/api/health').then(r=>{if(!r.ok)throw 1})"]
    interval: 30s
    timeout: 5s
    retries: 3
  logging:
    driver: json-file
    options: { max-size: "10m", max-file: "3" }
```

### Caddy

```caddyfile
{{ palais_subdomain }}.{{ domain_name }} {
    import vpn_only
    import vpn_error_page
    import security_headers
    reverse_proxy palais:3300
}
```

---

## Fichiers critiques a modifier

| Fichier | Action |
|---------|--------|
| `roles/postgresql/defaults/main.yml` | Ajouter DB `palais` a `postgresql_databases` |
| `roles/docker-stack/templates/docker-compose.yml.j2` | Ajouter service `palais`, retirer `kaneo-api` + `kaneo-web` |
| `roles/caddy/templates/Caddyfile.j2` | Ajouter block `palais.<domain>`, retirer block `hq.<domain>` |
| `inventory/group_vars/all/versions.yml` | Retirer images Kaneo |
| `inventory/group_vars/all/main.yml` | Ajouter variables `palais_*`, retirer variables `kaneo_*` |
| `inventory/group_vars/all/secrets.yml` | Ajouter `vault_palais_api_key`, `vault_palais_db_password` |
| `roles/openclaw/templates/skills/kaneo-bridge/` | Remplacer par `palais-bridge/` |
| `roles/openclaw/templates/agents/messenger/IDENTITY.md.j2` | Adapter pour Palais API |
| `roles/n8n-provision/files/workflows/` | Adapter workflows Kaneo → Palais |
| `playbooks/site.yml` | Ajouter role `palais`, retirer role `kaneo` |

---

## Definition of Done

### Phase 1 — Fondations + Design System (Semaine 1-2)
- [ ] Repo SvelteKit initialise avec Drizzle + shadcn-svelte + Tailwind 4
- [ ] **Theme Palais** : palette Afrofuturiste (noir/or/ambre/cyan), tokens CSS custom
- [ ] **Police Wakanda** : font geometrique pour titres (Orbitron ou custom), Inter pour body
- [ ] **Icones Adinkra** : set SVG custom pour la navigation (8 symboles)
- [ ] Schema DB complet migre (toutes les tables incluant time_entries, deliverables)
- [ ] Role Ansible fonctionnel (build Docker, env, DB creation, Caddy)
- [ ] API REST `/api/health` + CRUD projets/taches
- [ ] Auth cookie signe + API key
- [ ] Seed 10 agents avec avatars placeholder
- [ ] Collection Qdrant `palais_memory` creee
- [ ] Dashboard `/` avec layout Afrofuturiste (grille hexagonale en filigrane)
- [ ] Volume `{{ palais_data_dir }}/deliverables/` cree et monte

### Phase 2 — Agent Cockpit + Avatars (Semaine 3)
- [ ] WebSocket connecte a OpenClaw Gateway
- [ ] Grille agents avec statut live — cartes style Palais (bordure or, pulse quand busy)
- [ ] **Avatars agents generes** : 10 portraits style Black Panther (generes via Artist/Seedream)
- [ ] Feed d'activite temps-reel (SSE → browser)
- [ ] Page detail agent avec sessions
- [ ] Presence agent : curseur Figma-like sur les taches

### Phase 3 — Project Board Kanban (Semaine 4-5)
- [ ] Vue Kanban drag & drop — colonnes avec header Kuba, cartes avec accent or
- [ ] CRUD taches complet (creer, editer, deplacer, supprimer)
- [ ] Commentaires rich text TipTap
- [ ] Activity log automatique
- [ ] Labels, priorites, filtres
- [ ] Vue Liste filtrable

### Phase 4 — Dependances & Timeline (Semaine 6)
- [ ] Task dependencies (finish-to-start, etc.)
- [ ] Validation anti-cycles
- [ ] Blocage automatique
- [ ] Vue Gantt SVG — barres dorees, fleches cyan, chemin critique rouge lumineux
- [ ] Chemin critique (algo + UI rouge)
- [ ] Drag dates sur timeline

### Phase 5 — Boite a Idees + Mission Launcher (Semaine 7-8)
- [ ] CRUD idees + pipeline visuel
- [ ] Historique versions + diff
- [ ] Brainstorming LiteLLM (questions 1 par 1, sauvegarde)
- [ ] Co-editing du plan (modifications inline par l'humain — pas juste approve/reject)
- [ ] Dispatch automatique (Approved → taches + agents)
- [ ] Suivi live execution

### Phase 6 — Time Tracking & Livrables (Semaine 9)
- [ ] Timer auto (demarre quand agent commence tache, arrete quand done)
- [ ] Timer manuel (start/stop/pause depuis l'UI)
- [ ] Compteur d'iterations (re-ouvertures done → in-progress)
- [ ] Vue analytics projet (`/projects/[id]/analytics`) : temps, cout, iterations, phases
- [ ] Post-mortem auto : rapport genere quand projet termine → Knowledge Graph + Telegram
- [ ] Upload livrables (drag & drop UI + API + MCP tool)
- [ ] Liens de telechargement via Caddy (`/dl/:token`)
- [ ] Preview inline (images, PDF, markdown)
- [ ] Galerie livrables par projet

### Phase 7 — Budget Intelligence (Semaine 10)
- [ ] Dashboard budget (jauge, par agent/provider, historique 30j)
- [ ] **Tracking appels directs** : pull OpenAI/Anthropic/OpenRouter usage APIs
- [ ] Affichage "Via LiteLLM / Direct / Total"
- [ ] Scheduling budget-aware (priorisation par ratio priorite/cout)
- [ ] Prediction burn rate
- [ ] Toggle eco mode
- [ ] Cout estime vs reel sur chaque tache

### Phase 8 — Knowledge Graph (Semaine 11-12)
- [ ] Ingestion auto : evenements → noeuds episodiques
- [ ] Extraction semantique : LLM → triplets
- [ ] Stockage Qdrant embeddings + PostgreSQL relations
- [ ] API `/memory/search` (recherche semantique)
- [ ] UI `/memory` : recherche + graphe visuel style Afrofuturiste (noeuds or, aretes cyan)
- [ ] Enrichissement retroactif (re-linking)

### Phase 9 — Observabilite LLM (Semaine 13)
- [ ] Table `agent_spans` avec arbre de spans
- [ ] Ingestion spans depuis OpenClaw sessions
- [ ] UI trace depliable (arbre spans, cout/span, latence) — style holographique
- [ ] Score confiance sur les taches
- [ ] Badge presence agent sur Kanban

### Phase 10 — MCP Server (Semaine 14)
- [ ] MCP endpoint JSON-RPC over SSE
- [ ] Tools : palais.tasks.*, palais.agents.*, palais.memory.*, palais.budget.*, palais.deliverables.*
- [ ] Skill `palais-bridge` OpenClaw utilisant MCP
- [ ] Test : agent interroge Palais pour contexte avant execution

### Phase 11 — Proactive Intelligence (Semaine 15)
- [ ] Digital Standup : generation auto + envoi Telegram
- [ ] Insights : agent stuck, pattern erreur, budget warning, dependance critique
- [ ] UI insights (banniere + page dediee)
- [ ] Actions suggerees sur chaque insight

### Phase 12 — Integration n8n + OpenClaw (Semaine 16)
- [ ] Workflows adaptes (code-review, error-to-task, project-status → Palais API)
- [ ] Workflows supprimes (kaneo-*)
- [ ] Nouveaux workflows (palais-standup, palais-insight-alert)
- [ ] IDENTITY.md Messenger adapte
- [ ] Test E2E : Telegram → Concierge → Builder → tache Palais completee

### Phase 13 — Multi-Node Health + Atelier Creatif (Semaine 17-18)
- [ ] Modele `nodes` + `backup_status` en DB
- [ ] Integration Headscale API : topologie VPN, noeuds connectes
- [ ] Health check multi-noeud : VPS + Pi + Seko-VPN
- [ ] Carte reseau VPN visuelle (style Afrofuturiste — noeuds or, liens cyan)
- [ ] Backup Zerobyte : statut, alerte si > 24h, declenchement post-projet
- [ ] Dashboard Atelier : queue ComfyUI, galerie assets, Remotion renders
- [ ] One-click generation image (prompt → ComfyUI Pi via VPN)
- [ ] Assets generes automatiquement attaches comme livrables

### Phase 14 — Integration Claude Code MCP (Semaine 19)
- [ ] Config MCP server Palais dans `~/.claude/servers/palais.json` sur le Pi
- [ ] Claude Code peut querier : taches, projets, memory, agents via MCP
- [ ] Bouton [Lancer Claude Code] sur les taches de type "code"
- [ ] SSH vers Pi → session Claude Code avec contexte Palais injecte
- [ ] Boucle : tache → Claude Code → PR → code-review → deploy → tache done
- [ ] Test E2E : tache Palais "fix bug X" → Claude Code cree PR → review OK → done

### Phase 15 — War Room (Semaine 20)
- [ ] Mode War Room activable sur les missions complexes (5+ taches paralleles)
- [ ] Layout split : agents VPS | outils Pi
- [ ] Timeline live mission avec progression par tache
- [ ] Budget live qui se decompte
- [ ] Feed agrege multi-noeud
- [ ] Boutons action rapide : pause, reassigner, eco mode, escaler

### Phase 16 — Nettoyage + Migration (Semaine 21)
- [ ] Script migration donnees Kaneo → Palais (taches, projets, commentaires)
- [ ] Role Kaneo desactive
- [ ] Images Kaneo retirees de versions.yml
- [ ] DB `kaneo` en backup (pas supprimee)
- [ ] TROUBLESHOOTING.md : sections Kaneo archivees, sections Palais ajoutees
- [ ] Import REX existants dans Knowledge Graph (seed initial memoire)

### Criteres transversaux
- [ ] Idempotence Ansible : 0 changed a la 2eme execution
- [ ] Container : cap_drop ALL, no-new-privileges, mem_limit 192m
- [ ] Healthcheck Docker fonctionnel
- [ ] VPN-only verifie (acces bloque hors VPN)
- [ ] Mobile responsive
- [ ] Pas de valeur hardcodee (variables Jinja2)
- [ ] Keyboard shortcuts (style Linear : K pour Kanban, T pour Timeline, etc.)
- [ ] Tests Molecule pour le role Ansible
- [ ] **Design Afrofuturiste coherent** : toutes les pages suivent la palette + motifs Kuba/Adinkra
- [ ] **Avatars agents** : 10 portraits generes et deployes
- [ ] **Zero smiley/emoji generique** dans l'UI

---

## Risques et Mitigations

| Risque | Impact | Mitigation |
|--------|--------|-----------|
| WebSocket OpenClaw non documente | High | Reverse-engineer via logs. Fallback : polling HTTP sessions toutes les 10s |
| Knowledge Graph couteux en embeddings | Medium | Batch les embeddings. `text-embedding-3-small` ($0.02/1M tokens). ~$0.50/mois |
| VPS RAM 8GB partage | Medium | Container 192MB max. Qdrant deja deploye. Pas de nouveau service lourd |
| SvelteKit / Svelte 5 nouveau | Low | shadcn-svelte fournit les composants. Svelte 5 plus simple que React |
| Chemin critique complexe | Low | Algo O(V+E), cache. Projets < 100 taches |
| Migration Kaneo | Low | Script SQL one-shot, donnees conservees en backup |
| LLM-as-a-judge qualite/cout | Medium | Sampling (1 output sur 10), modele eco pour le scoring |
| Provider usage APIs instables | Medium | Fallback gracieux si API indisponible. Estimation basee sur tokens LiteLLM |
| Generation avatars couteuse | Low | Generer 1 fois, stocker. 10 images = ~$0.40 via DALL-E 3 |

---

## Hors scope v2 (backlog futur)

- Multi-utilisateurs / gestion d'equipe
- App mobile native (le responsive suffit)
- Integration GitHub directe (reste via n8n)
- Notifications push navigateur (WebPush)
- Fine-tuning de modeles base sur les scores qualite
- Canvas/whiteboard visuel (Excalidraw-like)
- Import/export CSV/JSON
- Integration calendrier
- Animations transitions entre pages (Svelte transitions)
- Mode sombre/clair toggle (Palais est toujours sombre — c'est son identite)

---

## Verification

Pour valider le deploiement complet :

```bash
# 1. Role Ansible
make deploy-role ROLE=palais ENV=prod

# 2. Container running
ssh prod 'docker ps | grep palais'
# → healthy

# 3. Health check
curl -sf https://palais.<domain>/api/health
# → {"status":"ok"}

# 4. API avec cle
curl -H "X-API-Key: <key>" https://palais.<domain>/api/v1/agents
# → 10 agents

# 5. WebSocket OpenClaw
# → Verifier dans les logs Palais que la connexion WS est etablie

# 6. Knowledge Graph
curl -H "X-API-Key: <key>" -X POST https://palais.<domain>/api/v1/memory/search \
  -d '{"query": "Caddy 403"}'
# → Noeuds pertinents retournes

# 7. MCP
# → Depuis un agent OpenClaw : palais.tasks.list retourne des resultats

# 8. E2E
# → Envoyer "cree un projet test" sur Telegram → Concierge → Palais → tache visible dans le dashboard
```
