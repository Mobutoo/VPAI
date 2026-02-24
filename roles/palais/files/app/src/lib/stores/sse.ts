import { browser } from '$app/environment';
import type { AgentEvent } from '$lib/types/agent';

type SSECallback = (event: AgentEvent) => void;

let eventSource: EventSource | null = null;
const listeners = new Set<SSECallback>();

export function connectSSE() {
	if (!browser || eventSource) return;

	eventSource = new EventSource('/api/sse');

	eventSource.addEventListener('agent', (e) => {
		const data: AgentEvent = JSON.parse((e as MessageEvent).data);
		for (const fn of listeners) fn(data);
	});

	eventSource.onerror = () => {
		eventSource?.close();
		eventSource = null;
		setTimeout(connectSSE, 5_000);
	};
}

export function onAgentEvent(fn: SSECallback) {
	listeners.add(fn);
	return () => listeners.delete(fn);
}
