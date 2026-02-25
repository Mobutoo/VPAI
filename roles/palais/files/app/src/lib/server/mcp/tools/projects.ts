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

			// Sum time entries for all project tasks
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
