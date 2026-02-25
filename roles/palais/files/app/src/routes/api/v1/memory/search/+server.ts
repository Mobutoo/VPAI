import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { memoryNodes } from '$lib/server/db/schema';
import { eq, or } from 'drizzle-orm';
import { generateEmbedding } from '$lib/server/memory/embeddings';
import { searchPoints } from '$lib/server/memory/qdrant';

/**
 * POST /api/v1/memory/search
 * Body: { query: string, topK?: number, threshold?: number }
 * Embeds the query, searches Qdrant, returns matching memory nodes with scores.
 */
export const POST: RequestHandler = async ({ request }) => {
	const { query, topK = 10, threshold = 0.5 } = await request.json();

	if (!query || typeof query !== 'string') {
		return json({ error: 'query is required' }, { status: 400 });
	}

	let embedding: number[];
	try {
		embedding = await generateEmbedding(query);
	} catch (err) {
		return json({ error: 'Embedding generation failed', detail: String(err) }, { status: 503 });
	}

	// Search Qdrant for top-K similar vectors
	const hits = await searchPoints(embedding, topK, threshold);

	if (hits.length === 0) return json({ results: [] });

	// Fetch full node data from PostgreSQL
	const nodeIds = hits.map((h) => parseInt(String(h.id).replace('node-', ''))).filter((n) => !isNaN(n));
	const nodes = nodeIds.length > 0
		? await db.select().from(memoryNodes)
			.where(or(...nodeIds.map((id) => eq(memoryNodes.id, id))))
		: [];

	// Merge scores
	const nodeMap = new Map(nodes.map((n) => [n.id, n]));
	const results = hits
		.map((h) => {
			const nid = parseInt(String(h.id).replace('node-', ''));
			const node = nodeMap.get(nid);
			return node ? { ...node, score: h.score } : null;
		})
		.filter(Boolean)
		.sort((a, b) => (b!.score ?? 0) - (a!.score ?? 0));

	return json({ results, query });
};
