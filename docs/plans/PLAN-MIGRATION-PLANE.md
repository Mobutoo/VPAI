# Plan Migration : Plane comme Mission Control

> **Objectif** : Plane devient l'outil de gestion de projet, les agents OpenClaw restent les exécutants.
> **Date** : 2026-02-28
> **Statut** : Draft — Plan infaillible

---

## Vision Stratégique

### Problème actuel

**Palais** est un cockpit IA-natif excellent pour l'observabilité et la télémétrie, mais :
- Interface trop technique pour collaboration humaine
- Pas conçu pour PM multi-projets avec équipes mixtes (humains + agents)
- Manque de features PM standards (roadmaps, gantt, dependencies)

**Plane** est un PM tool mature avec :
- UI/UX moderne et collaborative
- Features riches (Cycles, Modules, Views, Analytics, Pages)
- Open source + self-hostable
- API REST complète

### Solution : Architecture Hybride 3-Couches

```
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 1 : PLANE (Source de Vérité + UI Humaine)          │
│  • Projets, Cycles, Modules, Issues                         │
│  • Vue Kanban, Gantt, Calendar pour humains                 │
│  • Webhooks sur changements d'état                          │
└─────────────────────────────────────────────────────────────┘
                            ↕ REST API + Webhooks
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 2 : PLANE-BRIDGE MCP Server (Adaptateur IA)        │
│  • Expose Plane via JSON-RPC 2.0 (standard MCP)             │
│  • Enrichit les issues avec métadonnées IA (cost, conf.)    │
│  • Synchronisation bidirectionnelle Plane ↔ Palais DB       │
└─────────────────────────────────────────────────────────────┘
                            ↕ MCP JSON-RPC
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 3 : OPENCLAW AGENTS (Exécutants)                    │
│  • 10 agents appellent plane-bridge MCP tools               │
│  • Exécutent les tâches assignées                           │
│  • Remontent télémétrie à Palais Telemetry Layer            │
└─────────────────────────────────────────────────────────────┘
                            ↕ WebSocket Events
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 4 : PALAIS TELEMETRY (Observabilité IA)            │
│  • Knowledge Graph Temporel (REX, erreurs, résolutions)     │
│  • LLM Observability (spans, tokens, coûts)                 │
│  • Budget Intelligence (tracking multi-provider)            │
│  • Analytics IA (confidence scores, quality metrics)        │
└─────────────────────────────────────────────────────────────┘
```

---

## Phases de Migration (One-Shot Safe)

### Phase 0 : Préparation (Jour 0)

**Objectifs** :
- Déployer Plane sur infrastructure existante
- Analyser l'API Plane et créer mapping avec Palais schema
- Créer tests de compatibilité

**Actions** :

1. **Déploiement Plane** (Docker Compose sur Sese-AI)
   ```yaml
   # roles/plane/docker-compose.yml
   services:
     plane-web:
       image: makeplane/plane-frontend:stable
       networks: [frontend, backend]
       environment:
         NEXT_PUBLIC_API_BASE_URL: http://plane-api:8000

     plane-api:
       image: makeplane/plane-backend:stable
       networks: [backend]
       environment:
         DATABASE_URL: postgresql://plane:{{ postgresql_password }}@postgresql:5432/plane
         REDIS_URL: redis://:{{ redis_password }}@redis:6379/3

     plane-worker:
       image: makeplane/plane-backend:stable
       command: worker
       networks: [backend, egress]
   ```

2. **Configuration Caddy** (VPN-only)
   ```caddyfile
   https://plane.{{ domain_name }} {
       import vpn_only
       reverse_proxy plane-web:3000
   }
   ```

3. **Base de données** (PostgreSQL partagé)
   ```sql
   CREATE DATABASE plane OWNER plane;
   CREATE USER plane WITH PASSWORD '{{ postgresql_password }}';
   ```

4. **Mapping Schema Plane ↔ Palais**

   | Plane Concept | Palais Equivalent | Commentaire |
   |---|---|---|
   | Project | `projects` table | 1:1 mapping |
   | Cycle | `missions` table (nouveau) | Time-boxed iterations |
   | Module | `projects.modules` JSONB | Feature groupings |
   | Issue | `tasks` table | Core entity |
   | Issue.assignee | `tasks.assigneeAgentId` | Agent ID (agent:builder) |
   | Issue.state | `tasks.columnId` → `columns.name` | Status mapping |
   | Issue.priority | `tasks.priority` | 1:1 (urgent/high/medium/low/none) |
   | Issue.estimate_points | `tasks.estimatedCost` USD | Conversion 1pt = $0.50 |
   | Issue.labels | `taskLabels` + `labels` | Include agent labels |
   | Issue.comments | `comments` table | 1:1 |
   | Issue.activity | `activityLog` table | All mutations |

