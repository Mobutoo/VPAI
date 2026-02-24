import { db } from '$lib/server/db';
import { memoryNodes } from '$lib/server/db/schema';
import { tryGenerateEmbedding } from './embeddings';
import { upsertPoint } from './qdrant';
import { createRetroactiveEdges } from './enrich';
import { eq } from 'drizzle-orm';

// Events importants qui méritent un noeud mémoire
const IMPORTANT_ACTIONS = new Set([
	'task.completed', 'task.failed', 'task.created',
	'error', 'deployment', 'deployment.success', 'deployment.failed',
	'agent.error', 'agent.completed',
	'mission.completed', 'mission.failed'
]);

/**
 * Ingest an activity event as an episodic memory node.
 * Called from logActivity() for important events.
 * Non-blocking — never throws.
 */
export async function ingestActivityAsMemory(params: {
	entityType: string;
	entityId: number;
	action: string;
	actorAgentId?: string | null;
	oldValue?: string | null;
	newValue?: string | null;
}): Promise<void> {
	if (!IMPORTANT_ACTIONS.has(params.action)) return;

	try {
		const content = [
			`Action: ${params.action}`,
			`Entity: ${params.entityType} #${params.entityId}`,
			params.actorAgentId ? `Agent: ${params.actorAgentId}` : null,
			params.newValue ? `Context: ${params.newValue.slice(0, 500)}` : null,
			params.oldValue ? `Before: ${params.oldValue.slice(0, 200)}` : null
		].filter(Boolean).join('\n');

		const summary = `${params.action} on ${params.entityType} #${params.entityId}${params.actorAgentId ? ` by ${params.actorAgentId}` : ''}`;

		const [node] = await db.insert(memoryNodes).values({
			type: 'episodic',
			content,
			summary,
			entityType: params.entityType as 'agent' | 'service' | 'task' | 'error' | 'deployment' | 'decision' | null,
			entityId: String(params.entityId),
			tags: [params.action, params.entityType],
			createdBy: 'system'
		}).returning();

		// Embed + upsert to Qdrant
		const embedding = await tryGenerateEmbedding(summary);
		if (embedding) {
			const embeddingId = `node-${node.id}`;
			await upsertPoint(embeddingId, embedding, {
				nodeId: node.id,
				type: node.type,
				entityType: node.entityType,
				entityId: node.entityId,
				tags: node.tags,
				createdAt: node.createdAt?.toISOString()
			});
			await db.update(memoryNodes).set({ embeddingId }).where(eq(memoryNodes.id, node.id));
			createRetroactiveEdges(node.id, embedding).catch(() => {});
		}
	} catch {
		// Non-blocking — never disrupts the main request
	}
}
