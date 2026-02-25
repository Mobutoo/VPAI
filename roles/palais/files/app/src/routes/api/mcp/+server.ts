import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { handleMcpRequest } from '$lib/server/mcp/router';
import type { JsonRpcRequest } from '$lib/server/mcp/types';
import { MCP_ERRORS } from '$lib/server/mcp/types';

export const POST: RequestHandler = async ({ request, locals }) => {
	// Auth check — API key required (hooks.server.ts enforces globally, this is a safety net)
	if (!locals.user?.authenticated) {
		return json({
			jsonrpc: '2.0',
			id: null,
			error: { code: -32001, message: 'Unauthorized: X-API-Key required' }
		}, { status: 401 });
	}

	let body: JsonRpcRequest;
	try {
		body = await request.json();
	} catch {
		return json({
			jsonrpc: '2.0',
			id: null,
			error: { code: MCP_ERRORS.PARSE_ERROR, message: 'Invalid JSON' }
		}, { status: 400 });
	}

	const response = await handleMcpRequest(body);
	return json(response);
};
