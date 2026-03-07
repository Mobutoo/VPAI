import { db } from '$lib/server/db';
import { projectRegistry, deployments, deploymentSteps, servers } from '$lib/server/db/schema';
import { eq, desc, asc, inArray } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const { slug } = params;

	// Load workspace
	const [workspace] = await db
		.select()
		.from(projectRegistry)
		.where(eq(projectRegistry.slug, slug))
		.limit(1);

	if (!workspace) {
		throw error(404, `Workspace "${slug}" not found`);
	}

	// Load primary server info
	let server: { name: string; slug: string; status: string; location: string | null } | null = null;
	if (workspace.primaryServerId) {
		const [serverRow] = await db
			.select({
				name: servers.name,
				slug: servers.slug,
				status: servers.status,
				location: servers.location,
			})
			.from(servers)
			.where(eq(servers.id, workspace.primaryServerId))
			.limit(1);

		if (serverRow) {
			server = serverRow;
		}
	}

	// Load deployment history (most recent first)
	const deploymentRows = await db
		.select()
		.from(deployments)
		.where(eq(deployments.workspaceId, workspace.id))
		.orderBy(desc(deployments.startedAt))
		.limit(30);

	// Load all steps for those deployments
	const deploymentIds = deploymentRows.map((d) => d.id);
	const stepsMap = new Map<number, typeof deploymentSteps.$inferSelect[]>();

	if (deploymentIds.length > 0) {
		const allSteps = deploymentIds.length === 1
			? await db
					.select()
					.from(deploymentSteps)
					.where(eq(deploymentSteps.deploymentId, deploymentIds[0]))
					.orderBy(asc(deploymentSteps.position))
			: await db
					.select()
					.from(deploymentSteps)
					.where(inArray(deploymentSteps.deploymentId, deploymentIds))
					.orderBy(asc(deploymentSteps.position));

		for (const step of allSteps) {
			const existing = stepsMap.get(step.deploymentId) ?? [];
			existing.push(step);
			stepsMap.set(step.deploymentId, existing);
		}
	}

	const deploymentHistory = deploymentRows.map((d) => ({
		...d,
		steps: stepsMap.get(d.id) ?? [],
		durationMs:
			d.completedAt && d.startedAt
				? d.completedAt.getTime() - d.startedAt.getTime()
				: null,
	}));

	return { workspace, server, deploymentHistory };
};
