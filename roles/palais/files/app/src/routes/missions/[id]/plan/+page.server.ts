import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { db } from '$lib/server/db';
import { missions } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const load: PageServerLoad = async ({ params }) => {
	const id = parseInt(params.id);
	if (isNaN(id)) throw error(400, 'Invalid mission ID');

	const [mission] = await db.select().from(missions).where(eq(missions.id, id));
	if (!mission) throw error(404, 'Mission not found');

	return { mission };
};
