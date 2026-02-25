import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq, desc, and, ne } from 'drizzle-orm';

export const GET: RequestHandler = async ({ url }) => {
	const severity = url.searchParams.get('severity');
	const acknowledged = url.searchParams.get('acknowledged');
	const excludeStandup = url.searchParams.get('excludeStandup') !== 'false';

	const conditions = [];

	if (severity) {
		conditions.push(eq(insights.severity, severity as any));
	}
	if (acknowledged === 'true') {
		conditions.push(eq(insights.acknowledged, true));
	} else if (acknowledged === 'false') {
		conditions.push(eq(insights.acknowledged, false));
	}
	if (excludeStandup) {
		conditions.push(ne(insights.type, 'standup'));
	}

	const query = db.select().from(insights);
	const result = conditions.length > 0
		? await query.where(and(...conditions)).orderBy(desc(insights.createdAt)).limit(100)
		: await query.orderBy(desc(insights.createdAt)).limit(100);

	return json(result);
};
