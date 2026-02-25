import { db } from '$lib/server/db';
import { nodes, healthChecks, backupStatus } from '$lib/server/db/schema';
import { fetchVPNTopology } from '$lib/server/health/headscale';
import { desc, eq } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	// 1. Fetch VPN topology from Headscale
	const { nodes: vpnNodes, error: headscaleError } = await fetchVPNTopology();
	const headscaleOk = !headscaleError;

	// 2. Sync statuses to DB
	const allCurrentNodes = await db.select().from(nodes);

	for (const node of allCurrentNodes) {
		if (headscaleError) {
			// Headscale unreachable → mark degraded (only if not busy)
			if (node.status !== 'busy') {
				await db.update(nodes).set({ status: 'degraded' }).where(eq(nodes.id, node.id));
			}
		} else if (node.tailscaleIp) {
			// Match by Tailscale IP
			const vpnMatch = vpnNodes.find((v) => v.ip === node.tailscaleIp);
			if (vpnMatch) {
				if (vpnMatch.online && node.status !== 'busy') {
					await db.update(nodes).set({
						status: 'online',
						lastSeenAt: vpnMatch.lastSeen ? new Date(vpnMatch.lastSeen) : new Date()
					}).where(eq(nodes.id, node.id));
				} else if (!vpnMatch.online && node.status !== 'busy') {
					await db.update(nodes).set({ status: 'offline' }).where(eq(nodes.id, node.id));
				}
			} else if (node.status !== 'busy') {
				// Node has Tailscale IP but not found in Headscale
				await db.update(nodes).set({ status: 'offline' }).where(eq(nodes.id, node.id));
			}
		}
	}

	// 3. Re-fetch nodes after sync
	const allNodes = await db.select().from(nodes).orderBy(nodes.name);

	// 4. Health checks (latest per node+service)
	const recentChecks = await db
		.select()
		.from(healthChecks)
		.orderBy(desc(healthChecks.checkedAt))
		.limit(500);

	const latestByNodeService = new Map<string, typeof recentChecks[0]>();
	for (const check of recentChecks) {
		const key = `${check.nodeId}:${check.serviceName}`;
		if (!latestByNodeService.has(key)) {
			latestByNodeService.set(key, check);
		}
	}

	// 5. Backup status
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

	return { nodes: nodesWithHealth, vpnTopology: vpnNodes, headscaleOk };
};
