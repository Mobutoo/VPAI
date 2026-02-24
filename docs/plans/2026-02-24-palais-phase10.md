# Palais Phase 10 — MCP Server (Semaine 14)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose Palais as an MCP (Model Context Protocol) server so that OpenClaw agents can query tasks, projects, memory, budget, deliverables, and insights natively via JSON-RPC. Replace the legacy `kaneo-bridge` skill with a new `palais-bridge` skill that speaks MCP.

**Architecture:** MCP JSON-RPC endpoint (`POST /api/mcp`) and SSE transport (`GET /api/mcp/sse`) inside the existing SvelteKit 5 app. Each MCP tool maps to an existing Palais API service layer function. Auth via `X-API-Key` header. The `palais-bridge` OpenClaw skill is an Ansible-templated `SKILL.md.j2` that instructs agents to use MCP tools instead of raw curl.

**Tech Stack:** SvelteKit 5 (runes), JSON-RPC 2.0, Server-Sent Events, Drizzle ORM, PostgreSQL, Qdrant, Ansible Jinja2 templates

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 10 (MCP Server), Skill OpenClaw `palais-bridge` section.

**Dependencies:** Phases 1-9 must be complete (API routes, DB schema, Knowledge Graph, Budget Intelligence, Time Tracking, Deliverables all functional).

---

## Task 1: MCP JSON-RPC Endpoint

**Files:**
- Create: `roles/palais/files/app/src/routes/api/mcp/+server.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/router.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/types.ts`

**Step 1: Define MCP types**

Create `roles/palais/files/app/src/lib/server/mcp/types.ts`:
```typescript
// JSON-RPC 2.0 types for MCP protocol

export interface JsonRpcRequest {
	jsonrpc: '2.0';
	id: string | number;
	method: string;
	params?: Record<string, unknown>;
}

export interface JsonRpcResponse {
	jsonrpc: '2.0';
	id: string | number;
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
```

**Step 2: Create MCP router**

Create `roles/palais/files/app/src/lib/server/mcp/router.ts`:
```typescript
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
				return { jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: JSON.stringify(result) }] } };
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
```

**Step 3: Create POST endpoint**

Create `roles/palais/files/app/src/routes/api/mcp/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { handleMcpRequest } from '$lib/server/mcp/router';
import type { JsonRpcRequest } from '$lib/server/mcp/types';
import { MCP_ERRORS } from '$lib/server/mcp/types';

export const POST: RequestHandler = async ({ request, locals }) => {
	// Auth check — API key required
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
```

**Step 4: Commit**

```bash
git add roles/palais/files/app/src/lib/server/mcp/ roles/palais/files/app/src/routes/api/mcp/
git commit -m "feat(palais): MCP JSON-RPC endpoint — POST /api/mcp with router"
```

---

## Task 2: MCP SSE Transport

**Files:**
- Create: `roles/palais/files/app/src/routes/api/mcp/sse/+server.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/sse.ts`

**Step 1: Create SSE helper**

Create `roles/palais/files/app/src/lib/server/mcp/sse.ts`:
```typescript
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

export function sendSseEvent(controller: ReadableStreamDefaultController, event: string, data: string): void {
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
```

**Step 2: Create SSE GET endpoint**

Create `roles/palais/files/app/src/routes/api/mcp/sse/+server.ts`:
```typescript
import type { RequestHandler } from './$types';
import { createSession, removeSession, sendSseEvent } from '$lib/server/mcp/sse';

export const GET: RequestHandler = async ({ locals, url }) => {
	// Auth check
	if (!locals.user?.authenticated) {
		return new Response('Unauthorized', { status: 401 });
	}

	const stream = new ReadableStream({
		start(controller) {
			const sessionId = createSession(controller);

			// Send the endpoint event per MCP SSE transport spec
			const postEndpoint = `${url.origin}/api/mcp`;
			sendSseEvent(controller, 'endpoint', postEndpoint);

			// Send session ID so client can correlate
			sendSseEvent(controller, 'session', JSON.stringify({ sessionId }));

			// Keepalive every 30s
			const keepalive = setInterval(() => {
				try {
					sendSseEvent(controller, 'ping', new Date().toISOString());
				} catch {
					clearInterval(keepalive);
					removeSession(sessionId);
				}
			}, 30000);

			// Cleanup on close
			const cleanup = () => {
				clearInterval(keepalive);
				removeSession(sessionId);
			};

			// The controller's cancel will be called when the client disconnects
			controller.enqueue(new TextEncoder().encode('')); // flush
		},
		cancel() {
			// Stream cancelled by client
		}
	});

	return new Response(stream, {
		headers: {
			'Content-Type': 'text/event-stream',
			'Cache-Control': 'no-cache',
			'Connection': 'keep-alive',
			'X-Accel-Buffering': 'no'
		}
	});
};
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/lib/server/mcp/sse.ts roles/palais/files/app/src/routes/api/mcp/sse/
git commit -m "feat(palais): MCP SSE transport — GET /api/mcp/sse with session management"
```

---

## Task 3: Tool Handlers Implementation

