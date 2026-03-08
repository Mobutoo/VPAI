import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { scrollPoints } from '$lib/server/memory/qdrant';

/**
 * GET /api/v1/memory/collections/[name]/points
 * Scrolls through points in a specific Qdrant collection.
 * Query params: limit (default 20, max 100), offset (pagination cursor).
 */
export const GET: RequestHandler = async ({ params, url }) => {
	const collection = params.name;
	if (!collection) {
		return json({ error: 'Collection name is required' }, { status: 400 });
	}

	const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '20'), 100);
	const rawOffset = url.searchParams.get('offset');
	const offset = rawOffset ? (isNaN(Number(rawOffset)) ? rawOffset : Number(rawOffset)) : null;

	try {
		const result = await scrollPoints(collection, limit, offset);
		return json({
			collection,
			points: result.points,
			nextOffset: result.nextOffset,
			count: result.points.length
		});
	} catch (err) {
		return json({ error: 'Failed to scroll collection', detail: String(err) }, { status: 503 });
	}
};