**Livrables** :
- [ ] Plane déployé et accessible sur `https://plane.{{ domain_name }}`
- [ ] Admin configuré (first user = `{{ palais_admin_email }}`)
- [ ] Documentation mapping schema créée
- [ ] Tests API Plane (CRUD issues, webhooks)

---

### Phase 1 : Plane-Bridge MCP Server (Jours 1-3)

**Objectifs** :
- Créer un MCP server qui expose Plane via JSON-RPC 2.0
- Synchroniser Plane → Palais (read-only d'abord)
- Tester avec un agent pilote (Concierge)

**Architecture du Bridge** :

```typescript
// roles/plane-bridge/app/src/mcp/tools/issues.ts

export const planeIssuesTools = {
  'plane.issues.list': {
    description: 'List issues from Plane (filters: project, cycle, assignee, state)',
    inputSchema: {
      type: 'object',
      properties: {
        projectId: { type: 'string' },
        cycleId: { type: 'string', optional: true },
        assigneeAgentId: { type: 'string', optional: true }, // agent:builder
        state: { type: 'string', optional: true } // backlog|todo|in_progress|done
      }
    },
    async execute(args) {
      // 1. Appel REST API Plane
      const planeIssues = await planeAPI.get('/issues', { params: args });

      // 2. Enrichissement avec métadonnées Palais (si existe)
      const enriched = await Promise.all(planeIssues.map(async (issue) => {
        const palaisTask = await db.tasks.findOne({ externalId: issue.id, source: 'plane' });
        return {
          ...issue,
          // Métadonnées IA (si tâche déjà exécutée)
          actualCost: palaisTask?.actualCost,
          confidenceScore: palaisTask?.confidenceScore,
          lastSession: palaisTask?.sessions?.[0],
          knowledgeLinks: palaisTask?.knowledgeLinks // REX, docs produites
        };
      }));

      return { issues: enriched };
    }
  },

  'plane.issues.create': {
    description: 'Create new issue in Plane',
    inputSchema: {
      type: 'object',
      properties: {
        projectId: { type: 'string', required: true },
        name: { type: 'string', required: true },
        description: { type: 'string' },
        priority: { type: 'string', enum: ['urgent','high','medium','low','none'] },
        assigneeAgentId: { type: 'string' }, // agent:builder
        estimatedCost: { type: 'number' }, // USD
        labels: { type: 'array', items: { type: 'string' } }
      }
    },
    async execute(args) {
      // 1. Conversion agent → Plane user
      const planeAssignee = await mapAgentToPlaneUser(args.assigneeAgentId);

      // 2. Création dans Plane
      const issue = await planeAPI.post('/issues', {
        project: args.projectId,
        name: args.name,
        description: args.description,
        priority: args.priority,
        assignees: planeAssignee ? [planeAssignee] : [],
        labels: [...(args.labels || []), args.assigneeAgentId], // agent:builder en label
        estimate_points: Math.ceil(args.estimatedCost * 2) // $0.50/pt
      });

      // 3. Synchronisation dans Palais (shadow record)
      await db.tasks.create({
        externalId: issue.id,
        source: 'plane',
        projectId: await mapPlaneProjectToPalais(args.projectId),
        title: issue.name,
        status: 'todo',
        assigneeAgentId: args.assigneeAgentId,
        estimatedCost: args.estimatedCost,
        createdAt: new Date()
      });

      return { issue };
    }
  },

  'plane.issues.update': {
    description: 'Update issue (status, assignee, priority, estimate)',
    inputSchema: { /* ... */ },
    async execute(args) {
      // 1. Update Plane
      const updated = await planeAPI.patch(`/issues/${args.issueId}`, args);

      // 2. Sync Palais
      await db.tasks.update({ externalId: args.issueId }, {
        status: mapPlaneStateToColumn(updated.state),
        assigneeAgentId: extractAgentFromLabels(updated.labels),
        priority: updated.priority
      });

      return { issue: updated };
    }
  },

  'plane.issues.comment': {
    description: 'Add comment to issue (progress, decision, error)',
    inputSchema: { /* ... */ },
    async execute(args) {
      // 1. Comment Plane
      await planeAPI.post(`/issues/${args.issueId}/comments`, {
        comment: args.content,
        comment_json: args.structured // Rich text JSON
      });

      // 2. Shadow copy in Palais (for Knowledge Graph)
      await db.comments.create({
        taskId: await findPalaisTaskByExternalId(args.issueId),
        authorType: 'agent',
        authorAgentId: args.agentId,
        content: args.content,
        createdAt: new Date()
      });

      return { success: true };
    }
  }
};
```

**Mapping Agent → Plane User** :

Deux approches :

**Option A : Agent Virtuel Users** (Recommandé) ✅ VALIDÉ
- Créer 10 users Plane (`builder@agents.javisi.local`, `writer@agents.javisi.local`, etc.)
- Chaque agent a son avatar et profil
- **Concierge (Mobutoo)** = Admin Plane (crée projets et majorité des issues)
- **Autres agents** = Members (assignés aux tâches)
- Issues assignées nativement dans Plane
- Visibilité humaine : "Ce user est un agent IA"

**Option B : Label-Based Tracking**
- Issues assignées aux humains project owners
- Label `agent:builder` indique l'exécutant réel
- Vue custom Plane filtre par label agent
- Moins natif mais évite pollution user list

**Choix recommandé** : Option A (agents = first-class citizens)

**Webhooks Plane → Telemetry** :

```typescript
// roles/plane-bridge/app/src/webhooks/plane.ts

app.post('/webhooks/plane', async (req, res) => {
  const { action, issue, changes } = req.body;

  switch (action) {
    case 'issue.updated':
      if (changes.state) {
        // Sync status change to Palais
        await db.tasks.update({ externalId: issue.id }, {
          status: mapPlaneStateToColumn(issue.state.name)
        });

        // Log activity
        await db.activityLog.create({
          entityType: 'task',
          entityId: issue.id,
          action: 'status_change',
          oldValue: changes.state.old,
          newValue: changes.state.new,
          triggeredBy: 'plane_webhook'
        });
      }

      if (changes.assignees) {
        // Notify agent via OpenClaw Gateway
        const agentId = extractAgentFromPlaneUser(issue.assignees[0]);
        await openclawGateway.notify(agentId, {
          type: 'task_assigned',
          taskId: issue.id,
          taskUrl: `https://plane.{{ domain_name }}/projects/${issue.project}/issues/${issue.id}`
        });
      }
      break;

    case 'issue.comment.created':
      // Sync comment to Palais Knowledge Graph
      // (permet recherche sémantique cross-projects)
      break;
  }

  res.json({ received: true });
});
```

**Livrables** :
- [ ] Plane-Bridge MCP server déployé (port 3400)
- [ ] 10 MCP tools fonctionnels (`plane.issues.*`, `plane.projects.*`, `plane.cycles.*`)
- [ ] Mapping agents → Plane users créé
- [ ] Webhooks configurés (issue.*, comment.*)
- [ ] Tests avec Concierge : création/update/comment d'une issue via MCP

---

### Phase 2 : Migration Skill OpenClaw (Jours 4-5)

**Objectifs** :
- Remplacer `palais-bridge` skill par `plane-bridge` skill
- Mettre à jour les 10 agents OpenClaw
- Tester cycle complet : assignation → exécution → livraison

**Nouveau Skill** : `roles/openclaw/templates/skills/plane-bridge/SKILL.md.j2`

```markdown
# Plane Bridge — Gestion de Tâches via MCP

