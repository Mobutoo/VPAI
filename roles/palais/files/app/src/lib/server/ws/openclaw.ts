import WebSocket from 'ws';
import { env } from '$env/dynamic/private';
import { db } from '$lib/server/db';
import { agents, agentSessions } from '$lib/server/db/schema';
import { eq, and } from 'drizzle-orm';

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export type AgentEvent = {
	type: string;
	agentId: string;
	sessionId?: number;
	status?: string;
	taskId?: number;
	model?: string;
	tokens?: number;
	cost?: number;
	summary?: string;
};

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
