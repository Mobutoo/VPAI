import { env } from '$env/dynamic/private';

const BASE_URL = 'https://api.namecheap.com/xml.response';

interface DnsRecord {
    hostName: string;
    recordType: string;
    address: string;
    ttl: number;
    mxPref?: number;
}

interface Domain {
    name: string;
    created: string;
    expires: string;
    isExpired: boolean;
    autoRenew: boolean;
    whoisGuard: boolean;
}

function getAuthParams(): URLSearchParams {
    const apiUser = env.NAMECHEAP_API_USER;
    const apiKey = env.NAMECHEAP_API_KEY;
    const clientIp = env.NAMECHEAP_CLIENT_IP;

    if (!apiUser || !apiKey || !clientIp) {
        throw new Error('Namecheap API credentials not configured (NAMECHEAP_API_USER, NAMECHEAP_API_KEY, NAMECHEAP_CLIENT_IP)');
    }

    return new URLSearchParams({
        ApiUser: apiUser,
        ApiKey: apiKey,
        UserName: apiUser,
        ClientIp: clientIp,
    });
}

async function namecheapFetch(command: string, extraParams?: Record<string, string>): Promise<string> {
    const params = getAuthParams();
    params.set('Command', command);
    if (extraParams) {
        for (const [k, v] of Object.entries(extraParams)) {
            params.set(k, v);
        }
    }

    const res = await fetch(`${BASE_URL}?${params}`);
    if (!res.ok) {
        throw new Error(`Namecheap API HTTP error ${res.status}`);
    }

    const xml = await res.text();

    // Check for API-level errors in XML response
    if (xml.includes('<Status>ERROR</Status>') || xml.includes('Errors>')) {
        const errorMatch = xml.match(/<Error[^>]*>([^<]+)<\/Error>/);
        throw new Error(`Namecheap API error: ${errorMatch?.[1] ?? 'Unknown error'}`);
    }

    return xml;
}

// Parse XML helper — simple regex-based for Namecheap's flat XML responses
function extractAttribute(tag: string, attr: string, xml: string): string | null {
    const regex = new RegExp(`<${tag}[^>]*\\s${attr}="([^"]*)"`, 'i');
    const match = xml.match(regex);
    return match?.[1] ?? null;
}

function extractAllTags(tagName: string, xml: string): string[] {
    // Match self-closing <Tag ... /> or <Tag ...>content</Tag>
    // Uses [^>]* instead of [^/]* to handle dates with slashes in attributes (e.g. 08/03/2025)
    const regex = new RegExp(`<${tagName}\\s[^>]*\\/>|<${tagName}\\s[^>]*>[^<]*<\\/${tagName}>`, 'gi');
    return xml.match(regex) ?? [];
}

function extractTagContent(tagName: string, xml: string): string | null {
    const regex = new RegExp(`<${tagName}[^>]*>([^<]*)<\\/${tagName}>`, 'i');
    const match = xml.match(regex);
    return match?.[1] ?? null;
}

export async function getDomains(): Promise<Domain[]> {
    const xml = await namecheapFetch('namecheap.domains.getList');
    const domainTags = extractAllTags('Domain', xml);

    return domainTags.map(tag => ({
        name: extractAttribute('Domain', 'Name', tag) ?? '',
        created: extractAttribute('Domain', 'Created', tag) ?? '',
        expires: extractAttribute('Domain', 'Expires', tag) ?? '',
        isExpired: extractAttribute('Domain', 'IsExpired', tag) === 'true',
        autoRenew: extractAttribute('Domain', 'AutoRenew', tag) === 'true',
        whoisGuard: extractAttribute('Domain', 'WhoisGuard', tag)?.toLowerCase() === 'enabled',
    }));
}

export async function getDnsRecords(domain: string): Promise<DnsRecord[]> {
    const [sld, tld] = splitDomain(domain);

    const xml = await namecheapFetch('namecheap.domains.dns.getHosts', {
        SLD: sld,
        TLD: tld,
    });

    const hostTags = extractAllTags('host', xml);

    return hostTags.map(tag => ({
        hostName: extractAttribute('host', 'Name', tag) ?? '',
        recordType: extractAttribute('host', 'Type', tag) ?? '',
        address: extractAttribute('host', 'Address', tag) ?? '',
        ttl: parseInt(extractAttribute('host', 'TTL', tag) ?? '1800', 10),
        mxPref: extractAttribute('host', 'MXPref', tag)
            ? parseInt(extractAttribute('host', 'MXPref', tag)!, 10)
            : undefined,
    }));
}

export async function setDnsRecords(domain: string, records: DnsRecord[]): Promise<void> {
    const [sld, tld] = splitDomain(domain);

    const params: Record<string, string> = { SLD: sld, TLD: tld };

    records.forEach((record, i) => {
        const idx = i + 1;
        params[`HostName${idx}`] = record.hostName;
        params[`RecordType${idx}`] = record.recordType;
        params[`Address${idx}`] = record.address;
        params[`TTL${idx}`] = String(record.ttl);
        if (record.mxPref !== undefined) {
            params[`MXPref${idx}`] = String(record.mxPref);
        }
    });

    await namecheapFetch('namecheap.domains.dns.setHosts', params);
}

export async function addDnsRecord(domain: string, record: DnsRecord): Promise<void> {
    // GET all existing records, ADD the new one, SET all back
    const existing = await getDnsRecords(domain);
    await setDnsRecords(domain, [...existing, record]);
}

export async function removeDnsRecord(domain: string, hostName: string, recordType: string): Promise<void> {
    // GET all existing records, FILTER out the target, SET remaining back
    const existing = await getDnsRecords(domain);
    const filtered = existing.filter(
        r => !(r.hostName === hostName && r.recordType === recordType)
    );

    if (filtered.length === existing.length) {
        throw new Error(`DNS record not found: ${recordType} ${hostName}.${domain}`);
    }

    await setDnsRecords(domain, filtered);
}

export async function updateDnsRecord(
    domain: string,
    hostName: string,
    recordType: string,
    updates: Partial<DnsRecord>
): Promise<void> {
    const existing = await getDnsRecords(domain);
    const updated = existing.map(r => {
        if (r.hostName === hostName && r.recordType === recordType) {
            return { ...r, ...updates };
        }
        return r;
    });
    await setDnsRecords(domain, updated);
}

function splitDomain(domain: string): [string, string] {
    const parts = domain.split('.');
    if (parts.length < 2) throw new Error(`Invalid domain: ${domain}`);
    const tld = parts.pop()!;
    const sld = parts.join('.');
    return [sld, tld];
}

export type { DnsRecord, Domain };
