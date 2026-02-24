import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { comments } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { logActivity } from '$lib/server/activity';

export const GET: RequestHandler = async ({ params }) => {
	const taskId = parseInt(params.id);
	const result = await db.select().from(comments)
		.where(eq(comments.taskId, taskId))
		.orderBy(asc(comments.createdAt));
	return json(result);
};

export const POST: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	const body = await request.json();

	const [comment] = await db.insert(comments).values({
		taskId,
		content: body.content,
		authorType: body.authorType || 'user',
		authorAgentId: body.authorAgentId ?? null
	}).returning();

	await logActivity({
		entityType: 'task',
		entityId: taskId,
		action: 'comment_added',
		actorType: body.authorType === 'agent' ? 'agent' : 'user',
		actorAgentId: body.authorAgentId ?? undefined,
		newValue: body.content.slice(0, 200)
	});

	return json(comment, { status: 201 });
};
