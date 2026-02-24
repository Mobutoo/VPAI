import type { RequestHandler } from './$types';
import { createSession, removeSession, sendSseEvent } from '$lib/server/mcp/sse';

export const GET: RequestHandler = async ({ locals, url }) => {
	// Auth check
	if (!locals.user?.authenticated) {
		return new Response('Unauthorized', { status: 401 });
	}

	const stream = new ReadableStream({
		start(controller) {
			const sessionId = createSession(controller);

			// Send the endpoint event per MCP SSE transport spec
			const postEndpoint = `${url.origin}/api/mcp`;
			sendSseEvent(controller, 'endpoint', postEndpoint);

			// Send session ID so client can correlate
			sendSseEvent(controller, 'session', JSON.stringify({ sessionId }));

			// Keepalive every 30s
			const keepalive = setInterval(() => {
				try {
					sendSseEvent(controller, 'ping', new Date().toISOString());
				} catch {
					clearInterval(keepalive);
					removeSession(sessionId);
				}
			}, 30000);

			// Store cleanup reference on controller for cancel handler
			(controller as unknown as { _cleanup: () => void })._cleanup = () => {
				clearInterval(keepalive);
				removeSession(sessionId);
			};
		},
		cancel(controller) {
			const ctrl = controller as unknown as { _cleanup?: () => void };
			ctrl._cleanup?.();
		}
	});

	return new Response(stream, {
		headers: {
			'Content-Type': 'text/event-stream',
			'Cache-Control': 'no-cache',
			'Connection': 'keep-alive',
			'X-Accel-Buffering': 'no'
		}
	});
};
