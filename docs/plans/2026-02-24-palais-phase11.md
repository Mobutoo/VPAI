# Palais Phase 11 — Proactive Intelligence (Semaine 15)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform Palais from a passive dashboard into an active intelligence system. Implement the Digital Standup (daily auto-generated briefing) and the Insight Detection Engine (proactive alerts for agent stuck, budget warnings, error patterns, dependency blocks). Connect critical insights to n8n for Telegram relay.

**Architecture:** Server-side standup generator queries tasks/budget/agents completed yesterday and calls LiteLLM to format a natural language briefing. Insight detector runs periodic checks (cron-like via `setInterval` in the server process) against known patterns. Insights are stored in the existing `insights` table. The dashboard displays the latest standup at login and shows active insights as banners. A dedicated `/insights` page lists all insights with acknowledge and action buttons. Critical insights are pushed to n8n via webhook for Telegram delivery.

**Tech Stack:** SvelteKit 5 (runes), Drizzle ORM, PostgreSQL, LiteLLM API, n8n webhooks, SSE (browser push), shadcn-svelte

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 9 (Proactive Intelligence: Digital Standup + Insights Proactifs).

**Dependencies:** Phases 1-9 must be complete. Phase 10 (MCP) exposes `palais.insights.active` and `palais.standup.latest` tools.

---

## Task 1: Digital Standup Generator

**Files:**
- Create: `roles/palais/files/app/src/lib/server/standup/generate.ts`
- Create: `roles/palais/files/app/src/lib/server/standup/scheduler.ts`

**Step 1: Create standup generator**

Create `roles/palais/files/app/src/lib/server/standup/generate.ts`:
```typescript
import { db } from '$lib/server/db';
import {
	tasks, agents, insights, budgetSnapshots,
	activityLog, timeEntries
} from '$lib/server/db/schema';
import { eq, gte, desc, and, lt, sql } from 'drizzle-orm';
import { env } from '$env/dynamic/private';

interface StandupData {
	completedYesterday: Array<{ title: string; agent: string; cost: number | null }>;
	failedTasks: Array<{ title: string; agent: string; reason: string | null }>;
	budgetSpent: number;
	budgetRemaining: number;
	activeInsights: Array<{ type: string; title: string; severity: string }>;
	agentStatuses: Array<{ name: string; status: string; currentTask: string | null }>;
	inProgressCount: number;
	blockedCount: number;
}

export async function gatherStandupData(): Promise<StandupData> {
	const now = new Date();
	const yesterday = new Date(now);
	yesterday.setDate(yesterday.getDate() - 1);
	yesterday.setHours(0, 0, 0, 0);

	const todayStart = new Date(now);
	todayStart.setHours(0, 0, 0, 0);

	// Tasks completed yesterday
	const completedYesterday = await db.select({
		title: tasks.title,
		agent: tasks.assigneeAgentId,
		cost: tasks.actualCost
	}).from(tasks)
		.where(and(
			eq(tasks.status, 'done'),
			gte(tasks.updatedAt, yesterday),
			lt(tasks.updatedAt, todayStart)
		));

	// Failed tasks (status = failed, updated yesterday or today)
	const failedTasks = await db.select({
		title: tasks.title,
		agent: tasks.assigneeAgentId
	}).from(tasks)
		.where(and(
			eq(tasks.status, 'failed'),
			gte(tasks.updatedAt, yesterday)
		));

	// Budget spent today
	const todaySnapshots = await db.select().from(budgetSnapshots)
		.where(gte(budgetSnapshots.capturedAt, todayStart));
	const budgetSpent = todaySnapshots.reduce((sum, s) => sum + (s.spendAmount ?? 0), 0);
	const dailyBudget = 5.0;

	// Active insights (non-acknowledged)
	const activeInsights = await db.select({
		type: insights.type,
		title: insights.title,
		severity: insights.severity
	}).from(insights)
		.where(eq(insights.acknowledged, false))
		.orderBy(desc(insights.createdAt))
		.limit(10);

	// Agent statuses
	const allAgents = await db.select().from(agents).orderBy(agents.name);
	const agentStatuses = allAgents.map(a => ({
		name: a.name,
		status: a.status,
		currentTask: null as string | null // Would join with tasks if currentTaskId set
	}));

	// In-progress and blocked counts
	const inProgressTasks = await db.select({ id: tasks.id }).from(tasks)
		.where(eq(tasks.status, 'in-progress'));

	// Blocked = tasks with unresolved dependencies (simplified check)
	const blockedCount = 0; // Requires dependency resolution check from Phase 4

	return {
		completedYesterday: completedYesterday.map(t => ({
			title: t.title,
			agent: t.agent ?? 'unassigned',
			cost: t.cost
		})),
		failedTasks: failedTasks.map(t => ({
			title: t.title,
			agent: t.agent ?? 'unassigned',
			reason: null // Would come from activity_log or memory
		})),
		budgetSpent: Math.round(budgetSpent * 100) / 100,
		budgetRemaining: Math.round((dailyBudget - budgetSpent) * 100) / 100,
		activeInsights,
		agentStatuses,
		inProgressCount: inProgressTasks.length,
		blockedCount
	};
}

export async function generateStandupBriefing(): Promise<{ title: string; description: string; suggestedActions: unknown[] }> {
	const data = await gatherStandupData();

	// Build structured prompt for LiteLLM
	const prompt = buildStandupPrompt(data);

	// Call LiteLLM to generate natural language summary
	const litellmUrl = env.LITELLM_URL || 'http://litellm:4000';
	const litellmKey = env.LITELLM_KEY || '';

	let summary: string;
	try {
		const res = await fetch(`${litellmUrl}/chat/completions`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'Authorization': `Bearer ${litellmKey}`
			},
			body: JSON.stringify({
				model: 'gpt-4o-mini', // eco model for standup generation
				messages: [
					{
						role: 'system',
						content: 'Tu es Palais, le systeme nerveux central de la stack IA. Genere un briefing matinal concis en francais. Style: direct, factuel, avec des recommandations actionnables. Pas de smiley. Maximum 300 mots.'
					},
					{ role: 'user', content: prompt }
				],
				max_tokens: 500,
				temperature: 0.3
			})
		});

		if (!res.ok) {
			summary = buildFallbackSummary(data);
		} else {
			const llmData = await res.json();
			summary = llmData.choices?.[0]?.message?.content ?? buildFallbackSummary(data);
		}
	} catch {
		summary = buildFallbackSummary(data);
	}

	// Build suggested actions based on data
	const suggestedActions = [];
	if (data.budgetRemaining < 1.5) {
		suggestedActions.push({
			label: 'Activer mode eco',
			action_type: 'webhook',
			params: { url: '/api/v1/budget/eco-mode', method: 'POST' }
		});
	}
	if (data.failedTasks.length > 0) {
		suggestedActions.push({
			label: 'Voir taches echouees',
			action_type: 'navigate',
			params: { url: '/projects?status=failed' }
		});
	}
	if (data.activeInsights.filter(i => i.severity === 'critical').length > 0) {
		suggestedActions.push({
			label: 'Voir insights critiques',
			action_type: 'navigate',
			params: { url: '/insights?severity=critical' }
		});
	}

	const today = new Date().toLocaleDateString('fr-FR', {
		weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
	});

	return {
		title: `Briefing du ${today}`,
		description: summary,
		suggestedActions
	};
}

function buildStandupPrompt(data: StandupData): string {
	const lines = [];

	lines.push('=== DONNEES DU JOUR ===\n');

	lines.push(`## Taches completees hier: ${data.completedYesterday.length}`);
	for (const t of data.completedYesterday) {
		lines.push(`- "${t.title}" par ${t.agent}${t.cost ? ` ($${t.cost})` : ''}`);
	}

	lines.push(`\n## Taches echouees: ${data.failedTasks.length}`);
	for (const t of data.failedTasks) {
		lines.push(`- "${t.title}" par ${t.agent}${t.reason ? ` — Raison: ${t.reason}` : ''}`);
	}

	lines.push(`\n## Budget`);
	lines.push(`- Depense aujourd'hui: $${data.budgetSpent}`);
	lines.push(`- Restant: $${data.budgetRemaining} / $5.00`);

	lines.push(`\n## Etat actuel`);
	lines.push(`- Taches en cours: ${data.inProgressCount}`);
	lines.push(`- Taches bloquees: ${data.blockedCount}`);

	lines.push(`\n## Agents`);
	for (const a of data.agentStatuses) {
		lines.push(`- ${a.name}: ${a.status}`);
	}

	if (data.activeInsights.length > 0) {
		lines.push(`\n## Anomalies detectees: ${data.activeInsights.length}`);
		for (const i of data.activeInsights) {
			lines.push(`- [${i.severity.toUpperCase()}] ${i.title}`);
		}
	}

	lines.push('\n=== INSTRUCTIONS ===');
	lines.push('Genere un briefing matinal structure avec:');
	lines.push('1. Resume de la veille (completions + echecs)');
	lines.push('2. Etat budget et projection');
	lines.push('3. Points d\'attention (anomalies, blocages)');
	lines.push('4. Priorites recommandees pour la journee');

	return lines.join('\n');
}

