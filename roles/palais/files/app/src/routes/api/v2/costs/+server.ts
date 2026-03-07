import { getCostSummary } from '$lib/server/costs/aggregator';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ url }) => {
    try {
        const budgetParam = Number(url.searchParams.get('budget') ?? '60');
        const budget = Number.isFinite(budgetParam) && budgetParam > 0 ? budgetParam : 60;
        const summary = await getCostSummary(budget);
        return ok(summary);
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
