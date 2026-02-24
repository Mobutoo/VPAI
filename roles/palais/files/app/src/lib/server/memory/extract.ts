import { env } from '$env/dynamic/private';
import { db } from '$lib/server/db';
import { memoryNodes, memoryEdges } from '$lib/server/db/schema';
import { tryGenerateEmbedding } from './embeddings';
import { upsertPoint } from './qdrant';
import { createRetroactiveEdges } from './enrich';
import { eq } from 'drizzle-orm';

const LITELLM_URL = env.LITELLM_URL ?? 'http://litellm:4000';
const LITELLM_KEY = env.LITELLM_KEY ?? '';
// Cheap model for extraction (always active even in eco mode)
const EXTRACTION_MODEL = 'deepseek/deepseek-chat';

interface Triplet {
	subject: string;
	relation: string;
	object: string;
}

const EXTRACTION_PROMPT = `Extrais les faits clés de cet événement sous forme de triplets JSON.
Format: [{"subject": "...", "relation": "...", "object": "..."}]
Règles: 3-5 triplets max. Sujets/objets courts (< 40 chars). Relations en snake_case.
Réponds UNIQUEMENT avec le tableau JSON, sans markdown.`;

/**
 * Extract semantic triplets from an episodic node via LLM.
 * Creates semantic child nodes + edges in PostgreSQL.
 */
export async function extractTriplets(episodicNodeId: number): Promise<void> {
	const [sourceNode] = await db.select().from(memoryNodes).where(eq(memoryNodes.id, episodicNodeId));
	if (!sourceNode || sourceNode.type !== 'episodic') return;

	let triplets: Triplet[] = [];

	try {
		const res = await fetch(`${LITELLM_URL}/v1/chat/completions`, {
			method: 'POST',
			headers: {
				Authorization: `Bearer ${LITELLM_KEY}`,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				model: EXTRACTION_MODEL,
				max_tokens: 400,
				temperature: 0.1,
				messages: [
					{ role: 'system', content: EXTRACTION_PROMPT },
					{ role: 'user', content: sourceNode.content.slice(0, 1000) }
				]
			})
		});

		if (!res.ok) return;
		const data = await res.json();
		const raw = data?.choices?.[0]?.message?.content?.trim() ?? '';

		// Strip potential markdown fences
		const cleaned = raw.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
		triplets = JSON.parse(cleaned);
		if (!Array.isArray(triplets)) return;
	} catch {
		return; // LLM unavailable or malformed JSON — skip silently
	}

	for (const t of triplets.slice(0, 5)) {
		if (!t.subject || !t.relation || !t.object) continue;

		const content = `${t.subject} ${t.relation} ${t.object}`;

		const [semanticNode] = await db.insert(memoryNodes).values({
			type: 'semantic',
			content,
			summary: content,
			tags: [t.relation],
			createdBy: 'agent'
		}).returning();

		// Edge: episodic → semantic (learned_from)
		await db.insert(memoryEdges).values({
			sourceNodeId: episodicNodeId,
			targetNodeId: semanticNode.id,
			relation: 'learned_from',
			weight: 0.9
		});

		// Embed semantic node
		const embedding = await tryGenerateEmbedding(content);
		if (embedding) {
			const embeddingId = `node-${semanticNode.id}`;
			await upsertPoint(embeddingId, embedding, {
				nodeId: semanticNode.id,
				type: 'semantic',
				tags: [t.relation],
				createdAt: semanticNode.createdAt?.toISOString()
			});
			await db.update(memoryNodes).set({ embeddingId }).where(eq(memoryNodes.id, semanticNode.id));
			createRetroactiveEdges(semanticNode.id, embedding).catch(() => {});
		}
	}
}
