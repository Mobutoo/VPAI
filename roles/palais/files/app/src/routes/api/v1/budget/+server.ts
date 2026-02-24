import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { budgetSnapshots, agentSessions } from '$lib/server/db/schema';
import { gte, desc } from 'drizzle-orm';
import { env } from '$env/dynamic/private';
import { getLiteLLMSpendByModel } from '$lib/server/budget/litellm';

const DAILY_LIMIT = parseFloat(env.BUDGET_DAILY_LIMIT ?? '5.0');

function startOfDay(): Date {
	const d = new Date();
	d.setHours(0, 0, 0, 0);
	return d;
}

// GET /api/v1/budget — summary for today
export const GET: RequestHandler = async () => {
	const since = startOfDay();
	const snapshots = await db.select()
		.from(budgetSnapshots)
		.where(gte(budgetSnapshots.date, since))
		.orderBy(desc(budgetSnapshots.capturedAt));

	// Latest snapshot per source
	const latestBySource = new Map<string, typeof snapshots[0]>();
	for (const s of snapshots) {
		if (!latestBySource.has(s.source)) latestBySource.set(s.source, s);
	}

	const litellmSnap = latestBySource.get('litellm');
	const openrouterSnap = latestBySource.get('openrouter_direct');
	const openaiSnap = latestBySource.get('openai_direct');
	const anthropicSnap = latestBySource.get('anthropic_direct');

	const viaLitellm = litellmSnap?.spendAmount ?? 0;
	const viaDirect = (openrouterSnap?.spendAmount ?? 0)
		+ (openaiSnap?.spendAmount ?? 0)
		+ (anthropicSnap?.spendAmount ?? 0);

	// Total = max(litellm, direct_sum) to avoid double-counting
	// LiteLLM routes calls through providers, so LiteLLM spend ~= provider spend
	const total = Math.max(viaLitellm, viaDirect);
	const remaining = Math.max(0, DAILY_LIMIT - total);
	const percentUsed = Math.min(100, (total / DAILY_LIMIT) * 100);

	// By provider breakdown
	const byProvider: Record<string, number> = {};
	for (const [, s] of latestBySource) {
		byProvider[s.provider ?? s.source] = (byProvider[s.provider ?? s.source] ?? 0) + (s.spendAmount ?? 0);
	}

	// Per-model breakdown from LiteLLM
	const byModel = await getLiteLLMSpendByModel();

	// 30-day history (daily totals)
	const thirtyDaysAgo = new Date();
	thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
	const history = await db.select()
		.from(budgetSnapshots)
		.where(gte(budgetSnapshots.date, thirtyDaysAgo))
		.orderBy(desc(budgetSnapshots.capturedAt));

	// Group by day
	const dailyHistory = new Map<string, number>();
	for (const s of history) {
		const day = new Date(s.date).toISOString().split('T')[0];
		dailyHistory.set(day, Math.max(dailyHistory.get(day) ?? 0, s.spendAmount ?? 0));
	}
	const historyArray = [...dailyHistory.entries()]
		.map(([date, spend]) => ({ date, spend }))
		.sort((a, b) => a.date.localeCompare(b.date));

	// Burn rate — tokens/hour from last 2 snapshots
	const recentLitellm = snapshots.filter((s) => s.source === 'litellm').slice(0, 2);
	let burnRatePerHour = 0;
	if (recentLitellm.length >= 2) {
		const deltaSpend = (recentLitellm[0].spendAmount ?? 0) - (recentLitellm[1].spendAmount ?? 0);
		const deltaMs = new Date(recentLitellm[0].capturedAt).getTime()
			- new Date(recentLitellm[1].capturedAt).getTime();
		if (deltaMs > 0) {
			burnRatePerHour = (deltaSpend / deltaMs) * 3_600_000;
		}
	}

	// Predicted exhaustion
	let predictedExhaustionAt: string | null = null;
	if (burnRatePerHour > 0 && remaining > 0) {
		const hoursLeft = remaining / burnRatePerHour;
		const exhaustAt = new Date(Date.now() + hoursLeft * 3_600_000);
		predictedExhaustionAt = exhaustAt.toISOString();
	}

	return json({
		today: {
			viaLitellm,
			viaDirect,
			total,
			remaining,
			percentUsed,
			dailyLimit: DAILY_LIMIT
		},
		byProvider,
		byModel,
		burnRatePerHour,
		predictedExhaustionAt,
		history: historyArray
	});
};