**Files:**
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/registry.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/executor.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/tasks.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/projects.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/agents.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/budget.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/deliverables.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/memory.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/insights.ts`
- Create: `roles/palais/files/app/src/lib/server/mcp/tools/standup.ts`

**Step 1: Create tool registry**

Create `roles/palais/files/app/src/lib/server/mcp/tools/registry.ts`:
```typescript
import type { McpToolDefinition } from '../types';
import { taskToolDefs } from './tasks';
import { projectToolDefs } from './projects';
import { agentToolDefs } from './agents';
import { budgetToolDefs } from './budget';
import { deliverableToolDefs } from './deliverables';
import { memoryToolDefs } from './memory';
import { insightToolDefs } from './insights';
import { standupToolDefs } from './standup';

export function getToolDefinitions(): McpToolDefinition[] {
	return [
		...taskToolDefs,
		...projectToolDefs,
		...agentToolDefs,
		...budgetToolDefs,
		...deliverableToolDefs,
		...memoryToolDefs,
		...insightToolDefs,
		...standupToolDefs,
	];
}
```

**Step 2: Create tool executor**

Create `roles/palais/files/app/src/lib/server/mcp/tools/executor.ts`:
```typescript
import { handleTasksTool } from './tasks';
import { handleProjectsTool } from './projects';
import { handleAgentsTool } from './agents';
import { handleBudgetTool } from './budget';
import { handleDeliverablesTool } from './deliverables';
import { handleMemoryTool } from './memory';
import { handleInsightsTool } from './insights';
import { handleStandupTool } from './standup';

const handlers: Record<string, (args: Record<string, unknown>) => Promise<unknown>> = {};

// Register all tool handlers
function registerPrefix(
	prefix: string,
	handler: (method: string, args: Record<string, unknown>) => Promise<unknown>
) {
	// We store a resolver that extracts the sub-method
	handlers[prefix] = async (args) => handler('', args);
}

export async function executeToolCall(
	toolName: string,
	args: Record<string, unknown>
): Promise<unknown> {
	// Route by prefix: palais.tasks.list -> tasks handler with method "list"
	const parts = toolName.split('.');
	if (parts.length < 3 || parts[0] !== 'palais') {
		throw new Error(`Unknown tool: ${toolName}`);
	}

	const domain = parts[1]; // tasks, projects, agents, etc.
	const method = parts.slice(2).join('.'); // list, create, etc.

	switch (domain) {
		case 'tasks':
			return handleTasksTool(method, args);
		case 'projects':
			return handleProjectsTool(method, args);
		case 'agents':
			return handleAgentsTool(method, args);
		case 'budget':
			return handleBudgetTool(method, args);
		case 'deliverables':
			return handleDeliverablesTool(method, args);
		case 'memory':
			return handleMemoryTool(method, args);
		case 'insights':
			return handleInsightsTool(method, args);
		case 'standup':
			return handleStandupTool(method, args);
		default:
			throw new Error(`Unknown tool domain: ${domain}`);
	}
}
```

**Step 3: Tasks tool handler**

Create `roles/palais/files/app/src/lib/server/mcp/tools/tasks.ts`:
```typescript
import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { tasks, comments, timeEntries } from '$lib/server/db/schema';
import { eq, and, desc } from 'drizzle-orm';

export const taskToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.tasks.list',
		description: 'List tasks with optional filters by project, status, agent, priority',
		inputSchema: {
			type: 'object',
			properties: {
				projectId: { type: 'number', description: 'Filter by project ID' },
				status: { type: 'string', description: 'Filter by status (backlog, in-progress, review, done)' },
				assigneeAgentId: { type: 'string', description: 'Filter by assigned agent ID' },
				priority: { type: 'string', description: 'Filter by priority (none, low, medium, high, urgent)' },
				limit: { type: 'number', description: 'Max results (default 50)' }
			}
		}
	},
	{
		name: 'palais.tasks.create',
		description: 'Create a new task in a project',
		inputSchema: {
			type: 'object',
			properties: {
				projectId: { type: 'number', description: 'Project ID' },
				columnId: { type: 'number', description: 'Column ID' },
				title: { type: 'string', description: 'Task title' },
				description: { type: 'string', description: 'Task description (rich text)' },
				priority: { type: 'string', description: 'Priority level' },
				assigneeAgentId: { type: 'string', description: 'Agent ID to assign' },
				estimatedCost: { type: 'number', description: 'Estimated cost in USD' }
			},
			required: ['projectId', 'columnId', 'title']
		}
	},
	{
		name: 'palais.tasks.update',
		description: 'Update a task (status, assignee, description, priority, etc.)',
		inputSchema: {
			type: 'object',
			properties: {
				taskId: { type: 'number', description: 'Task ID to update' },
				status: { type: 'string' },
				columnId: { type: 'number' },
				assigneeAgentId: { type: 'string' },
				description: { type: 'string' },
				priority: { type: 'string' },
				actualCost: { type: 'number' },
				confidenceScore: { type: 'number' }
			},
			required: ['taskId']
		}
	},
	{
		name: 'palais.tasks.comment',
		description: 'Add a comment to a task',
		inputSchema: {
			type: 'object',
			properties: {
				taskId: { type: 'number', description: 'Task ID' },
				content: { type: 'string', description: 'Comment text' },
				authorAgentId: { type: 'string', description: 'Agent ID authoring the comment' }
			},
			required: ['taskId', 'content']
		}
	},
	{
		name: 'palais.tasks.start_timer',
		description: 'Start a time tracking timer on a task',
		inputSchema: {
			type: 'object',
			properties: {
				taskId: { type: 'number', description: 'Task ID' },
				agentId: { type: 'string', description: 'Agent ID (null for manual timer)' }
			},
			required: ['taskId']
		}
	},
	{
		name: 'palais.tasks.stop_timer',
		description: 'Stop a running time tracking timer on a task',
		inputSchema: {
			type: 'object',
			properties: {
				taskId: { type: 'number', description: 'Task ID' },
				agentId: { type: 'string', description: 'Agent ID' }
			},
			required: ['taskId']
		}
	}
];

