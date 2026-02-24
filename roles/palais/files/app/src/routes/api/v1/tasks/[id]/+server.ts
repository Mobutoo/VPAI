import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { tasks, taskDependencies, columns, timeEntries, taskIterations } from '$lib/server/db/schema';
import { eq, inArray, isNull, desc } from 'drizzle-orm';
import { logActivity } from '$lib/server/activity';

// Status values that mean "actively working"
const IN_PROGRESS_STATUSES = new Set(['in-progress', 'in_progress', 'assigned']);
// Status values that mean "done / paused"
const STOP_STATUSES = new Set(['done', 'review', 'backlog', 'planning']);

export const PUT: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	const body = await request.json();

	const [existing] = await db.select().from(tasks).where(eq(tasks.id, taskId));
	if (!existing) {
		return json({ error: 'Task not found' }, { status: 404 });
	}

	// Auto-blocking: when moving to a non-final column, check dependencies
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

	// Drizzle requires Date objects for timestamp columns
	const updatePayload = { ...body, updatedAt: new Date() };
	if (body.startDate) updatePayload.startDate = new Date(body.startDate);
	if (body.endDate) updatePayload.endDate = new Date(body.endDate);
	if (body.dueDate) updatePayload.dueDate = new Date(body.dueDate);

	const [updated] = await db.update(tasks)
		.set(updatePayload)
		.where(eq(tasks.id, taskId))
		.returning();

	// ── AUTO TIMER ────────────────────────────────────────────────────────────
	const newStatus = body.status as string | undefined;
	const oldStatus = existing.status ?? '';

	if (newStatus && newStatus !== oldStatus) {
		if (IN_PROGRESS_STATUSES.has(newStatus)) {
			// Start auto timer (close any open one first)
			await closeOpenTimer(taskId);
			await db.insert(timeEntries).values({ taskId, type: 'auto' });
		} else if (STOP_STATUSES.has(newStatus)) {
			await closeOpenTimer(taskId);
		}

		// ── ITERATION COUNTER ────────────────────────────────────────────────
		// Task re-opened: done → in-progress
		if (IN_PROGRESS_STATUSES.has(newStatus) && STOP_STATUSES.has(oldStatus) && oldStatus !== 'backlog' && oldStatus !== 'planning') {
			const existing_iters = await db.select()
				.from(taskIterations)
				.where(eq(taskIterations.taskId, taskId));
			await db.insert(taskIterations).values({
				taskId,
				iterationNumber: existing_iters.length + 1
			});
		}
	}
	// ─────────────────────────────────────────────────────────────────────────

	// Log activity
	if (body.columnId && body.columnId !== existing.columnId) {
		await logActivity({
			entityType: 'task', entityId: taskId, action: 'moved',
			oldValue: String(existing.columnId), newValue: String(body.columnId)
		});
	} else if (body.status && body.status !== existing.status) {
		await logActivity({
			entityType: 'task', entityId: taskId, action: 'status_changed',
			oldValue: existing.status ?? '', newValue: body.status
		});
	} else if (body.title && body.title !== existing.title) {
		await logActivity({
			entityType: 'task', entityId: taskId, action: 'title_changed',
			oldValue: existing.title, newValue: body.title
		});
	}

	// Cascade date shifts to dependents
	if (body.endDate && existing.endDate) {
		const newEnd = new Date(body.endDate);
		const oldEnd = new Date(existing.endDate);
		const deltaMs = newEnd.getTime() - oldEnd.getTime();
		if (deltaMs !== 0) await cascadeDates(taskId, deltaMs);
	}

	return json(updated);
};

// Close the most recent open auto time entry for a task
async function closeOpenTimer(taskId: number) {
	const [open] = await db.select()
		.from(timeEntries)
		.where(eq(timeEntries.taskId, taskId))
		.orderBy(desc(timeEntries.startedAt))
		.limit(1);

	if (open && !open.endedAt) {
		const endedAt = new Date();
		const durationSeconds = Math.round(
			(endedAt.getTime() - new Date(open.startedAt).getTime()) / 1000
		);
		await db.update(timeEntries)
			.set({ endedAt, durationSeconds })
			.where(eq(timeEntries.id, open.id));
	}
}

async function cascadeDates(taskId: number, deltaMs: number, visited = new Set<number>()): Promise<void> {
	if (visited.has(taskId)) return;
	visited.add(taskId);

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
