import { db } from '$lib/server/db';
import { projectRegistry, deployments, servers } from '$lib/server/db/schema';
import { eq, desc, inArray } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	// Load all workspaces
	const workspaces = await db
		.select({
			id: projectRegistry.id,
			name: projectRegistry.name,
			slug: projectRegistry.slug,
			description: projectRegistry.description,
			repoUrl: projectRegistry.repoUrl,
			stack: projectRegistry.stack,
			domainPattern: projectRegistry.domainPattern,
			currentVersion: projectRegistry.currentVersion,
			latestVersion: projectRegistry.latestVersion,
			lastDeployedAt: projectRegistry.lastDeployedAt,
			primaryServerId: projectRegistry.primaryServerId,
			onDemand: projectRegistry.onDemand,
			playbookPath: projectRegistry.playbookPath,
			createdAt: projectRegistry.createdAt,
		})
		.from(projectRegistry)
		.orderBy(projectRegistry.name);

	// Fetch all relevant server names in one query
	const serverIds = workspaces
		.map((w) => w.primaryServerId)
		.filter((id): id is number => id !== null);

	const serverMap = new Map<number, { name: string; slug: string }>();

	if (serverIds.length > 0) {
		const serverRows = serverIds.length === 1
			? await db
					.select({ id: servers.id, name: servers.name, slug: servers.slug })
					.from(servers)
					.where(eq(servers.id, serverIds[0]))
			: await db
					.select({ id: servers.id, name: servers.name, slug: servers.slug })
					.from(servers)
					.where(inArray(servers.id, serverIds));

		for (const s of serverRows) {
			serverMap.set(s.id, { name: s.name, slug: s.slug });
		}
	}

	// Fetch latest deployment per workspace
	const workspaceIds = workspaces.map((w) => w.id);
	const latestDeployMap = new Map<
		number,
		{ status: string; version: string | null; startedAt: Date }
	>();

	if (workspaceIds.length > 0) {
		const recentDeploys = await db
			.select({
				workspaceId: deployments.workspaceId,
				status: deployments.status,
				version: deployments.version,
				startedAt: deployments.startedAt,
			})
			.from(deployments)
			.orderBy(desc(deployments.startedAt))
			.limit(workspaceIds.length * 5);

		for (const d of recentDeploys) {
			if (!latestDeployMap.has(d.workspaceId)) {
				latestDeployMap.set(d.workspaceId, {
					status: d.status,
					version: d.version,
					startedAt: d.startedAt,
				});
			}
		}
	}

	const result = workspaces.map((w) => ({
		...w,
		server: w.primaryServerId ? (serverMap.get(w.primaryServerId) ?? null) : null,
		latestDeploy: latestDeployMap.get(w.id) ?? null,
	}));

	return { workspaces: result };
};
