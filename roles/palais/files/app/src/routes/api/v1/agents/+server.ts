import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { agents } from '$lib/server/db/schema';

export const GET: RequestHandler = async () => {
	const result = await db.select().from(agents).orderBy(agents.name);
	return json(result);
};
