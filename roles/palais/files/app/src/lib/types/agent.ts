// Shared types — safe to import on both server and client

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
	// span.* events
	span?: {
		id: string;           // external span ID (from OpenClaw)
		parentId?: string;    // parent span external ID
		type: 'llm_call' | 'tool_call' | 'decision' | 'delegation';
		name: string;
		input?: unknown;
		output?: unknown;
		model?: string;
		tokensIn?: number;
		tokensOut?: number;
		cost?: number;
		startedAt?: string;   // ISO
		endedAt?: string;     // ISO
		durationMs?: number;
		error?: unknown;
	};
};
