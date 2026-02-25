import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { budgetSnapshots } from '$lib/server/db/schema';
import { gte, desc } from 'drizzle-orm';
import { env } from '$env/dynamic/private';

const DAILY_LIMIT = parseFloat(env.BUDGET_DAILY_LIMIT ?? '5.0');

interface PendingTask {
	id: number | string;
	title: string;
	priority: 'urgent' | 'high' | 'medium' | 'low' | 'none';
	estimatedCost: number;
}

const PRIORITY_WEIGHTS: Record<string, number> = {
	urgent: 5,
	high: 4,
	medium: 3,
	low: 2,
	none: 1
};

/**
 * POST /api/v1/budget/schedule
 * Body: { tasks: PendingTask[] }
 * Returns tasks sorted by (priority_weight / estimated_cost) ratio,
 * split into "run_now" vs "defer" based on remaining budget.
 */
export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	const tasks: PendingTask[] = body.tasks ?? [];

	if (tasks.length === 0) {
		return json({ runNow: [], defer: [], remainingBudget: 0 });
	}

	// Get remaining budget for today
	const since = new Date();
	since.setHours(0, 0, 0, 0);

	const snapshots = await db.select()
		.from(budgetSnapshots)
		.where(gte(budgetSnapshots.date, since))
		.orderBy(desc(budgetSnapshots.capturedAt));

	const latestBySource = new Map<string, typeof snapshots[0]>();
	for (const s of snapshots) {
		if (!latestBySource.has(s.source)) latestBySource.set(s.source, s);
	}

	const totalSpent = Math.max(
		latestBySource.get('litellm')?.spendAmount ?? 0,
		[...latestBySource.values()]
			.filter((s) => s.source !== 'litellm')
			.reduce((sum, s) => sum + (s.spendAmount ?? 0), 0)
	);
	const remaining = Math.max(0, DAILY_LIMIT - totalSpent);

	// Score = priority_weight / max(estimatedCost, 0.001)
	const scored = tasks.map((t) => ({
		...t,
		score: (PRIORITY_WEIGHTS[t.priority] ?? 1) / Math.max(t.estimatedCost, 0.001)
	})).sort((a, b) => b.score - a.score);

	// Fill "run_now" until budget exhausted
	let budgetLeft = remaining;
	const runNow: typeof scored = [];
	const defer: typeof scored = [];

	for (const task of scored) {
		if (budgetLeft >= task.estimatedCost) {
			runNow.push(task);
			budgetLeft -= task.estimatedCost;
		} else {
			defer.push(task);
		}
	}

	return json({
		runNow: runNow.map(({ score: _, ...t }) => t),
		defer: defer.map(({ score: _, ...t }) => t),
		remainingBudget: remaining,
		spentToday: totalSpent
	});
};
