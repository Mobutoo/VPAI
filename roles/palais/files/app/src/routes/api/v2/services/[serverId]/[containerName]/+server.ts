import { db } from '$lib/server/db';
import { servers } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import * as dockerRemote from '$lib/server/providers/docker-remote';
import type { RequestHandler } from './$types';

const ALLOWED_ACTIONS = ['start', 'stop', 'restart'] as const;
type AllowedAction = typeof ALLOWED_ACTIONS[number];

async function resolveServer(serverIdParam: string) {
    const serverId = Number(serverIdParam);
    if (!Number.isInteger(serverId) || serverId <= 0) {
        return { server: null, validationError: 'Invalid serverId' };
    }

    const [server] = await db
        .select()
        .from(servers)
        .where(eq(servers.id, serverId));

    if (!server) {
        return { server: null, validationError: 'Server not found' };
    }

    return { server, validationError: null };
}

export const GET: RequestHandler = async ({ params }) => {
    try {
        const { server, validationError } = await resolveServer(params.serverId);
        if (validationError || !server) {
            return err(validationError ?? 'Server not found', server === null ? 404 : 400);
        }

        const stats = await dockerRemote.getContainerStats(server.slug);
        const containerStats = stats.find((s) => s.name === params.containerName);

        if (!containerStats) {
            return err(`Container '${params.containerName}' not found or not running`, 404);
        }

        return ok(containerStats);
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};

export const POST: RequestHandler = async ({ params, request }) => {
    try {
        const body = await request.json() as { action?: string };
        const { action } = body;

        if (!action) {
            return err('action is required in request body', 400);
        }

        if (!(ALLOWED_ACTIONS as readonly string[]).includes(action)) {
            return err(`Invalid action '${action}'. Allowed: ${ALLOWED_ACTIONS.join(', ')}`, 400);
        }

        const { server, validationError } = await resolveServer(params.serverId);
        if (validationError || !server) {
            return err(validationError ?? 'Server not found', server === null ? 404 : 400);
        }

        const result = await dockerRemote.controlContainer(
            server.slug,
            params.containerName,
            action as AllowedAction
        );

        return ok({ result });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
