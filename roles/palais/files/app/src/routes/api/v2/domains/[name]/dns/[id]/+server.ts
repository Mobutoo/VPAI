import { db } from '$lib/server/db';
import { domains, dnsRecords } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import * as namecheap from '$lib/server/providers/namecheap';
import type { RequestHandler } from './$types';

export const PATCH: RequestHandler = async ({ params, request }) => {
    try {
        const recordId = parseInt(params.id, 10);
        if (isNaN(recordId)) {
            return err('Invalid record ID', 400);
        }

        const body = await request.json() as {
            value?: string;
            ttl?: number;
            mxPref?: number;
        };

        if (body.value === undefined && body.ttl === undefined && body.mxPref === undefined) {
            return err('At least one of value, ttl or mxPref must be provided', 400);
        }

        const [record] = await db
            .select()
            .from(dnsRecords)
            .where(eq(dnsRecords.id, recordId));

        if (!record) {
            return err('DNS record not found', 404);
        }

        const [domain] = await db
            .select()
            .from(domains)
            .where(eq(domains.name, params.name));

        if (!domain) {
            return err('Domain not found', 404);
        }

        const namecheapUpdates: { address?: string; ttl?: number; mxPref?: number } = {};
        if (body.value !== undefined) namecheapUpdates.address = body.value;
        if (body.ttl !== undefined) namecheapUpdates.ttl = body.ttl;
        if (body.mxPref !== undefined) namecheapUpdates.mxPref = body.mxPref;

        await namecheap.updateDnsRecord(
            params.name,
            record.host,
            record.recordType,
            namecheapUpdates
        );

        const dbUpdates: { value?: string; ttl?: number; mxPref?: number; updatedAt: Date } = {
            updatedAt: new Date(),
        };
        if (body.value !== undefined) dbUpdates.value = body.value;
        if (body.ttl !== undefined) dbUpdates.ttl = body.ttl;
        if (body.mxPref !== undefined) dbUpdates.mxPref = body.mxPref;

        const [updated] = await db
            .update(dnsRecords)
            .set(dbUpdates)
            .where(eq(dnsRecords.id, recordId))
            .returning();

        return ok(updated);
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};

export const DELETE: RequestHandler = async ({ params }) => {
    try {
        const recordId = parseInt(params.id, 10);
        if (isNaN(recordId)) {
            return err('Invalid record ID', 400);
        }

        const [record] = await db
            .select()
            .from(dnsRecords)
            .where(eq(dnsRecords.id, recordId));

        if (!record) {
            return err('DNS record not found', 404);
        }

        await namecheap.removeDnsRecord(params.name, record.host, record.recordType);

        await db
            .delete(dnsRecords)
            .where(eq(dnsRecords.id, recordId));

        return ok({ deleted: true });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
