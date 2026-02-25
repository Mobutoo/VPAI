import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { ideas, ideaVersions } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';

export const GET: RequestHandler = async ({ params }) => {
	const id = parseInt(params.id);
	const [idea] = await db.select().from(ideas).where(eq(ideas.id, id));
	if (!idea) return json({ error: 'Not found' }, { status: 404 });
	return json(idea);
};

export const PUT: RequestHandler = async ({ params, request }) => {
	const id = parseInt(params.id);
	const body = await request.json();

	const [existing] = await db.select().from(ideas).where(eq(ideas.id, id));
	if (!existing) return json({ error: 'Not found' }, { status: 404 });

	// Auto-snapshot on status change or explicit version request
	if ((body.status && body.status !== existing.status) || body.createVersion) {
		const versionCount = await db.select().from(ideaVersions).where(eq(ideaVersions.ideaId, id));
		await db.insert(ideaVersions).values({
			ideaId: id,
			versionNumber: versionCount.length + 1,
			contentSnapshot: {
				title: existing.title,
				description: existing.description,
				status: existing.status,
				priority: existing.priority,
				tags: existing.tags
			},
			createdBy: body.createdBy ?? 'user'
		});
	}

	const [updated] = await db.update(ideas)
		.set({
			title: body.title ?? existing.title,
			description: body.description !== undefined ? body.description : existing.description,
			status: body.status ?? existing.status,
			priority: body.priority ?? existing.priority,
			tags: body.tags ?? existing.tags,
			updatedAt: new Date()
		})
		.where(eq(ideas.id, id))
		.returning();

	return json(updated);
};

export const DELETE: RequestHandler = async ({ params }) => {
	const id = parseInt(params.id);
	await db.delete(ideas).where(eq(ideas.id, id));
	return json({ ok: true });
};
