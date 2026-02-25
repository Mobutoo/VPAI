import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { nodes, healthChecks } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

interface ServiceCheck {
	name: string;
	status: string;
	response_time_ms?: number;
	details?: Record<string, unknown>;
}

interface HealthPayload {
	node: string;
	services: ServiceCheck[];
	cpu_percent?: number;
	ram_percent?: number;
	disk_percent?: number;
	temperature?: number;
}

export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json() as HealthPayload;

	if (!body.node || !Array.isArray(body.services)) {
		return json({ error: 'Missing node or services' }, { status: 400 });
	}

	// Find node by name
	const [node] = await db.select().from(nodes).where(eq(nodes.name, body.node));
	if (!node) {
		return json({ error: `Node "${body.node}" not found` }, { status: 404 });
	}

	const now = new Date();
	const allHealthy = body.services.every((s) => s.status === 'healthy');

	// Update node metrics + status
	await db
		.update(nodes)
		.set({
			status: allHealthy ? 'online' : 'offline',
			lastSeenAt: now,
			cpuPercent: body.cpu_percent ?? null,
			ramPercent: body.ram_percent ?? null,
			diskPercent: body.disk_percent ?? null,
			temperature: body.temperature ?? null
		})
		.where(eq(nodes.id, node.id));

	// Insert health checks for each service
	if (body.services.length > 0) {
		await db.insert(healthChecks).values(
			body.services.map((s) => ({
				nodeId: node.id,
				serviceName: s.name,
				status: s.status,
				responseTimeMs: s.response_time_ms ?? null,
				checkedAt: now,
				details: s.details ?? null
			}))
		);
	}

	return json({ ok: true, node: body.node, services: body.services.length, ts: now });
};
