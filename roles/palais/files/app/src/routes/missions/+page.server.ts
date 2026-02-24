import type { PageServerLoad } from './$types';
import { db } from '$lib/server/db';
import { missions, ideas } from '$lib/server/db/schema';
import { desc, eq } from 'drizzle-orm';

export const load: PageServerLoad = async () => {
	const allMissions = await db.select().from(missions).orderBy(desc(missions.createdAt));

	// Load approved ideas for "create from idea" workflow
	const approvedIdeas = await db.select({ id: ideas.id, title: ideas.title })
		.from(ideas)
		.where(eq(ideas.status, 'approved'));

	return { missions: allMissions, approvedIdeas };
};
