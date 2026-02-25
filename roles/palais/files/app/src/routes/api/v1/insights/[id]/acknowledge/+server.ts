import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const PUT: RequestHandler = async ({ params }) => {
	const insightId = parseInt(params.id);

	if (isNaN(insightId)) {
		return json({ error: 'Invalid insight ID' }, { status: 400 });
	}

	const [updated] = await db.update(insights)
		.set({ acknowledged: true })
		.where(eq(insights.id, insightId))
		.returning();

	if (!updated) {
		return json({ error: 'Insight not found' }, { status: 404 });
	}

	return json(updated);
};
