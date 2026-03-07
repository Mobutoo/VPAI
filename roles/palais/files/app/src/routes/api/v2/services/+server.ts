import { db } from '$lib/server/db';
import { servers } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import * as dockerRemote from '$lib/server/providers/docker-remote';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ url }) => {
    try {
        const serverIdParam = url.searchParams.get('serverId');
        if (!serverIdParam) {
            return err('serverId query parameter is required', 400);
        }

        const serverId = Number(serverIdParam);
        if (!Number.isInteger(serverId) || serverId <= 0) {
            return err('Invalid serverId', 400);
        }

        const [server] = await db
            .select()
            .from(servers)
            .where(eq(servers.id, serverId));

        if (!server) {
            return err('Server not found', 404);
        }

        const [containers, stats] = await Promise.all([
            dockerRemote.listContainers(server.slug),
            dockerRemote.getContainerStats(server.slug),
        ]);

        const statsByName = new Map(stats.map((s) => [s.name, s]));

        const result = containers.map((c) => ({
            ...c,
            stats: statsByName.get(c.name) ?? null,
        }));

        return ok(result);
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
