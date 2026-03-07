import { db } from '$lib/server/db';
import { domains, dnsRecords } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params }) => {
    try {
        const [domain] = await db
            .select()
            .from(domains)
            .where(eq(domains.name, params.name));

        if (!domain) {
            return err('Domain not found', 404);
        }

        const records = await db
            .select()
            .from(dnsRecords)
            .where(eq(dnsRecords.domainId, domain.id))
            .orderBy(dnsRecords.recordType, dnsRecords.host);

        return ok({ ...domain, dnsRecords: records });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
