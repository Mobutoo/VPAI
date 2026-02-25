import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { deliverables } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';

// GET /dl/:token — public download endpoint (token = auth)
export const GET: RequestHandler = async ({ params }) => {
	const { token } = params;

	const [entry] = await db.select()
		.from(deliverables)
		.where(eq(deliverables.downloadToken, token));

	if (!entry) throw error(404, 'File not found');

	if (!existsSync(entry.storagePath)) {
		throw error(410, 'File no longer available');
	}

	const buffer = await readFile(entry.storagePath);

	const mimeType = entry.mimeType ?? 'application/octet-stream';
	const disposition = isInlineType(mimeType)
		? `inline; filename="${entry.filename}"`
		: `attachment; filename="${entry.filename}"`;

	return new Response(buffer, {
		headers: {
			'Content-Type': mimeType,
			'Content-Disposition': disposition,
			'Content-Length': String(buffer.length),
			'Cache-Control': 'private, max-age=3600'
		}
	});
};

// Types that can be previewed inline in browser
function isInlineType(mime: string): boolean {
	return (
		mime.startsWith('image/') ||
		mime === 'application/pdf' ||
		mime === 'text/plain' ||
		mime === 'text/markdown' ||
		mime === 'text/html'
	);
}