function buildFallbackSummary(data: StandupData): string {
	const lines = [];
	lines.push(`Hier: ${data.completedYesterday.length} taches completees, ${data.failedTasks.length} echouees.`);
	lines.push(`Budget: $${data.budgetSpent} depenses, $${data.budgetRemaining} restant.`);
	lines.push(`En cours: ${data.inProgressCount} taches. Bloquees: ${data.blockedCount}.`);
	if (data.activeInsights.length > 0) {
		lines.push(`Attention: ${data.activeInsights.length} insight(s) actif(s).`);
	}
	return lines.join(' ');
}
```

**Step 2: Create standup scheduler**

Create `roles/palais/files/app/src/lib/server/standup/scheduler.ts`:
```typescript
import { generateStandupBriefing } from './generate';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { env } from '$env/dynamic/private';

let schedulerStarted = false;

export function startStandupScheduler(): void {
	if (schedulerStarted) return;
	schedulerStarted = true;

	const standupHour = parseInt(env.STANDUP_HOUR || '08', 10);

	// Check every 15 minutes if it's time for the standup
	setInterval(async () => {
		const now = new Date();
		if (now.getHours() === standupHour && now.getMinutes() < 15) {
			await generateAndStoreStandup();
		}
	}, 15 * 60 * 1000);

	console.log(`[Palais] Standup scheduler started — will generate at ${standupHour}:00`);
}

