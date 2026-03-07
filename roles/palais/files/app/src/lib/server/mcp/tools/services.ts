import type { McpToolDefinition } from '../types';
import * as dockerRemote from '$lib/server/providers/docker-remote';

export const servicesToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.services.list',
		description: 'List all containers on a given server (id, name, image, status, state, ports, created). Required: server slug.',
		inputSchema: {
			type: 'object',
			properties: {
				server: { type: 'string', description: 'Server slug identifier (e.g. sese-ai, seko-vpn)' }
			},
			required: ['server']
		}
	},
	{
		name: 'palais.services.control',
		description: 'Start, stop, or restart a container on a given server. Required: server slug, container name, and action.',
		inputSchema: {
			type: 'object',
			properties: {
				server: { type: 'string', description: 'Server slug identifier (e.g. sese-ai, seko-vpn)' },
				container: { type: 'string', description: 'Container name to control' },
				action: {
					type: 'string',
					enum: ['start', 'stop', 'restart'],
					description: 'Action to perform on the container'
				}
			},
			required: ['server', 'container', 'action']
		}
	}
];

export async function handleServicesTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'list': {
			const server = args.server as string;
			if (!server) throw new Error('Missing required parameter: server');

			return dockerRemote.listContainers(server);
		}

		case 'control': {
			const server = args.server as string;
			const container = args.container as string;
			const action = args.action as string;

			if (!server) throw new Error('Missing required parameter: server');
			if (!container) throw new Error('Missing required parameter: container');
			if (!action) throw new Error('Missing required parameter: action');

			if (!['start', 'stop', 'restart'].includes(action)) {
				throw new Error(`Invalid action: ${action}. Allowed values: start, stop, restart`);
			}

			return dockerRemote.controlContainer(
				server,
				container,
				action as 'start' | 'stop' | 'restart'
			);
		}

		default:
			throw new Error(`Unknown services method: ${method}`);
	}
}
