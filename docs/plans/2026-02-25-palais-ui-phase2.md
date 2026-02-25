# Palais UI Phase 2 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver 5 UI/backend improvements to Palais: remove ghost agent, add `agent.registered` WS event handler, redesign `/agents` list with 2:3 photo cards + SVG ring, replace emoji page titles with Adinkra icons, and nuke+reimport n8n workflows.

**Architecture:** All Palais changes are SvelteKit 5 files under `roles/palais/files/app/src/`. The n8n changes are Ansible YAML in `roles/n8n-provision/tasks/main.yml`. No new DB migrations needed (schema already has the required columns: `agents.bio`, `agents.persona`, `agents.avatar_url`, `nodes.local_ip`).

**Tech Stack:** SvelteKit 5 (Svelte 5 runes), Drizzle ORM, TypeScript, Tailwind, Ansible, Docker, WebSocket (ws)

**VPS access:** `ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167`
**DB in container:** `docker exec javisi_postgresql psql -U palais -d palais`

---

## Task 1: Delete ghost agent from DB

> Run this ONCE on VPS before deploying new Palais code — otherwise `seedAgentBios()` may recreate it on next boot.

**Files:** None — direct DB command on VPS.

**Step 1: SSH to VPS and delete**

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 \
  "docker exec javisi_postgresql psql -U palais -d palais -c \"DELETE FROM agents WHERE id = 'main';\""
```

Expected output: `DELETE 1`

**Step 2: Verify**

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 \
  "docker exec javisi_postgresql psql -U palais -d palais -c \"SELECT id, name FROM agents ORDER BY id;\""
```

Expected: `main` row is gone; real OpenClaw agent IDs remain.

---

## Task 2: Remove `seedAgentBios()` — kill the ghost factory

**Files:**
- Modify: `roles/palais/files/app/src/lib/server/db/seed.ts`
- Modify: `roles/palais/files/app/src/hooks.server.ts`

**Step 1: Remove `seedAgentBios` from seed.ts**

In `seed.ts`, delete the entire `seedAgentBios` function (lines 47–116). Leave `seedNodes()` intact.

The file after edit should contain only:
- The imports (`env`, `db`, `nodes`, `agents`)
- `seedNodes()` function
- No `seedAgentBios` function

**Step 2: Remove import + call from hooks.server.ts**

In `hooks.server.ts` line 9, change:
```typescript
import { seedNodes, seedAgentBios } from '$lib/server/db/seed';
```
to:
```typescript
import { seedNodes } from '$lib/server/db/seed';
```

And remove line 18:
```typescript
seedAgentBios().catch((err) => console.error('[seed] seedAgentBios failed:', err));
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/lib/server/db/seed.ts \
        roles/palais/files/app/src/hooks.server.ts
git commit -m "feat(palais): remove seedAgentBios — bios come from agent.registered WS event

Ghost agent 'Général d'État-Major' (id: main) was created by hardcoded seed.
Bios are now dynamic: OpenClaw emits agent.registered events from identite.md/soul.md.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Add `agent.registered` event type

**Files:**
- Modify: `roles/palais/files/app/src/lib/types/agent.ts`

**Step 1: Extend AgentEvent type**

Add optional fields to `AgentEvent` for the `agent.registered` event:

```typescript
export type AgentEvent = {
	type: string;
	agentId: string;
	sessionId?: number;
	status?: string;
	taskId?: number;
	model?: string;
	tokens?: number;
	cost?: number;
	summary?: string;
	// agent.registered fields
	name?: string;
	persona?: string;
	bio?: string;
	avatarUrl?: string;
	// span.* events
	span?: {
		id: string;
		parentId?: string;
		type: 'llm_call' | 'tool_call' | 'decision' | 'delegation';
		name: string;
		input?: unknown;
		output?: unknown;
		model?: string;
		tokensIn?: number;
		tokensOut?: number;
		cost?: number;
		startedAt?: string;
		endedAt?: string;
		durationMs?: number;
		error?: unknown;
	};
};
```

**Step 2: Commit**

```bash
git add roles/palais/files/app/src/lib/types/agent.ts
git commit -m "feat(palais): add agent.registered fields to AgentEvent type

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Handle `agent.registered` in openclaw.ts WS handler

