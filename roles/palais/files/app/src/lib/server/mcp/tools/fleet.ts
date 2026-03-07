import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { servers, serverMetrics } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';
import * as dockerRemote from '$lib/server/providers/docker-remote';

export const fleetToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.fleet.servers',
		description: 'List all servers with their current status and resource summary (CPU, RAM). No parameters required.',
		inputSchema: {
			type: 'object',
			properties: {}
		}
	},
	{
		name: 'palais.fleet.server_status',
		description: 'Get detailed information about a specific server by slug, including latest metrics and running containers.',
		inputSchema: {
			type: 'object',
			properties: {
				slug: { type: 'string', description: 'Server slug identifier (e.g. sese-ai, seko-vpn)' }
			},
			required: ['slug']
		}
	}
];

export async function handleFleetTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'servers': {
			const allServers = await db.select().from(servers).orderBy(servers.name);

			const result = await Promise.all(
				allServers.map(async (server) => {
					const [latestMetric] = await db
						.select()
						.from(serverMetrics)
						.where(eq(serverMetrics.serverId, server.id))
						.orderBy(desc(serverMetrics.recordedAt))
						.limit(1);

					const ramPercent =
						latestMetric &&
						latestMetric.ramTotalMb &&
						latestMetric.ramTotalMb > 0 &&
						latestMetric.ramUsedMb != null
							? (latestMetric.ramUsedMb / latestMetric.ramTotalMb) * 100
							: null;

					return {
						name: server.name,
						slug: server.slug,
						provider: server.provider,
						status: server.status,
						tailscaleIp: server.tailscaleIp ?? null,
						cpuPercent: latestMetric?.cpuPercent ?? null,
						ramPercent: ramPercent !== null ? Math.round(ramPercent * 10) / 10 : null
					};
				})
			);

			return result;
		}

		case 'server_status': {
			const slug = args.slug as string;
			if (!slug) throw new Error('Missing required parameter: slug');

			const [server] = await db
				.select()
				.from(servers)
				.where(eq(servers.slug, slug))
				.limit(1);

			if (!server) throw new Error(`Server not found: ${slug}`);

			const [latestMetric] = await db
				.select()
				.from(serverMetrics)
				.where(eq(serverMetrics.serverId, server.id))
				.orderBy(desc(serverMetrics.recordedAt))
				.limit(1);

			let containers: unknown[] = [];
			try {
				containers = await dockerRemote.listContainers(server.slug);
			} catch {
				// Docker remote access may not be configured for all servers; return empty list
				containers = [];
			}

			return {
				server,
				latestMetric: latestMetric ?? null,
				containers
			};
		}

		default:
			throw new Error(`Unknown fleet method: ${method}`);
	}
}
