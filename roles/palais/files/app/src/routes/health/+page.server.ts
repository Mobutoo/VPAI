import { db } from '$lib/server/db';
import { nodes, healthChecks, backupStatus } from '$lib/server/db/schema';
import { fetchVPNTopology } from '$lib/server/health/headscale';
import { desc } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allNodes = await db.select().from(nodes).orderBy(nodes.name);

	const recentChecks = await db
		.select()
		.from(healthChecks)
		.orderBy(desc(healthChecks.checkedAt))
		.limit(500);

	// Latest check per node+service
	const latestByNodeService = new Map<string, typeof recentChecks[0]>();
	for (const check of recentChecks) {
		const key = `${check.nodeId}:${check.serviceName}`;
		if (!latestByNodeService.has(key)) {
			latestByNodeService.set(key, check);
		}
	}

	const backups = await db.select().from(backupStatus).orderBy(desc(backupStatus.id));
	const latestBackupByNode = new Map<number, typeof backups[0]>();
	for (const b of backups) {
		if (!latestBackupByNode.has(b.nodeId)) {
			latestBackupByNode.set(b.nodeId, b);
		}
	}

	const nodesWithHealth = allNodes.map((node) => ({
		...node,
		services: Array.from(latestByNodeService.values()).filter((c) => c.nodeId === node.id),
		backup: latestBackupByNode.get(node.id) ?? null
	}));

	// VPN topology (non-blocking — empty array on failure)
	const vpnTopology = await fetchVPNTopology();

	return { nodes: nodesWithHealth, vpnTopology };
};
