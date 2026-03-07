import { db } from '$lib/server/db';
import { domains } from '$lib/server/db/schema';
import { asc } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allDomains = await db
		.select()
		.from(domains)
		.orderBy(asc(domains.name));

	return { domains: allDomains };
};
