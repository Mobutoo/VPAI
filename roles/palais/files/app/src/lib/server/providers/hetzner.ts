import { env } from '$env/dynamic/private';

const BASE_URL = 'https://api.hetzner.cloud/v1';

interface HetznerServer {
    id: number;
    name: string;
    status: string;
    public_net: {
        ipv4: { ip: string };
        ipv6: { ip: string };
    };
    server_type: {
        name: string;
        description: string;
        cores: number;
        memory: number;
        disk: number;
    };
    datacenter: {
        name: string;
        location: { name: string; city: string; country: string };
    };
    created: string;
    labels: Record<string, string>;
}

interface HetznerMetrics {
    metrics: {
        time_series: Record<string, { values: [number, string][] }>;
    };
}

interface HetznerVolume {
    id: number;
    name: string;
    size: number;
    status: string;
    server: number | null;
    location: { name: string };
    created: string;
}

async function hetznerFetch<T>(path: string, options?: RequestInit & { token?: string }): Promise<T> {
    const token = options?.token || env.HETZNER_API_TOKENS?.split(',')[0] || env.HETZNER_API_TOKEN;
    if (!token) throw new Error('HETZNER_API_TOKENS not configured');

    const res = await fetch(`${BASE_URL}${path}`, {
        ...options,
        headers: {
            'Authorization': `Bearer ${token.trim()}`,
            'Content-Type': 'application/json',
            ...options?.headers,
        },
    });

    if (!res.ok) {
        const body = await res.text();
        throw new Error(`Hetzner API error ${res.status}: ${body}`);
    }

    return res.json();
}

/** Get all configured Hetzner API tokens (comma-separated env var) */
export function getTokens(): string[] {
    const raw = env.HETZNER_API_TOKENS || env.HETZNER_API_TOKEN || '';
    return raw.split(',').map(t => t.trim()).filter(Boolean);
}

export async function listServers(token?: string): Promise<HetznerServer[]> {
    const data = await hetznerFetch<{ servers: HetznerServer[] }>('/servers', { token });
    return data.servers;
}

/** List servers from ALL configured projects */
export async function listAllServers(): Promise<HetznerServer[]> {
    const tokens = getTokens();
    const results: HetznerServer[] = [];

    for (const token of tokens) {
        const projectServers = await listServers(token);
        results.push(...projectServers);
    }

    return results;
}

export async function getServer(id: number): Promise<HetznerServer> {
    const data = await hetznerFetch<{ server: HetznerServer }>(`/servers/${id}`);
    return data.server;
}

export async function getServerMetrics(
    id: number,
    type: 'cpu' | 'disk' | 'network',
    start: Date,
    end: Date
): Promise<HetznerMetrics> {
    const params = new URLSearchParams({
        type,
        start: start.toISOString(),
        end: end.toISOString(),
    });
    return hetznerFetch<HetznerMetrics>(`/servers/${id}/metrics?${params}`);
}

export async function createServer(opts: {
    name: string;
    server_type: string;
    location: string;
    image: string;
    ssh_keys: string[];
    labels?: Record<string, string>;
}): Promise<{ server: HetznerServer; root_password: string | null }> {
    return hetznerFetch('/servers', {
        method: 'POST',
        body: JSON.stringify(opts),
    });
}

export async function deleteServer(id: number): Promise<void> {
    await hetznerFetch(`/servers/${id}`, { method: 'DELETE' });
}

export async function listVolumes(): Promise<HetznerVolume[]> {
    const data = await hetznerFetch<{ volumes: HetznerVolume[] }>('/volumes');
    return data.volumes;
}

export async function getUpcomingInvoice(): Promise<{ amount: number; currency: string }> {
    // Hetzner doesn't have an "upcoming invoice" endpoint directly
    // Use the pricing endpoint + server list to estimate
    const servers = await listAllServers();
    // CX22 = €5.39/mo, CX11 = €3.49/mo, etc — approximate from server_type
    const pricing: Record<string, number> = {
        cx22: 5.39, cx23: 5.39, cx11: 3.49, cx21: 4.49, cx31: 8.49, cx41: 15.49, cx51: 28.49,
        cpx11: 3.85, cpx21: 6.49, cpx31: 11.49, cpx41: 20.49, cpx51: 37.49,
    };
    const total = servers.reduce((sum, s) => sum + (pricing[s.server_type.name] ?? 5.0), 0);
    return { amount: total, currency: 'EUR' };
}

export type { HetznerServer, HetznerMetrics, HetznerVolume };
