import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { missions } from '$lib/server/db/schema';
import { desc } from 'drizzle-orm';

export const GET: RequestHandler = async () => {
	const result = await db.select().from(missions).orderBy(desc(missions.createdAt));
	return json(result);
};

export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	if (!body.title?.trim()) {
		return json({ error: 'Title is required' }, { status: 400 });
	}

	const [mission] = await db.insert(missions).values({
		title: body.title.trim(),
		briefText: body.briefText ?? null,
		ideaId: body.ideaId ?? null,
		status: 'briefing'
	}).returning();

	return json(mission, { status: 201 });
};
