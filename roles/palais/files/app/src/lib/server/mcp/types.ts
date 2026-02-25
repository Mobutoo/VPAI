// JSON-RPC 2.0 types for MCP protocol

export interface JsonRpcRequest {
	jsonrpc: '2.0';
	id: string | number;
	method: string;
	params?: Record<string, unknown>;
}

export interface JsonRpcResponse {
	jsonrpc: '2.0';
	id: string | number | null;
	result?: unknown;
	error?: {
		code: number;
		message: string;
		data?: unknown;
	};
}

export interface McpToolDefinition {
	name: string;
	description: string;
	inputSchema: Record<string, unknown>;
	outputSchema?: Record<string, unknown>;
}

// MCP method constants
export const MCP_METHODS = {
	INITIALIZE: 'initialize',
	LIST_TOOLS: 'tools/list',
	CALL_TOOL: 'tools/call',
} as const;

// Error codes
export const MCP_ERRORS = {
	PARSE_ERROR: -32700,
	INVALID_REQUEST: -32600,
	METHOD_NOT_FOUND: -32601,
	INVALID_PARAMS: -32602,
	INTERNAL_ERROR: -32603,
	TOOL_NOT_FOUND: -32000,
} as const;
