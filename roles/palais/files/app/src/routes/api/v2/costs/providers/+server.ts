import { db } from '$lib/server/db';
import { costEntries } from '$lib/server/db/schema';
import { gte } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
    try {
        const now = new Date();
        const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

        const entries = await db
            .select()
            .from(costEntries)
            .where(gte(costEntries.periodStart, firstOfMonth));

        const providerMap = new Map<string, { total: number; count: number }>();

        for (const entry of entries) {
            const existing = providerMap.get(entry.provider);
            if (existing) {
                providerMap.set(entry.provider, {
                    total: existing.total + entry.amountEur,
                    count: existing.count + 1,
                });
            } else {
                providerMap.set(entry.provider, { total: entry.amountEur, count: 1 });
            }
        }

        const providers = Array.from(providerMap.entries()).map(([name, { total, count }]) => ({
            name,
            total: Math.round(total * 100) / 100,
            count,
        }));

        return ok({ providers });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
