import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { db } from '$lib/server/db';
import { ideas, ideaVersions } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';

export const load: PageServerLoad = async ({ params }) => {
	const id = parseInt(params.id);
	if (isNaN(id)) throw error(400, 'Invalid idea ID');

	const [idea] = await db.select().from(ideas).where(eq(ideas.id, id));
	if (!idea) throw error(404, 'Idea not found');

	const versions = await db.select().from(ideaVersions)
		.where(eq(ideaVersions.ideaId, id))
		.orderBy(asc(ideaVersions.versionNumber));

	return { idea, versions };
};