export async function handleTasksTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'list': {
			const conditions = [];
			if (args.projectId) conditions.push(eq(tasks.projectId, args.projectId as number));
			if (args.status) conditions.push(eq(tasks.status, args.status as string));
			if (args.assigneeAgentId) conditions.push(eq(tasks.assigneeAgentId, args.assigneeAgentId as string));

			const limit = (args.limit as number) || 50;
			const query = db.select().from(tasks);

			if (conditions.length > 0) {
				return query.where(and(...conditions)).limit(limit).orderBy(desc(tasks.updatedAt));
			}
			return query.limit(limit).orderBy(desc(tasks.updatedAt));
		}

		case 'create': {
			const [task] = await db.insert(tasks).values({
				projectId: args.projectId as number,
				columnId: args.columnId as number,
				title: args.title as string,
				description: (args.description as string) ?? null,
				priority: (args.priority as any) ?? 'none',
				assigneeAgentId: (args.assigneeAgentId as string) ?? null,
				estimatedCost: (args.estimatedCost as number) ?? null,
				creator: 'agent'
			}).returning();
			return task;
		}

		case 'update': {
			const taskId = args.taskId as number;
			const { taskId: _, ...updates } = args;
			const [updated] = await db.update(tasks)
				.set({ ...updates, updatedAt: new Date() })
				.where(eq(tasks.id, taskId))
				.returning();
			if (!updated) throw new Error(`Task ${taskId} not found`);
			return updated;
		}

		case 'comment': {
			const [comment] = await db.insert(comments).values({
				taskId: args.taskId as number,
				content: args.content as string,
				authorType: args.authorAgentId ? 'agent' : 'user',
				authorAgentId: (args.authorAgentId as string) ?? null
			}).returning();
			return comment;
		}

		case 'start_timer': {
			const [entry] = await db.insert(timeEntries).values({
				taskId: args.taskId as number,
				agentId: (args.agentId as string) ?? null,
				type: args.agentId ? 'auto' : 'manual',
				startedAt: new Date()
			}).returning();
			return entry;
		}

		case 'stop_timer': {
			const taskId = args.taskId as number;
			const agentId = (args.agentId as string) ?? null;

			// Find running timer for this task
			const conditions = [eq(timeEntries.taskId, taskId)];
			if (agentId) conditions.push(eq(timeEntries.agentId, agentId));

			const running = await db.select().from(timeEntries)
				.where(and(...conditions))
				.orderBy(desc(timeEntries.startedAt))
				.limit(1);

			if (running.length === 0 || running[0].endedAt) {
				throw new Error('No running timer found for this task');
			}

			const now = new Date();
			const duration = Math.floor((now.getTime() - running[0].startedAt.getTime()) / 1000);

			const [stopped] = await db.update(timeEntries)
				.set({ endedAt: now, durationSeconds: duration })
				.where(eq(timeEntries.id, running[0].id))
				.returning();
			return stopped;
		}

		default:
			throw new Error(`Unknown tasks method: ${method}`);
	}
}
```

**Step 4: Projects tool handler**

Create `roles/palais/files/app/src/lib/server/mcp/tools/projects.ts`:
```typescript
import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { projects, columns, tasks, timeEntries } from '$lib/server/db/schema';
import { eq, sql } from 'drizzle-orm';

export const projectToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.projects.list',
		description: 'List all projects',
		inputSchema: {
			type: 'object',
			properties: {
				workspaceId: { type: 'number', description: 'Filter by workspace ID' }
			}
		}
	},
	{
		name: 'palais.projects.create',
		description: 'Create a new project with default Kanban columns',
		inputSchema: {
			type: 'object',
			properties: {
				name: { type: 'string', description: 'Project name' },
				description: { type: 'string', description: 'Project description' },
				workspaceId: { type: 'number', description: 'Workspace ID (default: 1)' }
			},
			required: ['name']
		}
	},
	{
		name: 'palais.projects.analytics',
		description: 'Get project analytics: time spent, cost, iterations, agents involved',
		inputSchema: {
			type: 'object',
			properties: {
				projectId: { type: 'number', description: 'Project ID' }
			},
			required: ['projectId']
		}
	}
];

