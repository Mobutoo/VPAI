import type { McpToolDefinition } from '../types';
import { taskToolDefs } from './tasks';
import { projectToolDefs } from './projects';
import { agentToolDefs } from './agents';
import { budgetToolDefs } from './budget';
import { deliverableToolDefs } from './deliverables';
import { memoryToolDefs } from './memory';
import { insightToolDefs } from './insights';
import { standupToolDefs } from './standup';

export function getToolDefinitions(): McpToolDefinition[] {
	return [
		...taskToolDefs,
		...projectToolDefs,
		...agentToolDefs,
		...budgetToolDefs,
		...deliverableToolDefs,
		...memoryToolDefs,
		...insightToolDefs,
		...standupToolDefs,
	];
}
