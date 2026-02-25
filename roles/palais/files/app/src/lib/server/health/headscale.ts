import { env } from '$env/dynamic/private';

interface HeadscaleMachine {
	givenName?: string;
	name?: string;
	ipAddresses?: string[];
	online?: boolean;
	lastSeen?: string | null;
}

export interface VPNNode {
	name: string;
	ip: string | null;
	online: boolean;
	lastSeen: string | null;
}

export interface VPNTopologyResult {
	nodes: VPNNode[];
	error: boolean;
}

export async function fetchVPNTopology(): Promise<VPNTopologyResult> {
	const url = env.HEADSCALE_URL;
	const apiKey = env.HEADSCALE_API_KEY;

	if (!url || !apiKey) {
		console.warn('[headscale] HEADSCALE_URL or HEADSCALE_API_KEY not configured');
		return { nodes: [], error: false };
	}

	try {
		const res = await fetch(`${url}/api/v1/machine`, {
			headers: { Authorization: `Bearer ${apiKey}` },
			signal: AbortSignal.timeout(5000)
		});

		if (!res.ok) {
			console.error(`[headscale] API error: ${res.status} ${res.statusText}`);
			return { nodes: [], error: true };
		}

		const data = await res.json();
		const machines: HeadscaleMachine[] = Array.isArray(data.machines) ? data.machines : [];

		return {
			nodes: machines.map((m) => ({
				name: m.givenName ?? m.name ?? 'unknown',
				ip: m.ipAddresses?.[0] ?? null,
				online: Boolean(m.online),
				lastSeen: m.lastSeen ?? null
			})),
			error: false
		};
	} catch (err) {
		console.error('[headscale] fetch failed:', err);
		return { nodes: [], error: true };
	}
}
