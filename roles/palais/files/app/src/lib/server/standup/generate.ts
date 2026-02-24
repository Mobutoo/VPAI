import { db } from '$lib/server/db';
import {
	tasks, agents, insights, budgetSnapshots
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

	// Budget spent today — use latest-per-source logic to avoid double-counting cumulative snapshots
	const todaySnapshots = await db.select().from(budgetSnapshots)
		.where(gte(budgetSnapshots.date, todayStart))
		.orderBy(desc(budgetSnapshots.capturedAt));

	const latestBySource = new Map<string, typeof todaySnapshots[0]>();
	for (const s of todaySnapshots) {
		if (!latestBySource.has(s.source)) latestBySource.set(s.source, s);
	}

	const viaLitellm = latestBySource.get('litellm')?.spendAmount ?? 0;
	const openrouterLatest = latestBySource.get('openrouter_direct');
	const [openrouterBaseline] = await db.select().from(budgetSnapshots)
		.where(eq(budgetSnapshots.source, 'openrouter_direct'))
		.orderBy(desc(budgetSnapshots.capturedAt))
		.limit(100)
		.then((rows) => rows.filter((r) => new Date(r.capturedAt) < todayStart).slice(0, 1));
	const openrouterDelta = openrouterLatest
		? Math.max(0, (openrouterLatest.spendAmount ?? 0) - (openrouterBaseline?.spendAmount ?? (openrouterLatest.spendAmount ?? 0)))
		: 0;
	const viaDirect = openrouterDelta
		+ (latestBySource.get('openai_direct')?.spendAmount ?? 0)
		+ (latestBySource.get('anthropic_direct')?.spendAmount ?? 0);
	const budgetSpent = Math.max(viaLitellm, viaDirect);
	const dailyBudget = parseFloat(env.BUDGET_DAILY_LIMIT ?? '5.0');

	// Active insights (non-acknowledged, non-standup)
	const activeInsights = await db.select({
		type: insights.type,
		title: insights.title,
		severity: insights.severity
	}).from(insights)
		.where(and(
			eq(insights.acknowledged, false),
			sql`${insights.type} != 'standup'`
		))
		.orderBy(desc(insights.createdAt))
		.limit(10);

	// Agent statuses
	const allAgents = await db.select().from(agents).orderBy(agents.name);
	const agentStatuses = allAgents.map(a => ({
		name: a.name,
		status: a.status,
		currentTask: null as string | null
	}));

	// In-progress count
	const inProgressTasks = await db.select({ id: tasks.id }).from(tasks)
		.where(eq(tasks.status, 'in-progress'));

	return {
		completedYesterday: completedYesterday.map(t => ({
			title: t.title,
			agent: t.agent ?? 'unassigned',
			cost: t.cost
		})),
		failedTasks: failedTasks.map(t => ({
			title: t.title,
			agent: t.agent ?? 'unassigned',
			reason: null
		})),
		budgetSpent: Math.round(budgetSpent * 1000) / 1000,
		budgetRemaining: Math.round((dailyBudget - budgetSpent) * 1000) / 1000,
		activeInsights,
		agentStatuses,
		inProgressCount: inProgressTasks.length,
		blockedCount: 0
	};
}

export async function generateStandupBriefing(): Promise<{ title: string; description: string; suggestedActions: unknown[] }> {
	const data = await gatherStandupData();

	const prompt = buildStandupPrompt(data);

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
				model: 'gpt-4o-mini',
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
	const suggestedActions: unknown[] = [];
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
	const lines: string[] = [];

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
	const lines: string[] = [];
	lines.push(`Hier: ${data.completedYesterday.length} taches completees, ${data.failedTasks.length} echouees.`);
	lines.push(`Budget: $${data.budgetSpent} depenses, $${data.budgetRemaining} restant.`);
	lines.push(`En cours: ${data.inProgressCount} taches. Bloquees: ${data.blockedCount}.`);
	if (data.activeInsights.length > 0) {
		lines.push(`Attention: ${data.activeInsights.length} insight(s) actif(s).`);
	}
	return lines.join(' ');
}
