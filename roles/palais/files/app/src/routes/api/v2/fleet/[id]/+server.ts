import type { RequestHandler } from "./$types";
import { db } from "$lib/server/db";
import { servers, serverMetrics } from "$lib/server/db/schema";
import { eq, desc } from "drizzle-orm";
import { ok, err } from "$lib/server/api/response";

export const GET: RequestHandler = async ({ params }) => {
    try {
        const id = Number(params.id);
        if (!Number.isInteger(id) || id <= 0) {
            return err("Invalid server ID", 400);
        }

        const [server] = await db
            .select()
            .from(servers)
            .where(eq(servers.id, id));

        if (!server) {
            return err("Server not found", 404);
        }

        const [latestMetric] = await db
            .select()
            .from(serverMetrics)
            .where(eq(serverMetrics.serverId, id))
            .orderBy(desc(serverMetrics.recordedAt))
            .limit(1);

        return ok({ ...server, latestMetric: latestMetric ?? null });
    } catch (e) {
        return err(e instanceof Error ? e.message : "Unknown error");
    }
};

export const PATCH: RequestHandler = async ({ params, request }) => {
    try {
        const id = Number(params.id);
        if (!Number.isInteger(id) || id <= 0) {
            return err("Invalid server ID", 400);
        }

        const body = await request.json() as Record<string, unknown>;

        const set: {
            name?: string;
            location?: string;
            sshPort?: number;
            sshUser?: string;
            sshKeyPath?: string;
            metadata?: Record<string, unknown>;
        } = {};

        if (typeof body.name === 'string') set.name = body.name;
        if (typeof body.location === 'string') set.location = body.location;
        if (typeof body.sshPort === 'number') set.sshPort = body.sshPort;
        if (typeof body.sshUser === 'string') set.sshUser = body.sshUser;
        if (typeof body.sshKeyPath === 'string') set.sshKeyPath = body.sshKeyPath;
        if (body.metadata && typeof body.metadata === 'object') set.metadata = body.metadata as Record<string, unknown>;

        if (Object.keys(set).length === 0) {
            return err("No valid fields to update", 400);
        }

        const [updated] = await db
            .update(servers)
            .set({ ...set, updatedAt: new Date() })
            .where(eq(servers.id, id))
            .returning();

        if (!updated) {
            return err("Server not found", 404);
        }

        return ok(updated);
    } catch (e) {
        return err(e instanceof Error ? e.message : "Unknown error");
    }
};