export async function generateAndStoreStandup(): Promise<void> {
	try {
		const briefing = await generateStandupBriefing();

		// Store as insight with type 'standup'
		await db.insert(insights).values({
			type: 'standup',
			severity: 'info',
			title: briefing.title,
			description: briefing.description,
			suggestedActions: briefing.suggestedActions,
			acknowledged: false
		});

		console.log(`[Palais] Standup generated: ${briefing.title}`);

		// Push to n8n webhook for Telegram relay
		await pushStandupToN8n(briefing);
	} catch (err) {
		console.error('[Palais] Standup generation failed:', err);
	}
}

async function pushStandupToN8n(briefing: { title: string; description: string }): Promise<void> {
	const n8nBase = env.N8N_WEBHOOK_BASE || 'http://n8n:5678/webhook';

	try {
		await fetch(`${n8nBase}/palais-standup`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				title: briefing.title,
				content: briefing.description,
				timestamp: new Date().toISOString()
			})
		});
	} catch {
		// n8n webhook failure is non-fatal
		console.warn('[Palais] Failed to push standup to n8n webhook');
	}
}
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/lib/server/standup/
git commit -m "feat(palais): Digital Standup generator — LiteLLM briefing + scheduler"
```

---

## Task 2: Standup API

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/standup/latest/+server.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/standup/generate/+server.ts`

**Step 1: GET latest standup**

Create `roles/palais/files/app/src/routes/api/v1/standup/latest/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';

export const GET: RequestHandler = async () => {
	const [latest] = await db.select().from(insights)
		.where(eq(insights.type, 'standup'))
		.orderBy(desc(insights.createdAt))
		.limit(1);

	if (!latest) {
		return json({ generated: false, message: 'No standup available yet' });
	}

	return json({
		generated: true,
		id: latest.id,
		title: latest.title,
		description: latest.description,
		suggestedActions: latest.suggestedActions,
		createdAt: latest.createdAt
	});
};
```

**Step 2: POST trigger standup generation (manual)**

Create `roles/palais/files/app/src/routes/api/v1/standup/generate/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { generateAndStoreStandup } from '$lib/server/standup/scheduler';

export const POST: RequestHandler = async () => {
	try {
		await generateAndStoreStandup();
		return json({ success: true, message: 'Standup generated' });
	} catch (err) {
		const message = err instanceof Error ? err.message : 'Unknown error';
		return json({ success: false, error: message }, { status: 500 });
	}
};
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/routes/api/v1/standup/
git commit -m "feat(palais): Standup API — GET /api/v1/standup/latest + POST generate"
```

---

## Task 3: Standup Display on Dashboard

**Files:**
- Create: `roles/palais/files/app/src/lib/components/dashboard/StandupCard.svelte`
- Modify: `roles/palais/files/app/src/routes/+page.svelte`
- Modify: `roles/palais/files/app/src/routes/+page.server.ts`

**Step 1: Create StandupCard component**

Create `roles/palais/files/app/src/lib/components/dashboard/StandupCard.svelte`:
```svelte
<script lang="ts">
	interface Standup {
		generated: boolean;
		title?: string;
		description?: string;
		suggestedActions?: Array<{ label: string; action_type: string; params: Record<string, string> }>;
		createdAt?: string;
	}

	let { standup }: { standup: Standup } = $props();
</script>

{#if standup.generated}
	<section
		class="rounded-lg p-6 relative overflow-hidden"
		style="background: var(--palais-surface); border: 1px solid var(--palais-gold); box-shadow: var(--palais-glow-sm);"
	>
		<!-- Gold accent bar -->
		<div class="absolute top-0 left-0 w-full h-0.5" style="background: var(--palais-gold);"></div>

		<div class="flex items-start justify-between mb-4">
			<h2 class="text-lg font-semibold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
				{standup.title}
			</h2>
			{#if standup.createdAt}
				<span class="text-xs tabular-nums" style="color: var(--palais-text-muted);">
					{new Date(standup.createdAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
				</span>
			{/if}
		</div>

		<div class="text-sm leading-relaxed whitespace-pre-wrap" style="color: var(--palais-text);">
			{standup.description}
		</div>

		{#if standup.suggestedActions && standup.suggestedActions.length > 0}
			<div class="flex flex-wrap gap-2 mt-4 pt-4" style="border-top: 1px solid var(--palais-border);">
				{#each standup.suggestedActions as action}
					{#if action.action_type === 'navigate'}
						<a
							href={action.params.url}
							class="px-3 py-1.5 rounded text-xs font-medium transition-all hover:brightness-110"
							style="background: transparent; color: var(--palais-gold); border: 1px solid var(--palais-gold);"
						>
							{action.label}
						</a>
					{:else}
						<button
							class="px-3 py-1.5 rounded text-xs font-medium transition-all hover:brightness-110"
							style="background: transparent; color: var(--palais-amber); border: 1px solid var(--palais-amber);"
						>
							{action.label}
						</button>
					{/if}
				{/each}
			</div>
		{/if}
	</section>
{/if}
```

**Step 2: Add standup to page server load**

Modify `roles/palais/files/app/src/routes/+page.server.ts` to also load the latest standup:
```typescript
import { db } from '$lib/server/db';
import { agents, insights } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allAgents = await db.select().from(agents).orderBy(agents.name);

	// Load latest standup
	const [latestStandup] = await db.select().from(insights)
		.where(eq(insights.type, 'standup'))
		.orderBy(desc(insights.createdAt))
		.limit(1);

	// Load active insights (non-standup)
	const activeInsights = await db.select().from(insights)
		.where(eq(insights.acknowledged, false))
		.orderBy(desc(insights.createdAt))
		.limit(5);

	return {
		agents: allAgents,
		standup: latestStandup
			? { generated: true, ...latestStandup }
			: { generated: false },
		insights: activeInsights.filter(i => i.type !== 'standup')
	};
};
```

