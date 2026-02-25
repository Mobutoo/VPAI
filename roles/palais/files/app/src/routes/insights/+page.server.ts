import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { desc, ne } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const showAcknowledged = url.searchParams.get('showAcknowledged') === 'true';

	const allInsights = await db.select().from(insights)
		.where(ne(insights.type, 'standup'))
		.orderBy(desc(insights.createdAt))
		.limit(200);

	return {
		insights: showAcknowledged
			? allInsights
			: allInsights.filter(i => !i.acknowledged),
		showAcknowledged
	};
};
