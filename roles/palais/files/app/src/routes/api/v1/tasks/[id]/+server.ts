import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { tasks } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { logActivity } from '$lib/server/activity';

export const PUT: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	const body = await request.json();

	const [existing] = await db.select().from(tasks).where(eq(tasks.id, taskId));
	if (!existing) {
		return json({ error: 'Task not found' }, { status: 404 });
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

	return json(updated);
};
