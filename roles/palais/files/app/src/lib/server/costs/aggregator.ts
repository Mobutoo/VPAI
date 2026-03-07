import { db } from '../db';
import { costEntries } from '../db/schema';
import { desc, gte } from 'drizzle-orm';

interface CostSummary {
    totalEur: number;
    budgetEur: number;
    byProvider: Record<string, number>;
    byProject: Record<string, number>;
    trend: { month: string; amount: number }[];
}

export async function getCostSummary(budgetEur: number = 60): Promise<CostSummary> {
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    const entries = await db
        .select()
        .from(costEntries)
        .where(gte(costEntries.periodStart, thirtyDaysAgo))
        .orderBy(desc(costEntries.recordedAt));

    const byProvider: Record<string, number> = {};
    const byProject: Record<string, number> = {};
    let totalEur = 0;

    for (const entry of entries) {
        totalEur += entry.amountEur;
        byProvider[entry.provider] = (byProvider[entry.provider] ?? 0) + entry.amountEur;
        if (entry.workspaceId) {
            const key = String(entry.workspaceId);
            byProject[key] = (byProject[key] ?? 0) + entry.amountEur;
        }
    }

    return {
        totalEur: Math.round(totalEur * 100) / 100,
        budgetEur,
        byProvider,
        byProject,
        trend: [], // Populated by monthly aggregation query in the API route
    };
}

export async function recordCost(
    provider: string,
    category: string,
    amountEur: number,
    periodStart: Date,
    periodEnd: Date,
    workspaceId?: number,
    description?: string,
    rawData?: Record<string, unknown>
): Promise<void> {
    await db.insert(costEntries).values({
        provider,
        category,
        amountEur,
        periodStart,
        periodEnd,
        workspaceId: workspaceId ?? null,
        description: description ?? null,
        rawData: rawData ?? {},
    });
}
