import { db } from '$lib/server/db';
import { deployments, deploymentSteps, projectRegistry } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params }) => {
	try {
		const deploymentId = parseInt(params.id, 10);
		if (isNaN(deploymentId)) {
			return err('Invalid deployment id', 400);
		}

		const [row] = await db
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
			.where(eq(deployments.id, deploymentId));

		if (!row) {
			return err('Deployment not found', 404);
		}

		const steps = await db
			.select()
			.from(deploymentSteps)
			.where(eq(deploymentSteps.deploymentId, deploymentId))
			.orderBy(asc(deploymentSteps.position));

		return ok({ ...row, steps });
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
