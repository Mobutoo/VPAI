import { db } from '$lib/server/db';
import { deployments, projectRegistry } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const rows = await db
		.select({
			id: deployments.id,
			workspaceId: deployments.workspaceId,
			serverId: deployments.serverId,
			version: deployments.version,
			status: deployments.status,
			startedAt: deployments.startedAt,
			completedAt: deployments.completedAt,
			triggeredBy: deployments.triggeredBy,
			deployType: deployments.deployType,
			rollbackOf: deployments.rollbackOf,
			n8nExecutionId: deployments.n8nExecutionId,
			errorSummary: deployments.errorSummary,
			workspaceName: projectRegistry.name,
			workspaceSlug: projectRegistry.slug,
		})
		.from(deployments)
		.leftJoin(projectRegistry, eq(deployments.workspaceId, projectRegistry.id))
		.orderBy(desc(deployments.startedAt))
		.limit(100);

	const enriched = rows.map((d) => ({
		...d,
		durationMs:
			d.completedAt && d.startedAt
				? d.completedAt.getTime() - d.startedAt.getTime()
				: null,
	}));

	return { deployments: enriched };
};
