import { db } from '$lib/server/db';
import { agents, servers, serverMetrics, deployments, projectRegistry, wazaServices } from '$lib/server/db/schema';
import { desc, eq } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const [allAgents, allServers, recentDeploys, allWaza] = await Promise.all([
		db.select().from(agents).orderBy(agents.name),
		db.select().from(servers).orderBy(servers.name),
		db.select({
			id: deployments.id,
			version: deployments.version,
			status: deployments.status,
			startedAt: deployments.startedAt,
			workspaceName: projectRegistry.name,
			workspaceSlug: projectRegistry.slug,
		})
			.from(deployments)
			.leftJoin(projectRegistry, eq(deployments.workspaceId, projectRegistry.id))
			.orderBy(desc(deployments.startedAt))
			.limit(5),
		db.select().from(wazaServices).orderBy(wazaServices.name),
	]);

	// Get latest metric per server
	const serversWithMetrics = await Promise.all(
		allServers.map(async (s) => {
			const [metric] = await db.select().from(serverMetrics)
				.where(eq(serverMetrics.serverId, s.id))
				.orderBy(desc(serverMetrics.recordedAt))
				.limit(1);
			return { ...s, latestMetric: metric ?? null };
		})
	);

	const onlineCount = allServers.filter(s => s.status === 'online').length;
	const containerCount = serversWithMetrics.reduce((sum, s) => sum + (s.latestMetric?.containerCount ?? 0), 0);
	const activeDeploys = recentDeploys.filter(d => d.status === 'running').length;

	return {
		agents: allAgents,
		servers: serversWithMetrics,
		serverCount: allServers.length,
		onlineCount,
		containerCount,
		activeDeploys,
		recentDeploys,
		wazaServices: allWaza,
	};
};
