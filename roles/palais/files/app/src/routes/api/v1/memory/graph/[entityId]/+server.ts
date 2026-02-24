import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { memoryNodes, memoryEdges } from '$lib/server/db/schema';
import { eq, or } from 'drizzle-orm';

/**
 * GET /api/v1/memory/graph/:entityId
 * Traverse the memory graph up to depth 2 from a given node.
 * Returns { nodes, edges } sub-graph suitable for d3-force rendering.
 */
export const GET: RequestHandler = async ({ params, url }) => {
	const rootId = parseInt(params.entityId);
	if (isNaN(rootId)) return json({ error: 'Invalid entityId' }, { status: 400 });

	const maxDepth = Math.min(parseInt(url.searchParams.get('depth') ?? '2'), 3);

	// BFS traversal
	const visitedNodes = new Map<number, typeof allNodes[0]>();
	const visitedEdges = new Map<number, typeof allEdges[0]>();
	const queue: number[] = [rootId];
	const seenIds = new Set<number>([rootId]);

	// Fetch all nodes and edges in one go (efficient for small graphs)
	const allNodes = await db.select().from(memoryNodes);
	const allEdges = await db.select().from(memoryEdges);

	const nodeMap = new Map(allNodes.map((n) => [n.id, n]));
	const edgesByNode = new Map<number, typeof allEdges>();

	for (const edge of allEdges) {
		if (!edgesByNode.has(edge.sourceNodeId)) edgesByNode.set(edge.sourceNodeId, []);
		if (!edgesByNode.has(edge.targetNodeId)) edgesByNode.set(edge.targetNodeId, []);
		edgesByNode.get(edge.sourceNodeId)!.push(edge);
		edgesByNode.get(edge.targetNodeId)!.push(edge);
	}

	let depth = 0;
	while (queue.length > 0 && depth < maxDepth) {
		depth++;
		const currentLevel = [...queue];
		queue.length = 0;

		for (const nodeId of currentLevel) {
			const node = nodeMap.get(nodeId);
			if (!node) continue;
			visitedNodes.set(nodeId, node);

			const edges = edgesByNode.get(nodeId) ?? [];
			for (const edge of edges) {
				visitedEdges.set(edge.id, edge);
				const neighborId = edge.sourceNodeId === nodeId ? edge.targetNodeId : edge.sourceNodeId;
				if (!seenIds.has(neighborId)) {
					seenIds.add(neighborId);
					queue.push(neighborId);
				}
			}
		}
	}

	// Also include any nodes referenced by collected edges
	for (const edge of visitedEdges.values()) {
		for (const nid of [edge.sourceNodeId, edge.targetNodeId]) {
			if (!visitedNodes.has(nid)) {
				const n = nodeMap.get(nid);
				if (n) visitedNodes.set(nid, n);
			}
		}
	}

	return json({
		rootId,
		nodes: [...visitedNodes.values()].map((n) => ({
			id: n.id,
			type: n.type,
			summary: n.summary ?? n.content.slice(0, 120),
			entityType: n.entityType,
			entityId: n.entityId,
			tags: n.tags,
			createdAt: n.createdAt
		})),
		edges: [...visitedEdges.values()].map((e) => ({
			id: e.id,
			source: e.sourceNodeId,
			target: e.targetNodeId,
			relation: e.relation,
			weight: e.weight
		}))
	});
};
