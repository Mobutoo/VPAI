import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

const ADMIN_PASSWORD = env.PALAIS_ADMIN_PASSWORD || 'admin';

export const POST: RequestHandler = async ({ request, cookies }) => {
	const { password } = await request.json();

	if (password !== ADMIN_PASSWORD) {
		return json({ error: 'Invalid password' }, { status: 401 });
	}

	cookies.set('palais_session', `s_${Date.now()}_${crypto.randomUUID()}`, {
		httpOnly: true,
		secure: true,
		sameSite: 'strict',
		maxAge: 60 * 60 * 24 * 7,
		path: '/'
	});

	return json({ success: true });
};
