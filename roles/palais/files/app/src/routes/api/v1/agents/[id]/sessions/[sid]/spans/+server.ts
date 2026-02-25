import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { agentSpans, agentSessions, agents } from '$lib/server/db/schema';
import { eq, and, asc } from 'drizzle-orm';

/**
 * GET /api/v1/agents/:id/sessions/:sid/spans
 * Returns flat array of spans for a session, ordered by startedAt.
 * Client reconstructs the tree using parentSpanId.
 */
export const GET: RequestHandler = async ({ params }) => {
	const agentId = params.id;
	const sessionId = parseInt(params.sid);
	if (isNaN(sessionId)) return json({ error: 'Invalid session id' }, { status: 400 });

	// Verify agent owns this session
	const [session] = await db.select()
		.from(agentSessions)
		.where(and(eq(agentSessions.id, sessionId), eq(agentSessions.agentId, agentId)));

	if (!session) return json({ error: 'Session not found' }, { status: 404 });

	const spans = await db.select()
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

	return json({
		session: {
			id: session.id,
			agentId: session.agentId,
			taskId: session.taskId,
			model: session.model,
			status: session.status,
			startedAt: session.startedAt,
			endedAt: session.endedAt,
			confidenceScore: session.confidenceScore,
			summary: session.summary,
			totalTokens: totalTokens || session.totalTokens,
			totalCost: totalCost || session.totalCost,
			durationMs
		},
		spans: spans.map((s) => ({
			id: s.id,
			parentSpanId: s.parentSpanId,
			type: s.type,
			name: s.name,
			model: s.model,
			tokensIn: s.tokensIn,
			tokensOut: s.tokensOut,
			cost: s.cost,
			startedAt: s.startedAt,
			endedAt: s.endedAt,
			durationMs: s.durationMs,
			hasError: s.error !== null,
			error: s.error,
			input: s.input,
			output: s.output
		})),
		stats: { totalTokens, totalCost, errorCount, spanCount: spans.length, durationMs }
	});
};
