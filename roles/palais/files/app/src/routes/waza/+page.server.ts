import { db } from '$lib/server/db';
import { wazaServices } from '$lib/server/db/schema';
import { asc } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const services = await db
		.select()
		.from(wazaServices)
		.orderBy(asc(wazaServices.name));

	// Build profile groups
	const profileMap = new Map<string, string[]>();
	for (const svc of services) {
		const profile = svc.profile ?? 'default';
		if (!profileMap.has(profile)) {
			profileMap.set(profile, []);
		}
		profileMap.get(profile)!.push(svc.slug);
	}

	const profiles = Array.from(profileMap.entries()).map(([name, slugs]) => ({ name, slugs }));

	return { services, profiles };
};
