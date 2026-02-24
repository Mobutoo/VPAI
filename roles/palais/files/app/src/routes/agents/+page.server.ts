import { db } from '$lib/server/db';
import { agents, agentSessions, agentSpans } from '$lib/server/db/schema';
import { eq, gte, and, isNotNull } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allAgents = await db.select().from(agents).orderBy(agents.name);

	// 30-day performance metrics per agent
	const since30d = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);

	const sessions30d = await db.select().from(agentSessions)
		.where(gte(agentSessions.startedAt, since30d));

	const sessionIds30d = sessions30d.map(s => s.id);

	// Error counts from spans (only if sessions exist)
	let spanErrors: Record<number, number> = {}; // sessionId → error count
	if (sessionIds30d.length > 0) {
		const errorSpans = await db.select({ sessionId: agentSpans.sessionId })
			.from(agentSpans)
			.where(isNotNull(agentSpans.error));

		for (const sp of errorSpans) {
			if (sessionIds30d.includes(sp.sessionId)) {
				spanErrors[sp.sessionId] = (spanErrors[sp.sessionId] ?? 0) + 1;
			}
		}
	}

	// Aggregate per agent
	type PerfRow = {
		agentId: string;
		sessionCount: number;
		totalTokens: number;
		totalCost: number;
		avgConfidence: number | null;
		errorRate: number;
	};

	const perfMap = new Map<string, PerfRow>();

	for (const agent of allAgents) {
		perfMap.set(agent.id, {
			agentId: agent.id,
			sessionCount: 0,
			totalTokens: 0,
			totalCost: 0,
			avgConfidence: null,
			errorRate: 0
		});
	}

	for (const session of sessions30d) {
		const row = perfMap.get(session.agentId);
		if (!row) continue;
		row.sessionCount++;
		row.totalTokens += session.totalTokens ?? 0;
		row.totalCost += session.totalCost ?? 0;
	}

	// Compute avgConfidence and errorRate
	for (const agentId of perfMap.keys()) {
		const agentSess = sessions30d.filter(s => s.agentId === agentId);
		const withConf = agentSess.filter(s => s.confidenceScore !== null && s.confidenceScore !== undefined);
		const row = perfMap.get(agentId)!;

		if (withConf.length > 0) {
			row.avgConfidence = withConf.reduce((acc, s) => acc + (s.confidenceScore ?? 0), 0) / withConf.length;
		}

		const totalErrors = agentSess.reduce((acc, s) => acc + (spanErrors[s.id] ?? 0), 0);
		const totalSpans = agentSess.length; // sessions as proxy; could be spans count
		row.errorRate = agentSess.length > 0 ? totalErrors / Math.max(totalSpans, 1) : 0;
	}

	return { agents: allAgents, perf: [...perfMap.values()] };
};
