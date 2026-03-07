import { db } from '$lib/server/db';
import { domains, dnsRecords } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import * as namecheap from '$lib/server/providers/namecheap';
import * as ovh from '$lib/server/providers/ovh';
import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

/** Sync domains + DNS records from Namecheap and OVH */
export const POST: RequestHandler = async () => {
    try {
        let synced = 0;
        const errors: { source: string; domain: string; error: string }[] = [];

        // ── Namecheap domains ─────────────────────────────────────────
        if (env.NAMECHEAP_API_KEY && env.NAMECHEAP_API_USER) {
            try {
                const remoteDomains = await namecheap.getDomains();

                for (const domain of remoteDomains) {
                    try {
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
                                    registrar: 'namecheap',
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

                        synced++;
                    } catch (e) {
                        errors.push({
                            source: 'namecheap',
                            domain: domain.name,
                            error: e instanceof Error ? e.message : 'Unknown error'
                        });
                    }
                }
            } catch (e) {
                errors.push({
                    source: 'namecheap',
                    domain: '*',
                    error: e instanceof Error ? e.message : 'Namecheap API error'
                });
            }
        }

        // ── OVH domains ──────────────────────────────────────────────
        if (env.OVH_APPLICATION_KEY && env.OVH_APPLICATION_SECRET && env.OVH_CONSUMER_KEY) {
            try {
                const ovhDomainNames = await ovh.listDomains();

                for (const domainName of ovhDomainNames) {
                    try {
                        let expiryDate: Date | null = null;
                        let autoRenew = true;

                        try {
                            const svcInfo = await ovh.getDomainServiceInfo(domainName);
                            expiryDate = svcInfo.expiration ? new Date(svcInfo.expiration) : null;
                            autoRenew = svcInfo.renew?.automatic ?? true;
                        } catch {
                            // Service info may not be available for all domains
                        }

                        const [upserted] = await db
                            .insert(domains)
                            .values({
                                name: domainName,
                                registrar: 'ovh',
                                apiProvider: 'ovh',
                                expiryDate: expiryDate ?? undefined,
                                autoRenew,
                                updatedAt: new Date(),
                            })
                            .onConflictDoUpdate({
                                target: domains.name,
                                set: {
                                    registrar: 'ovh',
                                    expiryDate: expiryDate ?? undefined,
                                    autoRenew,
                                    updatedAt: new Date(),
                                },
                            })
                            .returning();

                        // Sync DNS records from OVH zone
                        try {
                            const ovhRecords = await ovh.getDomainDnsRecords(domainName);

                            await db
                                .delete(dnsRecords)
                                .where(eq(dnsRecords.domainId, upserted.id));

                            if (ovhRecords.length > 0) {
                                await db.insert(dnsRecords).values(
                                    ovhRecords.map(r => ({
                                        domainId: upserted.id,
                                        recordType: r.fieldType,
                                        host: r.subDomain || '@',
                                        value: r.target,
                                        ttl: r.ttl,
                                        mxPref: r.fieldType === 'MX' ? 10 : null,
                                    }))
                                );
                            }
                        } catch {
                            // DNS zone may not exist for all domains
                        }

                        synced++;
                    } catch (e) {
                        errors.push({
                            source: 'ovh',
                            domain: domainName,
                            error: e instanceof Error ? e.message : 'Unknown error'
                        });
                    }
                }
            } catch (e) {
                errors.push({
                    source: 'ovh',
                    domain: '*',
                    error: e instanceof Error ? e.message : 'OVH API error'
                });
            }
        }

        return ok({ synced, errors });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
