import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { memoryNodes, memoryEdges } from '$lib/server/db/schema';
import { desc, eq } from 'drizzle-orm';
import { tryGenerateEmbedding } from '$lib/server/memory/embeddings';
import { upsertPoint } from '$lib/server/memory/qdrant';
import { createRetroactiveEdges } from '$lib/server/memory/enrich';

/**
 * POST /api/v1/memory/nodes
 * Body: { type, content, summary?, entityType?, entityId?, tags?, metadata?, createdBy? }
 * Creates a memory node, generates embedding, upserts to Qdrant, triggers retroactive enrichment.
 */
export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	const { type, content, summary, entityType, entityId, tags, metadata, createdBy } = body;

	if (!type || !content) {
		return json({ error: 'type and content are required' }, { status: 400 });
	}

	// Insert into PostgreSQL
	const [node] = await db.insert(memoryNodes).values({
		type,
		content,
		summary: summary ?? null,
		entityType: entityType ?? null,
		entityId: entityId ?? null,
		tags: tags ?? [],
		metadata: metadata ?? null,
		createdBy: createdBy ?? 'system'
	}).returning();

	// Generate embedding (non-blocking on failure)
	const embedding = await tryGenerateEmbedding(summary ?? content);
	const embeddingId = `node-${node.id}`;

	if (embedding) {
		// Upsert into Qdrant
		await upsertPoint(embeddingId, embedding, {
			nodeId: node.id,
			type: node.type,
			entityType: node.entityType,
			entityId: node.entityId,
			tags: node.tags,
			createdAt: node.createdAt?.toISOString()
		});

		// Store embeddingId reference in DB
		await db.update(memoryNodes)
			.set({ embeddingId })
			.where(eq(memoryNodes.id, node.id));

		// Retroactive enrichment: create edges to similar nodes (A-MEM pattern)
		createRetroactiveEdges(node.id, embedding).catch(console.error);
	}

	return json({ ...node, embeddingId }, { status: 201 });
};

/**
 * GET /api/v1/memory/nodes
 * Returns recent memory nodes (latest 50).
 */
export const GET: RequestHandler = async ({ url }) => {
	const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '50'), 200);
	const type = url.searchParams.get('type');

	const query = db.select().from(memoryNodes).orderBy(desc(memoryNodes.createdAt)).limit(limit);
	const nodes = await query;
	const filtered = type ? nodes.filter((n) => n.type === type) : nodes;

	return json(filtered);
};