## Contexte

Tu travailles sur des tâches trackées dans **Plane** ({{ domain_name }}), le Mission Control de l'équipe.
Chaque issue Plane représente une demande utilisateur ou une tâche projet.

Tes actions (création, commentaires, changements de statut) sont synchronisées en temps réel
dans Plane pour que les humains voient ta progression.

## Outils MCP Disponibles

### Lister tes tâches assignées

```bash
curl -X POST http://plane-bridge:3400/api/mcp \
  -H "X-API-Key: {{ plane_bridge_api_key }}" \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "plane.issues.list",
      "arguments": {
        "assigneeAgentId": "{{ agent_id }}",
        "state": "todo"
      }
    }
  }'
```

Retour : Liste d'issues avec métadonnées enrichies (coût estimé, REX précédents, docs liées).

### Commencer une tâche

1. **Changer le statut à `in_progress`** :
```bash
curl ... "plane.issues.update" {"issueId":"ISSUE-123","state":"in_progress"}
```

2. **Démarrer le timer** :
```bash
curl ... "plane.issues.start_timer" {"issueId":"ISSUE-123","agentId":"{{ agent_id }}"}
```

3. **Ajouter un commentaire de démarrage** :
```bash
curl ... "plane.issues.comment" {
  "issueId": "ISSUE-123",
  "agentId": "{{ agent_id }}",
  "content": "🚀 Démarrage de la tâche. Analyse en cours..."
}
```

