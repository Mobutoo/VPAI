import type { RequestHandler } from "./$types";
import { db } from "$lib/server/db";
import { serverMetrics } from "$lib/server/db/schema";
import { eq, desc, gte, and } from "drizzle-orm";
import { ok, err } from "$lib/server/api/response";

function parseCutoff(range: string): Date {
    const now = new Date();
    if (range === "7d") {
        return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    }
    // Default: 24h
    return new Date(now.getTime() - 24 * 60 * 60 * 1000);
}

export const GET: RequestHandler = async ({ params, url }) => {
    try {
        const id = Number(params.id);
        if (!Number.isInteger(id) || id <= 0) {
            return err("Invalid server ID", 400);
        }

        const range = url.searchParams.get("range") ?? "24h";
        const cutoff = parseCutoff(range);

        const metrics = await db
            .select()
            .from(serverMetrics)
            .where(
                and(
                    eq(serverMetrics.serverId, id),
                    gte(serverMetrics.recordedAt, cutoff)
                )
            )
            .orderBy(serverMetrics.recordedAt);

        return ok(metrics);
    } catch (e) {
        return err(e instanceof Error ? e.message : "Unknown error");
    }
};
