import { db } from '$lib/server/db';
import { projectRegistry, deployments, servers } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import { triggerDeploy } from '$lib/server/deploy/ansible-runner';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ params, request }) => {
	try {
		const body = await request.json() as {
			deploymentId: number;
		};

		if (!body.deploymentId) {
			return err('Field "deploymentId" is required', 400);
		}

		const [workspace] = await db
			.select()
			.from(projectRegistry)
			.where(eq(projectRegistry.slug, params.slug))
			.limit(1);

		if (!workspace) {
			return err('Workspace not found', 404);
		}

		const [sourceDeployment] = await db
			.select()
			.from(deployments)
			.where(eq(deployments.id, body.deploymentId))
			.limit(1);

		if (!sourceDeployment) {
			return err('Referenced deployment not found', 404);
		}

		if (sourceDeployment.workspaceId !== workspace.id) {
			return err('Deployment does not belong to this workspace', 400);
		}

		if (!sourceDeployment.version) {
			return err('Referenced deployment has no version to roll back to', 400);
		}

		const now = new Date();

		const [rollbackDeployment] = await db
			.insert(deployments)
			.values({
				workspaceId: workspace.id,
				version: sourceDeployment.version,
				status: 'pending',
				startedAt: now,
				triggeredBy: 'user',
				deployType: 'rollback',
				rollbackOf: body.deploymentId,
			})
			.returning();

		let serverSlug: string | undefined;

		if (workspace.primaryServerId) {
			const [server] = await db
				.select({ slug: servers.slug })
				.from(servers)
				.where(eq(servers.id, workspace.primaryServerId))
				.limit(1);

			if (server) {
				serverSlug = server.slug;
			}
		}

		if (!serverSlug) {
			return err('No target server found for this workspace', 400);
		}

		const { executionId } = await triggerDeploy({
			workspaceSlug: params.slug,
			version: sourceDeployment.version,
			targetServer: serverSlug,
			playbook: workspace.playbookPath ?? 'playbooks/site.yml',
		});

		const [updatedDeployment] = await db
			.update(deployments)
			.set({ n8nExecutionId: executionId })
			.where(eq(deployments.id, rollbackDeployment.id))
			.returning();

		return ok(updatedDeployment);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