**Step 3: Update dashboard page**

Modify `roles/palais/files/app/src/routes/+page.svelte` to include the standup card at the top:
```svelte
<script lang="ts">
	import StandupCard from '$lib/components/dashboard/StandupCard.svelte';
	import InsightBanner from '$lib/components/dashboard/InsightBanner.svelte';
	let { data } = $props();
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
			PALAIS
		</h1>
		<span class="text-sm tabular-nums" style="color: var(--palais-text-muted);">
			{new Date().toLocaleDateString('fr-FR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
		</span>
	</div>

	<!-- Insight Banners -->
	{#each data.insights.filter(i => i.severity === 'critical') as insight}
		<InsightBanner {insight} />
	{/each}

	<!-- Digital Standup -->
	<StandupCard standup={data.standup} />

	<!-- Agent Grid -->
	<section>
		<h2 class="text-sm font-semibold uppercase tracking-wider mb-4" style="color: var(--palais-text-muted);">
			Agents
		</h2>
		<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
			{#each data.agents as agent}
				<div class="p-4 rounded-lg transition-all hover:scale-[1.02]"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border);"
					style:box-shadow={agent.status === 'busy' ? 'var(--palais-glow-md)' : 'none'}
					style:border-color={agent.status === 'busy' ? 'var(--palais-gold)' : 'var(--palais-border)'}
				>
					<div class="w-10 h-10 rounded-full flex items-center justify-center mb-3"
						style="background: linear-gradient(135deg, var(--palais-gold), var(--palais-amber)); color: var(--palais-bg);">
						<span class="text-sm font-bold">{agent.name.substring(0, 2).toUpperCase()}</span>
					</div>
					<h3 class="text-sm font-semibold" style="color: var(--palais-text);">{agent.name}</h3>
					<p class="text-xs mt-1 capitalize"
						style:color={
							agent.status === 'idle' ? 'var(--palais-green)' :
							agent.status === 'busy' ? 'var(--palais-gold)' :
							agent.status === 'error' ? 'var(--palais-red)' :
							'var(--palais-text-muted)'
						}
					>
						{agent.status}
					</p>
				</div>
			{/each}
		</div>
	</section>
</div>
```

**Step 4: Commit**

```bash
git add roles/palais/files/app/src/lib/components/dashboard/ roles/palais/files/app/src/routes/+page.*
git commit -m "feat(palais): display Digital Standup on dashboard at login"
```

---

## Task 4: Insight Detection Engine

**Files:**
- Create: `roles/palais/files/app/src/lib/server/insights/detector.ts`
- Create: `roles/palais/files/app/src/lib/server/insights/scheduler.ts`

**Step 1: Create insight detector**

Create `roles/palais/files/app/src/lib/server/insights/detector.ts`:
```typescript
import { db } from '$lib/server/db';
import {
	agents, tasks, insights, budgetSnapshots,
	activityLog, taskDependencies
} from '$lib/server/db/schema';
import { eq, and, gte, desc, sql, ne } from 'drizzle-orm';

interface DetectedInsight {
	type: 'agent_stuck' | 'budget_warning' | 'error_pattern' | 'dependency_blocked';
	severity: 'info' | 'warning' | 'critical';
	title: string;
	description: string;
	suggestedActions: Array<{ label: string; action_type: string; params: Record<string, unknown> }>;
	entityType?: string;
	entityId?: number;
}

/**
 * Check: Agent stuck on same task for > 2 hours
 */
async function detectAgentStuck(): Promise<DetectedInsight[]> {
	const results: DetectedInsight[] = [];
	const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000);

	const busyAgents = await db.select().from(agents)
		.where(eq(agents.status, 'busy'));

	for (const agent of busyAgents) {
		if (!agent.currentTaskId) continue;

		// Check if agent has been busy since before 2 hours ago
		if (agent.lastSeenAt && agent.lastSeenAt < twoHoursAgo) {
			const [task] = await db.select().from(tasks)
				.where(eq(tasks.id, agent.currentTaskId));

			results.push({
				type: 'agent_stuck',
				severity: 'warning',
				title: `${agent.name} bloque depuis 2h+`,
				description: `L'agent ${agent.name} travaille sur "${task?.title ?? 'tache inconnue'}" depuis plus de 2 heures. Intervention possible requise.`,
				suggestedActions: [
					{
						label: 'Redemarrer l\'agent',
						action_type: 'webhook',
						params: { url: `/api/v1/agents/${agent.id}/restart`, method: 'POST' }
					},
					{
						label: 'Reassigner la tache',
						action_type: 'navigate',
						params: { url: `/projects?taskId=${agent.currentTaskId}` }
					},
					{
						label: 'Passer en eco model',
						action_type: 'webhook',
						params: { url: '/api/v1/budget/eco-mode', method: 'POST' }
					}
				],
				entityType: 'agent',
				entityId: undefined // agent id is string, not number
			});
		}
	}

	return results;
}

/**
 * Check: Budget > 85% used today
 */
