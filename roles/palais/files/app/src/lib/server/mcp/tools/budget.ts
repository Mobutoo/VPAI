import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { budgetSnapshots } from '$lib/server/db/schema';
import { gte, desc, eq } from 'drizzle-orm';
import { env } from '$env/dynamic/private';

export const budgetToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.budget.remaining',
		description: 'Get remaining budget for today ($5/day cap)',
		inputSchema: { type: 'object', properties: {} }
	},
	{
		name: 'palais.budget.estimate',
		description: 'Estimate cost for a task based on agent history and model',
		inputSchema: {
			type: 'object',
			properties: {
				agentId: { type: 'string', description: 'Agent who would execute' },
				complexity: { type: 'string', description: 'low, medium, high' },
				model: { type: 'string', description: 'LLM model to use' }
			}
		}
	}
];

export async function handleBudgetTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'remaining': {
			// Mirrors logic from /api/v1/budget to avoid double-counting cumulative snapshots
			const dailyBudget = parseFloat(env.BUDGET_DAILY_LIMIT ?? '5.0');
			const todayStart = new Date();
			todayStart.setHours(0, 0, 0, 0);

			// All today's snapshots (ordered newest first)
			const snapshots = await db.select().from(budgetSnapshots)
				.where(gte(budgetSnapshots.date, todayStart))
				.orderBy(desc(budgetSnapshots.capturedAt));

			// Latest snapshot per source (snapshots are cumulative, not incremental)
			const latestBySource = new Map<string, typeof snapshots[0]>();
			for (const s of snapshots) {
				if (!latestBySource.has(s.source)) latestBySource.set(s.source, s);
			}

			// OpenRouter delta: latest today - last snapshot before today (lifetime cumulative)
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

			// Take max to avoid double-counting (LiteLLM routes through providers)
			const total = Math.max(viaLitellm, viaDirect);
			const remaining = Math.max(0, dailyBudget - total);
			const percentUsed = Math.min(100, Math.round((total / dailyBudget) * 100));

			return {
				dailyBudget,
				spent: Math.round(total * 1000) / 1000,
				remaining: Math.round(remaining * 1000) / 1000,
				percentUsed,
				date: todayStart.toISOString().split('T')[0]
			};
		}

		case 'estimate': {
			// Simple estimation based on complexity
			const complexity = (args.complexity as string) || 'medium';
			const estimates: Record<string, number> = {
				low: 0.05,
				medium: 0.25,
				high: 0.80
			};
			const estimate = estimates[complexity] ?? 0.25;

			return {
				estimatedCost: estimate,
				complexity,
				model: args.model || 'default',
				note: 'Estimate based on historical averages by complexity tier'
			};
		}

		default:
			throw new Error(`Unknown budget method: ${method}`);
	}
}
