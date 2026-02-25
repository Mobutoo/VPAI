import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { agents } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const PATCH: RequestHandler = async ({ params, request }) => {
	const { id } = params;
	const body = await request.json() as { bio?: string; persona?: string };

	if (body.bio === undefined && body.persona === undefined) {
		throw error(400, 'No fields to update');
	}

	const set: Record<string, unknown> = {};
	if (body.bio !== undefined) set.bio = body.bio;
	if (body.persona !== undefined) set.persona = body.persona;

	const [updated] = await db
		.update(agents)
		.set(set)
		.where(eq(agents.id, id))
		.returning({ id: agents.id });

	if (!updated) throw error(404, 'Agent not found');

	return json({ ok: true });
};
