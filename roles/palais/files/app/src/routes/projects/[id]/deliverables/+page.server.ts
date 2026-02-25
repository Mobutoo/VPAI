import { db } from '$lib/server/db';
import { projects, tasks, deliverables } from '$lib/server/db/schema';
import { eq, inArray } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const projectId = parseInt(params.id);
	if (isNaN(projectId)) throw error(404, 'Project not found');

	const [project] = await db.select().from(projects).where(eq(projects.id, projectId));
	if (!project) throw error(404, 'Project not found');

	const projectTasks = await db.select({ id: tasks.id, title: tasks.title })
		.from(tasks).where(eq(tasks.projectId, projectId));

	const taskIds = projectTasks.map((t) => t.id);
	const taskMap = new Map(projectTasks.map((t) => [t.id, t.title]));

	const entries = taskIds.length
		? await db.select().from(deliverables).where(inArray(deliverables.entityId, taskIds))
		: [];

	const result = entries.map((d) => ({ ...d, taskTitle: taskMap.get(d.entityId) ?? null }));

	return { project, deliverables: result };
};
