import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';

export const standupToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.standup.latest',
		description: 'Get the latest digital standup briefing',
		inputSchema: { type: 'object', properties: {} }
	}
];

export async function handleStandupTool(
	method: string,
	_args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'latest': {
			// Standups are stored as insights with type 'standup'
			const [latest] = await db.select().from(insights)
				.where(eq(insights.type, 'standup'))
				.orderBy(desc(insights.createdAt))
				.limit(1);

			if (!latest) {
				return { message: 'No standup available yet', generated: false };
			}

			return {
				generated: true,
				title: latest.title,
				description: latest.description,
				suggestedActions: latest.suggestedActions,
				createdAt: latest.createdAt
			};
		}

		default:
			throw new Error(`Unknown standup method: ${method}`);
	}
}
