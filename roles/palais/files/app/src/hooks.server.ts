import type { Handle } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { building } from '$app/environment';
import { connectOpenClaw } from '$lib/server/ws/openclaw';
import { startBudgetCron } from '$lib/server/budget/cron';

const API_KEY = env.PALAIS_API_KEY || 'dev-key';

if (!building) {
	connectOpenClaw();
	startBudgetCron();
}

export const handle: Handle = async ({ event, resolve }) => {
	// API key auth (agents, n8n, MCP)
	const apiKey = event.request.headers.get('x-api-key');
	if (apiKey && apiKey === API_KEY) {
		event.locals.user = { authenticated: true, source: 'api' };
		return resolve(event);
	}

	// Cookie auth (browser)
	const session = event.cookies.get('palais_session');
	if (session) {
		event.locals.user = { authenticated: true, source: 'cookie' };
		return resolve(event);
	}

	// Public routes
	const publicPaths = ['/login', '/api/auth/login', '/api/health', '/dl/'];
	const isPublic = publicPaths.some((p) => event.url.pathname.startsWith(p));

	if (!isPublic && event.url.pathname.startsWith('/api/')) {
		return new Response(JSON.stringify({ error: 'Unauthorized' }), {
			status: 401,
			headers: { 'Content-Type': 'application/json' }
		});
	}

	if (!isPublic) {
		return new Response(null, {
			status: 302,
			headers: { Location: '/login' }
		});
	}

	event.locals.user = { authenticated: false, source: 'none' };
	return resolve(event);
};
