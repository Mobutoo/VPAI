import * as dockerRemote from '$lib/server/providers/docker-remote';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params }) => {
	try {
		const containers = await dockerRemote.listContainers('waza');
		const container = containers.find((c) => c.name === params.slug);

		if (!container) {
			return ok({ status: 'stopped' });
		}

		return ok(container);
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
