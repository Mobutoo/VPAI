import type { RequestHandler } from './$types';
import { subscribe } from '$lib/server/ws/openclaw';

export const GET: RequestHandler = async ({ request }) => {
	const stream = new ReadableStream({
		start(controller) {
			const encoder = new TextEncoder();

			const send = (event: string, data: unknown) => {
				controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
			};

			// Heartbeat every 30s to keep connection alive
			const heartbeat = setInterval(() => {
				send('ping', { ts: Date.now() });
			}, 30_000);

			// Subscribe to OpenClaw agent events
			const unsub = subscribe((evt) => {
				send('agent', evt);
			});

			// Cleanup on client disconnect
			request.signal.addEventListener('abort', () => {
				clearInterval(heartbeat);
				unsub();
			});

			send('connected', { ts: Date.now() });
		}
	});

	return new Response(stream, {
		headers: {
			'Content-Type': 'text/event-stream',
			'Cache-Control': 'no-cache',
			Connection: 'keep-alive'
		}
	});
};
