import { db } from '$lib/server/db';
import { domains } from '$lib/server/db/schema';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
    try {
        const rows = await db
            .select()
            .from(domains)
            .orderBy(domains.name);

        return ok(rows);
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
