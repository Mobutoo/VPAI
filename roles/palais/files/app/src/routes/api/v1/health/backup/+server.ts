import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { backupStatus, nodes, insights } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';

// GET /api/v1/health/backup — latest backup status per node
export const GET: RequestHandler = async () => {
	const allBackups = await db
		.select()
		.from(backupStatus)
		.orderBy(desc(backupStatus.id));

	// Return latest per node
	const latestByNode = new Map<number, typeof allBackups[0]>();
	for (const b of allBackups) {
		if (!latestByNode.has(b.nodeId)) {
			latestByNode.set(b.nodeId, b);
		}
	}

	return json(Array.from(latestByNode.values()));
};

interface BackupPayload {
	node: string;
	last_backup_at: string;
	next_backup_at?: string;
	size_bytes?: number;
	status: 'ok' | 'failed' | 'running';
	details?: Record<string, unknown>;
}

// POST /api/v1/health/backup — update backup status from n8n/cron
export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json() as BackupPayload;

	if (!body.node || !body.status) {
		return json({ error: 'Missing node or status' }, { status: 400 });
	}

	// Find node
	const [node] = await db.select().from(nodes).where(eq(nodes.name, body.node));
	if (!node) {
		return json({ error: `Node "${body.node}" not found` }, { status: 404 });
	}

	const lastBackupAt = body.last_backup_at ? new Date(body.last_backup_at) : null;
	const nextBackupAt = body.next_backup_at ? new Date(body.next_backup_at) : null;

	// Upsert backup status
	await db.insert(backupStatus).values({
		nodeId: node.id,
		lastBackupAt,
		nextBackupAt,
		sizeBytes: body.size_bytes ?? null,
		status: body.status,
		details: body.details ?? null
	});

	// Alert: stale backup (> 24h) → create insight
	const isStale = lastBackupAt
		? Date.now() - lastBackupAt.getTime() > 24 * 60 * 60 * 1000
		: true;

	if (isStale || body.status === 'failed') {
		await db.insert(insights).values({
			type: 'error_pattern',
			severity: body.status === 'failed' ? 'critical' : 'warning',
			title: `Backup ${body.status === 'failed' ? 'échoué' : 'obsolète'} — ${node.name}`,
			description: isStale
				? `Dernier backup : ${lastBackupAt?.toISOString() ?? 'jamais'}. Délai > 24h.`
				: `Backup en status "${body.status}" sur ${node.name}.`,
			suggestedActions: [{ action: 'Vérifier Zerobyte sur le noeud cible' }],
			acknowledged: false
		});
	}

	return json({ ok: true, node: body.node, status: body.status });
};
