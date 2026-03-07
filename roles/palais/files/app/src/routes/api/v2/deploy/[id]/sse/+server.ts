import { db } from '$lib/server/db';
import { deployments, deploymentSteps } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

const POLL_INTERVAL_MS = 2_000;
const MAX_DURATION_MS = 5 * 60 * 1_000;
const TERMINAL_STATUSES = new Set(['success', 'failed', 'cancelled']);

export const GET: RequestHandler = async ({ params, request }) => {
	const deploymentId = parseInt(params.id, 10);
	if (isNaN(deploymentId)) {
		return err('Invalid deployment id', 400);
	}

	const encoder = new TextEncoder();

	const stream = new ReadableStream({
		start(controller) {
			let pollTimer: ReturnType<typeof setTimeout> | null = null;
			let done = false;

			const deadline = setTimeout(() => {
				if (!done) {
					controller.enqueue(encoder.encode('event: done\ndata: {"reason":"timeout"}\n\n'));
					controller.close();
					done = true;
				}
			}, MAX_DURATION_MS);

			const cleanup = () => {
				done = true;
				if (pollTimer !== null) clearTimeout(pollTimer);
				clearTimeout(deadline);
			};

			request.signal.addEventListener('abort', () => {
				cleanup();
			});

			const poll = async () => {
				if (done) return;

				try {
					const steps = await db
						.select()
						.from(deploymentSteps)
						.where(eq(deploymentSteps.deploymentId, deploymentId))
						.orderBy(asc(deploymentSteps.position));

					const stepsEvent =
						`event: steps\ndata: ${JSON.stringify(steps)}\n\n`;
					controller.enqueue(encoder.encode(stepsEvent));

					const [deployment] = await db
						.select({ status: deployments.status })
						.from(deployments)
						.where(eq(deployments.id, deploymentId));

					if (deployment && TERMINAL_STATUSES.has(deployment.status)) {
						controller.enqueue(
							encoder.encode(
								`event: done\ndata: ${JSON.stringify({ status: deployment.status })}\n\n`
							)
						);
						controller.close();
						cleanup();
						return;
					}
				} catch {
					// Swallow transient DB errors; keep polling
				}

				if (!done) {
					pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
				}
			};

			// Start first poll immediately
			poll();
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