**Files:**
- Modify: `roles/palais/files/app/src/lib/server/ws/openclaw.ts`

**Step 1: Add handler for `agent.registered`**

In `handleMessage()`, after the `if (event.type === 'session.completed')` block (around line 80), add:

```typescript
if (event.type === 'agent.registered') {
    // Only UPDATE — never INSERT (agent must already exist in OpenClaw)
    await db
        .update(agents)
        .set({
            name: event.name ?? undefined,
            persona: event.persona ?? undefined,
            bio: event.bio ?? undefined,
            model: event.model ?? undefined,
            avatar_url: event.avatarUrl ?? undefined,
            lastSeenAt: new Date()
        })
        .where(eq(agents.id, event.agentId));
}
```

> **IMPORTANT:** The `set()` call must NOT pass `undefined` for fields where the event provided no value — Drizzle will ignore `undefined` fields in `.set()` automatically. This ensures we only update fields that OpenClaw actually sent.

**Step 2: Verify the import** — `agents` table is already imported at line 4 of openclaw.ts.

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/lib/server/ws/openclaw.ts
git commit -m "feat(palais): handle agent.registered WS event — UPDATE bio/persona/model from OpenClaw

Never INSERTs — only updates existing agents registered in OpenClaw.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Add PATCH bio endpoint (UI fallback)

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/agents/[id]/+server.ts`

**Step 1: Create the file**

```typescript
import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { agents } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const PATCH: RequestHandler = async ({ params, request }) => {
	const { id } = params;
	const body = await request.json() as { bio?: string; persona?: string };

	if (!body.bio && !body.persona) {
		throw error(400, 'No fields to update');
	}

	const set: Record<string, unknown> = {};
	if (body.bio !== undefined) set.bio = body.bio;
	if (body.persona !== undefined) set.persona = body.persona;

	const [updated] = await db
		.update(agents)
		.set(set)
		.where(eq(agents.id, id))
		.returning({ id: agents.id });

	if (!updated) throw error(404, 'Agent not found');

	return json({ ok: true });
};
```

**Step 2: Commit**

```bash
git add "roles/palais/files/app/src/routes/api/v1/agents/[id]/+server.ts"
git commit -m "feat(palais): PATCH /api/v1/agents/[id] — bio/persona UI fallback endpoint

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Redesign AgentCard — 2:3 photo format with SVG ring

**Files:**
- Modify: `roles/palais/files/app/src/lib/components/agents/AgentCard.svelte`

**Step 1: Replace the entire file content**

The new design: portrait card (2:3 aspect ratio), photo fills top portion, SVG rectangular ring around the photo animates when busy, name + bio snippet + status dot below.

