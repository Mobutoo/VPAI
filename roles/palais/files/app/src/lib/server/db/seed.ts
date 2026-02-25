import { env } from '$env/dynamic/private';
import { db } from './index';
import { nodes } from './schema';

/**
 * Seed the 3 infrastructure nodes.
 * Idempotent — ON CONFLICT DO UPDATE to refresh IPs and descriptions.
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
			name: 'rpi5',
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
}

