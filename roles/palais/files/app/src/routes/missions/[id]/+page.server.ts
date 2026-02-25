import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { db } from '$lib/server/db';
import { missions, missionConversations, tasks } from '$lib/server/db/schema';
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

	// War Room suggestion — detect 5+ parallel in-progress tasks
	const missionTasks = await db.select({ id: tasks.id, status: tasks.status })
		.from(tasks)
		.where(eq(tasks.missionId, id));

	const parallelTasks = missionTasks.filter((t) => t.status === 'in-progress').length;
	const suggestWarRoom = parallelTasks >= 5;

	return { mission, conversation, suggestWarRoom, parallelTasks };
};
