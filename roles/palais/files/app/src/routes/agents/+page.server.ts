import { db } from '$lib/server/db';
import { agents } from '$lib/server/db/schema';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allAgents = await db.select().from(agents).orderBy(agents.name);
	return { agents: allAgents };
};
