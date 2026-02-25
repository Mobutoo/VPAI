import { env } from '$env/dynamic/private';

export interface VPNNode {
	name: string;
	ip: string | null;
	online: boolean;
	lastSeen: string | null;
}

export async function fetchVPNTopology(): Promise<VPNNode[]> {
	const url = env.HEADSCALE_URL;
	const apiKey = env.HEADSCALE_API_KEY;

	if (!url || !apiKey) {
		console.warn('[headscale] HEADSCALE_URL or HEADSCALE_API_KEY not configured');
		return [];
	}

	try {
		const res = await fetch(`${url}/api/v1/machine`, {
			headers: { Authorization: `Bearer ${apiKey}` },
			signal: AbortSignal.timeout(5000)
		});

		if (!res.ok) {
			console.error(`[headscale] API error: ${res.status} ${res.statusText}`);
			return [];
		}

		const data = await res.json();
		const machines: unknown[] = data.machines ?? [];

		return machines.map((m: any) => ({
			name: m.givenName ?? m.name ?? 'unknown',
			ip: m.ipAddresses?.[0] ?? null,
			online: Boolean(m.online),
			lastSeen: m.lastSeen ?? null
		}));
	} catch (err) {
		console.error('[headscale] fetch failed:', err);
		return [];
	}
}
