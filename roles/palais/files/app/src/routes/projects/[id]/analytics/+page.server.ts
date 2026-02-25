import { db } from '$lib/server/db';
import { projects, columns, tasks, timeEntries, taskIterations } from '$lib/server/db/schema';
import { eq, asc, inArray, sum, count } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const projectId = parseInt(params.id);
	if (isNaN(projectId)) throw error(404, 'Project not found');

	const [project] = await db.select().from(projects).where(eq(projects.id, projectId));
	if (!project) throw error(404, 'Project not found');

	const cols = await db.select().from(columns)
		.where(eq(columns.projectId, projectId))
		.orderBy(asc(columns.position));

	const allTasks = await db.select().from(tasks)
		.where(eq(tasks.projectId, projectId));

	const taskIds = allTasks.map((t) => t.id);

	// Time entries
	const entries = taskIds.length
		? await db.select().from(timeEntries).where(inArray(timeEntries.taskId, taskIds))
		: [];

	// Iterations
	const iterations = taskIds.length
		? await db.select().from(taskIterations).where(inArray(taskIterations.taskId, taskIds))
		: [];

	// ── Compute analytics ───────────────────────────────────────────────────
	const totalTimeSeconds = entries.reduce((s, e) => s + (e.durationSeconds ?? 0), 0);

	// Time per column (tasks grouped by current column)
	const colMap = new Map(cols.map((c) => [c.id, c.name]));
	const timeByColumn: Record<string, number> = {};
	for (const t of allTasks) {
		const colName = colMap.get(t.columnId) ?? 'Unknown';
		const taskTime = entries
			.filter((e) => e.taskId === t.id)
			.reduce((s, e) => s + (e.durationSeconds ?? 0), 0);
		timeByColumn[colName] = (timeByColumn[colName] ?? 0) + taskTime;
	}

	const totalIterations = iterations.length;

	const totalEstimated = allTasks.reduce((s, t) => s + (t.estimatedCost ?? 0), 0);
	const totalActual = allTasks.reduce((s, t) => s + (t.actualCost ?? 0), 0);

	// Top 3 most expensive tasks
	const topTasks = [...allTasks]
		.filter((t) => (t.actualCost ?? 0) > 0 || (t.estimatedCost ?? 0) > 0)
		.sort((a, b) => (b.actualCost ?? b.estimatedCost ?? 0) - (a.actualCost ?? a.estimatedCost ?? 0))
		.slice(0, 3)
		.map((t) => ({ id: t.id, title: t.title, estimated: t.estimatedCost, actual: t.actualCost }));

	// Tasks by iteration count
	const iterByTask: Record<number, number> = {};
	for (const iter of iterations) {
		iterByTask[iter.taskId] = (iterByTask[iter.taskId] ?? 0) + 1;
	}
	const taskIterCounts = allTasks
		.map((t) => ({ id: t.id, title: t.title, iterations: iterByTask[t.id] ?? 0 }))
		.filter((t) => t.iterations > 0)
		.sort((a, b) => b.iterations - a.iterations)
		.slice(0, 5);

	// Cost / iteration ratio (per task)
	const costPerIteration = totalIterations > 0
		? totalActual / totalIterations
		: null;

	return {
		project,
		analytics: {
			totalTimeSeconds,
			timeByColumn,
			totalIterations,
			totalEstimated,
			totalActual,
			topTasks,
			taskIterCounts,
			costPerIteration,
			taskCount: allTasks.length,
			completedCount: allTasks.filter((t) => cols.find((c) => c.id === t.columnId)?.isFinal).length
		}
	};
};
