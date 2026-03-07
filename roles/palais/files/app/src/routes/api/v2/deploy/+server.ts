import { db } from '$lib/server/db';
import { deployments, projectRegistry } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
	try {
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
				workspaceSlug: projectRegistry.slug
			})
			.from(deployments)
			.leftJoin(projectRegistry, eq(deployments.workspaceId, projectRegistry.id))
			.orderBy(desc(deployments.startedAt))
			.limit(50);

		return ok(rows);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
