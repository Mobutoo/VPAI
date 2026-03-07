import { db } from '$lib/server/db';
import { wazaServices } from '$lib/server/db/schema';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
	try {
		const services = await db
			.select()
			.from(wazaServices)
			.orderBy(wazaServices.name);

		return ok(services);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
