import { db } from '$lib/server/db';
import {
	agents, tasks, insights, budgetSnapshots,
	activityLog, taskDependencies
} from '$lib/server/db/schema';
import { eq, and, gte, desc, sql, ne } from 'drizzle-orm';
import { env } from '$env/dynamic/private';

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
 * Check: Agent stuck on same task for > 2 hours (busy + lastSeenAt old)
 */
async function detectAgentStuck(): Promise<DetectedInsight[]> {
	const results: DetectedInsight[] = [];
	const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000);

	const busyAgents = await db.select().from(agents)
		.where(eq(agents.status, 'busy'));

	for (const agent of busyAgents) {
		if (!agent.currentTaskId) continue;

		// Agent stuck if last heartbeat was > 2h ago
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
						label: 'Reassigner la tache',
						action_type: 'navigate',
						params: { url: `/projects?taskId=${agent.currentTaskId}` }
					},
					{
						label: 'Passer en eco model',
						action_type: 'webhook',
						params: { url: '/api/v1/budget/eco-mode', method: 'POST' }
					}
				]
			});
		}
	}

	return results;
}

/**
 * Check: Budget > 85% used today — uses correct cumulative snapshot logic
 */
async function detectBudgetWarning(): Promise<DetectedInsight[]> {
	const results: DetectedInsight[] = [];
	const todayStart = new Date();
	todayStart.setHours(0, 0, 0, 0);

	const dailyBudget = parseFloat(env.BUDGET_DAILY_LIMIT ?? '5.0');

	// Latest snapshot per source (snapshots are cumulative, not incremental)
	const todaySnapshots = await db.select().from(budgetSnapshots)
		.where(gte(budgetSnapshots.date, todayStart))
		.orderBy(desc(budgetSnapshots.capturedAt));

	const latestBySource = new Map<string, typeof todaySnapshots[0]>();
	for (const s of todaySnapshots) {
		if (!latestBySource.has(s.source)) latestBySource.set(s.source, s);
	}

	// OpenRouter delta: latest today - last snapshot before today
	const openrouterLatest = latestBySource.get('openrouter_direct');
	const [openrouterBaseline] = await db.select().from(budgetSnapshots)
		.where(eq(budgetSnapshots.source, 'openrouter_direct'))
		.orderBy(desc(budgetSnapshots.capturedAt))
		.limit(100)
		.then((rows) => rows.filter((r) => new Date(r.capturedAt) < todayStart).slice(0, 1));

	const openrouterDelta = openrouterLatest
		? Math.max(0, (openrouterLatest.spendAmount ?? 0) - (openrouterBaseline?.spendAmount ?? (openrouterLatest.spendAmount ?? 0)))
		: 0;

	const viaLitellm = latestBySource.get('litellm')?.spendAmount ?? 0;
	const viaDirect = openrouterDelta
		+ (latestBySource.get('openai_direct')?.spendAmount ?? 0)
		+ (latestBySource.get('anthropic_direct')?.spendAmount ?? 0);
	const totalSpent = Math.max(viaLitellm, viaDirect);
	const percentUsed = (totalSpent / dailyBudget) * 100;

	if (percentUsed >= 85) {
		const severity = percentUsed >= 95 ? 'critical' : 'warning';

		const pendingHighPri = await db.select({ id: tasks.id }).from(tasks)
			.where(and(
				eq(tasks.status, 'backlog'),
				sql`${tasks.priority} IN ('high', 'urgent')`
			));

		results.push({
			type: 'budget_warning',
			severity,
			title: `Budget a ${Math.round(percentUsed)}%`,
			description: `$${totalSpent.toFixed(2)} depenses sur $${dailyBudget.toFixed(2)}. ${pendingHighPri.length} tache(s) haute priorite en attente. Envisager le mode eco.`,
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

	const errorPatterns = await db.select({
		action: activityLog.action,
		count: sql<number>`COUNT(*)`.as('count')
	}).from(activityLog)
		.where(and(
			sql`(${activityLog.action} LIKE '%error%' OR ${activityLog.action} LIKE '%failed%')`,
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
 * Check: Tasks assigned to offline/error agents that have dependents waiting
 */
async function detectDependencyBlocked(): Promise<DetectedInsight[]> {
	const results: DetectedInsight[] = [];

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
 * Run all detectors and store new insights (deduplication by type+title).
 */
export async function runAllDetectors(): Promise<DetectedInsight[]> {
	const [stuck, budget, errors, deps] = await Promise.all([
		detectAgentStuck(),
		detectBudgetWarning(),
		detectErrorPattern(),
		detectDependencyBlocked()
	]);

	const allDetected: DetectedInsight[] = [...stuck, ...budget, ...errors, ...deps];

	// Deduplicate: skip insights already stored and non-acknowledged
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
