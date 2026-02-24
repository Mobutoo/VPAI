import { handleTasksTool } from './tasks';
import { handleProjectsTool } from './projects';
import { handleAgentsTool } from './agents';
import { handleBudgetTool } from './budget';
import { handleDeliverablesTool } from './deliverables';
import { handleMemoryTool } from './memory';
import { handleInsightsTool } from './insights';
import { handleStandupTool } from './standup';

export async function executeToolCall(
	toolName: string,
	args: Record<string, unknown>
): Promise<unknown> {
	// Route by prefix: palais.tasks.list -> tasks handler with method "list"
	const parts = toolName.split('.');
	if (parts.length < 3 || parts[0] !== 'palais') {
		throw new Error(`Unknown tool: ${toolName}`);
	}

	const domain = parts[1]; // tasks, projects, agents, etc.
	const method = parts.slice(2).join('.'); // list, create, etc.

	switch (domain) {
		case 'tasks':
			return handleTasksTool(method, args);
		case 'projects':
			return handleProjectsTool(method, args);
		case 'agents':
			return handleAgentsTool(method, args);
		case 'budget':
			return handleBudgetTool(method, args);
		case 'deliverables':
			return handleDeliverablesTool(method, args);
		case 'memory':
			return handleMemoryTool(method, args);
		case 'insights':
			return handleInsightsTool(method, args);
		case 'standup':
			return handleStandupTool(method, args);
		default:
			throw new Error(`Unknown tool domain: ${domain}`);
	}
}
