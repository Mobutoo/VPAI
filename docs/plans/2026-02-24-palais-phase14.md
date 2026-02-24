# Palais Phase 14 — Integration Claude Code MCP

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** MCP bidirectionnel — Claude Code sur le Pi consomme Palais comme outil MCP (query taches, memoire, agents), et Palais peut declencher des sessions Claude Code sur le Pi via SSH.

**Architecture:** Direction 1 : Palais expose un MCP server SSE que Claude Code consomme (`~/.claude/servers/palais.json`). Direction 2 : Palais trigger SSH vers le Pi pour lancer une session Claude Code avec contexte injecte.

**Tech Stack:** MCP JSON-RPC over SSE, SSH, n8n workflows, SvelteKit 5

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 13 (Integration Claude Code)

---

## Task 1: MCP SSE Transport Server

**Files:**
- Create: `roles/palais/files/app/src/routes/api/mcp/sse/+server.ts`

Implementer le transport SSE pour MCP (JSON-RPC over Server-Sent Events) :

```typescript
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ request }) => {
  // Verify API key
  const apiKey = request.headers.get('x-api-key');
  if (apiKey !== env.PALAIS_API_KEY) {
    return new Response('Unauthorized', { status: 401 });
  }

  const stream = new ReadableStream({
    start(controller) {
      // Send initial capabilities
      const capabilities = {
        jsonrpc: '2.0',
        method: 'notifications/initialized',
        params: { serverInfo: { name: 'palais', version: '1.0.0' } }
      };
      controller.enqueue(`data: ${JSON.stringify(capabilities)}\n\n`);
    }
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    }
  });
};
```

Commit: `feat(palais): MCP SSE transport server endpoint`

## Task 2: MCP JSON-RPC Handler

**Files:**
- Create: `roles/palais/files/app/src/routes/api/mcp/+server.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/handler.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools.ts`

Handler JSON-RPC : `POST /api/mcp` — recoit les requetes, route vers les tools.

```typescript
// tools.ts — Tool registry
export const mcpTools = {
  'palais.tasks.list': async (params) => { /* GET /api/v1/projects/:id/tasks */ },
  'palais.tasks.create': async (params) => { /* POST /api/v1/projects/:id/tasks */ },
  'palais.tasks.update': async (params) => { /* PUT /api/v1/tasks/:id */ },
  'palais.tasks.comment': async (params) => { /* POST /api/v1/tasks/:id/comments */ },
  'palais.tasks.start_timer': async (params) => { /* POST /api/v1/tasks/:id/timer/start */ },
  'palais.tasks.stop_timer': async (params) => { /* POST /api/v1/tasks/:id/timer/stop */ },
  'palais.projects.list': async (params) => { /* GET /api/v1/projects */ },
  'palais.projects.create': async (params) => { /* POST /api/v1/projects */ },
  'palais.projects.analytics': async (params) => { /* GET /api/v1/projects/:id/analytics */ },
  'palais.agents.status': async (params) => { /* GET /api/v1/agents */ },
  'palais.agents.available': async (params) => { /* idle + budget ok agents */ },
  'palais.budget.remaining': async (params) => { /* GET /api/v1/budget/summary */ },
  'palais.budget.estimate': async (params) => { /* estimate cost for a task */ },
  'palais.deliverables.upload': async (params) => { /* upload deliverable */ },
  'palais.deliverables.list': async (params) => { /* list deliverables */ },
  'palais.memory.search': async (params) => { /* POST /api/v1/memory/search */ },
  'palais.memory.recall': async (params) => { /* GET /api/v1/memory/nodes/:id */ },
  'palais.memory.store': async (params) => { /* POST /api/v1/memory/nodes */ },
  'palais.insights.active': async (params) => { /* GET /api/v1/insights?acknowledged=false */ },
  'palais.standup.latest': async (params) => { /* GET /api/v1/standup/latest */ },
};
```

Handler :
```typescript
// handler.ts
export async function handleMCPRequest(body: any) {
  const { method, params, id } = body;

  if (method === 'tools/list') {
    return { jsonrpc: '2.0', id, result: { tools: Object.keys(mcpTools).map(name => ({ name })) } };
  }

  if (method === 'tools/call') {
    const tool = mcpTools[params.name];
    if (!tool) return { jsonrpc: '2.0', id, error: { code: -32601, message: 'Tool not found' } };
    const result = await tool(params.arguments);
    return { jsonrpc: '2.0', id, result };
  }

  return { jsonrpc: '2.0', id, error: { code: -32601, message: 'Method not found' } };
}
```

