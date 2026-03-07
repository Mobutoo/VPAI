import type { RequestHandler } from "./$types";
import { db } from "$lib/server/db";
import { servers, serverMetrics } from "$lib/server/db/schema";
import { eq } from "drizzle-orm";
import { ok, err } from "$lib/server/api/response";
import * as dockerRemote from "$lib/server/providers/docker-remote";
import * as hetzner from "$lib/server/providers/hetzner";
import * as ovh from "$lib/server/providers/ovh";
import { env } from "$env/dynamic/private";

/** Sync fleet: discover Hetzner + OVH servers, collect Docker metrics */
export const POST: RequestHandler = async () => {
    try {
        const imported: string[] = [];
        const errors: { source: string; slug: string; error: string }[] = [];

        // ── Phase 1a: Import servers from Hetzner API (all projects) ─────
        const hetznerTokens = hetzner.getTokens();
        if (hetznerTokens.length > 0) {
            try {
                const hetznerServers = await hetzner.listAllServers();

                for (const hs of hetznerServers) {
                    const slug = hs.name.toLowerCase().replace(/[^a-z0-9]/g, '-');
                    const loc = hs.datacenter?.location;

                    try {
                        await db
                            .insert(servers)
                            .values({
                                name: hs.name,
                                slug,
                                provider: 'hetzner',
                                serverRole: 'app_prod',
                                location: loc ? `${loc.city} (${loc.country})` : null,
                                publicIp: hs.public_net?.ipv4?.ip ?? null,
                                status: hs.status === 'running' ? 'online' : 'offline',
                                cpuCores: hs.server_type?.cores ?? null,
                                ramMb: hs.server_type?.memory ? hs.server_type.memory * 1024 : null,
                                diskGb: hs.server_type?.disk ?? null,
                                os: hs.server_type?.description ?? null,
                                sshPort: 22,
                                sshUser: 'root',
                                metadata: {
                                    hetzner_id: hs.id,
                                    server_type: hs.server_type?.name,
                                    labels: hs.labels,
                                    datacenter: hs.datacenter?.name
                                },
                                updatedAt: new Date()
                            })
                            .onConflictDoUpdate({
                                target: servers.slug,
                                set: {
                                    publicIp: hs.public_net?.ipv4?.ip ?? null,
                                    status: hs.status === 'running' ? 'online' : 'offline',
                                    cpuCores: hs.server_type?.cores ?? null,
                                    ramMb: hs.server_type?.memory ? hs.server_type.memory * 1024 : null,
                                    diskGb: hs.server_type?.disk ?? null,
                                    metadata: {
                                        hetzner_id: hs.id,
                                        server_type: hs.server_type?.name,
                                        labels: hs.labels,
                                        datacenter: hs.datacenter?.name
                                    },
                                    updatedAt: new Date()
                                }
                            });

                        imported.push(slug);
                    } catch (e) {
                        errors.push({
                            source: 'hetzner',
                            slug,
                            error: e instanceof Error ? e.message : 'Unknown error'
                        });
                    }
                }
            } catch (e) {
                errors.push({
                    source: 'hetzner',
                    slug: '*',
                    error: e instanceof Error ? e.message : 'Hetzner API error'
                });
            }
        }

        // ── Phase 1b: Import VPS from OVH API ───────────────────────────
        if (env.OVH_APPLICATION_KEY && env.OVH_APPLICATION_SECRET && env.OVH_CONSUMER_KEY) {
            try {
                const vpsNames = await ovh.listVps();

                for (const vpsName of vpsNames) {
                    try {
                        const status = await ovh.getVpsStatus(vpsName);
                        const slug = vpsName.toLowerCase().replace(/[^a-z0-9]/g, '-');

                        // Skip stopped/inactive VPS (avoid re-importing decommissioned servers)
                        if (status.state !== 'running') {
                            continue;
                        }

                        await db
                            .insert(servers)
                            .values({
                                name: status.name || vpsName,
                                slug,
                                provider: 'ovh',
                                serverRole: 'app_prod',
                                location: status.zone ?? null,
                                status: status.state === 'running' ? 'online' : 'offline',
                                cpuCores: status.model?.vcore ?? null,
                                ramMb: status.model?.memory ? status.model.memory * 1024 : null,
                                diskGb: status.model?.disk ?? null,
                                os: status.model?.name ?? null,
                                sshPort: 22,
                                sshUser: 'root',
                                metadata: {
                                    ovh_service: vpsName,
                                    model: status.model?.name
                                },
                                updatedAt: new Date()
                            })
                            .onConflictDoUpdate({
                                target: servers.slug,
                                set: {
                                    status: status.state === 'running' ? 'online' : 'offline',
                                    cpuCores: status.model?.vcore ?? null,
                                    ramMb: status.model?.memory ? status.model.memory * 1024 : null,
                                    diskGb: status.model?.disk ?? null,
                                    os: status.model?.name ?? null,
                                    metadata: {
                                        ovh_service: vpsName,
                                        model: status.model?.name
                                    },
                                    updatedAt: new Date()
                                }
                            });

                        imported.push(slug);
                    } catch (e) {
                        errors.push({
                            source: 'ovh',
                            slug: vpsName,
                            error: e instanceof Error ? e.message : 'Unknown error'
                        });
                    }
                }
            } catch (e) {
                errors.push({
                    source: 'ovh',
                    slug: '*',
                    error: e instanceof Error ? e.message : 'OVH API error'
                });
            }
        }

        // ── Phase 2: Sync Docker metrics for configured servers ───────────
        const configuredSlugs = new Set(dockerRemote.getConfiguredServers());
        const allServers = await db.select().from(servers);
        const syncableServers = allServers.filter((s) => configuredSlugs.has(s.slug));

        let metricsSynced = 0;

        await Promise.all(
            syncableServers.map(async (server) => {
                try {
                    const stats = await dockerRemote.getSystemStats(server.slug);

                    await db.insert(serverMetrics).values({
                        serverId: server.id,
                        cpuPercent: stats.cpuPercent,
                        ramUsedMb: stats.ramUsedMb,
                        ramTotalMb: stats.ramTotalMb,
                        diskUsedGb: stats.diskUsedGb,
                        diskTotalGb: stats.diskTotalGb,
                        loadAvg1m: stats.loadAvg1m,
                        recordedAt: new Date(),
                    });

                    await db
                        .update(servers)
                        .set({ status: 'online', updatedAt: new Date() })
                        .where(eq(servers.id, server.id));

                    metricsSynced++;
                } catch (e) {
                    errors.push({
                        source: 'docker',
                        slug: server.slug,
                        error: e instanceof Error ? e.message : "Unknown error",
                    });
                }
            })
        );

        return ok({
            imported: imported.length,
            metricsSynced,
            total: allServers.length,
            errors
        });
    } catch (e) {
        return err(e instanceof Error ? e.message : "Unknown error");
    }
};
