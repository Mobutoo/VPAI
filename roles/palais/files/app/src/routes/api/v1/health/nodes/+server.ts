import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { nodes, healthChecks, backupStatus } from '$lib/server/db/schema';
import { desc, eq } from 'drizzle-orm';

export const GET: RequestHandler = async () => {
	const allNodes = await db.select().from(nodes).orderBy(nodes.name);

	// Get latest health checks per node (last 24h)
	const recentChecks = await db
		.select()
		.from(healthChecks)
		.orderBy(desc(healthChecks.checkedAt))
		.limit(500);

	// Group by nodeId + serviceName, keeping only the latest per service
	const latestByNodeService = new Map<string, typeof recentChecks[0]>();
	for (const check of recentChecks) {
		const key = `${check.nodeId}:${check.serviceName}`;
		if (!latestByNodeService.has(key)) {
			latestByNodeService.set(key, check);
		}
	}

	// Get backup status per node
	const backups = await db.select().from(backupStatus).orderBy(desc(backupStatus.id));
	const latestBackupByNode = new Map<number, typeof backups[0]>();
	for (const b of backups) {
		if (!latestBackupByNode.has(b.nodeId)) {
			latestBackupByNode.set(b.nodeId, b);
		}
	}

	const result = allNodes.map((node) => ({
		...node,
		services: Array.from(latestByNodeService.values()).filter((c) => c.nodeId === node.id),
		backup: latestBackupByNode.get(node.id) ?? null
	}));

	return json(result);
};
