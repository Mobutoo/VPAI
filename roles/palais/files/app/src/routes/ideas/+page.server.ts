import { db } from '$lib/server/db';
import { ideas } from '$lib/server/db/schema';
import { desc } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allIdeas = await db.select().from(ideas).orderBy(desc(ideas.updatedAt));
	return { ideas: allIdeas };
};
