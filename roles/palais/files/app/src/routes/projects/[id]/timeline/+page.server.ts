import { db } from '$lib/server/db';
import { projects, tasks, taskDependencies } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import { computeCriticalPath } from '$lib/server/utils/critical-path';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const projectId = parseInt(params.id);
	if (isNaN(projectId)) throw error(404, 'Project not found');

	const [project] = await db.select().from(projects).where(eq(projects.id, projectId));
	if (!project) throw error(404, 'Project not found');

	const allTasks = await db.select().from(tasks)
		.where(eq(tasks.projectId, projectId))
		.orderBy(asc(tasks.position));

	const deps = await db.select().from(taskDependencies);
	const taskIds = new Set(allTasks.map((t) => t.id));

	// Compute critical path
	const ONE_DAY_MS = 86_400_000;
	const taskNodes = allTasks.map((t) => ({
		id: t.id,
		duration: t.startDate && t.endDate
			? Math.max(1, t.endDate.getTime() - t.startDate.getTime())
			: ONE_DAY_MS,
		deps: deps.filter((d) => d.taskId === t.id && taskIds.has(d.dependsOnTaskId))
			.map((d) => d.dependsOnTaskId)
	}));

	const criticalPath = computeCriticalPath(taskNodes);

	return {
		project,
		tasks: allTasks,
		dependencies: deps.filter((d) => taskIds.has(d.taskId) && taskIds.has(d.dependsOnTaskId)),
		criticalPathIds: criticalPath
	};
};
