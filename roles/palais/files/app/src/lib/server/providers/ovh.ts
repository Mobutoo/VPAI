import { env } from '$env/dynamic/private';

interface OvhVpsStatus {
    name: string;
    state: string;
    model: { name: string; memory: number; vcore: number; disk: number };
    zone: string;
}

interface OvhInvoice {
    billId: string;
    date: string;
    priceWithTax: { value: number; currencyCode: string };
    url: string;
}

async function ovhFetch<T>(path: string): Promise<T> {
    const endpoint = env.OVH_ENDPOINT ?? 'https://eu.api.ovh.com/1.0';
    const appKey = env.OVH_APPLICATION_KEY;
    const appSecret = env.OVH_APPLICATION_SECRET;
    const consumerKey = env.OVH_CONSUMER_KEY;

    if (!appKey || !appSecret || !consumerKey) {
        throw new Error('OVH API credentials not configured');
    }

    const url = `${endpoint}${path}`;
    const timestamp = Math.floor(Date.now() / 1000);
    const method = 'GET';
    const body = '';

    // OVH signature: $1$SHA1(appSecret+consumerKey+method+url+body+timestamp)
    const { createHash } = await import('crypto');
    const toSign = [appSecret, consumerKey, method, url, body, timestamp].join('+');
    const signature = '$1$' + createHash('sha1').update(toSign).digest('hex');

    const res = await fetch(url, {
        method,
        headers: {
            'X-Ovh-Application': appKey,
            'X-Ovh-Consumer': consumerKey,
            'X-Ovh-Signature': signature,
            'X-Ovh-Timestamp': String(timestamp),
            'Content-Type': 'application/json',
        },
    });

    if (!res.ok) {
        const text = await res.text();
        throw new Error(`OVH API error ${res.status}: ${text}`);
    }

    return res.json();
}

export async function listVps(): Promise<string[]> {
    return ovhFetch<string[]>('/vps');
}

export async function getVpsStatus(serviceName: string): Promise<OvhVpsStatus> {
    return ovhFetch<OvhVpsStatus>(`/vps/${serviceName}`);
}

export async function getRecentInvoices(count: number = 5): Promise<OvhInvoice[]> {
    const ids = await ovhFetch<string[]>('/me/bill');
    const recentIds = ids.slice(0, count);

    const invoices: OvhInvoice[] = [];
    for (const id of recentIds) {
        const invoice = await ovhFetch<OvhInvoice>(`/me/bill/${id}`);
        invoices.push(invoice);
    }

    return invoices;
}

// ── Domain management ─────────────────────────────────────────────────

interface OvhDomainInfo {
    domain: string;
    nameServerType: string;
    offer: string;
    transferLockStatus: string;
    whoisOwner: string;
}

interface OvhDomainServiceInfo {
    domain: string;
    expiration: string;
    renew: { automatic: boolean };
}

export async function listDomains(): Promise<string[]> {
    return ovhFetch<string[]>('/domain');
}

export async function getDomainInfo(domain: string): Promise<OvhDomainInfo> {
    return ovhFetch<OvhDomainInfo>(`/domain/${domain}`);
}

export async function getDomainServiceInfo(domain: string): Promise<OvhDomainServiceInfo> {
    return ovhFetch<OvhDomainServiceInfo>(`/domain/${domain}/serviceInfos`);
}

export async function getDomainDnsRecords(domain: string): Promise<OvhDnsRecord[]> {
    const ids = await ovhFetch<number[]>(`/domain/zone/${domain}/record`);
    const records: OvhDnsRecord[] = [];

    for (const id of ids) {
        const record = await ovhFetch<OvhDnsRecord>(`/domain/zone/${domain}/record/${id}`);
        records.push(record);
    }

    return records;
}

interface OvhDnsRecord {
    id: number;
    fieldType: string;
    subDomain: string;
    target: string;
    ttl: number;
    zone: string;
}

export type { OvhVpsStatus, OvhInvoice, OvhDomainInfo, OvhDomainServiceInfo, OvhDnsRecord };
