import { db } from '$lib/server/db';
import { domains, dnsRecords } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const [domain] = await db
		.select()
		.from(domains)
		.where(eq(domains.name, params.name));

	if (!domain) {
		error(404, `Domain "${params.name}" not found`);
	}

	const records = await db
		.select()
		.from(dnsRecords)
		.where(eq(dnsRecords.domainId, domain.id))
		.orderBy(asc(dnsRecords.recordType), asc(dnsRecords.host));

	return { domain, records };
};
