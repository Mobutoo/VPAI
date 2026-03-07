import { getCostSummary } from '$lib/server/costs/aggregator';
import { db } from '$lib/server/db';
import { costEntries } from '$lib/server/db/schema';
import { desc, gte } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	// 1. Cost summary (current 30-day period)
	const summary = await getCostSummary(60);

	// 2. Monthly history — last 6 months
	const sixMonthsAgo = new Date();
	sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
	sixMonthsAgo.setDate(1);
	sixMonthsAgo.setHours(0, 0, 0, 0);

	const rawEntries = await db
		.select()
		.from(costEntries)
		.where(gte(costEntries.periodStart, sixMonthsAgo))
		.orderBy(desc(costEntries.recordedAt));

	// Build monthly aggregation map
	const monthMap = new Map<string, { total: number; byProvider: Record<string, number> }>();

	for (const entry of rawEntries) {
		const d = entry.periodStart;
		const monthKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
		const existing = monthMap.get(monthKey);
		if (existing) {
			existing.total += entry.amountEur;
			existing.byProvider[entry.provider] =
				(existing.byProvider[entry.provider] ?? 0) + entry.amountEur;
		} else {
			monthMap.set(monthKey, {
				total: entry.amountEur,
				byProvider: { [entry.provider]: entry.amountEur },
			});
		}
	}

	const monthlyHistory = Array.from(monthMap.entries())
		.sort(([a], [b]) => a.localeCompare(b))
		.map(([month, { total, byProvider }]) => ({
			month,
			total: Math.round(total * 100) / 100,
			byProvider: Object.fromEntries(
				Object.entries(byProvider).map(([p, v]) => [p, Math.round(v * 100) / 100])
			),
		}));

	// 3. Recent entries for the log (latest 20)
	const recentEntries = rawEntries.slice(0, 20).map((e) => ({
		id: e.id,
		provider: e.provider,
		category: e.category,
		amountEur: e.amountEur,
		description: e.description,
		recordedAt: e.recordedAt.toISOString(),
		periodStart: e.periodStart.toISOString(),
		periodEnd: e.periodEnd.toISOString(),
	}));

	return {
		summary,
		monthlyHistory,
		recentEntries,
	};
};
