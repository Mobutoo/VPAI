import type { RequestHandler } from "./$types";
import { db } from "$lib/server/db";
import { servers } from "$lib/server/db/schema";
import { eq } from "drizzle-orm";
import { ok, err } from "$lib/server/api/response";
import * as dockerRemote from "$lib/server/providers/docker-remote";

const DEFAULT_TAIL = 100;
const MAX_TAIL = 5000;

export const GET: RequestHandler = async ({ params, url }) => {
    try {
        const id = Number(params.id);
        if (!Number.isInteger(id) || id <= 0) {
            return err("Invalid server ID", 400);
        }

        const tailParam = url.searchParams.get("tail");
        let tail = DEFAULT_TAIL;
        if (tailParam !== null) {
            const parsed = parseInt(tailParam, 10);
            if (Number.isNaN(parsed) || parsed <= 0) {
                return err("Invalid tail parameter: must be a positive integer", 400);
            }
            tail = Math.min(parsed, MAX_TAIL);
        }

        const [server] = await db
            .select({ slug: servers.slug })
            .from(servers)
            .where(eq(servers.id, id));

        if (!server) {
            return err("Server not found", 404);
        }

        const logs = await dockerRemote.getContainerLogs(server.slug, params.name, tail);
        return ok({ container: params.name, tail, logs });
    } catch (e) {
        return err(e instanceof Error ? e.message : "Unknown error");
    }
};
