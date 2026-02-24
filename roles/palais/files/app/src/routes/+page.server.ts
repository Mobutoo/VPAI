import { db } from '$lib/server/db';
import { agents, insights } from '$lib/server/db/schema';
import { eq, desc, ne } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allAgents = await db.select().from(agents).orderBy(agents.name);

	// Load latest standup
	const [latestStandup] = await db.select().from(insights)
		.where(eq(insights.type, 'standup'))
		.orderBy(desc(insights.createdAt))
		.limit(1);

	// Load active non-standup insights
	const activeInsights = await db.select().from(insights)
		.where(eq(insights.acknowledged, false))
		.orderBy(desc(insights.createdAt))
		.limit(5);

	return {
		agents: allAgents,
		standup: latestStandup
			? { generated: true, ...latestStandup }
			: { generated: false },
		insights: activeInsights.filter(i => i.type !== 'standup')
	};
};