export async function handleProjectsTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'list': {
			if (args.workspaceId) {
				return db.select().from(projects)
					.where(eq(projects.workspaceId, args.workspaceId as number))
					.orderBy(projects.updatedAt);
			}
			return db.select().from(projects).orderBy(projects.updatedAt);
		}

		case 'create': {
			const name = args.name as string;
			const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
			const workspaceId = (args.workspaceId as number) || 1;

			const [project] = await db.insert(projects).values({
				workspaceId,
				name,
				slug,
				description: (args.description as string) ?? null
			}).returning();

			// Create default Kanban columns
			const defaultCols = ['Backlog', 'Planning', 'Assigned', 'In Progress', 'Review', 'Done'];
			for (let i = 0; i < defaultCols.length; i++) {
				await db.insert(columns).values({
					projectId: project.id,
					name: defaultCols[i],
					position: i,
					isFinal: i === defaultCols.length - 1
				});
			}

			return project;
		}

		case 'analytics': {
			const projectId = args.projectId as number;

			const projectTasks = await db.select().from(tasks)
				.where(eq(tasks.projectId, projectId));

			const totalCost = projectTasks.reduce((sum, t) => sum + (t.actualCost ?? 0), 0);
			const estimatedCost = projectTasks.reduce((sum, t) => sum + (t.estimatedCost ?? 0), 0);
			const completed = projectTasks.filter(t => t.status === 'done').length;
			const failed = projectTasks.filter(t => t.status === 'failed').length;
			const agentsInvolved = [...new Set(projectTasks.map(t => t.assigneeAgentId).filter(Boolean))];

			// Sum time entries
			const taskIds = projectTasks.map(t => t.id);
			let totalDuration = 0;
			if (taskIds.length > 0) {
				const entries = await db.select().from(timeEntries)
					.where(sql`${timeEntries.taskId} IN (${sql.join(taskIds.map(id => sql`${id}`), sql`, `)})`);
				totalDuration = entries.reduce((sum, e) => sum + (e.durationSeconds ?? 0), 0);
			}

			return {
				projectId,
				totalTasks: projectTasks.length,
				tasksCompleted: completed,
				tasksFailed: failed,
				totalCost,
				estimatedCost,
				totalDurationSeconds: totalDuration,
				agentsInvolved
			};
		}

		default:
			throw new Error(`Unknown projects method: ${method}`);
	}
}
```

**Step 5: Agents tool handler**

Create `roles/palais/files/app/src/lib/server/mcp/tools/agents.ts`:
```typescript
import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { agents } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const agentToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.agents.status',
		description: 'Get status of all agents (id, name, status, current task, last seen)',
		inputSchema: { type: 'object', properties: {} }
	},
	{
		name: 'palais.agents.available',
		description: 'List agents currently available (idle status)',
		inputSchema: { type: 'object', properties: {} }
	}
];

export async function handleAgentsTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'status':
			return db.select().from(agents).orderBy(agents.name);

		case 'available':
			return db.select().from(agents)
				.where(eq(agents.status, 'idle'))
				.orderBy(agents.name);

		default:
			throw new Error(`Unknown agents method: ${method}`);
	}
}
```

**Step 6: Budget tool handler**

Create `roles/palais/files/app/src/lib/server/mcp/tools/budget.ts`:
```typescript
import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { budgetSnapshots, budgetForecasts } from '$lib/server/db/schema';
import { desc, sql, gte } from 'drizzle-orm';

export const budgetToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.budget.remaining',
		description: 'Get remaining budget for today ($5/day cap)',
		inputSchema: { type: 'object', properties: {} }
	},
	{
		name: 'palais.budget.estimate',
		description: 'Estimate cost for a task based on agent history and model',
		inputSchema: {
			type: 'object',
			properties: {
				agentId: { type: 'string', description: 'Agent who would execute' },
				complexity: { type: 'string', description: 'low, medium, high' },
				model: { type: 'string', description: 'LLM model to use' }
			}
		}
	}
];

export async function handleBudgetTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'remaining': {
			const todayStart = new Date();
			todayStart.setHours(0, 0, 0, 0);

			const todaySnapshots = await db.select().from(budgetSnapshots)
				.where(gte(budgetSnapshots.capturedAt, todayStart));

			const totalSpent = todaySnapshots.reduce((sum, s) => sum + (s.spendAmount ?? 0), 0);
			const dailyBudget = 5.0; // $5/day from PRD

			return {
				dailyBudget,
				spent: Math.round(totalSpent * 100) / 100,
				remaining: Math.round((dailyBudget - totalSpent) * 100) / 100,
				percentUsed: Math.round((totalSpent / dailyBudget) * 100),
				date: todayStart.toISOString().split('T')[0]
			};
		}

		case 'estimate': {
			// Simple estimation based on complexity
			const complexity = (args.complexity as string) || 'medium';
			const estimates: Record<string, number> = {
				low: 0.05,
				medium: 0.25,
				high: 0.80
			};
			const estimate = estimates[complexity] ?? 0.25;

			return {
				estimatedCost: estimate,
				complexity,
				model: args.model || 'default',
				note: 'Estimate based on historical averages by complexity tier'
			};
		}

		default:
			throw new Error(`Unknown budget method: ${method}`);
	}
}
```

**Step 7: Deliverables tool handler**

Create `roles/palais/files/app/src/lib/server/mcp/tools/deliverables.ts`:
```typescript
import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { deliverables } from '$lib/server/db/schema';
import { eq, and } from 'drizzle-orm';

export const deliverableToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.deliverables.upload',
		description: 'Register a deliverable file for a task or project (file must already exist on disk)',
		inputSchema: {
			type: 'object',
			properties: {
				entityType: { type: 'string', description: 'task, project, or mission' },
				entityId: { type: 'number', description: 'ID of the task/project/mission' },
				filename: { type: 'string', description: 'Filename' },
				storagePath: { type: 'string', description: 'Relative path in deliverables directory' },
				mimeType: { type: 'string', description: 'MIME type' },
				sizeBytes: { type: 'number', description: 'File size in bytes' },
				agentId: { type: 'string', description: 'Agent ID uploading the file' }
			},
			required: ['entityType', 'entityId', 'filename', 'storagePath']
		}
	},
	{
		name: 'palais.deliverables.list',
		description: 'List deliverables for a task, project, or mission',
		inputSchema: {
			type: 'object',
			properties: {
				entityType: { type: 'string', description: 'task, project, or mission' },
				entityId: { type: 'number', description: 'ID of the entity' }
			},
			required: ['entityType', 'entityId']
		}
	}
];