async function detectBudgetWarning(): Promise<DetectedInsight[]> {
	const results: DetectedInsight[] = [];
	const todayStart = new Date();
	todayStart.setHours(0, 0, 0, 0);

	const todaySnapshots = await db.select().from(budgetSnapshots)
		.where(gte(budgetSnapshots.capturedAt, todayStart));

	const totalSpent = todaySnapshots.reduce((sum, s) => sum + (s.spendAmount ?? 0), 0);
	const dailyBudget = 5.0;
	const percentUsed = (totalSpent / dailyBudget) * 100;

	if (percentUsed >= 85) {
		const severity = percentUsed >= 95 ? 'critical' : 'warning';

		// Count high-priority tasks in queue
		const pendingHighPri = await db.select({ id: tasks.id }).from(tasks)
			.where(and(
				eq(tasks.status, 'backlog'),
				sql`${tasks.priority} IN ('high', 'urgent')`
			));

		results.push({
			type: 'budget_warning',
			severity,
			title: `Budget a ${Math.round(percentUsed)}%`,
			description: `$${totalSpent.toFixed(2)} depenses sur $${dailyBudget.toFixed(2)}. ${pendingHighPri.length} tache(s) haute priorite en attente. Envisager le mode eco ou reporter les taches basse priorite.`,
			suggestedActions: [
				{
					label: 'Activer mode eco',
					action_type: 'webhook',
					params: { url: '/api/v1/budget/eco-mode', method: 'POST' }
				},
				{
					label: 'Voir le budget',
					action_type: 'navigate',
					params: { url: '/budget' }
				}
			]
		});
	}

	return results;
}

/**
 * Check: Repeated error types in activity_log (3+ same errors this week)
 */
async function detectErrorPattern(): Promise<DetectedInsight[]> {
	const results: DetectedInsight[] = [];
	const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);

	// Find error actions that repeat 3+ times
	const errorPatterns = await db.select({
		action: activityLog.action,
		count: sql<number>`COUNT(*)`.as('count')
	}).from(activityLog)
		.where(and(
			sql`${activityLog.action} LIKE '%error%' OR ${activityLog.action} LIKE '%failed%'`,
			gte(activityLog.createdAt, weekAgo)
		))
		.groupBy(activityLog.action)
		.having(sql`COUNT(*) >= 3`);

	for (const pattern of errorPatterns) {
		results.push({
			type: 'error_pattern',
			severity: 'warning',
			title: `Pattern d'erreur recurrent: ${pattern.action}`,
			description: `L'erreur "${pattern.action}" s'est produite ${pattern.count} fois cette semaine. Verifier la memoire pour une resolution connue.`,
			suggestedActions: [
				{
					label: 'Chercher dans la memoire',
					action_type: 'navigate',
					params: { url: `/memory?q=${encodeURIComponent(pattern.action)}` }
				}
			]
		});
	}

	return results;
}

/**
 * Check: Critical path tasks blocked by offline agents
 */
async function detectDependencyBlocked(): Promise<DetectedInsight[]> {
	const results: DetectedInsight[] = [];

	// Find tasks that are blocked (have unfinished dependencies)
	// and are assigned to offline/error agents
	const blockedTasks = await db.select({
		taskId: tasks.id,
		taskTitle: tasks.title,
		agentId: tasks.assigneeAgentId,
		agentName: agents.name,
		agentStatus: agents.status
	}).from(tasks)
		.innerJoin(agents, eq(tasks.assigneeAgentId, agents.id))
		.where(and(
			ne(tasks.status, 'done'),
			sql`${agents.status} IN ('offline', 'error')`
		));

	// Check if any of these have dependents waiting on them
	for (const blocked of blockedTasks) {
		const dependents = await db.select().from(taskDependencies)
			.where(eq(taskDependencies.dependsOnTaskId, blocked.taskId));

		if (dependents.length > 0) {
			results.push({
				type: 'dependency_blocked',
				severity: 'critical',
				title: `Tache critique bloquee — ${blocked.agentName} offline`,
				description: `"${blocked.taskTitle}" est assignee a ${blocked.agentName} (${blocked.agentStatus}) et bloque ${dependents.length} autre(s) tache(s).`,
				suggestedActions: [
					{
						label: 'Reassigner',
						action_type: 'navigate',
						params: { url: `/projects?taskId=${blocked.taskId}` }
					},
					{
						label: 'Voir les dependances',
						action_type: 'navigate',
						params: { url: `/projects?taskId=${blocked.taskId}&view=timeline` }
					}
				],
				entityType: 'task',
				entityId: blocked.taskId
			});
		}
	}

	return results;
}

/**
 * Run all detectors and return new insights.
 * Deduplicates: only creates insights if a similar one doesn't already exist (non-acknowledged, same type+title).
 */
export async function runAllDetectors(): Promise<DetectedInsight[]> {
	const allDetected: DetectedInsight[] = [];

	const [stuck, budget, errors, deps] = await Promise.all([
		detectAgentStuck(),
		detectBudgetWarning(),
		detectErrorPattern(),
		detectDependencyBlocked()
	]);

	allDetected.push(...stuck, ...budget, ...errors, ...deps);

	// Deduplicate against existing non-acknowledged insights
	const existing = await db.select({ title: insights.title, type: insights.type })
		.from(insights)
		.where(eq(insights.acknowledged, false));

	const existingSet = new Set(existing.map(i => `${i.type}:${i.title}`));
	const newInsights = allDetected.filter(i => !existingSet.has(`${i.type}:${i.title}`));

	// Store new insights
	for (const insight of newInsights) {
		await db.insert(insights).values({
			type: insight.type,
			severity: insight.severity,
			title: insight.title,
			description: insight.description,
			suggestedActions: insight.suggestedActions,
			entityType: insight.entityType ?? null,
			entityId: insight.entityId ?? null,
			acknowledged: false
		});
	}

	return newInsights;
}
```

**Step 2: Create insight scheduler**

Create `roles/palais/files/app/src/lib/server/insights/scheduler.ts`:
```typescript
import { runAllDetectors } from './detector';
import { env } from '$env/dynamic/private';

