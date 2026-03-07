import { db } from '$lib/server/db';
import { costEntries } from '$lib/server/db/schema';
import { desc } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import { recordCost } from '$lib/server/costs/aggregator';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ url }) => {
    try {
        const limitParam = Number(url.searchParams.get('limit') ?? '50');
        const limit = Number.isFinite(limitParam) && limitParam > 0 ? Math.floor(limitParam) : 50;

        const entries = await db
            .select()
            .from(costEntries)
            .orderBy(desc(costEntries.recordedAt))
            .limit(limit);

        return ok(entries);
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};

export const POST: RequestHandler = async ({ request }) => {
    try {
        const body = await request.json();

        const { provider, category, amountEur, periodStart, periodEnd, workspaceId, description, rawData } = body;

        if (!provider || typeof provider !== 'string') {
            return err('Missing or invalid field: provider', 400);
        }
        if (!category || typeof category !== 'string') {
            return err('Missing or invalid field: category', 400);
        }
        if (amountEur === undefined || amountEur === null || typeof amountEur !== 'number') {
            return err('Missing or invalid field: amountEur', 400);
        }
        if (!periodStart) {
            return err('Missing required field: periodStart', 400);
        }
        if (!periodEnd) {
            return err('Missing required field: periodEnd', 400);
        }

        const start = new Date(periodStart);
        const end = new Date(periodEnd);

        if (isNaN(start.getTime())) {
            return err('Invalid date: periodStart', 400);
        }
        if (isNaN(end.getTime())) {
            return err('Invalid date: periodEnd', 400);
        }

        await recordCost(
            provider,
            category,
            amountEur,
            start,
            end,
            workspaceId !== undefined ? Number(workspaceId) : undefined,
            description ?? undefined,
            rawData ?? undefined
        );

        return ok({ created: true });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