export async function handleDeliverablesTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'upload': {
			const downloadToken = crypto.randomUUID();
			const [deliverable] = await db.insert(deliverables).values({
				entityType: args.entityType as any,
				entityId: args.entityId as number,
				filename: args.filename as string,
				storagePath: args.storagePath as string,
				mimeType: (args.mimeType as string) ?? 'application/octet-stream',
				sizeBytes: (args.sizeBytes as number) ?? null,
				downloadToken,
				uploadedByType: args.agentId ? 'agent' : 'system',
				uploadedByAgentId: (args.agentId as string) ?? null
			}).returning();
			return { ...deliverable, downloadUrl: `/dl/${downloadToken}` };
		}

		case 'list': {
			return db.select().from(deliverables)
				.where(and(
					eq(deliverables.entityType, args.entityType as any),
					eq(deliverables.entityId, args.entityId as number)
				));
		}

		default:
			throw new Error(`Unknown deliverables method: ${method}`);
	}
}
```

**Step 8: Memory tool handler**

Create `roles/palais/files/app/src/lib/server/mcp/tools/memory.ts`:
```typescript
import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { memoryNodes, memoryEdges } from '$lib/server/db/schema';
import { eq, desc, sql } from 'drizzle-orm';
import { env } from '$env/dynamic/private';

export const memoryToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.memory.search',
		description: 'Search the Knowledge Graph by semantic query (uses embeddings + full-text)',
		inputSchema: {
			type: 'object',
			properties: {
				query: { type: 'string', description: 'Natural language search query' },
				limit: { type: 'number', description: 'Max results (default 10)' },
				entityType: { type: 'string', description: 'Filter by entity type (agent, service, task, error, deployment, decision)' }
			},
			required: ['query']
		}
	},
	{
		name: 'palais.memory.recall',
		description: 'Recall a specific memory node by ID, including its edges',
		inputSchema: {
			type: 'object',
			properties: {
				nodeId: { type: 'number', description: 'Memory node ID' }
			},
			required: ['nodeId']
		}
	},
	{
		name: 'palais.memory.store',
		description: 'Store a new memory node in the Knowledge Graph',
		inputSchema: {
			type: 'object',
			properties: {
				type: { type: 'string', description: 'episodic, semantic, or procedural' },
				content: { type: 'string', description: 'Full content of the memory' },
				summary: { type: 'string', description: 'Brief summary' },
				entityType: { type: 'string', description: 'Entity type (agent, service, task, error, deployment, decision)' },
				entityId: { type: 'string', description: 'Related entity ID' },
				tags: { type: 'array', items: { type: 'string' }, description: 'Tags for categorization' }
			},
			required: ['type', 'content']
		}
	}
];

async function searchQdrant(query: string, limit: number): Promise<number[]> {
	const qdrantUrl = env.QDRANT_URL || 'http://qdrant:6333';
	const collection = env.QDRANT_COLLECTION || 'palais_memory';
	const litellmUrl = env.LITELLM_URL || 'http://litellm:4000';
	const litellmKey = env.LITELLM_KEY || '';

	try {
		// Get embedding from LiteLLM
		const embRes = await fetch(`${litellmUrl}/embeddings`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'Authorization': `Bearer ${litellmKey}`
			},
			body: JSON.stringify({
				model: 'text-embedding-3-small',
				input: query
			})
		});

		if (!embRes.ok) return [];
		const embData = await embRes.json();
		const vector = embData.data?.[0]?.embedding;
		if (!vector) return [];

		// Search Qdrant
		const searchRes = await fetch(`${qdrantUrl}/collections/${collection}/points/search`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				vector,
				limit,
				with_payload: true
			})
		});

		if (!searchRes.ok) return [];
		const searchData = await searchRes.json();
		return (searchData.result ?? []).map((r: any) => r.payload?.node_id).filter(Boolean);
	} catch {
		return [];
	}
}

export async function handleMemoryTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'search': {
			const query = args.query as string;
			const limit = (args.limit as number) || 10;

			// 1. Vector search via Qdrant
			const vectorNodeIds = await searchQdrant(query, limit);

			// 2. Full-text fallback via PostgreSQL
			const textResults = await db.select().from(memoryNodes)
				.where(sql`to_tsvector('english', ${memoryNodes.content}) @@ plainto_tsquery('english', ${query})`)
				.limit(limit);

			// Merge results: vector results first, then text results not already included
			const seenIds = new Set<number>();
			const results = [];

			if (vectorNodeIds.length > 0) {
				const vectorNodes = await db.select().from(memoryNodes)
					.where(sql`${memoryNodes.id} IN (${sql.join(vectorNodeIds.map(id => sql`${id}`), sql`, `)})`);
				for (const node of vectorNodes) {
					seenIds.add(node.id);
					results.push(node);
				}
			}

			for (const node of textResults) {
				if (!seenIds.has(node.id)) {
					results.push(node);
				}
			}

			return results.slice(0, limit);
		}

		case 'recall': {
			const nodeId = args.nodeId as number;
			const [node] = await db.select().from(memoryNodes)
				.where(eq(memoryNodes.id, nodeId));

			if (!node) throw new Error(`Memory node ${nodeId} not found`);

			// Get connected edges
			const edges = await db.select().from(memoryEdges)
				.where(sql`${memoryEdges.sourceNodeId} = ${nodeId} OR ${memoryEdges.targetNodeId} = ${nodeId}`);

			return { node, edges };
		}

		case 'store': {
			const [node] = await db.insert(memoryNodes).values({
				type: args.type as any,
				content: args.content as string,
				summary: (args.summary as string) ?? null,
				entityType: (args.entityType as any) ?? null,
				entityId: (args.entityId as string) ?? null,
				tags: (args.tags as string[]) ?? [],
				createdBy: 'agent'
			}).returning();

			// Async: generate embedding and store in Qdrant (fire and forget)
			generateAndStoreEmbedding(node.id, args.content as string).catch(() => {
				// Log but do not fail the MCP call
			});

			return node;
		}

		default:
			throw new Error(`Unknown memory method: ${method}`);
	}
}

