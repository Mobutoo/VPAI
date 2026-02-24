import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { missions } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const GET: RequestHandler = async ({ params }) => {
	const id = parseInt(params.id);
	const [mission] = await db.select().from(missions).where(eq(missions.id, id));
	if (!mission) return json({ error: 'Not found' }, { status: 404 });
	return json(mission);
};

export const PUT: RequestHandler = async ({ params, request }) => {
	const id = parseInt(params.id);
	const body = await request.json();

	const [existing] = await db.select().from(missions).where(eq(missions.id, id));
	if (!existing) return json({ error: 'Not found' }, { status: 404 });

	const updatePayload: Record<string, unknown> = {};
	if (body.status) updatePayload.status = body.status;
	if (body.briefText !== undefined) updatePayload.briefText = body.briefText;
	if (body.planSnapshot !== undefined) updatePayload.planSnapshot = body.planSnapshot;
	if (body.totalEstimatedCost !== undefined) updatePayload.totalEstimatedCost = body.totalEstimatedCost;
	if (body.projectId !== undefined) updatePayload.projectId = body.projectId;
	if (body.status === 'completed') updatePayload.completedAt = new Date();

	const [updated] = await db.update(missions)
		.set(updatePayload)
		.where(eq(missions.id, id))
		.returning();

	return json(updated);
};
