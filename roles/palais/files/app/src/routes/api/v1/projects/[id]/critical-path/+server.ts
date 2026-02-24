import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { tasks, taskDependencies } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { computeCriticalPath } from '$lib/server/utils/critical-path';

export const GET: RequestHandler = async ({ params }) => {
	const projectId = parseInt(params.id);

	const projectTasks = await db.select({
		id: tasks.id,
		startDate: tasks.startDate,
		endDate: tasks.endDate
	}).from(tasks).where(eq(tasks.projectId, projectId));

	if (projectTasks.length === 0) return json([]);

	const allDeps = await db.select().from(taskDependencies);
	const taskIds = new Set(projectTasks.map((t) => t.id));

	// Build TaskNode list — duration in ms, fallback to 1 day
	const ONE_DAY_MS = 86_400_000;
	const taskNodes = projectTasks.map((t) => {
		const duration =
			t.startDate && t.endDate
				? Math.max(1, t.endDate.getTime() - t.startDate.getTime())
				: ONE_DAY_MS;
		const deps = allDeps
			.filter((d) => d.taskId === t.id && taskIds.has(d.dependsOnTaskId))
			.map((d) => d.dependsOnTaskId);
		return { id: t.id, duration, deps };
	});

	const criticalPath = computeCriticalPath(taskNodes);
	return json(criticalPath);
};