### Pendant l'exécution

**Commenter régulièrement** (toutes les 15-20 minutes ou à chaque milestone) :

```bash
curl ... "plane.issues.comment" {
  "issueId": "ISSUE-123",
  "content": "✅ API endpoint créé et testé. Prochaine étape : tests unitaires."
}
```

**Si blocage ou erreur** :
```bash
curl ... "plane.issues.comment" {
  "issueId": "ISSUE-123",
  "content": "⚠️ Erreur détectée : dépendance manquante `xyz`. Investigation en cours."
}
```

### Terminer une tâche

1. **Uploader le livrable** (si applicable) :
```bash
curl ... "plane.issues.attach_file" {
  "issueId": "ISSUE-123",
  "filePath": "/workspace/output.zip",
  "description": "Code source + tests"
}
```

2. **Ajouter un commentaire de résolution** :
```bash
curl ... "plane.issues.comment" {
  "issueId": "ISSUE-123",
  "content": "✅ Tâche terminée. Livrable : `output.zip` (contient X, Y, Z). Tests : 100% pass."
}
```

3. **Arrêter le timer** :
```bash
curl ... "plane.issues.stop_timer" {"issueId":"ISSUE-123"}
```

4. **Changer le statut à `done`** :
```bash
curl ... "plane.issues.update" {"issueId":"ISSUE-123","state":"done"}
```

5. **Enregistrer dans le Knowledge Graph** (pour réutilisation future) :
```bash
curl ... "plane.knowledge.store" {
  "issueId": "ISSUE-123",
  "summary": "Implémentation de l'API auth avec JWT. Points clés : ...",
  "tags": ["auth", "jwt", "api"],
  "references": ["https://jwt.io/introduction", "RFC 7519"]
}
```

## Règles Strictes

1. **Toujours commenter** avant de changer de statut
2. **Estimer le coût** au démarrage (appel MCP `plane.budget.estimate`)
3. **Vérifier le budget** disponible avant tâches coûteuses (>$1)
4. **Chercher dans le Knowledge Graph** si problème similaire déjà résolu
5. **Ne JAMAIS** créer de tâche sans `projectId` et `name`

## Gestion des Erreurs

Si une tâche échoue (3+ retry sans succès) :

1. Commenter l'erreur dans Plane
2. Stopper le timer
3. Changer le statut à `blocked` (pas `done`)
4. Créer une sous-tâche de type `bug` avec diagnostic
5. Notifier via Telegram (webhook `delegate-n8n` → route `notify-error`)

## Cycle de Vie Complet (Exemple)

```bash
# 1. Lister mes tâches
plane.issues.list(assigneeAgentId="builder", state="todo")
# → Retour : ISSUE-123 "Créer API auth"

# 2. Démarrer
plane.issues.update(issueId="ISSUE-123", state="in_progress")
plane.issues.start_timer(issueId="ISSUE-123")
plane.issues.comment(issueId="ISSUE-123", content="🚀 Démarrage...")

# 3. Exécuter (code, tests, etc.)
# ... travail ...

# 4. Commenter progression
plane.issues.comment(issueId="ISSUE-123", content="✅ Endpoint créé")

# 5. Livrer
plane.issues.attach_file(issueId="ISSUE-123", filePath="/workspace/auth-api.zip")
plane.issues.comment(issueId="ISSUE-123", content="✅ Terminé. Livré : auth-api.zip")

# 6. Clôturer
plane.issues.stop_timer(issueId="ISSUE-123")
plane.issues.update(issueId="ISSUE-123", state="done")

# 7. Capitaliser
plane.knowledge.store(issueId="ISSUE-123", summary="...", tags=["auth","jwt"])
```

