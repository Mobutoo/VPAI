import { db } from '$lib/server/db';
import { servers, serverMetrics } from '$lib/server/db/schema';
import { desc, eq } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allServers = await db.select().from(servers).orderBy(servers.name);

	const serversWithMetrics = await Promise.all(
		allServers.map(async (s) => {
			const [metric] = await db
				.select()
				.from(serverMetrics)
				.where(eq(serverMetrics.serverId, s.id))
				.orderBy(desc(serverMetrics.recordedAt))
				.limit(1);
			return { ...s, latestMetric: metric ?? null };
		})
	);

	return { servers: serversWithMetrics };
};
