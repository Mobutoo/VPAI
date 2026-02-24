import { env } from '$env/dynamic/private';

const LITELLM_URL = env.LITELLM_URL ?? 'http://litellm:4000';
const LITELLM_KEY = env.LITELLM_KEY ?? '';
const EMBEDDING_MODEL = 'text-embedding-3-small';

/**
 * Generate a 1536-dim embedding vector for the given text via LiteLLM.
 */
export async function generateEmbedding(text: string): Promise<number[]> {
	const res = await fetch(`${LITELLM_URL}/v1/embeddings`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${LITELLM_KEY}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({ model: EMBEDDING_MODEL, input: text })
	});

	if (!res.ok) {
		const err = await res.text();
		throw new Error(`[Memory] Embedding generation failed (${res.status}): ${err}`);
	}

	const data = await res.json();
	const embedding = data?.data?.[0]?.embedding;
	if (!Array.isArray(embedding) || embedding.length === 0) {
		throw new Error('[Memory] Invalid embedding response from LiteLLM');
	}
	return embedding;
}

/**
 * Generate an embedding, returning null on failure (non-blocking path).
 */
export async function tryGenerateEmbedding(text: string): Promise<number[] | null> {
	try {
		return await generateEmbedding(text);
	} catch (err) {
		console.error('[Memory] Embedding error (non-critical):', err);
		return null;
	}
}
