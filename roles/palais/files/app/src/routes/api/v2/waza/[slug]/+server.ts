import { db } from '$lib/server/db';
import { wazaServices } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import * as dockerRemote from '$lib/server/providers/docker-remote';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params }) => {
	try {
		const [service] = await db
			.select()
			.from(wazaServices)
			.where(eq(wazaServices.slug, params.slug));

		if (!service) {
			return err('Service not found', 404);
		}

		return ok(service);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};

export const POST: RequestHandler = async ({ params, request }) => {
	try {
		const [service] = await db
			.select()
			.from(wazaServices)
			.where(eq(wazaServices.slug, params.slug));

		if (!service) {
			return err('Service not found', 404);
		}

		const body = await request.json();
		const { action } = body as { action?: string };

		if (action !== 'start' && action !== 'stop') {
			return err('Invalid action. Must be "start" or "stop"', 400);
		}

		await dockerRemote.controlContainer('workstation', params.slug, action);

		if (action === 'start') {
			await db
				.update(wazaServices)
				.set({ status: 'running', startedAt: new Date() })
				.where(eq(wazaServices.slug, params.slug));
		} else {
			await db
				.update(wazaServices)
				.set({ status: 'stopped', lastStoppedAt: new Date() })
				.where(eq(wazaServices.slug, params.slug));
		}

		const [updated] = await db
			.select()
			.from(wazaServices)
			.where(eq(wazaServices.slug, params.slug));

		return ok(updated);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