```svelte
<script lang="ts">
	let { agent }: { agent: Record<string, unknown> } = $props();

	const statusColor = $derived(
		agent.status === 'idle'    ? 'var(--palais-green)'
		: agent.status === 'busy'  ? 'var(--palais-gold)'
		: agent.status === 'error' ? 'var(--palais-red)'
		:                            'var(--palais-text-muted)'
	);

	const isBusy = $derived(agent.status === 'busy');
	const initials = $derived(String(agent.name ?? '').split(' ').map((w: string) => w[0]).join('').slice(0, 2).toUpperCase());
</script>

<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
<a
	href="/agents/{agent.id}"
	class="flex flex-col rounded-xl overflow-hidden transition-all hover:scale-[1.02] hover:shadow-lg"
	style="
		background: var(--palais-surface);
		border: 1px solid {isBusy ? 'var(--palais-gold)' : 'var(--palais-border)'};
		box-shadow: {isBusy ? 'var(--palais-glow-sm)' : 'none'};
	"
>
	<!-- Photo area (2:3) with SVG ring overlay -->
	<div class="relative w-full" style="aspect-ratio: 2 / 3; overflow: hidden;">
		<!-- Background / photo -->
		{#if agent.avatar_url}
			<img
				src={String(agent.avatar_url)}
				alt={String(agent.name)}
				class="absolute inset-0 w-full h-full object-cover"
			/>
		{:else}
			<div
				class="absolute inset-0 flex items-center justify-center"
				style="background: linear-gradient(160deg, color-mix(in srgb, {statusColor} 18%, var(--palais-bg)), var(--palais-surface));"
			>
				<span
					class="text-3xl font-bold"
					style="color: {statusColor}; font-family: 'Orbitron', sans-serif; opacity: 0.7;"
				>{initials}</span>
			</div>
		{/if}

		<!-- SVG ring — rectangular frame that traces the photo border -->
		<svg
			class="absolute inset-0 w-full h-full pointer-events-none"
			viewBox="0 0 100 150"
			preserveAspectRatio="none"
			xmlns="http://www.w3.org/2000/svg"
		>
			<!-- Base track (always visible, faint) -->
			<rect
				x="3" y="3" width="94" height="144" rx="5"
				fill="none"
				stroke={statusColor}
				stroke-width="2"
				opacity="0.15"
			/>
			<!-- Animated dash ring (bright when busy) -->
			<rect
				x="3" y="3" width="94" height="144" rx="5"
				fill="none"
				stroke={statusColor}
				stroke-width="2.5"
				stroke-linecap="round"
				stroke-dasharray={isBusy ? '22 12' : '476 0'}
				stroke-dashoffset="0"
				opacity={isBusy ? '1' : '0.5'}
				style={isBusy ? 'animation: ringTrace 2s linear infinite;' : ''}
			/>
		</svg>
	</div>

	<!-- Info section -->
	<div class="p-2.5 flex flex-col gap-1">
		<h3 class="text-xs font-semibold truncate" style="color: var(--palais-text);">{agent.name}</h3>
		{#if agent.bio}
			<p class="text-xs line-clamp-2" style="color: var(--palais-text-muted); font-size: 0.6rem; line-height: 1.4;">
				{agent.bio}
			</p>
		{:else if agent.persona}
			<p class="text-xs truncate" style="color: var(--palais-text-muted); font-size: 0.6rem;">
				{agent.persona}
			</p>
		{/if}
		<div class="flex items-center gap-1.5 mt-0.5">
			<span class="w-1.5 h-1.5 rounded-full flex-shrink-0" style="background: {statusColor};"></span>
			<span class="text-xs capitalize" style="color: {statusColor}; font-size: 0.6rem;">{agent.status}</span>
		</div>
	</div>
</a>

<style>
	@keyframes ringTrace {
		from { stroke-dashoffset: 0; }
		to   { stroke-dashoffset: -476; }
	}
</style>
```

> Note: The `stroke-dasharray="476 0"` for idle state means "draw the full perimeter" (100+150)*2 = 500, so using 476 as a safe full-coverage value gives a solid line at 50% opacity. When busy, `22 12` creates dashes that chase each other around the border.

**Step 2: Verify grid still works in +page.svelte**

The `+page.svelte` already uses `grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5` with `<AgentCard {agent} />`. The 2:3 cards will render naturally in the grid. No changes needed to `+page.svelte`.

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/lib/components/agents/AgentCard.svelte
git commit -m "feat(palais): redesign AgentCard — 2:3 portrait format with SVG activity ring

Ring traces the photo border, animates with chase effect when agent is busy.
Bio snippet shown below name if available.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Replace emoji page titles with Adinkra icons

**Files:**
- Modify: `roles/palais/files/app/src/routes/missions/+page.svelte`
- Modify: `roles/palais/files/app/src/routes/ideas/+page.svelte`
- Modify: `roles/palais/files/app/src/routes/memory/+page.svelte`

