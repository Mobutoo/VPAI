import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { tasks } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const GET: RequestHandler = async ({ params }) => {
	const projectId = parseInt(params.id);
	const result = await db.select().from(tasks).where(eq(tasks.projectId, projectId)).orderBy(tasks.position);
	return json(result);
};

export const POST: RequestHandler = async ({ params, request }) => {
	const projectId = parseInt(params.id);
	const body = await request.json();

	const [task] = await db.insert(tasks).values({
		projectId,
		columnId: body.columnId,
		title: body.title,
		description: body.description,
		priority: body.priority || 'none',
		assigneeAgentId: body.assigneeAgentId,
		creator: body.creator || 'user',
		startDate: body.startDate ? new Date(body.startDate) : null,
		endDate: body.endDate ? new Date(body.endDate) : null,
		dueDate: body.dueDate ? new Date(body.dueDate) : null,
		estimatedCost: body.estimatedCost ?? null
	}).returning();

	return json(task, { status: 201 });
};
