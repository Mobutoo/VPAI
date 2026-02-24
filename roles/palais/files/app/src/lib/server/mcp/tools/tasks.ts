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
				.set({ ...updates, updatedAt: new Date() } as any)
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
