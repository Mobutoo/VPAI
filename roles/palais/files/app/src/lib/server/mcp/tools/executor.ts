import { handleAgentsTool } from './agents';
import { handleMemoryTool } from './memory';
import { handleFleetTool } from './fleet';
import { handleWorkspacesTool } from './workspaces';
import { handleServicesTool } from './services';
import { handleCostsTool } from './costs';
import { handleDomainsTool } from './domains';

export async function executeToolCall(
	toolName: string,
	args: Record<string, unknown>
): Promise<unknown> {
	// Route by prefix: palais.memory.set -> memory handler with method "set"
	const parts = toolName.split('.');
	if (parts.length < 3 || parts[0] !== 'palais') {
		throw new Error(`Unknown tool: ${toolName}`);
	}

	const domain = parts[1]; // memory, agents, fleet, workspaces, services, costs, domains
	const method = parts.slice(2).join('.'); // get, set, list, etc.

	switch (domain) {
		case 'memory':
			return handleMemoryTool(method, args);
		case 'agents':
			return handleAgentsTool(method, args);
		case 'fleet':
			return handleFleetTool(method, args);
		case 'workspaces':
			return handleWorkspacesTool(method, args);
		case 'services':
			return handleServicesTool(method, args);
		case 'costs':
			return handleCostsTool(method, args);
		case 'domains':
			return handleDomainsTool(method, args);
		default:
			throw new Error(`Unknown tool domain: ${domain}`);
	}
}
