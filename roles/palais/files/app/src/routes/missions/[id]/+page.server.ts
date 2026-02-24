import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { db } from '$lib/server/db';
import { missions, missionConversations } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';

export const load: PageServerLoad = async ({ params }) => {
	const id = parseInt(params.id);
	if (isNaN(id)) throw error(400, 'Invalid mission ID');

	const [mission] = await db.select().from(missions).where(eq(missions.id, id));
	if (!mission) throw error(404, 'Mission not found');

	const conversation = await db.select()
		.from(missionConversations)
		.where(eq(missionConversations.missionId, id))
		.orderBy(asc(missionConversations.createdAt));

	return { mission, conversation };
};
