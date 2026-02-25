# Health Page v2 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Corriger la page Health pour qu'elle affiche les statuts réels des nodes via Headscale, montre les IPs, et permette l'édition des nodes via modal.

**Architecture:** Headscale devient la source de vérité des statuts au chargement. `+page.server.ts` sync les statuts en DB via l'API Headscale. Si Headscale est injoignable, status `degraded`. Le frontend ajoute un modal d'édition par node (PATCH existant), et des badges améliorés.

**Tech Stack:** SvelteKit 5 (Svelte 5 runes), Drizzle ORM, PostgreSQL, TypeScript, Tailwind CSS, JetBrains Mono / Orbitron fonts

---

## Contexte important

- **Pas de suite de tests unitaires** dans ce projet — vérification via `npm run check` (svelte-check + TypeScript) puis inspection visuelle dans le navigateur après déploiement.
- **App path :** `roles/palais/files/app/src/`
- **Deploy :** `source .venv/bin/activate && make deploy-role ROLE=palais ENV=prod` depuis `/home/asus/seko/VPAI`
- **Status enum valides :** `'online' | 'offline' | 'busy' | 'degraded'` (déjà dans DB schema)
- **PATCH endpoint existant :** `PATCH /api/v1/health/nodes/[name]` — accepte `{ localIp?, description? }` — **PAS tailscaleIp** (le backend actuel ne l'a pas encore). À étendre.

---

## Task 1: Étendre headscale.ts — retourner erreur distinguable

**Fichiers :**
- Modifier : `src/lib/server/health/headscale.ts`

**Contexte :** La fonction retourne actuellement `VPNNode[]` (tableau vide en cas d'erreur). On ne peut pas distinguer "0 nodes" de "API down". Il faut changer le type de retour.

**Step 1: Remplacer le contenu de headscale.ts**

```typescript
import { env } from '$env/dynamic/private';

export interface VPNNode {
	name: string;
	ip: string | null;
	online: boolean;
	lastSeen: string | null;
}

export interface VPNTopologyResult {
	nodes: VPNNode[];
	error: boolean;
}

export async function fetchVPNTopology(): Promise<VPNTopologyResult> {
	const url = env.HEADSCALE_URL;
	const apiKey = env.HEADSCALE_API_KEY;

	if (!url || !apiKey) {
		console.warn('[headscale] HEADSCALE_URL or HEADSCALE_API_KEY not configured');
		return { nodes: [], error: false };
	}

	try {
		const res = await fetch(`${url}/api/v1/machine`, {
			headers: { Authorization: `Bearer ${apiKey}` },
			signal: AbortSignal.timeout(5000)
		});

		if (!res.ok) {
			console.error(`[headscale] API error: ${res.status} ${res.statusText}`);
			return { nodes: [], error: true };
		}

		const data = await res.json();
		const machines: unknown[] = data.machines ?? [];

		return {
			nodes: machines.map((m: any) => ({
				name: m.givenName ?? m.name ?? 'unknown',
				ip: m.ipAddresses?.[0] ?? null,
				online: Boolean(m.online),
				lastSeen: m.lastSeen ?? null
			})),
			error: false
		};
	} catch (err) {
		console.error('[headscale] fetch failed:', err);
		return { nodes: [], error: true };
	}
}
```

**Step 2: Vérifier TypeScript**

```bash
cd roles/palais/files/app && npm run check 2>&1 | head -30
```

Attendu: Erreurs TypeScript sur `+page.server.ts` (utilise encore l'ancien return type) → normal, on les corrige à la tâche suivante.

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/lib/server/health/headscale.ts
git commit -m "feat(palais/health): headscale returns {nodes, error} to distinguish API down from empty"
```

---

## Task 2: Mettre à jour +page.server.ts — sync Headscale → DB

**Fichiers :**
- Modifier : `src/routes/health/+page.server.ts`

**Contexte :** Après fetch Headscale, mettre à jour les statuts en DB. Si `error: true` → tous les nodes passent à `degraded`. Si succès → chaque node avec un `tailscaleIp` est matché et mis à jour. Les nodes avec status `busy` (envoyés par webhook n8n) ne sont **pas** écrasés si le node est online dans Headscale (Headscale dit online → on respecte le `busy` du webhook).

**Step 1: Remplacer le contenu de +page.server.ts**

```typescript
import { db } from '$lib/server/db';
import { nodes, healthChecks, backupStatus } from '$lib/server/db/schema';
import { fetchVPNTopology } from '$lib/server/health/headscale';
import { desc, eq } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	// 1. Fetch VPN topology from Headscale
	const { nodes: vpnNodes, error: headscaleError } = await fetchVPNTopology();
	const headscaleOk = !headscaleError;

	// 2. Sync statuses to DB
	const allCurrentNodes = await db.select().from(nodes);

	for (const node of allCurrentNodes) {
		if (headscaleError) {
			// Headscale unreachable → mark degraded (only if not busy)
			if (node.status !== 'busy') {
				await db.update(nodes).set({ status: 'degraded' }).where(eq(nodes.id, node.id));
			}
		} else if (node.tailscaleIp) {
			// Match by Tailscale IP
			const vpnMatch = vpnNodes.find((v) => v.ip === node.tailscaleIp);
			if (vpnMatch) {
				if (vpnMatch.online && node.status !== 'busy') {
					await db.update(nodes).set({
						status: 'online',
						lastSeenAt: vpnMatch.lastSeen ? new Date(vpnMatch.lastSeen) : new Date()
					}).where(eq(nodes.id, node.id));
				} else if (!vpnMatch.online && node.status !== 'busy') {
					await db.update(nodes).set({ status: 'offline' }).where(eq(nodes.id, node.id));
				}
			} else if (node.status !== 'busy') {
				// Node has Tailscale IP but not found in Headscale
				await db.update(nodes).set({ status: 'offline' }).where(eq(nodes.id, node.id));
			}
		}
	}

	// 3. Re-fetch nodes after sync
	const allNodes = await db.select().from(nodes).orderBy(nodes.name);

	// 4. Health checks (latest per node+service)
	const recentChecks = await db
		.select()
		.from(healthChecks)
		.orderBy(desc(healthChecks.checkedAt))
		.limit(500);

	const latestByNodeService = new Map<string, typeof recentChecks[0]>();
	for (const check of recentChecks) {
		const key = `${check.nodeId}:${check.serviceName}`;
		if (!latestByNodeService.has(key)) {
			latestByNodeService.set(key, check);
		}
	}

	// 5. Backup status
	const backups = await db.select().from(backupStatus).orderBy(desc(backupStatus.id));
	const latestBackupByNode = new Map<number, typeof backups[0]>();
	for (const b of backups) {
		if (!latestBackupByNode.has(b.nodeId)) {
			latestBackupByNode.set(b.nodeId, b);
		}
	}

	const nodesWithHealth = allNodes.map((node) => ({
		...node,
		services: Array.from(latestByNodeService.values()).filter((c) => c.nodeId === node.id),
		backup: latestBackupByNode.get(node.id) ?? null
	}));

	return { nodes: nodesWithHealth, vpnTopology: vpnNodes, headscaleOk };
};
```

**Step 2: Vérifier TypeScript**

```bash
cd roles/palais/files/app && npm run check 2>&1 | head -40
```

Attendu: 0 erreurs TypeScript (ou uniquement des erreurs dans `+page.svelte` sur `headscaleOk` qui n'est pas encore utilisé — acceptable).

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/routes/health/+page.server.ts
git commit -m "feat(palais/health): sync Headscale status to DB on page load (degraded if unreachable)"
```

---

## Task 3: Étendre PATCH endpoint — ajouter tailscaleIp

**Fichiers :**
- Modifier : `src/routes/api/v1/health/nodes/[name]/+server.ts`

**Contexte :** Le PATCH actuel accepte `localIp` et `description`. On doit ajouter `tailscaleIp` pour que le modal puisse l'éditer.

**Step 1: Remplacer le contenu du PATCH endpoint**

```typescript
import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { nodes } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const PATCH: RequestHandler = async ({ params, request }) => {
	const { name } = params;
	const body = await request.json() as {
		localIp?: string;
		tailscaleIp?: string;
		description?: string;
	};

	if (body.localIp === undefined && body.description === undefined && body.tailscaleIp === undefined) {
		throw error(400, 'No fields to update');
	}

	const set: Record<string, unknown> = {};
	if (body.localIp !== undefined) set.localIp = body.localIp || null;
	if (body.tailscaleIp !== undefined) set.tailscaleIp = body.tailscaleIp || null;
	if (body.description !== undefined) set.description = body.description || null;

	const [updated] = await db
		.update(nodes)
		.set(set)
		.where(eq(nodes.name, name))
		.returning({ id: nodes.id });

	if (!updated) throw error(404, `Node "${name}" not found`);

	return json({ ok: true });
};
```

**Step 2: Vérifier TypeScript**

```bash
cd roles/palais/files/app && npm run check 2>&1 | grep -E 'error|Error' | head -20
```

Attendu: Aucune nouvelle erreur.

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/routes/api/v1/health/nodes/[name]/+server.ts
git commit -m "feat(palais/health): PATCH /nodes/[name] accepts tailscaleIp field"
```

---

## Task 4: Fix Ansible — variables IPs manquantes

**Fichiers :**
- Modifier : `inventory/group_vars/all/main.yml`
- Modifier : `roles/palais/templates/palais.env.j2`

**Contexte :** `vpn_server_ip` et `workstation_pi_local_ip` ne sont pas définis dans `main.yml`. Le template `.env.j2` les utilise. Résultat : IPs locales vides dans la DB.

**Step 1: Ajouter les variables manquantes dans main.yml**

Dans `main.yml`, après la ligne `workstation_pi_tailscale_ip:` (ligne ~195), ajouter :

```yaml
workstation_pi_local_ip: "{{ vault_workstation_pi_local_ip | default(workstation_pi_ip) }}"
```

Après la ligne `vpn_server_public_ip:` (ligne ~187), ajouter :

```yaml
vpn_server_ip: "{{ vault_vpn_server_ip | default(vpn_server_public_ip) }}"
```

**Logique :**
- `workstation_pi_local_ip` utilise `workstation_pi_ip` comme fallback (déjà vault-backed, c'est l'IP LAN du Pi)
- `vpn_server_ip` utilise `vpn_server_public_ip` comme fallback (IP publique du serveur VPN)

**Step 2: Vérifier que le template .env.j2 est correct**

Vérifier que `roles/palais/templates/palais.env.j2` contient bien :
```
SESE_AI_LOCAL_IP={{ prod_ssh_host | default('') }}
WORKSTATION_PI_LOCAL_IP={{ workstation_pi_local_ip | default('') }}
SEKO_VPN_LOCAL_IP={{ vpn_server_ip | default('') }}
```

Si `prod_ssh_host` n'est pas défini, remplacer par `vps_ip | default('')` (vérifier le nom de la variable dans main.yml).

**Step 3: Vérifier main.yml syntax**

```bash
source .venv/bin/activate && ansible-inventory --list --yaml 2>&1 | grep -E 'ERROR|error' | head -10
```

Attendu: Aucune erreur.

**Step 4: Commit**

```bash
git add inventory/group_vars/all/main.yml
git commit -m "fix(ansible): add workstation_pi_local_ip and vpn_server_ip aliases for palais env seed"
```

---

## Task 5: Refonte +page.svelte — modal édition + UI améliorée

**Fichiers :**
- Modifier : `src/routes/health/+page.svelte`

**Contexte :** Ajouter le modal d'édition par node et améliorer les status badges. L'icône d'édition est un **SVG crayon** (pas un emoji). Les champs éditables : description, tailscaleIp, localIp.

**Step 1: Remplacer le script section (lines 1-71)**

```svelte
<script lang="ts">
	import { invalidateAll } from '$app/navigation';

	let { data } = $props();

	// ─── Edit modal state ────────────────────────────────────────────
	interface EditState {
		name: string;
		description: string;
		tailscaleIp: string;
		localIp: string;
	}

	let editNode = $state<EditState | null>(null);
	let saving = $state(false);
	let saveError = $state('');

	function openEdit(node: typeof data.nodes[0]) {
		editNode = {
			name: node.name,
			description: node.description ?? '',
			tailscaleIp: node.tailscaleIp ?? '',
			localIp: node.localIp ?? ''
		};
		saveError = '';
	}

	function closeEdit() {
		editNode = null;
		saveError = '';
	}

	async function saveEdit() {
		if (!editNode) return;
		saving = true;
		saveError = '';
		try {
			const res = await fetch(`/api/v1/health/nodes/${encodeURIComponent(editNode.name)}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					description: editNode.description,
					tailscaleIp: editNode.tailscaleIp,
					localIp: editNode.localIp
				})
			});
			if (!res.ok) {
				const err = await res.json().catch(() => ({ message: 'Erreur inconnue' }));
				saveError = err.message ?? `HTTP ${res.status}`;
			} else {
				closeEdit();
				await invalidateAll();
			}
		} catch (e) {
			saveError = 'Erreur réseau';
		} finally {
			saving = false;
		}
	}

	// ─── Topology positions ──────────────────────────────────────────
	const POSITION_SLOTS = [
		{ x: 200, y: 80  },
		{ x: 50,  y: 200 },
		{ x: 350, y: 200 },
		{ x: 200, y: 300 }
	];

	const VPN_LINKS = [
		{ from: 'sese-ai', to: 'seko-vpn' },
		{ from: 'rpi5',    to: 'seko-vpn' },
		{ from: 'sese-ai', to: 'rpi5' }
	];

	function nodePos(name: string): { x: number; y: number; label: string } {
		const idx = data.nodes.findIndex((n) => n.name === name);
		const slot = POSITION_SLOTS[idx] ?? { x: 200, y: 140 };
		const node = data.nodes.find((n) => n.name === name);
		return { ...slot, label: node?.description ?? name };
	}

	function statusColor(status: string) {
		return status === 'online'   ? 'var(--palais-green)'      :
		       status === 'offline'  ? 'var(--palais-red)'        :
		       status === 'busy'     ? 'var(--palais-gold)'       :
		       status === 'degraded' ? 'var(--palais-amber)'      : 'var(--palais-text-muted)';
	}

	function statusGlow(status: string) {
		return status === 'online'   ? '0 0 12px 2px rgba(0,255,136,0.4)'   :
		       status === 'busy'     ? '0 0 12px 2px rgba(212,168,67,0.4)'  :
		       status === 'offline'  ? '0 0 8px 2px rgba(255,60,60,0.3)'    :
		       status === 'degraded' ? '0 0 12px 2px rgba(255,165,0,0.35)'  : 'none';
	}

	function cardGlow(status: string) {
		return status === 'online'   ? '0 4px 32px 0 rgba(0,255,136,0.07), 0 1px 0 0 rgba(76,175,80,0.18)'    :
		       status === 'busy'     ? '0 4px 32px 0 rgba(212,168,67,0.09), 0 1px 0 0 rgba(212,168,67,0.22)'  :
		       status === 'offline'  ? '0 4px 32px 0 rgba(255,60,60,0.08), 0 1px 0 0 rgba(229,57,53,0.2)'     :
		       status === 'degraded' ? '0 4px 32px 0 rgba(255,165,0,0.09), 0 1px 0 0 rgba(255,165,0,0.22)'    : 'none';
	}

	function statusBg(status: string) {
		return status === 'online'   ? 'rgba(76,175,80,0.12)'  :
		       status === 'busy'     ? 'rgba(212,168,67,0.12)' :
		       status === 'degraded' ? 'rgba(255,165,0,0.12)'  : 'rgba(229,57,53,0.12)';
	}

	function statusBorder(status: string) {
		return status === 'online'   ? 'rgba(76,175,80,0.25)'  :
		       status === 'busy'     ? 'rgba(212,168,67,0.25)' :
		       status === 'degraded' ? 'rgba(255,165,0,0.25)'  : 'rgba(229,57,53,0.25)';
	}

	function serviceColor(status: string) {
		return status === 'healthy'   ? 'var(--palais-green)' :
		       status === 'unhealthy' ? 'var(--palais-red)'   : 'var(--palais-amber)';
	}

	function gaugeStyle(value: number | null) {
		const pct = Math.min(Math.max(value ?? 0, 0), 100);
		const color = pct > 90 ? 'var(--palais-red)' : pct > 75 ? 'var(--palais-amber)' : 'var(--palais-green)';
		return { width: `${pct}%`, background: color };
	}

	function isBackupStale(lastBackupAt: string | Date | null) {
		if (!lastBackupAt) return true;
		const ms = Date.now() - new Date(lastBackupAt).getTime();
		return ms > 24 * 60 * 60 * 1000;
	}

	function vpnNode(tailscaleIp: string | null) {
		if (!tailscaleIp) return null;
		return data.vpnTopology.find((v) => v.ip === tailscaleIp) ?? null;
	}

	// Status counts
	const onlineCount   = $derived(data.nodes.filter((n) => n.status === 'online').length);
	const busyCount     = $derived(data.nodes.filter((n) => n.status === 'busy').length);
	const offlineCount  = $derived(data.nodes.filter((n) => n.status === 'offline').length);
	const degradedCount = $derived(data.nodes.filter((n) => n.status === 'degraded').length);
</script>
```

**Step 2: Remplacer le header section (garder la structure, ajouter headscaleOk + degraded badge)**

Remplacer la section `<!-- Status summary pills -->` et ajouter le badge "VPN UNREACHABLE" + indicateur sync :

```svelte
<!-- Status summary pills -->
<div class="flex items-center gap-2 flex-wrap">
    {#if !data.headscaleOk}
        <span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
            style="background: rgba(255,165,0,0.15); color: var(--palais-amber); border: 1px solid rgba(255,165,0,0.4); font-family: 'Orbitron', sans-serif; animation: pulseGold 1.5s ease-in-out infinite;">
            ⚠ VPN UNREACHABLE
        </span>
    {:else}
        <span class="px-2 py-0.5 rounded text-xs tracking-wider"
            style="background: rgba(0,255,136,0.06); color: rgba(0,255,136,0.4); border: 1px solid rgba(0,255,136,0.15); font-family: 'JetBrains Mono', monospace; font-size: 0.6rem;">
            ● HEADSCALE SYNC
        </span>
    {/if}
    {#if onlineCount > 0}
        <span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
            style="background: rgba(76,175,80,0.13); color: var(--palais-green); border: 1px solid rgba(76,175,80,0.3); font-family: 'Orbitron', sans-serif;">
            {onlineCount} ONLINE
        </span>
    {/if}
    {#if busyCount > 0}
        <span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
            style="background: rgba(212,168,67,0.13); color: var(--palais-gold); border: 1px solid rgba(212,168,67,0.3); font-family: 'Orbitron', sans-serif;">
            {busyCount} BUSY
        </span>
    {/if}
    {#if degradedCount > 0}
        <span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
            style="background: rgba(255,165,0,0.13); color: var(--palais-amber); border: 1px solid rgba(255,165,0,0.3); font-family: 'Orbitron', sans-serif;">
            {degradedCount} DEGRADED
        </span>
    {/if}
    {#if offlineCount > 0}
        <span class="px-3 py-1 rounded-full text-xs font-semibold tracking-wider"
            style="background: rgba(229,57,53,0.13); color: var(--palais-red); border: 1px solid rgba(229,57,53,0.3); font-family: 'Orbitron', sans-serif;">
            {offlineCount} OFFLINE
        </span>
    {/if}
</div>
```

**Step 3: Ajouter le bouton crayon SVG sur chaque node card**

Dans chaque node card, dans la section `<!-- ── Node header ── -->`, à côté du bloc `<!-- Status badge + glow ring dot -->`, ajouter un bouton édition :

```svelte
<!-- Edit button — SVG pencil icon -->
<button
    onclick={() => openEdit(node)}
    title="Éditer {node.name}"
    style="
        background: none; border: none; cursor: pointer; padding: 4px;
        color: var(--palais-gold); opacity: 0.45;
        transition: opacity 0.2s, filter 0.2s;
        flex-shrink: 0;
    "
    onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.opacity = '1'; (e.currentTarget as HTMLElement).style.filter = 'drop-shadow(0 0 6px rgba(212,168,67,0.6))'; }}
    onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.opacity = '0.45'; (e.currentTarget as HTMLElement).style.filter = 'none'; }}
>
    <!-- Pencil SVG 16×16 -->
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
</button>
```

Le bloc `flex items-start justify-between` du header de card doit intégrer ce bouton entre le nom/IPs et le badge status.

**Structure exacte du header de card :**
```svelte
<div class="flex items-start justify-between gap-2 mb-4">
    <!-- Gauche: nom + description + IPs -->
    <div class="flex-1 min-w-0">
        <!-- ... nom, description, IPs ... -->
    </div>

    <!-- Droite: bouton éditer + badge status + dot -->
    <div class="flex flex-col items-end gap-2 flex-shrink-0">
        <!-- Bouton crayon SVG -->
        <button onclick={() => openEdit(node)} ...>SVG</button>
        <!-- Status badge -->
        <span ...>{node.status.toUpperCase()}</span>
        <!-- Glow dot -->
        <span ...></span>
    </div>
</div>
```

**Step 4: Ajouter le modal d'édition (après la section `</section>` finale, avant `</div>` du wrapper)**

```svelte
<!-- ══════════════════════════════════════ EDIT NODE MODAL ═══ -->
{#if editNode}
    <!-- Backdrop -->
    <div
        style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.72); backdrop-filter: blur(4px);"
        onclick={closeEdit}
        role="presentation"
    ></div>

    <!-- Modal panel -->
    <div
        class="glass-panel hud-bracket rounded-xl"
        style="
            position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
            z-index: 101; width: min(480px, 95vw); padding: 1.5rem;
            border: 1px solid rgba(212,168,67,0.3);
            box-shadow: 0 8px 64px 0 rgba(0,0,0,0.6), 0 0 0 1px rgba(212,168,67,0.1);
        "
        role="dialog"
        aria-label="Éditer le node"
    >
        <span class="hud-bracket-bottom" style="display: block;">
            <!-- Modal header -->
            <div class="flex items-center justify-between mb-5">
                <h2 style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif; font-size: 0.85rem; letter-spacing: 0.15em; text-transform: uppercase;">
                    Éditer — {editNode.name.toUpperCase()}
                </h2>
                <button
                    onclick={closeEdit}
                    style="background: none; border: none; cursor: pointer; color: rgba(212,168,67,0.4); font-size: 1.2rem; line-height: 1; padding: 2px 6px;"
                >×</button>
            </div>

            <!-- Fields -->
            <div class="space-y-4">
                <!-- Description -->
                <div>
                    <label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
                        Description
                    </label>
                    <input
                        type="text"
                        bind:value={editNode.description}
                        placeholder="ex: OVH VPS 8 Go — Cerveau IA"
                        style="
                            width: 100%; padding: 8px 10px;
                            background: rgba(0,0,0,0.35); border-radius: 6px;
                            border: 1px solid rgba(212,168,67,0.2);
                            color: var(--palais-text); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
                            outline: none; transition: border-color 0.2s;
                        "
                        onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.5)'; }}
                        onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(212,168,67,0.2)'; }}
                    />
                </div>

                <!-- Tailscale IP -->
                <div>
                    <label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
                        IP Tailscale / VPN Singa
                    </label>
                    <input
                        type="text"
                        bind:value={editNode.tailscaleIp}
                        placeholder="100.x.x.x"
                        style="
                            width: 100%; padding: 8px 10px;
                            background: rgba(0,0,0,0.35); border-radius: 6px;
                            border: 1px solid rgba(0,212,255,0.2);
                            color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
                            outline: none; transition: border-color 0.2s;
                        "
                        onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.5)'; }}
                        onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.2)'; }}
                    />
                </div>

                <!-- Local IP -->
                <div>
                    <label style="display: block; font-family: 'Orbitron', sans-serif; font-size: 0.6rem; letter-spacing: 0.2em; color: rgba(212,168,67,0.55); text-transform: uppercase; margin-bottom: 6px;">
                        IP Locale / LAN
                    </label>
                    <input
                        type="text"
                        bind:value={editNode.localIp}
                        placeholder="192.168.x.x"
                        style="
                            width: 100%; padding: 8px 10px;
                            background: rgba(0,0,0,0.35); border-radius: 6px;
                            border: 1px solid rgba(0,212,255,0.2);
                            color: var(--palais-cyan); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
                            outline: none; transition: border-color 0.2s;
                        "
                        onfocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.5)'; }}
                        onblur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.2)'; }}
                    />
                </div>
            </div>

            <!-- Error message -->
            {#if saveError}
                <p style="color: var(--palais-red); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; margin-top: 10px;">
                    ✗ {saveError}
                </p>
            {/if}

            <!-- Buttons -->
            <div class="flex gap-3 justify-end mt-6">
                <button
                    onclick={closeEdit}
                    disabled={saving}
                    style="
                        padding: 8px 18px; border-radius: 6px; cursor: pointer;
                        background: transparent; color: rgba(212,168,67,0.6);
                        border: 1px solid rgba(212,168,67,0.25);
                        font-family: 'Orbitron', sans-serif; font-size: 0.65rem; letter-spacing: 0.12em;
                        transition: all 0.2s;
                    "
                >
                    ANNULER
                </button>
                <button
                    onclick={saveEdit}
                    disabled={saving}
                    style="
                        padding: 8px 18px; border-radius: 6px; cursor: pointer;
                        background: rgba(212,168,67,0.15); color: var(--palais-gold);
                        border: 1px solid rgba(212,168,67,0.4);
                        font-family: 'Orbitron', sans-serif; font-size: 0.65rem; letter-spacing: 0.12em;
                        transition: all 0.2s;
                        {saving ? 'opacity: 0.5; cursor: not-allowed;' : ''}
                    "
                >
                    {saving ? 'ENREGISTREMENT…' : 'ENREGISTRER'}
                </button>
            </div>
        </span>
    </div>
{/if}
```

**Step 5: Vérifier TypeScript**

```bash
cd roles/palais/files/app && npm run check 2>&1 | head -40
```

Attendu: 0 erreurs TypeScript.

**Step 6: Commit**

```bash
git add roles/palais/files/app/src/routes/health/+page.svelte
git commit -m "feat(palais/health): node edit modal (SVG pencil, PATCH tailscaleIp/localIp/description) + degraded status UI"
```

---

## Task 5.5: Topologie SVG — animations vivantes (frontend-design)

**Fichiers :**
- Modifier : `src/routes/health/+page.svelte` (section SVG topology uniquement)

**Contexte :** La topologie actuelle a des liens qui s'animent indépendamment du statut — même les nœuds offline ont des lignes animées. Les nœuds online ont des cercles statiques. L'objectif est une carte réseau "vivante" qui réagit au statut réel : nœuds respirants, liens avec paquets de données en transit, nœuds dégradés qui flickent.

**Principe frontend-design :**
- `online` → anneaux respirants verts lents (2.5s), expansion douce
- `busy` → anneaux pulsants gold rapides (1.2s), urgence visuelle
- `degraded` → flicker irrégulier amber, label "DEGRADED" clignotant
- `offline` → statique, dim, sans animation
- Liens **conditionnels** : animés + paquets en transit uniquement si les 2 extrémités sont `online` ou `busy`
- Paquets voyageurs : vert (aller) + gold (retour décalé 1.1s) via SMIL `animateMotion`

**Step 1: Remplacer la section `<!-- ═══ VPN TOPOLOGY MAP ═══ -->` entière**

Remplacer le bloc SVG (viewBox + contenu) par la version animée :

```svelte
<svg viewBox="0 0 420 360" class="w-full max-w-lg mx-auto" style="height: 240px;">

    <!-- ── Links ── -->
    {#each VPN_LINKS as link}
        {@const from = nodePos(link.from)}
        {@const to   = nodePos(link.to)}
        {@const fromNode = data.nodes.find((n) => n.name === link.from)}
        {@const toNode   = data.nodes.find((n) => n.name === link.to)}
        {@const bothActive = (fromNode?.status === 'online' || fromNode?.status === 'busy')
                          && (toNode?.status   === 'online' || toNode?.status   === 'busy')}

        <!-- Base link line — brighter + animated when both active -->
        <line
            x1={from.x} y1={from.y} x2={to.x} y2={to.y}
            stroke={bothActive ? 'rgba(212,168,67,0.28)' : 'rgba(212,168,67,0.05)'}
            stroke-width={bothActive ? '1.5' : '0.8'}
            stroke-dasharray={bothActive ? '4 6' : '2 10'}
        >
            {#if bothActive}
                <animate attributeName="stroke-dashoffset" values="0;-10" dur="1.6s" repeatCount="indefinite"/>
            {/if}
        </line>

        <!-- Traveling packet — green (aller) — only when both active -->
        {#if bothActive}
            <circle r="2.5" fill="var(--palais-green)" opacity="0">
                <animateMotion
                    dur="2.4s"
                    repeatCount="indefinite"
                    path={`M${from.x},${from.y} L${to.x},${to.y}`}
                />
                <animate attributeName="opacity" values="0;0.9;0.9;0" keyTimes="0;0.08;0.92;1"
                    dur="2.4s" repeatCount="indefinite"/>
            </circle>
            <!-- Return packet — gold (retour) — offset 1.2s -->
            <circle r="2" fill="rgba(212,168,67,0.75)" opacity="0">
                <animateMotion
                    dur="2.4s"
                    begin="1.2s"
                    repeatCount="indefinite"
                    path={`M${to.x},${to.y} L${from.x},${from.y}`}
                />
                <animate attributeName="opacity" values="0;0.75;0.75;0" keyTimes="0;0.08;0.92;1"
                    begin="1.2s" dur="2.4s" repeatCount="indefinite"/>
            </circle>
        {/if}
    {/each}

    <!-- ── Nodes ── -->
    {#each data.nodes as node}
        {@const pos       = nodePos(node.name)}
        {@const vpn       = vpnNode(node.tailscaleIp)}
        {@const isActive  = node.status === 'online' || node.status === 'busy'}
        {@const isBusy    = node.status === 'busy'}
        {@const isDeg     = node.status === 'degraded'}
        {@const pulseSpeed = isBusy ? '1.2s' : '2.8s'}

        <g transform={`translate(${pos.x}, ${pos.y})`}>

            <!-- Outer ambient ring — breathes when active, flickers when degraded -->
            <circle r="26" fill="none"
                stroke={statusColor(node.status)}
                stroke-width={isActive ? '0.8' : '0.5'}
                opacity="0.2"
            >
                {#if isActive}
                    <animate attributeName="r"       values="26;31;26" dur={pulseSpeed} repeatCount="indefinite"/>
                    <animate attributeName="opacity" values="0.12;0.45;0.12" dur={pulseSpeed} repeatCount="indefinite"/>
                {:else if isDeg}
                    <animate attributeName="opacity" values="0.15;0.06;0.22;0.04;0.18"
                        keyTimes="0;0.25;0.5;0.75;1" dur="2.8s" repeatCount="indefinite"/>
                {/if}
            </circle>

            <!-- Mid ring — synced pulse -->
            <circle r="21" fill="none"
                stroke={statusColor(node.status)}
                stroke-width="1"
                opacity={isActive ? '0.4' : '0.12'}
            >
                {#if isActive}
                    <animate attributeName="opacity" values="0.25;0.6;0.25" dur={pulseSpeed} repeatCount="indefinite"/>
                {/if}
            </circle>

            <!-- Node core -->
            <circle r="17"
                fill="var(--palais-surface)"
                stroke={statusColor(node.status)}
                stroke-width={isActive ? '2' : '1.2'}
                opacity={isDeg ? '0.6' : isActive ? '1' : '0.5'}
            />

            <!-- Node initials -->
            <text
                text-anchor="middle"
                dominant-baseline="middle"
                font-size="10"
                font-weight="bold"
                fill={statusColor(node.status)}
                font-family="JetBrains Mono, monospace"
                opacity={isActive ? '1' : isDeg ? '0.6' : '0.4'}
            >
                {node.name.substring(0, 2).toUpperCase()}
            </text>

            <!-- Label below -->
            <text
                text-anchor="middle"
                y="34"
                font-size="7.5"
                fill="rgba(212,168,67,0.6)"
                font-family="Orbitron, sans-serif"
                letter-spacing="1"
            >
                {nodePos(node.name).label.toUpperCase().substring(0, 12)}
            </text>

            <!-- DEGRADED label — flickers -->
            {#if isDeg}
                <text
                    text-anchor="middle"
                    y="-28"
                    font-size="5.5"
                    fill="var(--palais-amber)"
                    font-family="Orbitron, sans-serif"
                    letter-spacing="1.5"
                >
                    <animate attributeName="opacity" values="0.7;0.2;0.8;0.1;0.6" keyTimes="0;0.3;0.5;0.7;1"
                        dur="1.8s" repeatCount="indefinite"/>
                    DEGRADED
                </text>
            {/if}

            <!-- VPN active dot — pulsing expand when online in Headscale -->
            {#if vpn?.online}
                <circle cx="14" cy="-14" r="4" fill="var(--palais-green)" opacity="0.9">
                    <animate attributeName="r"       values="4;5.5;4"     dur="1.6s" repeatCount="indefinite"/>
                    <animate attributeName="opacity" values="0.9;0.55;0.9" dur="1.6s" repeatCount="indefinite"/>
                </circle>
                <circle cx="14" cy="-14" r="7" fill="none" stroke="var(--palais-green)" stroke-width="0.8" opacity="0">
                    <animate attributeName="r"       values="5;12;5"   dur="1.6s" repeatCount="indefinite"/>
                    <animate attributeName="opacity" values="0.5;0;0.5" dur="1.6s" repeatCount="indefinite"/>
                </circle>
            {/if}
        </g>
    {/each}
</svg>
```

**Step 2: Vérifier TypeScript**

```bash
cd roles/palais/files/app && npm run check 2>&1 | grep -E 'error|Error' | head -20
```

Attendu: 0 erreurs.

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/routes/health/+page.svelte
git commit -m "feat(palais/health): topology SVG — live animations (breathing nodes, conditional packets, degraded flicker)"
```

---

## Task 6: Déployer et vérifier

**Step 1: Déployer**

```bash
cd /home/asus/seko/VPAI
source .venv/bin/activate
make deploy-role ROLE=palais ENV=prod
```

Attendu: `changed=2, failed=0` (rsync + rebuild container)

**Step 2: Vérifier dans le navigateur**

Ouvrir `https://palais.ewutelo.cloud/health` :

1. ✅ Les nodes s'affichent avec des IPs (si les variables Ansible sont peuplées)
2. ✅ Le badge "HEADSCALE SYNC" apparaît en haut à droite des status pills (si Headscale répond)
3. ✅ Les statuts sont `online` ou `offline` (pas tous `offline` comme avant)
4. ✅ Chaque node card a un icône crayon SVG en haut à droite
5. ✅ Cliquer sur le crayon ouvre un modal glass-panel avec 3 champs
6. ✅ Modifier les IPs et sauvegarder recharge la page avec les nouvelles valeurs
7. ✅ Annuler ferme le modal sans modification

**Step 3: Release v1.9.2**

```bash
cd /home/asus/seko/VPAI
git push origin main
git tag -a v1.9.2 -m "feat(palais): health page v2 — Headscale sync + node edit modal"
git push origin v1.9.2
```

Créer la GitHub Release :

```bash
gh release create v1.9.2 \
  --title "v1.9.2 — Health page v2: Headscale sync + node edit" \
  --notes-file /tmp/release_v1.9.2.md
```

---

## Résumé des fichiers modifiés

| Fichier | Type |
|---|---|
| `src/lib/server/health/headscale.ts` | Modifier — return type |
| `src/routes/health/+page.server.ts` | Modifier — sync Headscale→DB |
| `src/routes/api/v1/health/nodes/[name]/+server.ts` | Modifier — ajouter tailscaleIp |
| `src/routes/health/+page.svelte` | Modifier — modal + UI améliorée |
| `inventory/group_vars/all/main.yml` | Modifier — vars IPs manquantes |

**5 fichiers, 5 commits, 1 deploy, release v1.9.2**
