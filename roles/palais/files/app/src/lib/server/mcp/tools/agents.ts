import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { agents } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const agentToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.agents.status',
		description: 'Get status of all agents (id, name, status, current task, last seen)',
		inputSchema: { type: 'object', properties: {} }
	},
	{
		name: 'palais.agents.available',
		description: 'List agents currently available (idle status)',
		inputSchema: { type: 'object', properties: {} }
	}
];

export async function handleAgentsTool(
	method: string,
	_args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'status':
			return db.select().from(agents).orderBy(agents.name);

		case 'available':
			return db.select().from(agents)
				.where(eq(agents.status, 'idle'))
				.orderBy(agents.name);

		default:
			throw new Error(`Unknown agents method: ${method}`);
	}
}
