import { db } from '$lib/server/db';
import { domains, dnsRecords } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import * as namecheap from '$lib/server/providers/namecheap';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async () => {
    try {
        const remoteDomains = await namecheap.getDomains();

        for (const domain of remoteDomains) {
            const expiryDate = domain.expires ? new Date(domain.expires) : null;

            const [upserted] = await db
                .insert(domains)
                .values({
                    name: domain.name,
                    registrar: 'namecheap',
                    apiProvider: 'namecheap',
                    expiryDate: expiryDate ?? undefined,
                    autoRenew: domain.autoRenew,
                    updatedAt: new Date(),
                })
                .onConflictDoUpdate({
                    target: domains.name,
                    set: {
                        expiryDate: expiryDate ?? undefined,
                        autoRenew: domain.autoRenew,
                        updatedAt: new Date(),
                    },
                })
                .returning();

            const remoteRecords = await namecheap.getDnsRecords(domain.name);

            await db
                .delete(dnsRecords)
                .where(eq(dnsRecords.domainId, upserted.id));

            if (remoteRecords.length > 0) {
                await db.insert(dnsRecords).values(
                    remoteRecords.map(r => ({
                        domainId: upserted.id,
                        recordType: r.recordType,
                        host: r.hostName,
                        value: r.address,
                        ttl: r.ttl,
                        mxPref: r.mxPref ?? null,
                    }))
                );
            }
        }

        return ok({ synced: remoteDomains.length });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
