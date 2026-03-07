import { db } from '$lib/server/db';
import { domains, dnsRecords } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import * as namecheap from '$lib/server/providers/namecheap';
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

        return ok(records);
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};

export const POST: RequestHandler = async ({ params, request }) => {
    try {
        const body = await request.json() as {
            recordType: string;
            host: string;
            value: string;
            ttl?: number;
            mxPref?: number;
        };

        if (!body.recordType || !body.host || !body.value) {
            return err('recordType, host and value are required', 400);
        }

        const [domain] = await db
            .select()
            .from(domains)
            .where(eq(domains.name, params.name));

        if (!domain) {
            return err('Domain not found', 404);
        }

        await namecheap.addDnsRecord(params.name, {
            hostName: body.host,
            recordType: body.recordType,
            address: body.value,
            ttl: body.ttl ?? 1800,
            mxPref: body.mxPref,
        });

        const [inserted] = await db
            .insert(dnsRecords)
            .values({
                domainId: domain.id,
                recordType: body.recordType,
                host: body.host,
                value: body.value,
                ttl: body.ttl ?? 1800,
                mxPref: body.mxPref ?? null,
            })
            .returning();

        return ok(inserted);
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