async function generateAndStoreEmbedding(nodeId: number, content: string): Promise<void> {
	const qdrantUrl = env.QDRANT_URL || 'http://qdrant:6333';
	const collection = env.QDRANT_COLLECTION || 'palais_memory';
	const litellmUrl = env.LITELLM_URL || 'http://litellm:4000';
	const litellmKey = env.LITELLM_KEY || '';

	const embRes = await fetch(`${litellmUrl}/embeddings`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'Authorization': `Bearer ${litellmKey}`
		},
		body: JSON.stringify({ model: 'text-embedding-3-small', input: content })
	});

	if (!embRes.ok) return;
	const embData = await embRes.json();
	const vector = embData.data?.[0]?.embedding;
	if (!vector) return;

	const pointId = crypto.randomUUID();
	await fetch(`${qdrantUrl}/collections/${collection}/points`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			points: [{
				id: pointId,
				vector,
				payload: { node_id: nodeId, type: 'memory' }
			}]
		})
	});

	// Update node with embedding ID
	await db.update(memoryNodes)
		.set({ embeddingId: pointId })
		.where(eq(memoryNodes.id, nodeId));
}
```

**Step 9: Insights tool handler**

Create `roles/palais/files/app/src/lib/server/mcp/tools/insights.ts`:
```typescript
import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';

export const insightToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.insights.active',
		description: 'Get all active (non-acknowledged) insights',
		inputSchema: { type: 'object', properties: {} }
	}
];

export async function handleInsightsTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'active':
			return db.select().from(insights)
				.where(eq(insights.acknowledged, false))
				.orderBy(desc(insights.createdAt));

		default:
			throw new Error(`Unknown insights method: ${method}`);
	}
}
```

**Step 10: Standup tool handler**

Create `roles/palais/files/app/src/lib/server/mcp/tools/standup.ts`:
```typescript
import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';

export const standupToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.standup.latest',
		description: 'Get the latest digital standup briefing',
		inputSchema: { type: 'object', properties: {} }
	}
];

export async function handleStandupTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'latest': {
			// Standups are stored as insights with type 'standup'
			const [latest] = await db.select().from(insights)
				.where(eq(insights.type, 'standup'))
				.orderBy(desc(insights.createdAt))
				.limit(1);

			if (!latest) {
				return { message: 'No standup available yet', generated: false };
			}

			return {
				generated: true,
				title: latest.title,
				description: latest.description,
				suggestedActions: latest.suggestedActions,
				createdAt: latest.createdAt
			};
		}

		default:
			throw new Error(`Unknown standup method: ${method}`);
	}
}
```

**Step 11: Commit**

```bash
git add roles/palais/files/app/src/lib/server/mcp/tools/
git commit -m "feat(palais): MCP tool handlers — tasks, projects, agents, budget, deliverables, memory, insights, standup"
```

---

## Task 4: Tool Schema Definitions

**Files:**
- Modify: `roles/palais/files/app/src/lib/server/mcp/tools/registry.ts`

The tool schemas are already defined inline in each tool file's `*ToolDefs` arrays (see Task 3). This task ensures the `tools/list` MCP response returns properly formatted JSON Schema for every tool input.

**Step 1: Validate and test tool definitions**

No new files needed — the schemas are already embedded in each tool handler file (Tasks 3.3 through 3.10). Each `McpToolDefinition` has `name`, `description`, and `inputSchema` with JSON Schema format.

**Step 2: Add output schema annotations (optional enhancement)**

If needed, add `outputSchema` to tool definitions in each file. This is optional per MCP spec but useful for documentation.

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/lib/server/mcp/
git commit -m "feat(palais): validate MCP tool schema definitions — all 17 tools"
```

---

## Task 5: Auth — Validate X-API-Key on MCP Endpoints

**Files:**
- Modify: `roles/palais/files/app/src/hooks.server.ts`

**Step 1: Ensure MCP routes are protected**

The auth hook from Phase 1 already validates `X-API-Key` globally. Verify that `/api/mcp` and `/api/mcp/sse` are NOT in the public paths list. They should require authentication.

In `roles/palais/files/app/src/hooks.server.ts`, verify the public paths array does NOT include `/api/mcp`:
```typescript
const publicPaths = ['/login', '/api/health', '/dl/'];
// /api/mcp is NOT here — it requires X-API-Key auth
```

