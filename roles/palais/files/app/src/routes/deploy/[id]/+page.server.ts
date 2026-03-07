import { db } from '$lib/server/db';
import { deployments, deploymentSteps, projectRegistry } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const deploymentId = parseInt(params.id, 10);
	if (isNaN(deploymentId)) {
		throw error(400, 'Invalid deployment ID');
	}

	// Load deployment with workspace info
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
			workspaceSlug: projectRegistry.slug,
		})
		.from(deployments)
		.leftJoin(projectRegistry, eq(deployments.workspaceId, projectRegistry.id))
		.where(eq(deployments.id, deploymentId))
		.limit(1);

	if (!row) {
		throw error(404, `Deployment #${deploymentId} not found`);
	}

	// Load steps ordered by position
	const steps = await db
		.select()
		.from(deploymentSteps)
		.where(eq(deploymentSteps.deploymentId, deploymentId))
		.orderBy(asc(deploymentSteps.position));

	const durationMs =
		row.completedAt && row.startedAt
			? row.completedAt.getTime() - row.startedAt.getTime()
			: null;

	return {
		deployment: { ...row, durationMs },
		steps,
	};
};
