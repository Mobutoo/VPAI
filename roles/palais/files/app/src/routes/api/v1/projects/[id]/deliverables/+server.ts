import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { deliverables, tasks } from '$lib/server/db/schema';
import { eq, inArray } from 'drizzle-orm';

// GET — list all deliverables for a project (across all tasks)
export const GET: RequestHandler = async ({ params }) => {
	const projectId = parseInt(params.id);

	const projectTasks = await db.select({ id: tasks.id, title: tasks.title })
		.from(tasks)
		.where(eq(tasks.projectId, projectId));

	if (projectTasks.length === 0) return json([]);

	const taskIds = projectTasks.map((t) => t.id);
	const taskMap = new Map(projectTasks.map((t) => [t.id, t.title]));

	const entries = await db.select()
		.from(deliverables)
		.where(inArray(deliverables.entityId, taskIds));

	// Annotate with task title
	const result = entries.map((d) => ({
		...d,
		taskTitle: taskMap.get(d.entityId) ?? null
	}));

	return json(result);
};