let schedulerStarted = false;

export function startInsightScheduler(): void {
	if (schedulerStarted) return;
	schedulerStarted = true;

	// Run detection every 10 minutes
	setInterval(async () => {
		try {
			const newInsights = await runAllDetectors();
			if (newInsights.length > 0) {
				console.log(`[Palais] Detected ${newInsights.length} new insight(s)`);

				// Push critical insights to n8n for Telegram
				for (const insight of newInsights) {
					if (insight.severity === 'critical') {
						await pushInsightToN8n(insight);
					}
				}
			}
		} catch (err) {
			console.error('[Palais] Insight detection failed:', err);
		}
	}, 10 * 60 * 1000);

	// Run once on startup (after 30s delay to let DB settle)
	setTimeout(() => {
		runAllDetectors().catch(console.error);
	}, 30000);

	console.log('[Palais] Insight scheduler started — checks every 10 minutes');
}

async function pushInsightToN8n(insight: { type: string; severity: string; title: string; description: string }): Promise<void> {
	const n8nBase = env.N8N_WEBHOOK_BASE || 'http://n8n:5678/webhook';

	try {
		await fetch(`${n8nBase}/palais-insight-alert`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				type: insight.type,
				severity: insight.severity,
				title: insight.title,
				description: insight.description,
				timestamp: new Date().toISOString()
			})
		});
	} catch {
		console.warn('[Palais] Failed to push insight to n8n webhook');
	}
}
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/lib/server/insights/
git commit -m "feat(palais): Insight Detection Engine — agent stuck, budget warning, error patterns, dependency blocks"
```

---

## Task 5: Insights API

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/insights/+server.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/insights/[id]/acknowledge/+server.ts`

**Step 1: GET all insights**

Create `roles/palais/files/app/src/routes/api/v1/insights/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq, desc, and, ne } from 'drizzle-orm';

export const GET: RequestHandler = async ({ url }) => {
	const severity = url.searchParams.get('severity');
	const acknowledged = url.searchParams.get('acknowledged');
	const excludeStandup = url.searchParams.get('excludeStandup') !== 'false';

	const conditions = [];

	if (severity) {
		conditions.push(eq(insights.severity, severity as any));
	}
	if (acknowledged === 'true') {
		conditions.push(eq(insights.acknowledged, true));
	} else if (acknowledged === 'false') {
		conditions.push(eq(insights.acknowledged, false));
	}
	if (excludeStandup) {
		conditions.push(ne(insights.type, 'standup'));
	}

	const query = db.select().from(insights);
	const result = conditions.length > 0
		? await query.where(and(...conditions)).orderBy(desc(insights.createdAt)).limit(100)
		: await query.orderBy(desc(insights.createdAt)).limit(100);

	return json(result);
};
```

**Step 2: PUT acknowledge insight**

Create `roles/palais/files/app/src/routes/api/v1/insights/[id]/acknowledge/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const PUT: RequestHandler = async ({ params }) => {
	const insightId = parseInt(params.id);

	const [updated] = await db.update(insights)
		.set({ acknowledged: true })
		.where(eq(insights.id, insightId))
		.returning();

	if (!updated) {
		return json({ error: 'Insight not found' }, { status: 404 });
	}

	return json(updated);
};
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/routes/api/v1/insights/
git commit -m "feat(palais): Insights API — GET /api/v1/insights + PUT acknowledge"
```

---

## Task 6: Insights UI — Banner + Dedicated Page

**Files:**
- Create: `roles/palais/files/app/src/lib/components/dashboard/InsightBanner.svelte`
- Create: `roles/palais/files/app/src/routes/insights/+page.svelte`
- Create: `roles/palais/files/app/src/routes/insights/+page.server.ts`

**Step 1: Create InsightBanner component**

Create `roles/palais/files/app/src/lib/components/dashboard/InsightBanner.svelte`:
```svelte
<script lang="ts">
	interface Insight {
		id: number;
		type: string;
		severity: string;
		title: string;
		description: string | null;
		suggestedActions: unknown;
		createdAt: string;
	}

	let { insight }: { insight: Insight } = $props();
	let dismissed = $state(false);

	const severityStyles: Record<string, { bg: string; border: string; text: string }> = {
		critical: {
			bg: 'rgba(229, 57, 53, 0.1)',
			border: 'var(--palais-red)',
			text: 'var(--palais-red)'
		},
		warning: {
			bg: 'rgba(232, 131, 58, 0.1)',
			border: 'var(--palais-amber)',
			text: 'var(--palais-amber)'
		},
		info: {
			bg: 'rgba(79, 195, 247, 0.1)',
			border: 'var(--palais-cyan)',
			text: 'var(--palais-cyan)'
		}
	};

	const style = $derived(severityStyles[insight.severity] ?? severityStyles.info);

	async function acknowledge() {
		await fetch(`/api/v1/insights/${insight.id}/acknowledge`, { method: 'PUT' });
		dismissed = true;
	}
</script>

{#if !dismissed}
	<div
		class="rounded-lg px-4 py-3 flex items-center justify-between gap-4"
		style:background={style.bg}
		style:border="1px solid {style.border}"
	>
		<div class="flex items-center gap-3 min-w-0">
			<span class="text-xs font-bold uppercase shrink-0 px-2 py-0.5 rounded"
				style:background={style.border}
				style="color: var(--palais-bg);"
			>
				{insight.severity}
			</span>
			<span class="text-sm truncate" style:color={style.text}>
				{insight.title}
			</span>
		</div>
		<div class="flex items-center gap-2 shrink-0">
			<a href="/insights" class="text-xs underline" style="color: var(--palais-text-muted);">
				Details
			</a>
			<button
				onclick={acknowledge}
				class="text-xs px-2 py-1 rounded transition-colors"
				style="color: var(--palais-text-muted); border: 1px solid var(--palais-border);"
			>
				OK
			</button>
		</div>
	</div>
{/if}
```

