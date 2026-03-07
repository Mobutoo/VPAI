import type { RequestHandler } from "./$types";
import { db } from "$lib/server/db";
import { servers, serverMetrics } from "$lib/server/db/schema";
import { eq } from "drizzle-orm";
import { ok, err } from "$lib/server/api/response";
import * as dockerRemote from "$lib/server/providers/docker-remote";

export const POST: RequestHandler = async () => {
    try {
        const configuredSlugs = new Set(dockerRemote.getConfiguredServers());

        const allServers = await db.select().from(servers);
        const syncableServers = allServers.filter((s) => configuredSlugs.has(s.slug));

        let synced = 0;
        const errors: { serverId: number; slug: string; error: string }[] = [];

        await Promise.all(
            syncableServers.map(async (server) => {
                try {
                    const stats = await dockerRemote.getSystemStats(server.slug);

                    await db.insert(serverMetrics).values({
                        serverId: server.id,
                        cpuPercent: stats.cpuPercent,
                        ramUsedMb: stats.ramUsedMb,
                        ramTotalMb: stats.ramTotalMb,
                        diskUsedGb: stats.diskUsedGb,
                        diskTotalGb: stats.diskTotalGb,
                        loadAvg1m: stats.loadAvg1m,
                        recordedAt: new Date(),
                    });

                    await db
                        .update(servers)
                        .set({ updatedAt: new Date() })
                        .where(eq(servers.id, server.id));

                    synced++;
                } catch (e) {
                    errors.push({
                        serverId: server.id,
                        slug: server.slug,
                        error: e instanceof Error ? e.message : "Unknown error",
                    });
                }
            })
        );

        return ok({ synced, total: syncableServers.length, errors });
    } catch (e) {
        return err(e instanceof Error ? e.message : "Unknown error");
    }
};
