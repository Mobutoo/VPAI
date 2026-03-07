import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { domains, dnsRecords } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const domainsToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.domains.list',
		description: 'List all domains with their expiry date, registrar, auto-renew flag, and SSL status. No parameters required.',
		inputSchema: {
			type: 'object',
			properties: {}
		}
	},
	{
		name: 'palais.domains.dns_records',
		description: 'Get all DNS records for a specific domain. Required: domain name.',
		inputSchema: {
			type: 'object',
			properties: {
				domain: { type: 'string', description: 'Domain name (e.g. example.com)' }
			},
			required: ['domain']
		}
	}
];

export async function handleDomainsTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'list': {
			const allDomains = await db.select().from(domains).orderBy(domains.name);

			return allDomains.map((d) => ({
				name: d.name,
				registrar: d.registrar,
				expiryDate: d.expiryDate ?? null,
				autoRenew: d.autoRenew ?? null,
				sslStatus: d.sslStatus ?? null
			}));
		}

		case 'dns_records': {
			const domainName = args.domain as string;
			if (!domainName) throw new Error('Missing required parameter: domain');

			const [domain] = await db
				.select()
				.from(domains)
				.where(eq(domains.name, domainName))
				.limit(1);

			if (!domain) throw new Error(`Domain not found: ${domainName}`);

			return db
				.select()
				.from(dnsRecords)
				.where(eq(dnsRecords.domainId, domain.id))
				.orderBy(dnsRecords.recordType, dnsRecords.host);
		}

		default:
			throw new Error(`Unknown domains method: ${method}`);
	}
}
