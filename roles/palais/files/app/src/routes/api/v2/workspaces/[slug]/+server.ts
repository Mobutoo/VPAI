import { db } from '$lib/server/db';
import { projectRegistry, deployments, deploymentSteps } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params }) => {
	try {
		const [workspace] = await db
			.select()
			.from(projectRegistry)
			.where(eq(projectRegistry.slug, params.slug))
			.limit(1);

		if (!workspace) {
			return err('Workspace not found', 404);
		}

		const [latestDeployment] = await db
			.select()
			.from(deployments)
			.where(eq(deployments.workspaceId, workspace.id))
			.orderBy(desc(deployments.startedAt))
			.limit(1);

		let deploymentWithSteps: typeof latestDeployment & { steps?: typeof deploymentSteps.$inferSelect[] } | null = null;

		if (latestDeployment) {
			const steps = await db
				.select()
				.from(deploymentSteps)
				.where(eq(deploymentSteps.deploymentId, latestDeployment.id))
				.orderBy(deploymentSteps.position);

			deploymentWithSteps = { ...latestDeployment, steps };
		}

		return ok({ ...workspace, latestDeployment: deploymentWithSteps });
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};

export const PATCH: RequestHandler = async ({ params, request }) => {
	try {
		const body = await request.json() as {
			name?: string;
			description?: string;
			repoUrl?: string;
			repoType?: string;
			stack?: string;
			playbookPath?: string;
			primaryServerId?: number | null;
			domainPattern?: string;
			healthcheckUrl?: string;
			onDemand?: boolean;
			composeFile?: string;
			minRamMb?: number | null;
			minCpuCores?: number | null;
			minDiskGb?: number | null;
			currentVersion?: string;
			latestVersion?: string;
		};

		const set: Record<string, unknown> = { updatedAt: new Date() };

		if (body.name !== undefined) set.name = body.name;
		if (body.description !== undefined) set.description = body.description;
		if (body.repoUrl !== undefined) set.repoUrl = body.repoUrl;
		if (body.repoType !== undefined) set.repoType = body.repoType;
		if (body.stack !== undefined) set.stack = body.stack;
		if (body.playbookPath !== undefined) set.playbookPath = body.playbookPath;
		if (body.primaryServerId !== undefined) set.primaryServerId = body.primaryServerId;
		if (body.domainPattern !== undefined) set.domainPattern = body.domainPattern;
		if (body.healthcheckUrl !== undefined) set.healthcheckUrl = body.healthcheckUrl;
		if (body.onDemand !== undefined) set.onDemand = body.onDemand;
		if (body.composeFile !== undefined) set.composeFile = body.composeFile;
		if (body.minRamMb !== undefined) set.minRamMb = body.minRamMb;
		if (body.minCpuCores !== undefined) set.minCpuCores = body.minCpuCores;
		if (body.minDiskGb !== undefined) set.minDiskGb = body.minDiskGb;
		if (body.currentVersion !== undefined) set.currentVersion = body.currentVersion;
		if (body.latestVersion !== undefined) set.latestVersion = body.latestVersion;

		const [updated] = await db
			.update(projectRegistry)
			.set(set)
			.where(eq(projectRegistry.slug, params.slug))
			.returning();

		if (!updated) {
			return err('Workspace not found', 404);
		}

		return ok(updated);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};

export const DELETE: RequestHandler = async ({ params }) => {
	try {
		const [deleted] = await db
			.delete(projectRegistry)
			.where(eq(projectRegistry.slug, params.slug))
			.returning({ id: projectRegistry.id, slug: projectRegistry.slug });

		if (!deleted) {
			return err('Workspace not found', 404);
		}

		return ok({ deleted: true, id: deleted.id, slug: deleted.slug });
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
