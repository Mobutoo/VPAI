import { db } from '$lib/server/db';
import { projectRegistry, deployments, servers } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import { triggerDeploy } from '$lib/server/deploy/ansible-runner';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ params, request }) => {
	try {
		const body = await request.json() as {
			version: string;
			targetServer?: string;
			extraVars?: Record<string, string>;
		};

		if (!body.version) {
			return err('Field "version" is required', 400);
		}

		const [workspace] = await db
			.select()
			.from(projectRegistry)
			.where(eq(projectRegistry.slug, params.slug))
			.limit(1);

		if (!workspace) {
			return err('Workspace not found', 404);
		}

		const now = new Date();

		const [deployment] = await db
			.insert(deployments)
			.values({
				workspaceId: workspace.id,
				version: body.version,
				status: 'pending',
				startedAt: now,
				triggeredBy: 'user',
				deployType: 'update',
			})
			.returning();

		let serverSlug = body.targetServer;

		if (!serverSlug && workspace.primaryServerId) {
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
			return err('No target server specified and workspace has no primaryServerId', 400);
		}

		const { executionId } = await triggerDeploy({
			workspaceSlug: params.slug,
			version: body.version,
			targetServer: serverSlug,
			playbook: workspace.playbookPath ?? 'playbooks/site.yml',
			extraVars: body.extraVars,
		});

		const [updatedDeployment] = await db
			.update(deployments)
			.set({ n8nExecutionId: executionId })
			.where(eq(deployments.id, deployment.id))
			.returning();

		return ok(updatedDeployment);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