**Step 2: Create insights page server load**

Create `roles/palais/files/app/src/routes/insights/+page.server.ts`:
```typescript
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { desc, ne } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const showAcknowledged = url.searchParams.get('showAcknowledged') === 'true';

	const allInsights = await db.select().from(insights)
		.where(ne(insights.type, 'standup'))
		.orderBy(desc(insights.createdAt))
		.limit(200);

	return {
		insights: showAcknowledged
			? allInsights
			: allInsights.filter(i => !i.acknowledged),
		showAcknowledged
	};
};
```

**Step 3: Create insights page**

Create `roles/palais/files/app/src/routes/insights/+page.svelte`:
```svelte
<script lang="ts">
	let { data } = $props();

	const severityOrder: Record<string, number> = { critical: 0, warning: 1, info: 2 };
	let sorted = $derived(
		[...data.insights].sort((a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3))
	);

	const severityColors: Record<string, string> = {
		critical: 'var(--palais-red)',
		warning: 'var(--palais-amber)',
		info: 'var(--palais-cyan)'
	};

	const typeLabels: Record<string, string> = {
		agent_stuck: 'Agent bloque',
		budget_warning: 'Budget',
		error_pattern: 'Pattern erreur',
		dependency_blocked: 'Dependance bloquee'
	};

	async function acknowledge(id: number) {
		await fetch(`/api/v1/insights/${id}/acknowledge`, { method: 'PUT' });
		// Reload
		window.location.reload();
	}

	async function executeAction(action: { action_type: string; params: Record<string, unknown> }) {
		if (action.action_type === 'navigate') {
			window.location.href = action.params.url as string;
		} else if (action.action_type === 'webhook') {
			await fetch(action.params.url as string, {
				method: (action.params.method as string) || 'POST'
			});
		}
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
			INSIGHTS
		</h1>
		<div class="flex items-center gap-4">
			<span class="text-sm" style="color: var(--palais-text-muted);">
				{data.insights.filter(i => !i.acknowledged).length} actif(s)
			</span>
			<a
				href={data.showAcknowledged ? '/insights' : '/insights?showAcknowledged=true'}
				class="text-xs px-3 py-1.5 rounded"
				style="color: var(--palais-gold); border: 1px solid var(--palais-border);"
			>
				{data.showAcknowledged ? 'Masquer acquittes' : 'Afficher tous'}
			</a>
		</div>
	</div>

	{#if sorted.length === 0}
		<div class="text-center py-16" style="color: var(--palais-text-muted);">
			<p class="text-lg">Aucun insight actif</p>
			<p class="text-sm mt-2">Tout est nominal.</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each sorted as insight}
				<div
					class="rounded-lg p-5 transition-all"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border);"
					style:opacity={insight.acknowledged ? '0.5' : '1'}
				>
					<div class="flex items-start justify-between gap-4">
						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2 mb-2">
								<span class="text-xs font-bold uppercase px-2 py-0.5 rounded"
									style:background={severityColors[insight.severity] ?? 'var(--palais-cyan)'}
									style="color: var(--palais-bg);"
								>
									{insight.severity}
								</span>
								<span class="text-xs px-2 py-0.5 rounded"
									style="color: var(--palais-text-muted); border: 1px solid var(--palais-border);"
								>
									{typeLabels[insight.type] ?? insight.type}
								</span>
								<span class="text-xs tabular-nums" style="color: var(--palais-text-muted);">
									{new Date(insight.createdAt).toLocaleString('fr-FR')}
								</span>
							</div>
							<h3 class="text-sm font-semibold mb-1" style="color: var(--palais-text);">
								{insight.title}
							</h3>
							{#if insight.description}
								<p class="text-sm" style="color: var(--palais-text-muted);">
									{insight.description}
								</p>
							{/if}
						</div>
						{#if !insight.acknowledged}
							<button
								onclick={() => acknowledge(insight.id)}
								class="shrink-0 text-xs px-3 py-1.5 rounded transition-colors"
								style="color: var(--palais-text-muted); border: 1px solid var(--palais-border);"
							>
								Acquitter
							</button>
						{/if}
					</div>

					<!-- Suggested Actions -->
					{#if insight.suggestedActions && !insight.acknowledged}
						{@const actions = insight.suggestedActions as Array<{label: string; action_type: string; params: Record<string, unknown>}>}
						{#if actions.length > 0}
							<div class="flex flex-wrap gap-2 mt-3 pt-3" style="border-top: 1px solid var(--palais-border);">
								{#each actions as action}
									<button
										onclick={() => executeAction(action)}
										class="px-3 py-1.5 rounded text-xs font-medium transition-all hover:brightness-110"
										style="background: transparent; color: var(--palais-gold); border: 1px solid var(--palais-gold);"
									>
										{action.label}
									</button>
								{/each}
							</div>
						{/if}
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
```

