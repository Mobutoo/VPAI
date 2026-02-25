import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { timeEntries, tasks } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';

// GET /api/v1/tasks/:id/timer — list all time entries for task
export const GET: RequestHandler = async ({ params }) => {
	const taskId = parseInt(params.id);
	const entries = await db.select()
		.from(timeEntries)
		.where(eq(timeEntries.taskId, taskId))
		.orderBy(desc(timeEntries.startedAt));
	return json(entries);
};

// POST /api/v1/tasks/:id/timer — start or stop manual timer
// body: { action: 'start' | 'stop', notes?: string }
export const POST: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	const body = await request.json();
	const { action, notes } = body;

	const [task] = await db.select().from(tasks).where(eq(tasks.id, taskId));
	if (!task) return json({ error: 'Task not found' }, { status: 404 });

	if (action === 'start') {
		// Close any open timer first
		const [open] = await db.select()
			.from(timeEntries)
			.where(eq(timeEntries.taskId, taskId))
			.orderBy(desc(timeEntries.startedAt))
			.limit(1);

		if (open && !open.endedAt) {
			return json({ error: 'Timer already running', entry: open }, { status: 409 });
		}

		const [entry] = await db.insert(timeEntries).values({
			taskId,
			type: 'manual',
			notes: notes ?? null
		}).returning();

		return json(entry, { status: 201 });
	}

	if (action === 'stop') {
		const [open] = await db.select()
			.from(timeEntries)
			.where(eq(timeEntries.taskId, taskId))
			.orderBy(desc(timeEntries.startedAt))
			.limit(1);

		if (!open || open.endedAt) {
			return json({ error: 'No running timer' }, { status: 404 });
		}

		const endedAt = new Date();
		const durationSeconds = Math.round(
			(endedAt.getTime() - new Date(open.startedAt).getTime()) / 1000
		);

		const [updated] = await db.update(timeEntries)
			.set({ endedAt, durationSeconds, notes: notes ?? open.notes })
			.where(eq(timeEntries.id, open.id))
			.returning();

		return json(updated);
	}

	return json({ error: 'action must be start or stop' }, { status: 400 });
};
