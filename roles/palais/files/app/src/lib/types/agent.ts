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
};