The MCP endpoint handlers (Task 1 and Task 2) already check `locals.user?.authenticated` and return 401 if not authenticated. No changes needed.

**Step 2: Commit (if changes were needed)**

```bash
git add roles/palais/files/app/src/hooks.server.ts
git commit -m "fix(palais): ensure MCP endpoints require X-API-Key auth"
```

---

## Task 6: OpenClaw Skill `palais-bridge`

**Files:**
- Create: `roles/openclaw/templates/skills/palais-bridge/SKILL.md.j2`
- Delete (or archive): `roles/openclaw/templates/skills/kaneo-bridge/SKILL.md.j2`

**Step 1: Create palais-bridge skill template**

Create `roles/openclaw/templates/skills/palais-bridge/SKILL.md.j2`:
```markdown
# Skill: palais-bridge

## Purpose
Bridge entre les agents OpenClaw et Palais (plateforme d'intelligence operationnelle).
Permet aux agents de gerer les taches, projets, memoire, budget et livrables via MCP JSON-RPC.

## Endpoint
- **URL**: `http://palais:{{ palais_port }}/api/mcp`
- **Auth**: Header `X-API-Key: {{ palais_api_key }}`
- **Protocol**: MCP JSON-RPC 2.0

## How to Call

Toutes les interactions avec Palais passent par un appel JSON-RPC POST:

```bash
curl -s -X POST http://palais:{{ palais_port }}/api/mcp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: {{ palais_api_key }}" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "<TOOL_NAME>",
      "arguments": { ... }
    }
  }'
```

## Available Tools

### Tasks
| Tool | Description |
|------|-------------|
| `palais.tasks.list` | Lister taches (filtres: projectId, status, assigneeAgentId, priority) |
| `palais.tasks.create` | Creer tache (projectId, columnId, title requis) |
| `palais.tasks.update` | Modifier tache (taskId requis + champs a modifier) |
| `palais.tasks.comment` | Ajouter commentaire (taskId, content requis) |
| `palais.tasks.start_timer` | Demarrer timer (taskId requis) |
| `palais.tasks.stop_timer` | Arreter timer (taskId requis) |

### Projects
| Tool | Description |
|------|-------------|
| `palais.projects.list` | Lister projets |
| `palais.projects.create` | Creer projet (name requis) |
| `palais.projects.analytics` | Analytics projet (projectId requis) |

### Agents
| Tool | Description |
|------|-------------|
| `palais.agents.status` | Statut de tous les agents |
| `palais.agents.available` | Agents disponibles (idle) |

### Budget
| Tool | Description |
|------|-------------|
| `palais.budget.remaining` | Budget restant aujourd'hui |
| `palais.budget.estimate` | Estimer cout d'une tache |

### Deliverables
| Tool | Description |
|------|-------------|
| `palais.deliverables.upload` | Enregistrer un livrable |
| `palais.deliverables.list` | Lister livrables d'une entite |

### Memory (Knowledge Graph)
| Tool | Description |
|------|-------------|
| `palais.memory.search` | Recherche semantique (query requis) |
| `palais.memory.recall` | Rappeler un noeud par ID |
| `palais.memory.store` | Stocker un nouveau noeud memoire |

### Intelligence
| Tool | Description |
|------|-------------|
| `palais.insights.active` | Insights non acquittes |
| `palais.standup.latest` | Dernier briefing du matin |

## Examples

### Lister les taches en cours
```json
{
  "jsonrpc": "2.0", "id": 1,
  "method": "tools/call",
  "params": {
    "name": "palais.tasks.list",
    "arguments": { "status": "in-progress", "limit": 10 }
  }
}
```

### Creer une tache
```json
{
  "jsonrpc": "2.0", "id": 2,
  "method": "tools/call",
  "params": {
    "name": "palais.tasks.create",
    "arguments": {
      "projectId": 1,
      "columnId": 1,
      "title": "Corriger le bug d'authentification",
      "priority": "high",
      "assigneeAgentId": "builder"
    }
  }
}
```

### Chercher dans la memoire
```json
{
  "jsonrpc": "2.0", "id": 3,
  "method": "tools/call",
  "params": {
    "name": "palais.memory.search",
    "arguments": { "query": "Caddy 403 erreur CIDR", "limit": 5 }
  }
}
```

### Verifier le budget
```json
{
  "jsonrpc": "2.0", "id": 4,
  "method": "tools/call",
  "params": {
    "name": "palais.budget.remaining",
    "arguments": {}
  }
}
```

## Important Notes

