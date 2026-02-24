# Palais Phase 2 — Agent Cockpit + Avatars

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connecter Palais a OpenClaw Gateway en temps-reel via WebSocket, afficher le statut live des 10 agents avec feed d'activite, et generer les avatars Black Panther.

**Architecture:** WebSocket client server-side vers OpenClaw (port 18789), SSE push vers le browser. Statuts agents persistes en DB, mis a jour par les events WS.

**Tech Stack:** SvelteKit 5, WebSocket (ws), SSE (native), Drizzle ORM

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 1 (Agent Cockpit)

**Prerequis:** Phase 1 complete (DB schema, agents seeds, API routes, theme)

---

## Task 1: WebSocket Client OpenClaw

**Files:**
- Create: `roles/palais/files/app/src/lib/server/ws/openclaw.ts`

**Step 1: Install ws package**

```bash
cd roles/palais/files/app
npm install ws
npm install -D @types/ws
```

**Step 2: Create OpenClaw WebSocket client**

```typescript
// src/lib/server/ws/openclaw.ts
import WebSocket from 'ws';
import { env } from '$env/dynamic/private';
import { db } from '$lib/server/db';
import { agents, agentSessions } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

type AgentEvent = {
  type: string;
  agentId: string;
  sessionId?: string;
  status?: string;
  taskId?: number;
  model?: string;
  tokens?: number;
  cost?: number;
  summary?: string;
};

const listeners = new Set<(event: AgentEvent) => void>();

export function subscribe(fn: (event: AgentEvent) => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function broadcast(event: AgentEvent) {
  for (const fn of listeners) fn(event);
}

async function handleMessage(data: string) {
  try {
    const event: AgentEvent = JSON.parse(data);

    if (event.type === 'agent.status') {
      await db.update(agents)
        .set({
          status: event.status as any,
          currentTaskId: event.taskId,
          lastSeenAt: new Date()
        })
        .where(eq(agents.id, event.agentId));
    }

    if (event.type === 'session.started') {
      await db.insert(agentSessions).values({
        agentId: event.agentId,
        taskId: event.taskId,
        model: event.model,
        status: 'running'
      });
    }

    if (event.type === 'session.completed') {
      // Update latest running session for this agent
      await db.execute(
        `UPDATE agent_sessions SET status = 'completed', ended_at = NOW(),
         total_tokens = $1, total_cost = $2, summary = $3
         WHERE agent_id = $4 AND status = 'running'
         ORDER BY started_at DESC LIMIT 1`,
        // Note: use raw SQL or drizzle subquery
      );
    }

    broadcast(event);
  } catch (err) {
    console.error('[WS] Parse error:', err);
  }
}

export function connectOpenClaw() {
  const url = env.OPENCLAW_WS_URL || 'ws://openclaw:18789';
  console.log(`[WS] Connecting to OpenClaw: ${url}`);

  ws = new WebSocket(url);

  ws.on('open', () => {
    console.log('[WS] Connected to OpenClaw Gateway');
    if (reconnectTimer) clearTimeout(reconnectTimer);
  });

  ws.on('message', (data) => handleMessage(data.toString()));

  ws.on('close', () => {
    console.log('[WS] Disconnected, reconnecting in 10s...');
    reconnectTimer = setTimeout(connectOpenClaw, 10_000);
  });

  ws.on('error', (err) => {
    console.error('[WS] Error:', err.message);
    ws?.close();
  });
}

export function disconnectOpenClaw() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  ws?.close();
}
```

**Step 3: Initialize WS on server startup**

Create `roles/palais/files/app/src/hooks.server.ts` — add at the top (after existing auth logic):
```typescript
import { connectOpenClaw } from '$lib/server/ws/openclaw';
import { building } from '$app/environment';

if (!building) {
  connectOpenClaw();
}
```

**Step 4: Commit**

```bash
git add roles/palais/files/app/src/lib/server/ws/ roles/palais/files/app/package*.json
git commit -m "feat(palais): WebSocket client for OpenClaw Gateway"
```

---

## Task 2: SSE Endpoint for Browser Push

**Files:**
- Create: `roles/palais/files/app/src/routes/api/sse/+server.ts`

**Step 1: Create SSE endpoint**

```typescript
// src/routes/api/sse/+server.ts
import type { RequestHandler } from './$types';
import { subscribe } from '$lib/server/ws/openclaw';

export const GET: RequestHandler = async ({ request }) => {
  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();

      const send = (event: string, data: unknown) => {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      };

      // Heartbeat every 30s
      const heartbeat = setInterval(() => {
        send('ping', { ts: Date.now() });
      }, 30_000);

      // Subscribe to OpenClaw events
      const unsub = subscribe((evt) => {
        send('agent', evt);
      });

      // Cleanup on disconnect
      request.signal.addEventListener('abort', () => {
        clearInterval(heartbeat);
        unsub();
      });

      send('connected', { ts: Date.now() });
    }
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive'
    }
  });
};
```

**Step 2: Commit**

```bash
git add roles/palais/files/app/src/routes/api/sse/
git commit -m "feat(palais): SSE endpoint for browser real-time push"
```

