/**
 * Test script: simulate an agent calling Palais MCP endpoint.
 * Usage: PALAIS_URL=http://localhost:3300 PALAIS_API_KEY=dev-key tsx scripts/test-mcp.ts
 */

const PALAIS_URL = process.env.PALAIS_URL || 'http://localhost:3300';
const API_KEY = process.env.PALAIS_API_KEY || 'dev-key';

async function mcpCall(method: string, toolName?: string, args?: Record<string, unknown>) {
	const body: Record<string, unknown> = {
		jsonrpc: '2.0',
		id: Date.now(),
		method,
	};

	if (toolName) {
		body.params = { name: toolName, arguments: args ?? {} };
	}

	const res = await fetch(`${PALAIS_URL}/api/mcp`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-API-Key': API_KEY
		},
		body: JSON.stringify(body)
	});

	return res.json();
}

async function runTests() {
	console.log('=== MCP Integration Test ===');
	console.log(`URL: ${PALAIS_URL}\n`);

	let passed = 0;
	let failed = 0;

	// Test 1: Initialize
	console.log('1. initialize...');
	const init = await mcpCall('initialize');
	if (init.result?.serverInfo?.name === 'palais') {
		console.log(`   ✓ Server: ${init.result.serverInfo.name} v${init.result.serverInfo.version}`);
		console.log(`   ✓ Protocol: ${init.result.protocolVersion}`);
		passed++;
	} else {
		console.log('   ✗ Initialize failed:', JSON.stringify(init));
		failed++;
	}

	// Test 2: List tools
	console.log('\n2. tools/list...');
	const toolsList = await mcpCall('tools/list');
	const tools = toolsList.result?.tools ?? [];
	if (tools.length >= 17) {
		console.log(`   ✓ Found ${tools.length} tools`);
		for (const tool of tools) {
			console.log(`     - ${tool.name}`);
		}
		passed++;
	} else {
		console.log(`   ✗ Expected ≥17 tools, got ${tools.length}`);
		failed++;
	}

	// Test 3: palais.tasks.list
	console.log('\n3. palais.tasks.list...');
	const taskResult = await mcpCall('tools/call', 'palais.tasks.list', { limit: 5 });
	if (taskResult.result?.content) {
		const content = JSON.parse(taskResult.result.content[0].text ?? '[]');
		console.log(`   ✓ Found ${Array.isArray(content) ? content.length : 0} tasks`);
		passed++;
	} else {
		console.log('   ✗ palais.tasks.list failed:', taskResult.error?.message);
		failed++;
	}

	// Test 4: palais.agents.status
	console.log('\n4. palais.agents.status...');
	const agentResult = await mcpCall('tools/call', 'palais.agents.status', {});
	if (agentResult.result?.content) {
		const agentList = JSON.parse(agentResult.result.content[0].text ?? '[]');
		console.log(`   ✓ Found ${Array.isArray(agentList) ? agentList.length : 0} agents`);
		passed++;
	} else {
		console.log('   ✗ palais.agents.status failed:', agentResult.error?.message);
		failed++;
	}

	// Test 5: palais.budget.remaining
	console.log('\n5. palais.budget.remaining...');
	const budgetResult = await mcpCall('tools/call', 'palais.budget.remaining', {});
	if (budgetResult.result?.content) {
		const budget = JSON.parse(budgetResult.result.content[0].text ?? '{}');
		console.log(`   ✓ Budget: $${budget.remaining} remaining (${budget.percentUsed}% used)`);
		passed++;
	} else {
		console.log('   ✗ palais.budget.remaining failed:', budgetResult.error?.message);
		failed++;
	}

	// Test 6: Unknown tool (should fail gracefully)
	console.log('\n6. Unknown tool (should return error)...');
	const unknownResult = await mcpCall('tools/call', 'palais.nonexistent.tool', {});
	if (unknownResult.error) {
		console.log(`   ✓ Error returned: ${unknownResult.error.message}`);
		passed++;
	} else {
		console.log('   ✗ Expected error but got result');
		failed++;
	}

	// Test 7: Auth failure (no API key)
	console.log('\n7. Auth failure (no X-API-Key)...');
	const noAuthRes = await fetch(`${PALAIS_URL}/api/mcp`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize' })
	});
	if (noAuthRes.status === 401) {
		console.log(`   ✓ Status 401 returned (as expected)`);
		passed++;
	} else {
		console.log(`   ✗ Expected 401, got ${noAuthRes.status}`);
		failed++;
	}

	console.log(`\n=== Results: ${passed} passed, ${failed} failed ===`);
	if (failed > 0) process.exit(1);
}

runTests().catch((err) => {
	console.error('Test script error:', err);
	process.exit(1);
});
