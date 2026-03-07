import type { McpToolDefinition } from '../types';
import { agentToolDefs } from './agents';
import { memoryToolDefs } from './memory';
import { fleetToolDefs } from './fleet';
import { workspacesToolDefs } from './workspaces';
import { servicesToolDefs } from './services';
import { costsToolDefs } from './costs';
import { domainsToolDefs } from './domains';

export function getToolDefinitions(): McpToolDefinition[] {
	return [
		...memoryToolDefs,
		...agentToolDefs,
		...fleetToolDefs,
		...workspacesToolDefs,
		...servicesToolDefs,
		...costsToolDefs,
		...domainsToolDefs,
	];
}