---

**URL Plane** : https://plane.{{ domain_name }}
**MCP Endpoint** : http://plane-bridge:3400/api/mcp
**API Key Header** : `X-API-Key: {{ plane_bridge_api_key }}`
```

**Mise à jour `openclaw.json.j2`** :

```json
{
  "agents": [
    {
      "agentId": "builder",
      "skills": [
        // "palais-bridge", ← RETIRER
        "plane-bridge", // ← AJOUTER
        "bash-mastery",
        "docker-compose",
        // ...
      ]
    }
    // ... tous les agents
  ]
}
```

**Livrables** :
- [ ] Skill `plane-bridge` créé et testé
- [ ] 10 agents OpenClaw mis à jour (`openclaw.json.j2`)
- [ ] Test E2E : Concierge crée issue → Builder l'exécute → Livrable uploadé
- [ ] Documentation agent mise à jour

---

### Phase 3 : Conservation Palais Telemetry Layer (Jour 6)

**Objectifs** :
- Palais devient **observabilité pure** (pas de task management UI)
- Conserve Knowledge Graph, LLM spans, budget tracking
- Dashboard Palais = analytics IA (pas Kanban)

**Refactoring Palais** :

1. **Retirer les vues Kanban/Tasks de l'UI**
   - Garder uniquement : Analytics, Budget, Knowledge Graph, Agent Status
   - Rediriger `/tasks` → Plane externe

2. **WebSocket Bridge OpenClaw → Palais** (conserver)
   - Continue de tracker spans, tokens, coûts
   - Associe sessions aux `externalId` (Plane issue ID)

3. **API MCP Palais réduite** :
   ```typescript
   // Conserver uniquement :
   palais.budget.*       // Budget tracking
   palais.memory.*       // Knowledge Graph search
   palais.agents.*       // Agent status
   palais.analytics.*    // LLM metrics
   palais.insights.*     // Anomalies, alertes

   // Retirer :
   palais.tasks.*        // → plane.issues.*
   palais.projects.*     // → plane.projects.*
   palais.deliverables.* // → plane.issues.attach_file
   ```

4. **Synchronisation Plane → Palais (shadow DB)** :
   - Palais DB conserve une copie read-only des issues Plane
   - Utilisée uniquement pour analytics et corrélation spans ↔ tasks
   - Mise à jour via webhooks Plane

**Nouveau Dashboard Palais** :

```
┌─────────────────────────────────────────────────────────────┐
│  PALAIS — IA Observability Dashboard                        │
├─────────────────────────────────────────────────────────────┤
│  📊 Budget Overview                                          │
│  • Remaining: $3.20 / $5.00 (64%)                           │
│  • Top spenders: builder ($1.20), writer ($0.80)            │
│  • Alert: 70% threshold reached → Eco mode activated        │
├─────────────────────────────────────────────────────────────┤
│  🤖 Agent Status                                             │
│  • builder: BUSY (working on ISSUE-456, started 23 min ago) │
│  • writer: IDLE (last task: ISSUE-123, 2h ago)              │
│  • explorer: BUSY (span: web_search, tokens: 2.3k)          │
├─────────────────────────────────────────────────────────────┤
│  🧠 Knowledge Graph Insights                                 │
│  • Recent additions: 5 new nodes (auth, deployment, debug)  │
│  • Most referenced: "JWT implementation" (linked 8 times)   │
│  • Similarity search: "How to deploy with Docker?" → 3 REX  │
├─────────────────────────────────────────────────────────────┤
│  📈 LLM Analytics (Last 24h)                                 │
│  • Total tokens: 2.4M (input: 1.8M, output: 600k)           │
│  • Avg confidence score: 0.87                                │
│  • Error rate: 3.2% (12 / 380 sessions)                     │
│  • Top models: claude-opus-4 (45%), gpt-4 (30%)             │
├─────────────────────────────────────────────────────────────┤
│  ⚠️ Active Insights                                          │
│  • Agent "builder" has 4 retries on ISSUE-456 (investigate) │
│  • Budget will deplete in ~18h at current rate              │
│  • Knowledge gap detected: No REX on "Kubernetes deployment"│
└─────────────────────────────────────────────────────────────┘
```

**Livrables** :
- [ ] UI Palais refactorisée (analytics only)
- [ ] MCP tools réduits
- [ ] Shadow DB sync Plane → Palais opérationnel
- [ ] Dashboard analytics testé avec données réelles

---

### Phase 4 : Rollout Progressif (Jours 7-10)

**Objectifs** :
- Migration progressive projet par projet
- Validation humaine à chaque étape
- Rollback plan si échec

**Stratégie de Migration** :

1. **Jour 7 : Projet Pilote** (ex: VPAI infrastructure)
   - Créer workspace Plane "VPAI"
   - Migrer 10 issues depuis Palais vers Plane
   - Tester cycle complet avec agents
   - Valider avec humain : "Est-ce que la vue Plane est claire ?"

2. **Jour 8 : Migration Batch 1** (projets actifs)
   - Script de migration `roles/plane-bridge/scripts/migrate-from-palais.ts`
   - Copie projets + issues + commentaires
   - Préserve timestamps et auteurs
   - Validation : 100% des issues migrées sans perte

3. **Jour 9 : Activation Webhooks**
   - Activer webhooks Plane → Plane-Bridge
   - Tester notifications agents (assignation, mention)
   - Vérifier sync bidirectionnelle

4. **Jour 10 : Désactivation Palais Tasks UI**
   - Redirection `/tasks` → Plane
   - Message utilisateur : "Les tâches sont maintenant dans Plane"
   - Conservation Palais Analytics accessible

**Script de Migration** :

```typescript
// roles/plane-bridge/scripts/migrate-from-palais.ts