- **Toujours verifier le budget** avant de lancer des taches couteuses (`palais.budget.remaining`)
- **Toujours chercher dans la memoire** avant de resoudre un probleme connu (`palais.memory.search`)
- **Stocker les resolutions** dans la memoire apres avoir resolu un probleme (`palais.memory.store`)
- **Ajouter des commentaires** sur les taches pour tracer les decisions (`palais.tasks.comment`)
- **Demarrer/arreter les timers** pour le tracking du temps (`palais.tasks.start_timer` / `palais.tasks.stop_timer`)
```

**Step 2: Archive kaneo-bridge**

Rename or delete `roles/openclaw/templates/skills/kaneo-bridge/SKILL.md.j2`. If the directory exists:
```bash
git rm -r roles/openclaw/templates/skills/kaneo-bridge/
```

If we want to keep a reference:
```bash
mv roles/openclaw/templates/skills/kaneo-bridge/ roles/openclaw/templates/skills/kaneo-bridge.archived/
git add roles/openclaw/templates/skills/kaneo-bridge.archived/
git rm -r roles/openclaw/templates/skills/kaneo-bridge/
```

**Step 3: Commit**

```bash
git add roles/openclaw/templates/skills/palais-bridge/
git commit -m "feat(openclaw): replace kaneo-bridge with palais-bridge skill — MCP JSON-RPC"
```

---

## Task 7: Test — Simulate Agent Calling palais.tasks.list via MCP

**Files:**
- Create: `roles/palais/files/app/scripts/test-mcp.ts`

**Step 1: Create MCP test script**

Create `roles/palais/files/app/scripts/test-mcp.ts`:
```typescript
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
	console.log('=== MCP Integration Test ===\n');

	// Test 1: Initialize
	console.log('1. Initialize...');
	const init = await mcpCall('initialize');
	console.log('   Server:', init.result?.serverInfo?.name, init.result?.serverInfo?.version);
	console.log('   Protocol:', init.result?.protocolVersion);

	// Test 2: List tools
	console.log('\n2. List tools...');
	const toolsList = await mcpCall('tools/list');
	const tools = toolsList.result?.tools ?? [];
	console.log(`   Found ${tools.length} tools:`);
	for (const tool of tools) {
		console.log(`     - ${tool.name}: ${tool.description.substring(0, 60)}...`);
	}

	// Test 3: Call palais.tasks.list
	console.log('\n3. palais.tasks.list...');
	const taskResult = await mcpCall('tools/call', 'palais.tasks.list', { limit: 5 });
	if (taskResult.error) {
		console.log('   ERROR:', taskResult.error.message);
	} else {
		const content = JSON.parse(taskResult.result?.content?.[0]?.text ?? '[]');
		console.log(`   Found ${Array.isArray(content) ? content.length : 0} tasks`);
	}

	// Test 4: Call palais.agents.status
	console.log('\n4. palais.agents.status...');
	const agentResult = await mcpCall('tools/call', 'palais.agents.status', {});
	if (agentResult.error) {
		console.log('   ERROR:', agentResult.error.message);
	} else {
		const agents = JSON.parse(agentResult.result?.content?.[0]?.text ?? '[]');
		console.log(`   Found ${Array.isArray(agents) ? agents.length : 0} agents`);
	}

	// Test 5: Call palais.budget.remaining
	console.log('\n5. palais.budget.remaining...');
	const budgetResult = await mcpCall('tools/call', 'palais.budget.remaining', {});
	if (budgetResult.error) {
		console.log('   ERROR:', budgetResult.error.message);
	} else {
		const budget = JSON.parse(budgetResult.result?.content?.[0]?.text ?? '{}');
		console.log(`   Budget: $${budget.remaining} remaining (${budget.percentUsed}% used)`);
	}

	// Test 6: Unknown tool (should fail gracefully)
	console.log('\n6. Unknown tool (should return error)...');
	const unknownResult = await mcpCall('tools/call', 'palais.nonexistent.tool', {});
	console.log('   Error:', unknownResult.error?.message ?? 'No error (unexpected)');

	// Test 7: Auth failure (no API key)
	console.log('\n7. Auth failure test...');
	const noAuthRes = await fetch(`${PALAIS_URL}/api/mcp`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize' })
	});
	console.log(`   Status: ${noAuthRes.status} (expected 401)`);

	console.log('\n=== Tests Complete ===');
}

runTests().catch(console.error);
```

**Step 2: Add test script to package.json**

In `roles/palais/files/app/package.json`, add to `"scripts"`:
```json
"test:mcp": "tsx scripts/test-mcp.ts"
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/scripts/test-mcp.ts roles/palais/files/app/package.json
git commit -m "test(palais): MCP integration test script — simulate agent calls"
```

---

## Verification Checklist

After implementation, verify:

- [ ] `POST /api/mcp` with `initialize` returns server info and capabilities
- [ ] `POST /api/mcp` with `tools/list` returns all 17 tool definitions with JSON Schema
- [ ] `POST /api/mcp` with `tools/call` + `palais.tasks.list` returns tasks from DB
- [ ] `POST /api/mcp` with `tools/call` + `palais.tasks.create` creates a task
- [ ] `POST /api/mcp` with `tools/call` + `palais.agents.status` returns 10 agents
- [ ] `POST /api/mcp` with `tools/call` + `palais.budget.remaining` returns budget info
- [ ] `POST /api/mcp` with `tools/call` + `palais.memory.store` creates a memory node
- [ ] `POST /api/mcp` with `tools/call` + `palais.memory.search` returns relevant nodes
- [ ] `POST /api/mcp` with `tools/call` + `palais.deliverables.list` returns deliverables
- [ ] `POST /api/mcp` with `tools/call` + `palais.insights.active` returns insights
- [ ] `POST /api/mcp` with `tools/call` + `palais.standup.latest` returns latest standup
- [ ] `GET /api/mcp/sse` opens SSE stream with `endpoint` event
- [ ] MCP endpoints reject requests without `X-API-Key` (401)
- [ ] Unknown tool names return proper JSON-RPC error
- [ ] `palais-bridge/SKILL.md.j2` renders correctly with Ansible variables
- [ ] `kaneo-bridge` skill is removed or archived
- [ ] `npm run test:mcp` passes all 7 test steps
- [ ] `make lint` passes (Ansible + YAML)
