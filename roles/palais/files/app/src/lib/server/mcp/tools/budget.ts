import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { budgetSnapshots } from '$lib/server/db/schema';
import { gte } from 'drizzle-orm';

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
			const todayStart = new Date();
			todayStart.setHours(0, 0, 0, 0);

			const todaySnapshots = await db.select().from(budgetSnapshots)
				.where(gte(budgetSnapshots.capturedAt, todayStart));

			const totalSpent = todaySnapshots.reduce((sum, s) => sum + (s.spendAmount ?? 0), 0);
			const dailyBudget = 5.0; // $5/day from PRD

			return {
				dailyBudget,
				spent: Math.round(totalSpent * 100) / 100,
				remaining: Math.round((dailyBudget - totalSpent) * 100) / 100,
				percentUsed: Math.round((totalSpent / dailyBudget) * 100),
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
