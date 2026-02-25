import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';

export const GET: RequestHandler = async () => {
	const [latest] = await db.select().from(insights)
		.where(eq(insights.type, 'standup'))
		.orderBy(desc(insights.createdAt))
		.limit(1);

	if (!latest) {
		return json({ generated: false, message: 'No standup available yet' });
	}

	return json({
		generated: true,
		id: latest.id,
		title: latest.title,
		description: latest.description,
		suggestedActions: latest.suggestedActions,
		createdAt: latest.createdAt
	});
};