Commit: `feat(palais): MCP JSON-RPC handler with full tool registry`

## Task 3: Config MCP Claude Code sur le Pi

**Files:**
- Create: `roles/palais/templates/claude-mcp-config.json.j2`
- Modify: `roles/palais/tasks/main.yml`

Template pour `~/.claude/servers/palais.json` deploye sur le Pi :

```json
{
  "palais": {
    "url": "https://{{ palais_subdomain }}.{{ domain_name }}/api/mcp/sse",
    "headers": {
      "X-API-Key": "{{ vault_palais_api_key }}"
    }
  }
}
```

Task Ansible : copier le fichier sur le Pi via la connexion SSH existante.

Commit: `feat(palais): Claude Code MCP config deployed to Pi`

## Task 4: Bouton "Lancer Claude Code" sur les taches

**Files:**
- Modify: `roles/palais/files/app/src/lib/components/TaskCard.svelte`
- Create: `roles/palais/files/app/src/routes/api/v1/tasks/[id]/launch-claude/+server.ts`

Sur les taches de type `code` (label "code" ou "dev") : ajouter un bouton `[Lancer Claude Code]`.

API endpoint `POST /api/v1/tasks/:id/launch-claude` :
1. Recuperer la tache + contexte projet
2. Construire le prompt avec le contexte Palais
3. Trigger via SSH ou n8n workflow vers le Pi
4. Mettre a jour la tache : status → `in-progress`, session liee

```typescript
export const POST: RequestHandler = async ({ params }) => {
  const task = await db.query.tasks.findFirst({ where: eq(tasks.id, params.id) });
  if (!task) return json({ error: 'Task not found' }, { status: 404 });

  const prompt = buildClaudeCodePrompt(task);

  // Trigger via n8n webhook (SSH to Pi → claude-code)
  await fetch(`${env.N8N_WEBHOOK_BASE}/launch-claude-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: task.id, prompt, project: task.projectId })
  });

  // Update task status
  await db.update(tasks).set({ status: 'in-progress' }).where(eq(tasks.id, params.id));

  return json({ ok: true, message: 'Claude Code session launched on Pi' });
};
```

Commit: `feat(palais): launch Claude Code button on code tasks`

## Task 5: Workflow n8n `launch-claude-code`

**Files:**
- Create: `roles/n8n-provision/files/workflows/launch-claude-code.json`

Workflow :
1. Webhook trigger: `POST /webhook/launch-claude-code`
2. SSH vers Pi : `ssh {{ workstation_pi_user }}@{{ workstation_pi_tailscale_ip }}`
3. Commande : `cd /workspace && claude-code --task "{{ prompt }}" --no-interactive`
4. Attendre completion (timeout 30min)
5. Recuperer le resultat (commit SHA, PR URL)
6. Callback Palais : `PUT /api/v1/tasks/:id` avec le resultat + status → `review`
7. Si PR creee : ajouter commentaire sur la tache avec lien PR

Commit: `feat(n8n): launch-claude-code workflow (Palais → Pi → PR)`

## Task 6: Boucle Complete — PR → Review → Done

**Files:**
- Modify: `roles/n8n-provision/files/workflows/code-review.json`

Etendre le workflow `code-review` pour la boucle complete :
1. Claude Code cree un commit/PR → webhook `code-review`
2. Code review via LiteLLM (existant)
3. Si OK : merge PR, callback Palais → tache status `done`
4. Si KO : commentaire sur la tache avec les issues, status → `in-progress` pour retry
5. Creer un livrable avec le diff/patch attache a la tache

Commit: `feat(n8n): complete code review loop with Palais callback`

---

## Verification Checklist

- [ ] MCP SSE endpoint accessible (`/api/mcp/sse`)
- [ ] MCP JSON-RPC handler route correctement les tools
- [ ] Claude Code sur le Pi peut querier taches via MCP
- [ ] Claude Code sur le Pi peut rechercher dans la memoire via MCP
- [ ] Bouton [Lancer Claude Code] visible sur les taches `code`
- [ ] SSH vers Pi declenche une session Claude Code
- [ ] Resultat (commit/PR) remonte vers Palais
- [ ] Boucle complete : tache → Claude Code → PR → review → done