**Step 4: Commit**

```bash
git add roles/palais/files/app/src/lib/components/dashboard/InsightBanner.svelte roles/palais/files/app/src/routes/insights/
git commit -m "feat(palais): Insights UI — banner on dashboard + dedicated /insights page with actions"
```

---

## Task 7: Suggested Actions on Insights

**Files:**
- Already handled in Task 4 (detector generates `suggestedActions` per insight)
- Already handled in Task 6 (UI renders action buttons)

The suggested actions system is fully integrated:

1. **Detection** (Task 4): Each detector generates insights with `suggestedActions[]` containing `{label, action_type, params}`.
2. **Storage**: Actions stored as JSONB in the `insights.suggested_actions` column.
3. **API** (Task 5): `GET /api/v1/insights` returns actions with each insight.
4. **UI** (Task 6): Action buttons rendered with `executeAction()` handler that supports `navigate` and `webhook` types.

No additional work needed. This task validates that the flow is end-to-end.

**Step 1: Verify action types are handled**

The `executeAction` function in `+page.svelte` handles:
- `navigate` — client-side navigation to URL
- `webhook` — POST/PUT to API endpoint

**Step 2: Commit (if any fixes needed)**

```bash
git add roles/palais/files/app/src/routes/insights/
git commit -m "fix(palais): ensure insight suggested actions render and execute correctly"
```

---

## Task 8: n8n Webhook Integration — Critical Insights to Telegram

**Files:**
- Already handled in `roles/palais/files/app/src/lib/server/insights/scheduler.ts` (Task 4, Step 2)
- Already handled in `roles/palais/files/app/src/lib/server/standup/scheduler.ts` (Task 1, Step 2)

The webhook integration pushes to two n8n endpoints:
- `POST {N8N_WEBHOOK_BASE}/palais-standup` — daily standup briefing
- `POST {N8N_WEBHOOK_BASE}/palais-insight-alert` — critical insight alerts

**Step 1: Initialize schedulers on app startup**

Create or modify `roles/palais/files/app/src/hooks.server.ts` to start the schedulers when the server starts. Add at the top of the file (after imports, before the `handle` export):

```typescript
import { startStandupScheduler } from '$lib/server/standup/scheduler';
import { startInsightScheduler } from '$lib/server/insights/scheduler';

// Start background schedulers (only once)
if (typeof globalThis.__palaisSchedulersStarted === 'undefined') {
	globalThis.__palaisSchedulersStarted = true;
	startStandupScheduler();
	startInsightScheduler();
}
```

Add to `roles/palais/files/app/src/app.d.ts`:
```typescript
declare global {
	var __palaisSchedulersStarted: boolean | undefined;
	namespace App {
		interface Locals {
			user: {
				authenticated: boolean;
				source: 'api' | 'cookie' | 'none';
			};
		}
	}
}
```

**Step 2: Document the expected n8n webhook payload**

The n8n `palais-standup` workflow expects:
```json
{
  "title": "Briefing du lundi 24 fevrier 2026",
  "content": "...(LLM-generated summary)...",
  "timestamp": "2026-02-24T08:00:00Z"
}
```

The n8n `palais-insight-alert` workflow expects:
```json
{
  "type": "agent_stuck",
  "severity": "critical",
  "title": "Imhotep bloque depuis 2h+",
  "description": "...",
  "timestamp": "2026-02-24T14:32:00Z"
}
```

Both workflows are created in Phase 12 (n8n integration).

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/hooks.server.ts roles/palais/files/app/src/app.d.ts
git commit -m "feat(palais): start standup + insight schedulers on app boot — n8n webhook push"
```

---

## Verification Checklist

After implementation, verify:

- [ ] `POST /api/v1/standup/generate` triggers standup generation
- [ ] `GET /api/v1/standup/latest` returns the generated standup with title, description, suggestedActions
- [ ] Dashboard `/` shows the StandupCard with the latest briefing at the top
- [ ] Dashboard `/` shows critical insight banners above the standup
- [ ] `GET /api/v1/insights` returns all non-standup insights
- [ ] `GET /api/v1/insights?severity=critical` filters correctly
- [ ] `GET /api/v1/insights?acknowledged=false` returns only active insights
- [ ] `PUT /api/v1/insights/:id/acknowledge` marks insight as acknowledged
- [ ] `/insights` page renders all active insights sorted by severity
- [ ] Insight action buttons work: `navigate` opens URL, `webhook` calls API
- [ ] Acknowledge button removes the insight from the active list
- [ ] Insight detector creates `agent_stuck` insight when agent busy > 2h
- [ ] Insight detector creates `budget_warning` when spend > 85%
- [ ] Insight detector creates `error_pattern` when 3+ same errors in a week
- [ ] Insight detector creates `dependency_blocked` when offline agent blocks tasks
- [ ] Duplicate insights are NOT created (deduplication by type+title)
- [ ] Critical insights are pushed to `n8n/webhook/palais-insight-alert`
- [ ] Standup is pushed to `n8n/webhook/palais-standup`
- [ ] Schedulers start on app boot (visible in server logs)
- [ ] MCP tool `palais.insights.active` returns active insights (Phase 10)
- [ ] MCP tool `palais.standup.latest` returns latest standup (Phase 10)
- [ ] `make lint` passes (Ansible + YAML)