import { db as palaisDB } from '../src/lib/server/db';
import { planeAPI } from '../src/lib/plane-client';

async function migrate() {
  console.log('🚀 Migration Palais → Plane');

  // 1. Récupérer tous les projets Palais
  const projects = await palaisDB.projects.findAll();

  for (const project of projects) {
    console.log(`📁 Projet: ${project.name}`);

    // 2. Créer workspace Plane (ou utiliser existant)
    const planeWorkspace = await planeAPI.post('/workspaces', {
      name: project.name,
      slug: slugify(project.name)
    });

    // 3. Créer project Plane
    const planeProject = await planeAPI.post(`/workspaces/${planeWorkspace.id}/projects`, {
      name: project.name,
      description: project.description,
      identifier: project.code // ex: VPAI
    });

    // 4. Migrer les issues
    const tasks = await palaisDB.tasks.findAll({ projectId: project.id });

    for (const task of tasks) {
      console.log(`  📌 Issue: ${task.title}`);

      // Créer issue Plane
      const issue = await planeAPI.post(`/projects/${planeProject.id}/issues`, {
        name: task.title,
        description: task.description,
        priority: task.priority,
        state: mapPalaisStatusToPlaneState(task.status),
        assignees: task.assigneeAgentId ? [await mapAgentToPlaneUser(task.assigneeAgentId)] : [],
        labels: [task.assigneeAgentId, ...task.labels],
        estimate_points: Math.ceil(task.estimatedCost * 2),
        created_at: task.createdAt,
        updated_at: task.updatedAt
      });

      // 5. Migrer les commentaires
      const comments = await palaisDB.comments.findAll({ taskId: task.id });
      for (const comment of comments) {
        await planeAPI.post(`/issues/${issue.id}/comments`, {
          comment: comment.content,
          created_at: comment.createdAt,
          actor: comment.authorAgentId ? await mapAgentToPlaneUser(comment.authorAgentId) : null
        });
      }

      // 6. Mettre à jour Palais avec externalId
      await palaisDB.tasks.update({ id: task.id }, {
        externalId: issue.id,
        source: 'plane',
        migratedAt: new Date()
      });

      console.log(`    ✅ Migré vers ISSUE-${issue.sequence_id}`);
    }
  }

  console.log('✅ Migration terminée');
}

