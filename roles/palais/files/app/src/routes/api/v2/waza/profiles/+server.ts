import { db } from '$lib/server/db';
import { wazaServices } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import * as dockerRemote from '$lib/server/providers/docker-remote';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
	try {
		const services = await db.select().from(wazaServices);

		const profileMap = new Map<string, { services: string[]; activeCount: number }>();

		for (const service of services) {
			const profileName = service.profile ?? 'default';

			if (!profileMap.has(profileName)) {
				profileMap.set(profileName, { services: [], activeCount: 0 });
			}

			const entry = profileMap.get(profileName)!;
			entry.services.push(service.slug);

			if (service.status === 'running') {
				entry.activeCount += 1;
			}
		}

		const profiles = Array.from(profileMap.entries()).map(([name, data]) => ({
			name,
			services: data.services,
			activeCount: data.activeCount,
		}));

		return ok({ profiles });
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};

export const POST: RequestHandler = async ({ request }) => {
	try {
		const body = await request.json();
		const { profile, action } = body as { profile?: string; action?: string };

		if (!profile) {
			return err('Missing required field: profile', 400);
		}

		if (action !== 'start' && action !== 'stop') {
			return err('Invalid action. Must be "start" or "stop"', 400);
		}

		const services = await db
			.select()
			.from(wazaServices)
			.where(eq(wazaServices.profile, profile));

		if (services.length === 0) {
			return ok({ affected: 0 });
		}

		await Promise.all(
			services.map(async (service) => {
				const customCmd = action === 'start' ? service.startCmd : service.stopCmd;
				if (customCmd) {
					await dockerRemote.execOnServer('waza', customCmd);
				} else {
					await dockerRemote.controlContainer('waza', service.slug, action);
				}

				if (action === 'start') {
					await db
						.update(wazaServices)
						.set({ status: 'running', startedAt: new Date() })
						.where(eq(wazaServices.slug, service.slug));
				} else {
					await db
						.update(wazaServices)
						.set({ status: 'stopped', lastStoppedAt: new Date() })
						.where(eq(wazaServices.slug, service.slug));
				}
			})
		);

		return ok({ affected: services.length });
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
