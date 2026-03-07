import { db } from '$lib/server/db';
import { costEntries } from '$lib/server/db/schema';
import { gte } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
    try {
        const sevenDaysAgo = new Date();
        sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

        const entries = await db
            .select()
            .from(costEntries)
            .where(gte(costEntries.periodStart, sevenDaysAgo));

        const total = entries.reduce((sum, entry) => sum + entry.amountEur, 0);
        const dailyAvg = Math.round((total / 7) * 10000) / 10000;
        const projected30d = Math.round(dailyAvg * 30 * 100) / 100;

        return ok({ dailyAvg, projected30d, currency: 'EUR' });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
