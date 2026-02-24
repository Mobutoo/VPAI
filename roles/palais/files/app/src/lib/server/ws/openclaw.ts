import WebSocket from 'ws';
import { env } from '$env/dynamic/private';
import { db } from '$lib/server/db';
import { agents, agentSessions, agentSpans } from '$lib/server/db/schema';
import { eq, and } from 'drizzle-orm';

// Map external span IDs → internal DB IDs (for parent lookups within same process)
const spanIdMap = new Map<string, number>();
import type { AgentEvent } from '$lib/types/agent';

export type { AgentEvent };

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

const listeners = new Set<(event: AgentEvent) => void>();

export function subscribe(fn: (event: AgentEvent) => void) {
	listeners.add(fn);
	return () => listeners.delete(fn);
}

function broadcast(event: AgentEvent) {
	for (const fn of listeners) fn(event);
}

async function handleMessage(data: string) {
	try {
		const event: AgentEvent = JSON.parse(data);

		if (event.type === 'agent.status') {
			await db
				.update(agents)
				.set({
					status: event.status as 'idle' | 'busy' | 'error' | 'offline',
					currentTaskId: event.taskId ?? null,
					lastSeenAt: new Date()
				})
				.where(eq(agents.id, event.agentId));
		}

		if (event.type === 'session.started') {
			await db.insert(agentSessions).values({
				agentId: event.agentId,
				taskId: event.taskId,
				model: event.model,
				status: 'running'
			});
		}

		if (event.type === 'session.completed') {
			// Find the latest running session for this agent and close it
			const [running] = await db
				.select({ id: agentSessions.id })
				.from(agentSessions)
				.where(
					and(
						eq(agentSessions.agentId, event.agentId),
						eq(agentSessions.status, 'running')
					)
				)
				.orderBy(agentSessions.startedAt)
				.limit(1);

			if (running) {
				await db
					.update(agentSessions)
					.set({
						status: 'completed',
						endedAt: new Date(),
						totalTokens: event.tokens ?? 0,
						totalCost: event.cost ?? 0,
						summary: event.summary ?? null
					})
					.where(eq(agentSessions.id, running.id));

				// Calculate confidence score for completed session
				calculateAndStoreConfidence(running.id).catch(console.error);
			}
		}

		// ── span.* events ───────────────────────────────────────────────────────
		if ((event.type === 'span.started' || event.type === 'span.completed') && event.span) {
			const span = event.span;

			// Resolve session ID
			const sessionId = event.sessionId ?? await resolveSessionId(event.agentId);
			if (!sessionId) { broadcast(event); return; }

			if (event.type === 'span.started') {
				const parentDbId = span.parentId ? (spanIdMap.get(span.parentId) ?? null) : null;
				const [inserted] = await db.insert(agentSpans).values({
					sessionId,
					parentSpanId: parentDbId,
					type: span.type,
					name: span.name,
					input: span.input ?? null,
					model: span.model ?? null,
					tokensIn: span.tokensIn ?? 0,
					tokensOut: span.tokensOut ?? 0,
					cost: span.cost ?? 0,
					startedAt: span.startedAt ? new Date(span.startedAt) : new Date(),
					error: span.error ?? null
				}).returning({ id: agentSpans.id });

				if (inserted && span.id) spanIdMap.set(span.id, inserted.id);
			}

			if (event.type === 'span.completed' && span.id) {
				const dbId = spanIdMap.get(span.id);
				if (dbId) {
					await db.update(agentSpans).set({
						output: span.output ?? null,
						tokensIn: span.tokensIn ?? 0,
						tokensOut: span.tokensOut ?? 0,
						cost: span.cost ?? 0,
						endedAt: span.endedAt ? new Date(span.endedAt) : new Date(),
						durationMs: span.durationMs ?? null,
						error: span.error ?? null
					}).where(eq(agentSpans.id, dbId));
					// Clean up map entry to avoid unbounded growth
					spanIdMap.delete(span.id);
				}
			}
		}

		broadcast(event);
	} catch (err) {
		console.error('[WS] Parse error:', err);
	}
}

export function connectOpenClaw() {
	const url = env.OPENCLAW_WS_URL || 'ws://openclaw:18789';
	console.log(`[WS] Connecting to OpenClaw: ${url}`);

	ws = new WebSocket(url);

	ws.on('open', () => {
		console.log('[WS] Connected to OpenClaw Gateway');
		if (reconnectTimer) clearTimeout(reconnectTimer);
	});

	ws.on('message', (data) => handleMessage(data.toString()));

	ws.on('close', () => {
		console.log('[WS] Disconnected, reconnecting in 10s...');
		reconnectTimer = setTimeout(connectOpenClaw, 10_000);
	});

	ws.on('error', (err) => {
		console.error('[WS] Error:', err.message);
		ws?.close();
	});
}

export function disconnectOpenClaw() {
	if (reconnectTimer) clearTimeout(reconnectTimer);
	ws?.close();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function resolveSessionId(agentId: string): Promise<number | null> {
	const [session] = await db.select({ id: agentSessions.id })
		.from(agentSessions)
		.where(and(eq(agentSessions.agentId, agentId), eq(agentSessions.status, 'running')))
		.orderBy(agentSessions.startedAt)
		.limit(1);
	return session?.id ?? null;
}

/**
 * Calculate confidence score after a session completes.
 * Score = 1.0 − error_penalty − retry_penalty − token_overage_penalty (clamped 0–1)
 */
async function calculateAndStoreConfidence(sessionId: number): Promise<void> {
	const spans = await db.select().from(agentSpans).where(eq(agentSpans.sessionId, sessionId));
	if (spans.length === 0) return;

	const totalSpans = spans.length;
	const errorSpans = spans.filter((s) => s.error !== null).length;
	const retrySpans = spans.filter((s) =>
		typeof s.name === 'string' && s.name.toLowerCase().includes('retry')
	).length;

	// Penalties
	const errorPenalty = Math.min(0.6, (errorSpans / totalSpans) * 0.8);
	const retryPenalty = Math.min(0.3, (retrySpans / totalSpans) * 0.4);
	const confidence = Math.max(0, Math.min(1, 1 - errorPenalty - retryPenalty));

	const [session] = await db.select({ taskId: agentSessions.taskId })
		.from(agentSessions).where(eq(agentSessions.id, sessionId));

	await db.update(agentSessions)
		.set({ confidenceScore: confidence })
		.where(eq(agentSessions.id, sessionId));

	// Propagate to task if linked
	if (session?.taskId) {
		const { tasks } = await import('$lib/server/db/schema');
		await db.update(tasks)
			.set({ confidenceScore: confidence })
			.where(eq(tasks.id, session.taskId));
	}
}
