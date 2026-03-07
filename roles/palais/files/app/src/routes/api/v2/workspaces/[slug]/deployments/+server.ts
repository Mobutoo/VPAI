import { db } from '$lib/server/db';
import { projectRegistry, deployments, deploymentSteps } from '$lib/server/db/schema';
import { eq, desc, inArray } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params }) => {
	try {
		const [workspace] = await db
			.select({ id: projectRegistry.id })
			.from(projectRegistry)
			.where(eq(projectRegistry.slug, params.slug))
			.limit(1);

		if (!workspace) {
			return err('Workspace not found', 404);
		}

		const deploymentRows = await db
			.select()
			.from(deployments)
			.where(eq(deployments.workspaceId, workspace.id))
			.orderBy(desc(deployments.startedAt));

		if (deploymentRows.length === 0) {
			return ok([]);
		}

		const deploymentIds = deploymentRows.map((d) => d.id);

		const allSteps = await db
			.select()
			.from(deploymentSteps)
			.where(
				deploymentIds.length === 1
					? eq(deploymentSteps.deploymentId, deploymentIds[0])
					: inArray(deploymentSteps.deploymentId, deploymentIds)
			)
			.orderBy(deploymentSteps.position);

		const stepsByDeploymentId = new Map<number, typeof deploymentSteps.$inferSelect[]>();
		for (const step of allSteps) {
			const existing = stepsByDeploymentId.get(step.deploymentId) ?? [];
			existing.push(step);
			stepsByDeploymentId.set(step.deploymentId, existing);
		}

		const result = deploymentRows.map((deployment) => ({
			...deployment,
			steps: stepsByDeploymentId.get(deployment.id) ?? [],
		}));

		return ok(result);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