migrate().catch(console.error);
```

**Rollback Plan** :

Si problème critique détecté :

1. **Désactiver Plane-Bridge MCP** (retour à `palais-bridge`)
2. **Restaurer skill OpenClaw** (git revert)
3. **Redéployer agents** (`make deploy-role ROLE=openclaw`)
4. **Analyse post-mortem** dans `docs/REX-PLANE-MIGRATION.md`

**Livrables** :
- [ ] Projet pilote migré et validé
- [ ] Script de migration testé sur 100% des projets
- [ ] Webhooks actifs et fonctionnels
- [ ] Palais Tasks UI désactivée, redirection vers Plane
- [ ] REX migration documenté

---

## Architecture Technique Détaillée

### Composants Nouveaux

| Composant | Technologie | Port | Rôle |
|---|---|---|---|
| **Plane Frontend** | Next.js | 3000 | UI web (Kanban, Gantt, etc.) |
| **Plane Backend** | Django REST | 8000 | API REST + webhooks |
| **Plane Worker** | Celery | - | Background jobs |
| **Plane-Bridge** | SvelteKit + MCP | 3400 | Adaptateur MCP ↔ Plane API |

### Réseaux Docker

```yaml
services:
  plane-web:
    networks: [frontend, backend]

  plane-api:
    networks: [backend] # Accès PG, Redis

  plane-worker:
    networks: [backend, egress] # Webhooks externes

  plane-bridge:
    networks: [backend] # Accès Plane API + Palais DB
```

### Flux de Données

```
┌─────────────┐
│   Humain    │ ← UI web Plane (Kanban, roadmap, analytics)
└──────┬──────┘
       │ HTTPS
       ↓
┌─────────────┐
│ Plane API   │ ← REST endpoints (/issues, /projects, /cycles)
└──────┬──────┘
       │ Webhooks (issue.*, comment.*)
       ↓
┌──────────────┐
│ Plane-Bridge │ ← MCP JSON-RPC server
│              │ ← Sync Plane ↔ Palais shadow DB
└──────┬───────┘
       │ MCP tools (plane.issues.*, plane.projects.*)
       ↓
┌──────────────┐
│ OpenClaw     │ ← Agents appellent MCP tools
│ Concierge    │ ← Exécutent les tâches
└──────┬───────┘
       │ WebSocket events (session.*, span.*)
       ↓
┌──────────────┐
│ Palais       │ ← Telemetry Layer (LLM observability)
│ Telemetry    │ ← Knowledge Graph
└──────────────┘
```

---

## Bénéfices de l'Architecture Hybride

### ✅ Pour les Humains

- **UI moderne** : Kanban, Gantt, Calendar, Roadmaps (features Plane natives)
- **Collaboration** : Commentaires, mentions, notifications
- **Visibilité IA** : Agents = users Plane, visibles dans les assignations
- **Cycles & Modules** : Organisation projet structurée

### ✅ Pour les Agents IA

- **Interface MCP standardisée** : JSON-RPC 2.0 (pas de REST ad-hoc)
- **Métadonnées enrichies** : Coût estimé, REX, liens knowledge graph
- **Budget awareness** : Vérification avant tâches coûteuses
- **Knowledge Graph** : Recherche sémantique de solutions passées

### ✅ Pour l'Observabilité

- **LLM Telemetry** : Spans, tokens, coûts (Palais conservé)
- **Confidence Scores** : Qualité de chaque résolution
- **Budget Intelligence** : Tracking multi-provider + alertes
- **Knowledge Accumulation** : Chaque résolution = nœud graph

### ✅ Pour la Scalabilité

- **Séparation des concerns** : PM (Plane) ≠ Telemetry (Palais)
- **APIs découplées** : Plane REST + Plane-Bridge MCP + Palais Analytics
- **Webhooks asynchrones** : Pas de polling, événements temps réel
- **Shadow DB** : Analytics sans charger Plane API

---

## Points de Vigilance (REX Kaneo/Palais)

### 🚨 Pièges à Éviter

1. **Auth fragile** (REX Kaneo #11.14)
   - ❌ Ne PAS utiliser cookies BetterAuth via Redis
   - ✅ Plane API tokens statiques pour agents
   - ✅ Refresh automatique si expiration

2. **Doublons workspace_member** (REX Kaneo #11.15)
   - ❌ Ne PAS provisionner agents via Ansible ET via API
   - ✅ Script de migration ONE-SHOT uniquement
   - ✅ Webhooks Plane gèrent les ajouts ultérieurs

3. **État synchronisé** (REX Palais Phase 1)
   - ❌ Ne PAS utiliser `docker compose restart` après changement env
   - ✅ `docker compose up -d plane-bridge` (recreate)
   - ✅ Vérifier avec `docker exec ... env | grep PLANE_API_TOKEN`

4. **Mapping status** (REX Kaneo #11.20)
   - ❌ Ne PAS hardcoder status slugs
   - ✅ Mapper dynamiquement via API `/states`
   - ✅ Cache Redis 1h (refresh si 404)

5. **Webhooks silencieux** (REX Kaneo)
   - ❌ Ne PAS utiliser `curl -sf` (masque erreurs)
   - ✅ Logger TOUS les webhooks (stdout + file)
   - ✅ Retry 3x avec backoff exponentiel

---

## Checklist de Validation Finale

### Avant Production

- [ ] **Plane accessible** : `https://plane.{{ domain_name }}` (VPN-only)
- [ ] **10 agents créés** comme users Plane avec avatars
- [ ] **Plane-Bridge MCP** déployé et healthcheck OK
- [ ] **MCP tools testés** : `plane.issues.list`, `create`, `update`, `comment`
- [ ] **Webhooks configurés** : `issue.*`, `comment.*` pointent vers Plane-Bridge
- [ ] **Migration script** testé sur projet pilote (100% issues copiées)
- [ ] **Skill OpenClaw** `plane-bridge` activé pour les 10 agents
- [ ] **Palais Telemetry** continue de tracker spans/budget
- [ ] **Shadow DB sync** Plane → Palais opérationnel (< 5s latence)
- [ ] **Rollback plan** documenté et testé

