import type { McpToolDefinition } from '../types';
import { getCostSummary } from '$lib/server/costs/aggregator';

export const costsToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.costs.summary',
		description: 'Get the current month total cost and per-provider breakdown (in EUR). No parameters required.',
		inputSchema: {
			type: 'object',
			properties: {}
		}
	}
];

export async function handleCostsTool(
	method: string,
	_args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'summary': {
			return getCostSummary();
		}

		default:
			throw new Error(`Unknown costs method: ${method}`);
	}
}