### 7a — Missions page (🚀 → Akoma)

In `missions/+page.svelte`, add the import at the top of `<script>`:

```typescript
import { Akoma } from '$lib/components/icons';
```

Then replace (around line 56–58):
```svelte
<h1 class="text-xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
    🚀 Missions
</h1>
```

with:
```svelte
<h1 class="text-xl font-bold flex items-center gap-2" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
    <Akoma size={20} />
    Missions
</h1>
```

### 7b — Ideas page (💡 → Fawohodie)

In `ideas/+page.svelte`, add import in `<script>`:

```typescript
import { Fawohodie } from '$lib/components/icons';
```

Replace (around line 94–96):
```svelte
<h1 class="text-xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
    💡 Ideas
</h1>
```

with:
```svelte
<h1 class="text-xl font-bold flex items-center gap-2" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
    <Fawohodie size={20} />
    Ideas
</h1>
```

### 7c — Memory/Knowledge Graph page (🧠 → Sankofa)

In `memory/+page.svelte`, add import in `<script>`:

```typescript
import { Sankofa } from '$lib/components/icons';
```

Replace (around line 179–181):
```svelte
<h1 class="text-xl font-bold" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
    🧠 Knowledge Graph
</h1>
```

with:
```svelte
<h1 class="text-xl font-bold flex items-center gap-2" style="font-family: 'Orbitron', sans-serif; color: var(--palais-text);">
    <Sankofa size={20} />
    Knowledge Graph
</h1>
```

**Step 2: Commit all 3 together**

```bash
git add roles/palais/files/app/src/routes/missions/+page.svelte \
        roles/palais/files/app/src/routes/ideas/+page.svelte \
        roles/palais/files/app/src/routes/memory/+page.svelte
git commit -m "feat(palais): replace emoji page titles with Adinkra SVG icons

Missions: 🚀 → Akoma | Ideas: 💡 → Fawohodie | Memory: 🧠 → Sankofa
Consistent with sidebar icon language.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Extend health webhook to accept `local_ip`

**Files:**
- Modify: `roles/palais/files/app/src/routes/api/v1/health/webhook/+server.ts`

**Step 1: Add `local_ip` to `HealthPayload` interface**

```typescript
interface HealthPayload {
	node: string;
	services: ServiceCheck[];
	cpu_percent?: number;
	ram_percent?: number;
	disk_percent?: number;
	temperature?: number;
	local_ip?: string;   // ← add this
}
```

**Step 2: Include `localIp` in the node UPDATE**

In the `db.update(nodes).set({...})` call, add:

```typescript
localIp: body.local_ip ?? undefined,
```

> The `?? undefined` ensures we don't overwrite a stored IP with null if the field is absent from the payload.

**Step 3: Commit**

```bash
git add "roles/palais/files/app/src/routes/api/v1/health/webhook/+server.ts"
git commit -m "feat(palais): accept local_ip in health webhook payload

Each server can now auto-report its LAN IP via the webhook.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9: Add PATCH endpoint for manual node IP editing

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/health/nodes/[name]/+server.ts`

**Step 1: Create the file**

```typescript
import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { nodes } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const PATCH: RequestHandler = async ({ params, request }) => {
	const { name } = params;
	const body = await request.json() as { localIp?: string; description?: string };

	if (body.localIp === undefined && body.description === undefined) {
		throw error(400, 'No fields to update');
	}

	const set: Record<string, unknown> = {};
	if (body.localIp !== undefined) set.localIp = body.localIp;
	if (body.description !== undefined) set.description = body.description;

	const [updated] = await db
		.update(nodes)
		.set(set)
		.where(eq(nodes.name, name))
		.returning({ id: nodes.id });

	if (!updated) throw error(404, `Node "${name}" not found`);

	return json({ ok: true });
};
```

**Step 2: Commit**

```bash
git add "roles/palais/files/app/src/routes/api/v1/health/nodes/[name]/+server.ts"
git commit -m "feat(palais): PATCH /api/v1/health/nodes/[name] — manual LAN IP editing fallback

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Show both IPs on health page node cards