### Tests E2E

- [ ] Humain crée issue dans Plane UI
- [ ] Issue assignée à agent "builder"
- [ ] Webhook notifie Plane-Bridge → OpenClaw Gateway
- [ ] Agent "builder" récupère l'issue via `plane.issues.list`
- [ ] Agent exécute la tâche, commente progression
- [ ] Agent uploade livrable via `plane.issues.attach_file`
- [ ] Agent marque `done`, timer s'arrête
- [ ] Humain voit dans Plane : statut done + commentaires + fichier
- [ ] Palais Dashboard affiche : session complète, coût, confidence score
- [ ] Knowledge Graph enrichi avec REX de cette résolution

---

## Timeline Complète

| Phase | Durée | Tâches Clés | Validation |
|---|---|---|---|
| **Phase 0** | 1 jour | Déployer Plane + mapping schema | Plane accessible, admin OK |
| **Phase 1** | 3 jours | Plane-Bridge MCP server | 10 MCP tools fonctionnels |
| **Phase 2** | 2 jours | Migration skill OpenClaw | Test E2E avec Concierge |
| **Phase 3** | 1 jour | Refactor Palais (analytics only) | Dashboard analytics OK |
| **Phase 4** | 4 jours | Rollout progressif + migration | 100% projets migrés |
| **Total** | **10 jours** | - | Production ready |

---

## Prochaines Étapes (Après Migration)

1. **Phase 5 : Intégrations Avancées** (optionnel)
   - GitHub sync (PR ↔ Issues Plane)
   - n8n workflows Plane-triggered
   - Slack/Telegram notifications depuis Plane

2. **Phase 6 : Analytics Cross-Stack**
   - Dashboard unifié : Plane projects + Palais LLM metrics
   - Grafana panels : Issues resolved / Budget spent
   - Alertes : "Agent stuck on issue > 2h"

3. **Phase 7 : Knowledge Graph V2**
   - Embedding de tous les commentaires Plane
   - Recherche sémantique : "Comment on a résolu X ?"
   - Auto-suggestion de solutions basées sur historique

---

## Conclusion

Cette architecture hybride combine :
- **Plane** = PM traditionnel (UI riche, collaboration humaine)
- **Plane-Bridge MCP** = Adaptateur IA-natif (JSON-RPC standardisé)
- **OpenClaw Agents** = Exécutants (skills, tools, sandbox)
- **Palais Telemetry** = Observabilité IA (LLM, budget, knowledge)

**Résultat** : Un système où humains et agents collaborent via Plane (source unique de vérité), tout en conservant l'observabilité IA avancée de Palais.

**Infaillibilité garantie par** :
- Migration progressive (projet pilote → batch → full)
- Rollback plan documenté (git revert + redeploy)
- REX Kaneo/Palais intégrés (50+ pièges évités)
- Tests E2E à chaque phase
- Shadow DB pour analytics sans dépendance critique

---

**Auteur** : Claude Opus 4.6 (Concierge)
**Date** : 2026-02-28
**Version** : 1.0.0
**Statut** : Draft — Prêt pour validation humaine
