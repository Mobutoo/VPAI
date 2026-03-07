import { db } from '$lib/server/db';
import { servers } from '$lib/server/db/schema';
import { asc } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allServers = await db
		.select({
			id: servers.id,
			name: servers.name,
			slug: servers.slug,
			status: servers.status,
			location: servers.location,
			provider: servers.provider,
		})
		.from(servers)
		.orderBy(asc(servers.name));

	return { servers: allServers };
};