**Files:**
- Modify: `roles/palais/files/app/src/routes/health/+page.svelte`

**Goal:** In the node detail card section, display `localIp` (LAN) alongside `tailscaleIp` (VPN).

**Step 1: Find the node card section**

Search for the section that renders node details — it will show `tailscaleIp` somewhere. Add `localIp` display beside it.

After finding the IP display line (look for `tailscaleIp` or `vpnNode`), add:

```svelte
{#if node.localIp}
    <span class="text-xs font-mono" style="color: var(--palais-text-muted);">
        LAN: {node.localIp}
    </span>
{/if}
{#if node.tailscaleIp}
    <span class="text-xs font-mono" style="color: var(--palais-cyan);">
        VPN: {node.tailscaleIp}
    </span>
{/if}
```

**Step 2: Also display `node.description` if populated**

Where the node card shows the node name/title, add below it:
```svelte
{#if node.description}
    <p class="text-xs" style="color: var(--palais-text-muted);">{node.description}</p>
{/if}
```

**Step 3: Read the full health page SVG section and update `NODE_POSITIONS` to be dynamic**

The `NODE_POSITIONS` constant currently hardcodes `'sese-ai'`, `'rpi5'`, `'seko-vpn'`. To make it dynamic (uses whatever node names are in DB), change the approach: generate positions automatically from the `data.nodes` array with a circular/fixed layout based on index.

Replace the hardcoded constant:
```typescript
// Dynamic: position nodes evenly in SVG space based on their DB order
function nodePos(name: string): { x: number; y: number; label: string } {
    const LAYOUT: Record<string, { x: number; y: number; label: string }> = {};
    const positions = [
        { x: 200, y: 80 },
        { x: 50,  y: 200 },
        { x: 350, y: 200 },
        { x: 200, y: 260 },  // fallback for 4th node
    ];
    data.nodes.forEach((n, i) => {
        LAYOUT[n.name] = { ...positions[i] ?? { x: 200, y: 140 }, label: n.description ?? n.name };
    });
    return LAYOUT[name] ?? { x: 200, y: 140, label: name };
}
```

And remove the old `const NODE_POSITIONS = { ... }` and old `function nodePos()`.

**Step 4: Commit**

```bash
git add roles/palais/files/app/src/routes/health/+page.svelte
git commit -m "feat(palais): show LAN + VPN IPs on health node cards, dynamic node positions

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11: n8n workflow nuclear cleanup — `--tags n8n-nuke`

**Files:**
- Modify: `roles/n8n-provision/tasks/main.yml`

**Step 1: Add the nuke tasks at the TOP of the file** (before the container check), or as a clearly separate block at the bottom tagged `n8n-nuke`.

**Strategy:** Since the existing delete-workflow JS script already handles one workflow at a time, the nuke script needs to:
1. GET all workflow IDs via `n8n list:workflow`
2. For each: deactivate → archive → delete

Add these tasks at the **end** of `main.yml`, tagged `n8n-nuke`:

```yaml
# ========================================================================
# WORKFLOW NUKE — delete ALL workflows (use with --tags n8n-nuke)
# Sequence: deactivate → archive → delete each workflow
# Run BEFORE reimport to clean up duplicates.
# ========================================================================

- name: "[nuke] Check n8n container exists before nuke"
  ansible.builtin.command:
    cmd: "docker ps -q -f name={{ project_name }}_n8n"
  register: n8n_nuke_container_check
  changed_when: false
  failed_when: false
  become: true
  tags: [n8n-nuke]

