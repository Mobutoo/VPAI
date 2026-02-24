import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { tasks } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const PUT: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	const body = await request.json();

	const [updated] = await db.update(tasks)
		.set({ ...body, updatedAt: new Date() })
		.where(eq(tasks.id, taskId))
		.returning();

	if (!updated) {
		return json({ error: 'Task not found' }, { status: 404 });
	}

	return json(updated);
};
