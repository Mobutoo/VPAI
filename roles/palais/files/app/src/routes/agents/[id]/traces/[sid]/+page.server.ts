import { db } from '$lib/server/db';
import { agents, agentSessions, agentSpans } from '$lib/server/db/schema';
import { eq, and, asc } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const agentId = params.id;
	const sessionId = parseInt(params.sid);
	if (isNaN(sessionId)) throw error(400, 'Invalid session id');

	const [agent] = await db.select().from(agents).where(eq(agents.id, agentId));
	if (!agent) throw error(404, 'Agent not found');

	const [session] = await db
		.select()
		.from(agentSessions)
		.where(and(eq(agentSessions.id, sessionId), eq(agentSessions.agentId, agentId)));
	if (!session) throw error(404, 'Session not found');

	const spans = await db
		.select()
		.from(agentSpans)
		.where(eq(agentSpans.sessionId, sessionId))
		.orderBy(asc(agentSpans.startedAt));

	// Summary stats
	const totalTokens = spans.reduce((s, sp) => s + (sp.tokensIn ?? 0) + (sp.tokensOut ?? 0), 0);
	const totalCost = spans.reduce((s, sp) => s + (sp.cost ?? 0), 0);
	const errorCount = spans.filter((s) => s.error !== null).length;
	const durationMs = session.endedAt
		? new Date(session.endedAt).getTime() - new Date(session.startedAt).getTime()
		: null;

	return {
		agent,
		session: {
			...session,
			durationMs,
			totalTokens: totalTokens || session.totalTokens,
			totalCost: totalCost || session.totalCost
		},
		spans,
		stats: { totalTokens, totalCost, errorCount, spanCount: spans.length, durationMs }
	};
};