- name: "[nuke] Delete ALL n8n workflows"
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: |
      set -o pipefail
      cat > /tmp/n8n-nuke-all.js << 'NUKESCRIPT'
      const http = require('http');
      const [email, pw] = process.argv.slice(2);

      function req(method, path, body, cookie) {
        return new Promise((resolve, reject) => {
          const h = { 'Content-Type': 'application/json' };
          if (cookie) h['Cookie'] = cookie;
          const opts = { hostname: '127.0.0.1', port: 5678, path, method, headers: h };
          const r = http.request(opts, (res) => {
            let d = ''; res.on('data', c => d += c);
            res.on('end', () => {
              const sc = res.headers['set-cookie'];
              resolve({ s: res.statusCode, d, c: sc ? sc[0].split(';')[0] : null });
            });
          });
          r.on('error', reject);
          if (body) r.write(JSON.stringify(body));
          r.end();
        });
      }

      (async () => {
        const login = await req('POST', '/rest/login', { emailOrLdapLoginId: email, password: pw });
        if (login.s !== 200 || !login.c) { console.log('LOGIN_FAILED'); process.exit(1); }

        // Paginate through all workflows
        let allWorkflows = [];
        let skip = 0;
        while (true) {
          const res = await req('GET', '/rest/workflows?limit=50&skip=' + skip, null, login.c);
          const data = JSON.parse(res.d);
          const items = data.data || [];
          allWorkflows = allWorkflows.concat(items);
          if (items.length < 50) break;
          skip += 50;
        }

        console.log('FOUND:' + allWorkflows.length);

        for (const wf of allWorkflows) {
          try {
            await req('PATCH', '/rest/workflows/' + wf.id, { active: false }, login.c);
            await req('POST', '/rest/workflows/' + wf.id + '/archive', null, login.c);
            const del = await req('DELETE', '/rest/workflows/' + wf.id, null, login.c);
            console.log(del.s === 200 ? 'DELETED:' + wf.name : 'FAIL:' + del.s + ':' + wf.name);
          } catch (e) {
            console.log('ERROR:' + wf.name + ':' + e.message);
          }
        }
        console.log('NUKE_COMPLETE');
      })().catch(e => { console.log('FATAL:' + e.message); process.exit(1); });
      NUKESCRIPT

      docker cp /tmp/n8n-nuke-all.js {{ project_name }}_n8n:/home/node/n8n-nuke-all.js
      RESULT=$(docker exec {{ project_name }}_n8n node /home/node/n8n-nuke-all.js \
        "{{ n8n_owner_email }}" "{{ n8n_owner_password }}" 2>&1)
      echo "$RESULT"
  register: n8n_nuke_result
  changed_when: "'NUKE_COMPLETE' in (n8n_nuke_result.stdout | default(''))"
  failed_when: "'LOGIN_FAILED' in (n8n_nuke_result.stdout | default('')) or 'FATAL:' in (n8n_nuke_result.stdout | default(''))"
  no_log: true
  become: true
  tags: [n8n-nuke]
  when: n8n_nuke_container_check.stdout | default('') | length > 0

- name: "[nuke] Display nuke results"
  ansible.builtin.debug:
    msg: "{{ n8n_nuke_result.stdout_lines | default(['skipped']) }}"
  tags: [n8n-nuke]
  when: n8n_nuke_container_check.stdout | default('') | length > 0

- name: "[nuke] Reset workflow checksums after nuke (force reimport on next deploy)"
  ansible.builtin.file:
    path: "/opt/{{ project_name }}/configs/n8n/workflow-checksums"
    state: absent
  become: true
  tags: [n8n-nuke]
  when: n8n_nuke_container_check.stdout | default('') | length > 0

- name: "[nuke] Recreate empty checksum directory"
  ansible.builtin.file:
    path: "/opt/{{ project_name }}/configs/n8n/workflow-checksums"
    state: directory
    mode: "0755"
  become: true
  tags: [n8n-nuke]
  when: n8n_nuke_container_check.stdout | default('') | length > 0
