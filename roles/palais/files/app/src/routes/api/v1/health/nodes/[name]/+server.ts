import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { nodes } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const PATCH: RequestHandler = async ({ params, request }) => {
	const { name } = params;
	const body = await request.json() as { localIp?: string; description?: string };

	if (body.localIp === undefined && body.description === undefined) {
		throw error(400, 'No fields to update');
	}

	const set: Record<string, unknown> = {};
	if (body.localIp !== undefined) set.localIp = body.localIp;
	if (body.description !== undefined) set.description = body.description;

	const [updated] = await db
		.update(nodes)
		.set(set)
		.where(eq(nodes.name, name))
		.returning({ id: nodes.id });

	if (!updated) throw error(404, `Node "${name}" not found`);

	return json({ ok: true });
};
