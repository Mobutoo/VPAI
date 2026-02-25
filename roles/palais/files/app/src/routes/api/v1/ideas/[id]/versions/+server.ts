import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { ideas, ideaVersions } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';

export const GET: RequestHandler = async ({ params }) => {
	const id = parseInt(params.id);
	const versions = await db.select().from(ideaVersions)
		.where(eq(ideaVersions.ideaId, id))
		.orderBy(asc(ideaVersions.versionNumber));
	return json(versions);
};

export const POST: RequestHandler = async ({ params, request }) => {
	const id = parseInt(params.id);
	const body = await request.json();

	const [idea] = await db.select().from(ideas).where(eq(ideas.id, id));
	if (!idea) return json({ error: 'Not found' }, { status: 404 });

	const existing = await db.select().from(ideaVersions).where(eq(ideaVersions.ideaId, id));

	const [version] = await db.insert(ideaVersions).values({
		ideaId: id,
		versionNumber: existing.length + 1,
		contentSnapshot: body.contentSnapshot ?? {
			title: idea.title,
			description: idea.description,
			status: idea.status,
			priority: idea.priority,
			tags: idea.tags
		},
		taskBreakdown: body.taskBreakdown ?? null,
		brainstormingLog: body.brainstormingLog ?? null,
		createdBy: body.createdBy ?? 'user'
	}).returning();

	return json(version, { status: 201 });
};
