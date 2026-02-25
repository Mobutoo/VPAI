import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { ideas } from '$lib/server/db/schema';
import { desc } from 'drizzle-orm';

export const GET: RequestHandler = async () => {
	const result = await db.select().from(ideas).orderBy(desc(ideas.createdAt));
	return json(result);
};

export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();

	const [idea] = await db.insert(ideas).values({
		title: body.title,
		description: body.description ?? null,
		status: body.status ?? 'draft',
		priority: body.priority ?? 'none',
		tags: body.tags ?? []
	}).returning();

	return json(idea, { status: 201 });
};
