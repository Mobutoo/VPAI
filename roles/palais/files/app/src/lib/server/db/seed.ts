import { env } from '$env/dynamic/private';
import { db } from './index';
import { nodes } from './schema';

/**
 * Seed the 3 infrastructure nodes.
 * Idempotent — uses ON CONFLICT DO NOTHING.
 * Called once at startup from hooks.server.ts.
 */
export async function seedNodes(): Promise<void> {
	const nodesSeed = [
		{
			name: 'sese-ai',
			tailscaleIp: env.SESE_AI_TAILSCALE_IP || null
		},
		{
			name: 'rpi5',
			tailscaleIp: env.WORKSTATION_PI_TAILSCALE_IP || null
		},
		{
			name: 'seko-vpn',
			tailscaleIp: env.SEKO_VPN_TAILSCALE_IP || null
		}
	];

	for (const node of nodesSeed) {
		await db.insert(nodes).values(node).onConflictDoNothing();
	}
}
