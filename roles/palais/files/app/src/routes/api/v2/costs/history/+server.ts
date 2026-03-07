import { db } from '$lib/server/db';
import { costEntries } from '$lib/server/db/schema';
import { gte } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ url }) => {
    try {
        const monthsParam = Number(url.searchParams.get('months') ?? '6');
        const months = Number.isFinite(monthsParam) && monthsParam > 0 ? Math.floor(monthsParam) : 6;

        const cutoff = new Date();
        cutoff.setMonth(cutoff.getMonth() - months);
        cutoff.setDate(1);
        cutoff.setHours(0, 0, 0, 0);

        const entries = await db
            .select()
            .from(costEntries)
            .where(gte(costEntries.periodStart, cutoff));

        const monthMap = new Map<string, { total: number; byProvider: Record<string, number> }>();

        for (const entry of entries) {
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

        const history = Array.from(monthMap.entries())
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([month, { total, byProvider }]) => ({
                month,
                total: Math.round(total * 100) / 100,
                byProvider: Object.fromEntries(
                    Object.entries(byProvider).map(([p, v]) => [p, Math.round(v * 100) / 100])
                ),
            }));

        return ok(history);
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
