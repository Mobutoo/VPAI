import { env } from '$env/dynamic/private';

const QDRANT_URL = env.QDRANT_URL ?? 'http://qdrant:6333';
const COLLECTION = env.QDRANT_COLLECTION ?? 'palais_memory';
const VECTOR_SIZE = 1536; // text-embedding-3-small

// ── HTTP helpers ──────────────────────────────────────────────────────────────

async function qdrantFetch(path: string, options?: RequestInit): Promise<Response> {
	return fetch(`${QDRANT_URL}${path}`, {
		...options,
		headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) }
	});
}

// ── Collection init ───────────────────────────────────────────────────────────

/**
 * Ensure the `palais_memory` Qdrant collection exists.
 * Called once at server startup. Idempotent.
 */
export async function ensureQdrantCollection(): Promise<void> {
	try {
		// Check if collection already exists
		const check = await qdrantFetch(`/collections/${COLLECTION}`);
		if (check.ok) {
			console.log(`[Memory] Qdrant collection "${COLLECTION}" already exists`);
			return;
		}

		// Create collection with cosine distance, 1536 dims (text-embedding-3-small)
		const res = await qdrantFetch(`/collections/${COLLECTION}`, {
			method: 'PUT',
			body: JSON.stringify({
				vectors: {
					size: VECTOR_SIZE,
					distance: 'Cosine'
				},
				optimizers_config: { default_segment_number: 2 },
				replication_factor: 1
			})
		});

		if (res.ok) {
			console.log(`[Memory] Qdrant collection "${COLLECTION}" created (${VECTOR_SIZE}d, cosine)`);
		} else {
			const err = await res.text();
			console.error(`[Memory] Failed to create Qdrant collection: ${err}`);
		}
	} catch (err) {
		// Non-blocking — Qdrant may not be available at boot time in some envs
		console.error('[Memory] Qdrant init error (non-critical):', err);
	}
}

// ── Upsert / Search ───────────────────────────────────────────────────────────

/**
 * Upsert a single point (node embedding) into Qdrant.
 */
export async function upsertPoint(
	id: string,
	vector: number[],
	payload: Record<string, unknown>
): Promise<void> {
	const res = await qdrantFetch(`/collections/${COLLECTION}/points`, {
		method: 'PUT',
		body: JSON.stringify({
			points: [{ id, vector, payload }]
		})
	});
	if (!res.ok) {
		const err = await res.text();
		throw new Error(`[Memory] Qdrant upsert failed: ${err}`);
	}
}

/**
 * Search top-K most similar points by vector.
 */
export async function searchPoints(
	vector: number[],
	topK = 10,
	scoreThreshold = 0.0
): Promise<Array<{ id: string; score: number; payload: Record<string, unknown> }>> {
	const res = await qdrantFetch(`/collections/${COLLECTION}/points/search`, {
		method: 'POST',
		body: JSON.stringify({
			vector,
			limit: topK,
			score_threshold: scoreThreshold,
			with_payload: true
		})
	});
	if (!res.ok) return [];
	const data = await res.json();
	return data.result ?? [];
}

/**
 * Delete a point by ID.
 */
export async function deletePoint(id: string): Promise<void> {
	await qdrantFetch(`/collections/${COLLECTION}/points/delete`, {
		method: 'POST',
		body: JSON.stringify({ points: [id] })
	});
}
