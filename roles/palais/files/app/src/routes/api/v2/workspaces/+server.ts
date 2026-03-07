import { db } from '$lib/server/db';
import { projectRegistry } from '$lib/server/db/schema';
import { asc } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
	try {
		const rows = await db
			.select()
			.from(projectRegistry)
			.orderBy(asc(projectRegistry.name));

		return ok(rows);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};

export const POST: RequestHandler = async ({ request }) => {
	try {
		const body = await request.json() as {
			name?: string;
			slug?: string;
			description?: string;
			repoUrl?: string;
			repoType?: string;
			stack?: string;
			playbookPath?: string;
			primaryServerId?: number;
			domainPattern?: string;
			healthcheckUrl?: string;
			onDemand?: boolean;
			composeFile?: string;
			minRamMb?: number;
			minCpuCores?: number;
			minDiskGb?: number;
		};

		if (!body.name || !body.slug) {
			return err('Fields "name" and "slug" are required', 400);
		}

		const now = new Date();

		const [created] = await db
			.insert(projectRegistry)
			.values({
				name: body.name,
				slug: body.slug,
				description: body.description ?? null,
				repoUrl: body.repoUrl ?? null,
				repoType: body.repoType ?? 'github',
				stack: body.stack ?? null,
				playbookPath: body.playbookPath ?? null,
				primaryServerId: body.primaryServerId ?? null,
				domainPattern: body.domainPattern ?? null,
				healthcheckUrl: body.healthcheckUrl ?? null,
				onDemand: body.onDemand ?? false,
				composeFile: body.composeFile ?? 'docker-compose.yml',
				minRamMb: body.minRamMb ?? null,
				minCpuCores: body.minCpuCores ?? null,
				minDiskGb: body.minDiskGb ?? null,
				createdAt: now,
				updatedAt: now,
			})
			.returning();

		return ok(created);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
