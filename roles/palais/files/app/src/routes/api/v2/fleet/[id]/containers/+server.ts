import type { RequestHandler } from "./$types";
import { db } from "$lib/server/db";
import { servers } from "$lib/server/db/schema";
import { eq } from "drizzle-orm";
import { ok, err } from "$lib/server/api/response";
import * as dockerRemote from "$lib/server/providers/docker-remote";

export const GET: RequestHandler = async ({ params }) => {
    try {
        const id = Number(params.id);
        if (!Number.isInteger(id) || id <= 0) {
            return err("Invalid server ID", 400);
        }

        const [server] = await db
            .select({ slug: servers.slug })
            .from(servers)
            .where(eq(servers.id, id));

        if (!server) {
            return err("Server not found", 404);
        }

        const containers = await dockerRemote.listContainers(server.slug);
        return ok(containers);
    } catch (e) {
        return err(e instanceof Error ? e.message : "Unknown error");
    }
};
