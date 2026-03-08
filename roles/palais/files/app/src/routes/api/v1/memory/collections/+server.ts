import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { listCollections } from '$lib/server/memory/qdrant';

/**
 * GET /api/v1/memory/collections
 * Returns all Qdrant collections with metadata (points count, vector size, distance, status).
 */
export const GET: RequestHandler = async () => {
	try {
		const collections = await listCollections();
		return json({ collections });
	} catch (err) {
		return json({ error: 'Failed to list Qdrant collections', detail: String(err) }, { status: 503 });
	}
};
