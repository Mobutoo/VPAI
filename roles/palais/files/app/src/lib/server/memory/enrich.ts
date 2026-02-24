import { db } from '$lib/server/db';
import { memoryNodes, memoryEdges } from '$lib/server/db/schema';
import { eq, ne, and, isNotNull } from 'drizzle-orm';
import { searchPoints } from './qdrant';

const SIMILARITY_THRESHOLD = 0.8;
const MAX_SIMILAR = 5;

/**
 * A-MEM retroactive enrichment pattern.
 * When a new node is added, find the most similar existing nodes in Qdrant
 * and create `related_to` edges for those with score > SIMILARITY_THRESHOLD.
 * Non-blocking — called with .catch() by the caller.
 */
export async function createRetroactiveEdges(
	newNodeId: number,
	embedding: number[]
): Promise<void> {
	// Search top similar nodes (exclude self)
	const hits = await searchPoints(embedding, MAX_SIMILAR + 1, SIMILARITY_THRESHOLD);

	for (const hit of hits) {
		const targetId = parseInt(String(hit.id).replace('node-', ''));
		if (isNaN(targetId) || targetId === newNodeId) continue;

		// Verify the target node exists in PostgreSQL
		const [target] = await db.select({ id: memoryNodes.id })
			.from(memoryNodes)
			.where(eq(memoryNodes.id, targetId));
		if (!target) continue;

		// Avoid duplicate edges
		const existing = await db.select({ id: memoryEdges.id })
			.from(memoryEdges)
			.where(
				and(
					eq(memoryEdges.sourceNodeId, newNodeId),
					eq(memoryEdges.targetNodeId, targetId)
				)
			);
		if (existing.length > 0) continue;

		await db.insert(memoryEdges).values({
			sourceNodeId: newNodeId,
			targetNodeId: targetId,
			relation: 'related_to',
			weight: Math.round(hit.score * 100) / 100
		});
	}
}