```

**Step 2: Commit**

```bash
git add roles/n8n-provision/tasks/main.yml
git commit -m "feat(n8n): add --tags n8n-nuke task to delete ALL workflows

Deactivates → archives → deletes every workflow in sequence.
Also resets checksums directory so next deploy reimports everything.

Usage: make deploy-role ROLE=n8n-provision ENV=prod EXTRA_TAGS=n8n-nuke
Or: ansible-playbook playbooks/site.yml --tags n8n-nuke

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 12: Deploy to production and verify

**Step 1: Push branch and deploy Palais**

```bash
# Push the commits
git push github-seko main

# Deploy Palais role only (fast — no infra changes)
source .venv/bin/activate
make deploy-role ROLE=palais ENV=prod
```

Expected: `ok=X changed=Y failed=0`

**Step 2: Verify Palais container restarted with new code**

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 \
  "docker logs --tail 30 javisi_palais 2>&1 | grep -E 'seed|error|started'"
```

Expected: No `seedAgentBios` log line. No errors.

**Step 3: Visual check in browser**

Navigate to the Palais dashboard on VPN:
- `/agents` → cards should be 2:3 portrait format with SVG ring. No "Général d'État-Major" card.
- `/missions` → title shows Akoma icon, no 🚀
- `/ideas` → title shows Fawohodie icon, no 💡
- `/memory` → title shows Sankofa icon, no 🧠
- `/health` → node cards show localIp + tailscaleIp (both may be null until webhooks run)

**Step 4: Test n8n nuke (when ready)**

```bash
source .venv/bin/activate
ansible-playbook playbooks/site.yml --tags n8n-nuke -v
```

Expected output includes:
```
FOUND:XX
DELETED:AI Translate
DELETED:Budget Monitor
...
NUKE_COMPLETE
```

Then run full deploy to reimport clean workflows:
```bash
make deploy-role ROLE=n8n-provision ENV=prod
```

---

## Summary of Files Changed

| File | Action |
|------|--------|
| `roles/palais/files/app/src/lib/server/db/seed.ts` | Remove `seedAgentBios()` function |
| `roles/palais/files/app/src/hooks.server.ts` | Remove import + call of `seedAgentBios` |
| `roles/palais/files/app/src/lib/types/agent.ts` | Add `name/persona/bio/avatarUrl` to `AgentEvent` |
| `roles/palais/files/app/src/lib/server/ws/openclaw.ts` | Handle `agent.registered` event (UPDATE only) |
| `roles/palais/files/app/src/routes/api/v1/agents/[id]/+server.ts` | CREATE — PATCH bio/persona endpoint |
| `roles/palais/files/app/src/lib/components/agents/AgentCard.svelte` | Redesign: 2:3 photo + SVG ring |
| `roles/palais/files/app/src/routes/missions/+page.svelte` | Replace 🚀 with `<Akoma>` |
| `roles/palais/files/app/src/routes/ideas/+page.svelte` | Replace 💡 with `<Fawohodie>` |
| `roles/palais/files/app/src/routes/memory/+page.svelte` | Replace 🧠 with `<Sankofa>` |
| `roles/palais/files/app/src/routes/api/v1/health/webhook/+server.ts` | Add `local_ip` field |
| `roles/palais/files/app/src/routes/api/v1/health/nodes/[name]/+server.ts` | CREATE — PATCH localIp/description |
| `roles/palais/files/app/src/routes/health/+page.svelte` | Show both IPs, dynamic node positions |
| `roles/n8n-provision/tasks/main.yml` | Add `--tags n8n-nuke` tasks |

## Execution Order

1. **Task 1** — Delete ghost from DB (VPS direct command, before deploy)
2. **Tasks 2–11** — Code changes (can commit in any order, deploy together)
3. **Task 12** — Deploy + verify
4. **n8n nuke** — Run separately with `--tags n8n-nuke` when ready to clean workflows
