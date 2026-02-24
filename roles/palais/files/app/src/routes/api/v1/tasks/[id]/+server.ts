import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { tasks, taskDependencies, columns } from '$lib/server/db/schema';
import { eq, inArray } from 'drizzle-orm';
import { logActivity } from '$lib/server/activity';

export const PUT: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	const body = await request.json();

	const [existing] = await db.select().from(tasks).where(eq(tasks.id, taskId));
	if (!existing) {
		return json({ error: 'Task not found' }, { status: 404 });
	}

	// Auto-blocking: when moving to a non-final column that means "in-progress",
	// check all dependencies are in final columns
	if (body.columnId && body.columnId !== existing.columnId) {
		const [targetColumn] = await db.select().from(columns).where(eq(columns.id, body.columnId));
		if (targetColumn && !targetColumn.isFinal) {
			const deps = await db.select().from(taskDependencies).where(eq(taskDependencies.taskId, taskId));
			if (deps.length > 0) {
				const depTaskIds = deps.map((d) => d.dependsOnTaskId);
				const depTasks = await db.select({ id: tasks.id, columnId: tasks.columnId })
					.from(tasks).where(inArray(tasks.id, depTaskIds));
				const depColumnIds = [...new Set(depTasks.map((t) => t.columnId))];
				const depColumns = await db.select({ id: columns.id, isFinal: columns.isFinal })
					.from(columns).where(inArray(columns.id, depColumnIds));
				const allDone = depColumns.every((c) => c.isFinal);
				if (!allDone) {
					return json({ error: 'Blocked: unresolved dependencies' }, { status: 409 });
				}
			}
		}
	}

	const [updated] = await db.update(tasks)
		.set({ ...body, updatedAt: new Date() })
		.where(eq(tasks.id, taskId))
		.returning();

	// Log activity for meaningful changes
	if (body.columnId && body.columnId !== existing.columnId) {
		await logActivity({
			entityType: 'task', entityId: taskId, action: 'moved',
			oldValue: String(existing.columnId), newValue: String(body.columnId)
		});
	} else if (body.title && body.title !== existing.title) {
		await logActivity({
			entityType: 'task', entityId: taskId, action: 'title_changed',
			oldValue: existing.title, newValue: body.title
		});
	}

	// Cascade: when endDate changes, shift dependent tasks' startDate + endDate
	if (body.endDate && existing.endDate) {
		const newEnd = new Date(body.endDate);
		const oldEnd = new Date(existing.endDate);
		const deltaMs = newEnd.getTime() - oldEnd.getTime();
		if (deltaMs !== 0) {
			await cascadeDates(taskId, deltaMs);
		}
	}

	return json(updated);
};

async function cascadeDates(taskId: number, deltaMs: number, visited = new Set<number>()): Promise<void> {
	if (visited.has(taskId)) return;
	visited.add(taskId);

	// Find tasks that depend on this one (finish-to-start)
	const dependents = await db.select({ taskId: taskDependencies.taskId })
		.from(taskDependencies)
		.where(eq(taskDependencies.dependsOnTaskId, taskId));

	for (const { taskId: depId } of dependents) {
		const [dep] = await db.select({ id: tasks.id, startDate: tasks.startDate, endDate: tasks.endDate })
			.from(tasks).where(eq(tasks.id, depId));
		if (!dep) continue;

		const newStart = dep.startDate ? new Date(dep.startDate.getTime() + deltaMs) : null;
		const newEnd = dep.endDate ? new Date(dep.endDate.getTime() + deltaMs) : null;

		await db.update(tasks)
			.set({ startDate: newStart, endDate: newEnd, updatedAt: new Date() })
			.where(eq(tasks.id, depId));

		await cascadeDates(depId, deltaMs, visited);
	}
}