---

## Task 3: Agent Grid Page (Live Status)

**Files:**
- Create: `roles/palais/files/app/src/routes/agents/+page.server.ts`
- Create: `roles/palais/files/app/src/routes/agents/+page.svelte`
- Create: `roles/palais/files/app/src/lib/components/agents/AgentCard.svelte`
- Create: `roles/palais/files/app/src/lib/stores/sse.ts`

**Step 1: Create SSE store for client-side reactivity**

```typescript
// src/lib/stores/sse.ts
import { browser } from '$app/environment';

type SSECallback = (event: { type: string; agentId: string; status?: string }) => void;

let eventSource: EventSource | null = null;
const listeners = new Set<SSECallback>();

export function connectSSE() {
  if (!browser || eventSource) return;

  eventSource = new EventSource('/api/sse');

  eventSource.addEventListener('agent', (e) => {
    const data = JSON.parse(e.data);
    for (const fn of listeners) fn(data);
  });

  eventSource.onerror = () => {
    eventSource?.close();
    eventSource = null;
    setTimeout(connectSSE, 5000);
  };
}

export function onAgentEvent(fn: SSECallback) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
```

**Step 2: Create AgentCard component**

```svelte
<!-- src/lib/components/agents/AgentCard.svelte -->
<script lang="ts">
  let { agent }: { agent: any } = $props();

  let statusColor = $derived(
    agent.status === 'idle' ? 'var(--palais-green)' :
    agent.status === 'busy' ? 'var(--palais-gold)' :
    agent.status === 'error' ? 'var(--palais-red)' :
    'var(--palais-text-muted)'
  );

  let isBusy = $derived(agent.status === 'busy');
</script>

<a href="/agents/{agent.id}"
  class="block p-4 rounded-lg transition-all hover:scale-[1.02]"
  style="background: var(--palais-surface); border: 1px solid {isBusy ? 'var(--palais-gold)' : 'var(--palais-border)'};"
  style:box-shadow={isBusy ? 'var(--palais-glow-md)' : 'none'}
  class:animate-pulse={isBusy}
>
  <!-- Avatar -->
  <div class="w-12 h-12 rounded-full flex items-center justify-center mb-3"
    style="background: linear-gradient(135deg, var(--palais-gold), var(--palais-amber)); color: var(--palais-bg);">
    {#if agent.avatar_url}
      <img src={agent.avatar_url} alt={agent.name} class="w-12 h-12 rounded-full object-cover" />
    {:else}
      <span class="text-sm font-bold">{agent.name.substring(0, 2).toUpperCase()}</span>
    {/if}
  </div>

  <h3 class="text-sm font-semibold" style="color: var(--palais-text);">{agent.name}</h3>
  <p class="text-xs" style="color: var(--palais-text-muted);">{agent.persona}</p>

  <div class="flex items-center gap-2 mt-3">
    <span class="w-2 h-2 rounded-full" style="background: {statusColor};"></span>
    <span class="text-xs capitalize" style="color: {statusColor};">{agent.status}</span>
  </div>

  {#if agent.totalSpend30d}
    <p class="text-xs mt-2 tabular-nums" style="color: var(--palais-cyan);">
      ${agent.totalSpend30d.toFixed(2)} / 30j
    </p>
  {/if}
</a>
```

**Step 3: Create agents page**

```typescript
// src/routes/agents/+page.server.ts
import { db } from '$lib/server/db';
import { agents } from '$lib/server/db/schema';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
  const allAgents = await db.select().from(agents).orderBy(agents.name);
  return { agents: allAgents };
};
```

```svelte
<!-- src/routes/agents/+page.svelte -->
<script lang="ts">
  import AgentCard from '$lib/components/agents/AgentCard.svelte';
  import { connectSSE, onAgentEvent } from '$lib/stores/sse';
  import { onMount } from 'svelte';

  let { data } = $props();
  let agentList = $state(data.agents);

  onMount(() => {
    connectSSE();
    const unsub = onAgentEvent((evt) => {
      agentList = agentList.map(a =>
        a.id === evt.agentId ? { ...a, status: evt.status || a.status } : a
      );
    });
    return unsub;
  });
</script>

<div class="space-y-6">
  <h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
    Agent Cockpit
  </h1>

  <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
    {#each agentList as agent (agent.id)}
      <AgentCard {agent} />
    {/each}
  </div>
</div>
```

**Step 4: Commit**

```bash
git add roles/palais/files/app/src/lib/stores/ roles/palais/files/app/src/lib/components/agents/ roles/palais/files/app/src/routes/agents/
git commit -m "feat(palais): agent cockpit grid with live status cards"
```

---

## Task 4: Agent Detail Page

**Files:**
- Create: `roles/palais/files/app/src/routes/agents/[id]/+page.server.ts`
- Create: `roles/palais/files/app/src/routes/agents/[id]/+page.svelte`

**Step 1: Server load with sessions**

