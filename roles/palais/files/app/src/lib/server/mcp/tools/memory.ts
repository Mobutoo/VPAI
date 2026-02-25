import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { memoryNodes, memoryEdges } from '$lib/server/db/schema';
import { eq, sql } from 'drizzle-orm';
import { env } from '$env/dynamic/private';

export const memoryToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.memory.search',
		description: 'Search the Knowledge Graph by semantic query (uses embeddings + full-text)',
		inputSchema: {
			type: 'object',
			properties: {
				query: { type: 'string', description: 'Natural language search query' },
				limit: { type: 'number', description: 'Max results (default 10)' },
				entityType: { type: 'string', description: 'Filter by entity type (agent, service, task, error, deployment, decision)' }
			},
			required: ['query']
		}
	},
	{
		name: 'palais.memory.recall',
		description: 'Recall a specific memory node by ID, including its edges',
		inputSchema: {
			type: 'object',
			properties: {
				nodeId: { type: 'number', description: 'Memory node ID' }
			},
			required: ['nodeId']
		}
	},
	{
		name: 'palais.memory.store',
		description: 'Store a new memory node in the Knowledge Graph',
		inputSchema: {
			type: 'object',
			properties: {
				type: { type: 'string', description: 'episodic, semantic, or procedural' },
				content: { type: 'string', description: 'Full content of the memory' },
				summary: { type: 'string', description: 'Brief summary' },
				entityType: { type: 'string', description: 'Entity type (agent, service, task, error, deployment, decision)' },
				entityId: { type: 'string', description: 'Related entity ID' },
				tags: { type: 'array', items: { type: 'string' }, description: 'Tags for categorization' }
			},
			required: ['type', 'content']
		}
	}
];

async function searchQdrant(query: string, limit: number): Promise<number[]> {
	const qdrantUrl = env.QDRANT_URL || 'http://qdrant:6333';
	const collection = env.QDRANT_COLLECTION || 'palais_memory';
	const litellmUrl = env.LITELLM_URL || 'http://litellm:4000';
	const litellmKey = env.LITELLM_KEY || '';

	try {
		// Get embedding from LiteLLM
		const embRes = await fetch(`${litellmUrl}/embeddings`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'Authorization': `Bearer ${litellmKey}`
			},
			body: JSON.stringify({
				model: 'text-embedding-3-small',
				input: query
			})
		});

		if (!embRes.ok) return [];
		const embData = await embRes.json();
		const vector = embData.data?.[0]?.embedding;
		if (!vector) return [];

		// Search Qdrant
		const searchRes = await fetch(`${qdrantUrl}/collections/${collection}/points/search`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ vector, limit, with_payload: true })
		});

		if (!searchRes.ok) return [];
		const searchData = await searchRes.json();
		return (searchData.result ?? []).map((r: any) => r.payload?.node_id).filter(Boolean);
	} catch {
		return [];
	}
}

async function generateAndStoreEmbedding(nodeId: number, content: string): Promise<void> {
	const qdrantUrl = env.QDRANT_URL || 'http://qdrant:6333';
	const collection = env.QDRANT_COLLECTION || 'palais_memory';
	const litellmUrl = env.LITELLM_URL || 'http://litellm:4000';
	const litellmKey = env.LITELLM_KEY || '';

	const embRes = await fetch(`${litellmUrl}/embeddings`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'Authorization': `Bearer ${litellmKey}`
		},
		body: JSON.stringify({ model: 'text-embedding-3-small', input: content })
	});

	if (!embRes.ok) return;
	const embData = await embRes.json();
	const vector = embData.data?.[0]?.embedding;
	if (!vector) return;

	const pointId = crypto.randomUUID();
	await fetch(`${qdrantUrl}/collections/${collection}/points`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			points: [{
				id: pointId,
				vector,
				payload: { node_id: nodeId, type: 'memory' }
			}]
		})
	});

	// Update node with embedding ID
	await db.update(memoryNodes)
		.set({ embeddingId: pointId })
		.where(eq(memoryNodes.id, nodeId));
}

export async function handleMemoryTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'search': {
			const query = args.query as string;
			const limit = (args.limit as number) || 10;

			// 1. Vector search via Qdrant
			const vectorNodeIds = await searchQdrant(query, limit);

			// 2. Full-text fallback via PostgreSQL
			const textResults = await db.select().from(memoryNodes)
				.where(sql`to_tsvector('english', ${memoryNodes.content}) @@ plainto_tsquery('english', ${query})`)
				.limit(limit);

			// Merge: vector results first, then text results not already included
			const seenIds = new Set<number>();
			const results = [];

			if (vectorNodeIds.length > 0) {
				const vectorNodes = await db.select().from(memoryNodes)
					.where(sql`${memoryNodes.id} IN (${sql.join(vectorNodeIds.map(id => sql`${id}`), sql`, `)})`);
				for (const node of vectorNodes) {
					seenIds.add(node.id);
					results.push(node);
				}
			}

			for (const node of textResults) {
				if (!seenIds.has(node.id)) {
					results.push(node);
				}
			}

			return results.slice(0, limit);
		}

		case 'recall': {
			const nodeId = args.nodeId as number;
			const [node] = await db.select().from(memoryNodes)
				.where(eq(memoryNodes.id, nodeId));

			if (!node) throw new Error(`Memory node ${nodeId} not found`);

			// Get connected edges
			const edges = await db.select().from(memoryEdges)
				.where(sql`${memoryEdges.sourceNodeId} = ${nodeId} OR ${memoryEdges.targetNodeId} = ${nodeId}`);

			return { node, edges };
		}

		case 'store': {
			const [node] = await db.insert(memoryNodes).values({
				type: args.type as any,
				content: args.content as string,
				summary: (args.summary as string) ?? null,
				entityType: (args.entityType as any) ?? null,
				entityId: (args.entityId as string) ?? null,
				tags: (args.tags as string[]) ?? [],
				createdBy: 'agent'
			}).returning();

			// Async: generate embedding and store in Qdrant (fire and forget)
			generateAndStoreEmbedding(node.id, args.content as string).catch(() => {
				// Log but do not fail the MCP call
			});

			return node;
		}

		default:
			throw new Error(`Unknown memory method: ${method}`);
	}
}
