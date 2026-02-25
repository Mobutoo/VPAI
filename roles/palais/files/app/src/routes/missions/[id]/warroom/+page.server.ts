import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { db } from '$lib/server/db';
import { missions, tasks, agents } from '$lib/server/db/schema';
import { eq, inArray } from 'drizzle-orm';

export const load: PageServerLoad = async ({ params }) => {
	const id = parseInt(params.id);
	if (isNaN(id)) throw error(400, 'Invalid mission ID');

	const [mission] = await db.select().from(missions).where(eq(missions.id, id));
	if (!mission) throw error(404, 'Mission not found');

	// Load all tasks assigned to this mission
	const missionTasks = await db.select().from(tasks).where(eq(tasks.missionId, id));

	// Load agents currently working on mission tasks
	const taskIds = missionTasks.map((t) => t.id);
	const assignedAgents =
		taskIds.length > 0
			? await db.select().from(agents).where(inArray(agents.currentTaskId, taskIds))
			: [];

	const done = missionTasks.filter((t) => t.status === 'done').length;
	const inProgress = missionTasks.filter((t) => t.status === 'in-progress').length;
	const progressPercent =
		missionTasks.length > 0 ? Math.round((done / missionTasks.length) * 100) : 0;

	return {
		mission,
		missionTasks,
		assignedAgents,
		progressPercent,
		inProgressCount: inProgress
	};
};
