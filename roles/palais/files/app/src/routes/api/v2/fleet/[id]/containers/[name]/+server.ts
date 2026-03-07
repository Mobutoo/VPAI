import type { RequestHandler } from "./$types";
import { db } from "$lib/server/db";
import { servers } from "$lib/server/db/schema";
import { eq } from "drizzle-orm";
import { ok, err } from "$lib/server/api/response";
import * as dockerRemote from "$lib/server/providers/docker-remote";

const ALLOWED_ACTIONS = ["start", "stop", "restart"] as const;
type AllowedAction = typeof ALLOWED_ACTIONS[number];

function isAllowedAction(value: unknown): value is AllowedAction {
    return typeof value === "string" && (ALLOWED_ACTIONS as readonly string[]).includes(value);
}

export const POST: RequestHandler = async ({ params, request }) => {
    try {
        const id = Number(params.id);
        if (!Number.isInteger(id) || id <= 0) {
            return err("Invalid server ID", 400);
        }

        const body = await request.json() as { action?: unknown };
        const { action } = body;

        if (!isAllowedAction(action)) {
            return err(
                `Invalid action. Allowed actions: ${ALLOWED_ACTIONS.join(", ")}`,
                400
            );
        }

        const [server] = await db
            .select({ slug: servers.slug })
            .from(servers)
            .where(eq(servers.id, id));

        if (!server) {
            return err("Server not found", 404);
        }

        const output = await dockerRemote.controlContainer(server.slug, params.name, action);
        return ok({ action, container: params.name, output });
    } catch (e) {
        return err(e instanceof Error ? e.message : "Unknown error");
    }
};
