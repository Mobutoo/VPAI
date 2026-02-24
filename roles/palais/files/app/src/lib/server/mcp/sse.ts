/**
 * MCP SSE transport helper.
 * The SSE endpoint keeps a connection open.
 * Clients send JSON-RPC requests to POST /api/mcp and receive responses here.
 * This implements the MCP "SSE transport" pattern:
 *   - GET /api/mcp/sse → opens SSE stream, sends `endpoint` event with POST URL
 *   - Client sends JSON-RPC to POST /api/mcp with session header
 *   - Server pushes response back through SSE stream
 */

export interface SseSession {
	id: string;
	controller: ReadableStreamDefaultController;
	createdAt: Date;
}

// In-memory session store (single-process, sufficient for Palais)
const sessions = new Map<string, SseSession>();

export function createSession(controller: ReadableStreamDefaultController): string {
	const id = crypto.randomUUID();
	sessions.set(id, { id, controller, createdAt: new Date() });
	return id;
}

export function getSession(id: string): SseSession | undefined {
	return sessions.get(id);
}

export function removeSession(id: string): void {
	sessions.delete(id);
}

export function sendSseEvent(
	controller: ReadableStreamDefaultController,
	event: string,
	data: string
): void {
	const message = `event: ${event}\ndata: ${data}\n\n`;
	controller.enqueue(new TextEncoder().encode(message));
}

// Cleanup stale sessions (older than 1 hour)
export function cleanupStaleSessions(): void {
	const now = Date.now();
	for (const [id, session] of sessions) {
		if (now - session.createdAt.getTime() > 3600000) {
			sessions.delete(id);
		}
	}
}