```typescript
// src/routes/agents/[id]/+page.server.ts
import { db } from '$lib/server/db';
import { agents, agentSessions } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
  const [agent] = await db.select().from(agents).where(eq(agents.id, params.id));
  if (!agent) throw error(404, 'Agent not found');

  const sessions = await db.select().from(agentSessions)
    .where(eq(agentSessions.agentId, params.id))
    .orderBy(desc(agentSessions.startedAt))
    .limit(50);

  return { agent, sessions };
};
```

**Step 2: Agent detail page**

```svelte
<!-- src/routes/agents/[id]/+page.svelte -->
<script lang="ts">
  let { data } = $props();
</script>

<div class="space-y-6">
  <div class="flex items-center gap-4">
    <div class="w-16 h-16 rounded-full flex items-center justify-center"
      style="background: linear-gradient(135deg, var(--palais-gold), var(--palais-amber)); color: var(--palais-bg);">
      <span class="text-xl font-bold">{data.agent.name.substring(0, 2).toUpperCase()}</span>
    </div>
    <div>
      <h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
        {data.agent.name}
      </h1>
      <p class="text-sm" style="color: var(--palais-text-muted);">{data.agent.persona}</p>
    </div>
  </div>

  <!-- Stats -->
  <div class="grid grid-cols-3 gap-4">
    {#each [
      { label: 'Tokens 30j', value: data.agent.totalTokens30d?.toLocaleString() || '0' },
      { label: 'Cout 30j', value: `$${(data.agent.totalSpend30d || 0).toFixed(2)}` },
      { label: 'Qualite moy.', value: data.agent.avgQualityScore?.toFixed(1) || 'N/A' }
    ] as stat}
      <div class="p-4 rounded-lg" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
        <p class="text-xs" style="color: var(--palais-text-muted);">{stat.label}</p>
        <p class="text-lg font-semibold tabular-nums" style="color: var(--palais-cyan);">{stat.value}</p>
      </div>
    {/each}
  </div>

  <!-- Sessions -->
  <section>
    <h2 class="text-sm font-semibold uppercase tracking-wider mb-4" style="color: var(--palais-text-muted);">
      Sessions recentes
    </h2>
    <div class="space-y-2">
      {#each data.sessions as session}
        <a href="/agents/{data.agent.id}/traces/{session.id}"
          class="block p-3 rounded-lg transition-all hover:bg-[var(--palais-surface-hover)]"
          style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
          <div class="flex items-center justify-between">
            <span class="text-sm" style="color: var(--palais-text);">
              {session.summary || `Session #${session.id}`}
            </span>
            <span class="text-xs tabular-nums"
              style="color: {session.status === 'completed' ? 'var(--palais-green)' : session.status === 'failed' ? 'var(--palais-red)' : 'var(--palais-amber)'};">
              {session.status}
            </span>
          </div>
          <div class="flex gap-4 mt-1 text-xs" style="color: var(--palais-text-muted);">
            <span>{session.model}</span>
            <span class="tabular-nums">{session.totalTokens?.toLocaleString()} tokens</span>
            <span class="tabular-nums">${session.totalCost?.toFixed(3)}</span>
          </div>
        </a>
      {/each}
    </div>
  </section>
</div>
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/routes/agents/
git commit -m "feat(palais): agent detail page with sessions history"
```

---

## Task 5: Activity Feed Component

**Files:**
- Create: `roles/palais/files/app/src/lib/components/ActivityFeed.svelte`

**Step 1: Create component**

```svelte
<!-- src/lib/components/ActivityFeed.svelte -->
<script lang="ts">
  let { activities = [], maxItems = 20 }: { activities: any[]; maxItems?: number } = $props();
</script>

<div class="space-y-1 max-h-96 overflow-y-auto">
  {#each activities.slice(0, maxItems) as item}
    <div class="flex items-start gap-3 p-2 rounded text-sm hover:bg-[var(--palais-surface-hover)]">
      <span class="text-xs tabular-nums whitespace-nowrap mt-0.5" style="color: var(--palais-text-muted);">
        {new Date(item.createdAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
      </span>
      <div>
        <span style="color: var(--palais-gold);">{item.actorAgentId || 'System'}</span>
        <span style="color: var(--palais-text-muted);"> {item.action} </span>
        <span style="color: var(--palais-text);">{item.entityType} #{item.entityId}</span>
      </div>
    </div>
  {/each}
  {#if activities.length === 0}
    <p class="text-sm text-center py-8" style="color: var(--palais-text-muted);">Aucune activite recente</p>
  {/if}
</div>
```

**Step 2: Commit**

```bash
git add roles/palais/files/app/src/lib/components/ActivityFeed.svelte
git commit -m "feat(palais): activity feed component"
```

---

## Verification Checklist

- [ ] WebSocket connects to OpenClaw (check server logs for `[WS] Connected`)
- [ ] SSE endpoint streams events at `/api/sse`
- [ ] `/agents` page shows 10 agent cards with status
- [ ] Agent cards pulse gold when status = busy
- [ ] `/agents/:id` shows agent details + session history
- [ ] Activity feed renders and auto-scrolls
- [ ] Avatar fallback shows initials on gold gradient
