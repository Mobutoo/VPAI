import type { RequestHandler } from "./$types";
import { db } from "$lib/server/db";
import { servers, serverMetrics } from "$lib/server/db/schema";
import { eq, desc } from "drizzle-orm";
import { ok, err } from "$lib/server/api/response";

export const GET: RequestHandler = async () => {
    try {
        const allServers = await db.select().from(servers).orderBy(servers.name);

        const result = await Promise.all(
            allServers.map(async (server) => {
                const [latestMetric] = await db
                    .select()
                    .from(serverMetrics)
                    .where(eq(serverMetrics.serverId, server.id))
                    .orderBy(desc(serverMetrics.recordedAt))
                    .limit(1);

                return {
                    ...server,
                    latestMetric: latestMetric ?? null,
                };
            })
        );

        return ok(result);
    } catch (e) {
        return err(e instanceof Error ? e.message : "Unknown error");
    }
};
