import { db } from '$lib/server/db';
import { agents, agentSessions } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const [agent] = await db.select().from(agents).where(eq(agents.id, params.id));
	if (!agent) throw error(404, 'Agent not found');

	const sessions = await db
		.select()
		.from(agentSessions)
		.where(eq(agentSessions.agentId, params.id))
		.orderBy(desc(agentSessions.startedAt))
		.limit(50);

	return { agent, sessions };
};
