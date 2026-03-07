import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { projectRegistry, deployments } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { triggerDeploy } from '$lib/server/deploy/ansible-runner';

export const workspacesToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.workspaces.list',
		description: 'List all project workspaces with their stack, current version, last deployment date, and primary server. No parameters required.',
		inputSchema: {
			type: 'object',
			properties: {}
		}
	},
	{
		name: 'palais.workspaces.deploy',
		description: 'Trigger a deployment for a workspace. Creates a pending deployment record and dispatches the Ansible deploy via n8n webhook.',
		inputSchema: {
			type: 'object',
			properties: {
				slug: { type: 'string', description: 'Workspace slug identifier (e.g. zimboo, nocodb)' },
				version: { type: 'string', description: 'Version to deploy (e.g. v1.14.0, latest)' }
			},
			required: ['slug', 'version']
		}
	}
];

export async function handleWorkspacesTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'list': {
			const workspaces = await db.select().from(projectRegistry).orderBy(projectRegistry.name);

			return workspaces.map((ws) => ({
				name: ws.name,
				slug: ws.slug,
				stack: ws.stack ?? null,
				currentVersion: ws.currentVersion ?? null,
				lastDeployedAt: ws.lastDeployedAt ?? null,
				primaryServerId: ws.primaryServerId ?? null
			}));
		}

		case 'deploy': {
			const slug = args.slug as string;
			const version = args.version as string;

			if (!slug) throw new Error('Missing required parameter: slug');
			if (!version) throw new Error('Missing required parameter: version');

			const [workspace] = await db
				.select()
				.from(projectRegistry)
				.where(eq(projectRegistry.slug, slug))
				.limit(1);

			if (!workspace) throw new Error(`Workspace not found: ${slug}`);

			const [deployment] = await db
				.insert(deployments)
				.values({
					workspaceId: workspace.id,
					serverId: workspace.primaryServerId ?? null,
					version,
					status: 'pending',
					triggeredBy: 'agent',
					deployType: 'update'
				})
				.returning();

			let n8nExecutionId: string | null = null;
			try {
				const { executionId } = await triggerDeploy({
					workspaceSlug: slug,
					version,
					targetServer: String(workspace.primaryServerId ?? ''),
					playbook: workspace.playbookPath ?? 'playbooks/site.yml',
					extraVars: {}
				});
				n8nExecutionId = executionId;

				await db
					.update(deployments)
					.set({ n8nExecutionId: executionId, status: 'running' })
					.where(eq(deployments.id, deployment.id));
			} catch (err) {
				const errorMsg = err instanceof Error ? err.message : String(err);
				await db
					.update(deployments)
					.set({ status: 'failed', errorSummary: errorMsg })
					.where(eq(deployments.id, deployment.id));
				throw new Error(`Deploy trigger failed: ${errorMsg}`);
			}

			return {
				deploymentId: deployment.id,
				workspaceSlug: slug,
				version,
				status: 'running',
				n8nExecutionId
			};
		}

		default:
			throw new Error(`Unknown workspaces method: ${method}`);
	}
}
