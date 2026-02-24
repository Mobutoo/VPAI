import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { labels, taskLabels } from '$lib/server/db/schema';
import { eq, and } from 'drizzle-orm';

// GET /api/v1/labels?workspaceId=1
export const GET: RequestHandler = async ({ url }) => {
	const workspaceId = parseInt(url.searchParams.get('workspaceId') ?? '1');
	const result = await db.select().from(labels).where(eq(labels.workspaceId, workspaceId));
	return json(result);
};

// POST /api/v1/labels  { name, color, workspaceId }
export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	const { name, color, workspaceId } = body;

	if (!name || !color || !workspaceId) {
		return json({ error: 'name, color, and workspaceId required' }, { status: 400 });
	}

	const [label] = await db.insert(labels).values({ name, color, workspaceId }).returning();
	return json(label, { status: 201 });
};
