import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';

export const insightToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.insights.active',
		description: 'Get all active (non-acknowledged) insights',
		inputSchema: { type: 'object', properties: {} }
	}
];

export async function handleInsightsTool(
	method: string,
	_args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'active':
			return db.select().from(insights)
				.where(eq(insights.acknowledged, false))
				.orderBy(desc(insights.createdAt));

		default:
			throw new Error(`Unknown insights method: ${method}`);
	}
}
