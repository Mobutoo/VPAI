import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { memoryNodes, memoryEdges } from '$lib/server/db/schema';
import { eq, or } from 'drizzle-orm';

/**
 * GET /api/v1/memory/nodes/:id
 * Returns a node with its edges (outgoing + incoming) and linked nodes.
 */
export const GET: RequestHandler = async ({ params }) => {
	const id = parseInt(params.id);
	if (isNaN(id)) return json({ error: 'Invalid id' }, { status: 400 });

	const [node] = await db.select().from(memoryNodes).where(eq(memoryNodes.id, id));
	if (!node) return json({ error: 'Not found' }, { status: 404 });

	// Fetch all edges involving this node
	const edges = await db.select().from(memoryEdges)
		.where(or(eq(memoryEdges.sourceNodeId, id), eq(memoryEdges.targetNodeId, id)));

	// Fetch connected node summaries
	const connectedIds = [
		...new Set(edges.flatMap((e) => [e.sourceNodeId, e.targetNodeId]).filter((nid) => nid !== id))
	];
	const connected = connectedIds.length > 0
		? await db.select({
			id: memoryNodes.id,
			type: memoryNodes.type,
			summary: memoryNodes.summary,
			content: memoryNodes.content,
			entityType: memoryNodes.entityType,
			createdAt: memoryNodes.createdAt
		}).from(memoryNodes)
			.where(or(...connectedIds.map((nid) => eq(memoryNodes.id, nid))))
		: [];

	return json({ node, edges, connected });
};
