import { env } from '$env/dynamic/private';
import { db } from './index';
import { nodes, servers } from './schema';

/**
 * Seed the 3 infrastructure nodes (legacy table) + servers table.
 * Idempotent — ON CONFLICT DO UPDATE to refresh IPs, descriptions, provider/role.
 * Called once at startup from hooks.server.ts.
 */
export async function seedNodes(): Promise<void> {
	const nodesSeed = [
		{
			name: 'sese-ai',
			tailscaleIp: env.SESE_AI_TAILSCALE_IP || null,
			localIp: env.SESE_AI_LOCAL_IP || null,
			description: 'OVH VPS 8 Go — Cerveau IA (OpenClaw, LiteLLM, n8n)'
		},
		{
			name: 'waza',
			tailscaleIp: env.WORKSTATION_PI_TAILSCALE_IP || null,
			localIp: env.WORKSTATION_PI_LOCAL_IP || null,
			description: 'Raspberry Pi 5 16 Go — Mission Control (Claude Code)'
		},
		{
			name: 'seko-vpn',
			tailscaleIp: env.SEKO_VPN_TAILSCALE_IP || null,
			localIp: env.SEKO_VPN_LOCAL_IP || null,
			description: 'Ionos VPS — Hub VPN Singa (Headscale) + Backup'
		}
	];

	for (const node of nodesSeed) {
		await db
			.insert(nodes)
			.values(node)
			.onConflictDoUpdate({
				target: nodes.name,
				set: {
					tailscaleIp: node.tailscaleIp,
					localIp: node.localIp,
					description: node.description
				}
			});
	}

	// Seed the v2 servers table with correct provider/role per server
	const serversSeed: {
		name: string;
		slug: string;
		provider: 'ovh' | 'ionos' | 'local' | 'hetzner';
		serverRole: 'ai_brain' | 'vpn_hub' | 'workstation' | 'app_prod' | 'storage';
		tailscaleIp: string | null;
		publicIp: string | null;
		sshPort: number;
		sshUser: string;
		location: string | null;
		os: string | null;
		cpuCores: number | null;
		ramMb: number | null;
		diskGb: number | null;
	}[] = [
		{
			name: 'sese-ai',
			slug: 'sese-ai',
			provider: 'ovh',
			serverRole: 'ai_brain',
			tailscaleIp: env.SESE_AI_TAILSCALE_IP || null,
			publicIp: env.SESE_AI_LOCAL_IP || null,
			sshPort: 804,
			sshUser: 'mobuone',
			location: 'GRA (France)',
			os: 'Debian 13',
			cpuCores: 4,
			ramMb: 8192,
			diskGb: 80
		},
		{
			name: 'waza',
			slug: 'waza',
			provider: 'local',
			serverRole: 'workstation',
			tailscaleIp: env.WORKSTATION_PI_TAILSCALE_IP || null,
			publicIp: env.WORKSTATION_PI_LOCAL_IP || null,
			sshPort: 22,
			sshUser: 'mobuone',
			location: 'Local (Paris)',
			os: 'Raspberry Pi OS',
			cpuCores: 4,
			ramMb: 16384,
			diskGb: 256
		},
		{
			name: 'seko-vpn',
			slug: 'seko-vpn',
			provider: 'ionos',
			serverRole: 'vpn_hub',
			tailscaleIp: env.SEKO_VPN_TAILSCALE_IP || null,
			publicIp: env.SEKO_VPN_LOCAL_IP || null,
			sshPort: 804,
			sshUser: 'mobuone',
			location: 'DE (Germany)',
			os: 'Debian 12',
			cpuCores: 1,
			ramMb: 1024,
			diskGb: 10
		}
	];

	for (const srv of serversSeed) {
		await db
			.insert(servers)
			.values(srv)
			.onConflictDoUpdate({
				target: servers.slug,
				set: {
					provider: srv.provider,
					serverRole: srv.serverRole,
					tailscaleIp: srv.tailscaleIp,
					publicIp: srv.publicIp,
					sshPort: srv.sshPort,
					sshUser: srv.sshUser,
					location: srv.location,
					os: srv.os,
					cpuCores: srv.cpuCores,
					ramMb: srv.ramMb,
					diskGb: srv.diskGb,
					updatedAt: new Date()
				}
			});
	}
}

