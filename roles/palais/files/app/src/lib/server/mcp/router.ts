import type { JsonRpcRequest, JsonRpcResponse } from './types';
import { MCP_METHODS, MCP_ERRORS } from './types';
import { getToolDefinitions } from './tools/registry';
import { executeToolCall } from './tools/executor';

export async function handleMcpRequest(request: JsonRpcRequest): Promise<JsonRpcResponse> {
	const { id, method, params } = request;

	if (!request.jsonrpc || request.jsonrpc !== '2.0') {
		return {
			jsonrpc: '2.0',
			id: id ?? null,
			error: { code: MCP_ERRORS.INVALID_REQUEST, message: 'Invalid JSON-RPC version' }
		};
	}

	switch (method) {
		case MCP_METHODS.INITIALIZE:
			return {
				jsonrpc: '2.0',
				id,
				result: {
					protocolVersion: '2024-11-05',
					serverInfo: { name: 'palais', version: '1.0.0' },
					capabilities: { tools: {} }
				}
			};

		case MCP_METHODS.LIST_TOOLS:
			return {
				jsonrpc: '2.0',
				id,
				result: { tools: getToolDefinitions() }
			};

		case MCP_METHODS.CALL_TOOL: {
			const toolName = (params as Record<string, unknown>)?.name as string;
			const toolArgs = (params as Record<string, unknown>)?.arguments as Record<string, unknown> ?? {};

			if (!toolName) {
				return {
					jsonrpc: '2.0',
					id,
					error: { code: MCP_ERRORS.INVALID_PARAMS, message: 'Missing tool name' }
				};
			}

			try {
				const result = await executeToolCall(toolName, toolArgs);
				return {
					jsonrpc: '2.0',
					id,
					result: { content: [{ type: 'text', text: JSON.stringify(result) }] }
				};
			} catch (err) {
				const message = err instanceof Error ? err.message : 'Unknown error';
				return {
					jsonrpc: '2.0',
					id,
					error: { code: MCP_ERRORS.INTERNAL_ERROR, message }
				};
			}
		}

		default:
			return {
				jsonrpc: '2.0',
				id,
				error: { code: MCP_ERRORS.METHOD_NOT_FOUND, message: `Unknown method: ${method}` }
			};
	}
}
