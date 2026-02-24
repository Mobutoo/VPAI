import { db } from '$lib/server/db';
import { projects, columns, tasks, agents } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const projectId = parseInt(params.id);
	if (isNaN(projectId)) throw error(404, 'Project not found');

	const [project] = await db.select().from(projects).where(eq(projects.id, projectId));
	if (!project) throw error(404, 'Project not found');

	const cols = await db.select().from(columns)
		.where(eq(columns.projectId, projectId))
		.orderBy(asc(columns.position));

	const allTasks = await db.select().from(tasks)
		.where(eq(tasks.projectId, projectId))
		.orderBy(asc(tasks.position));

	// Fetch agent statuses for assigned agents
	const assigneeIds = [...new Set(allTasks.map(t => t.assigneeAgentId).filter(Boolean))] as string[];
	let agentStatusMap: Record<string, string> = {};
	if (assigneeIds.length > 0) {
		const agentRows = await db.select({ id: agents.id, status: agents.status })
			.from(agents);
		for (const a of agentRows) {
			agentStatusMap[a.id] = a.status ?? 'offline';
		}
	}

	// Merge agent status into tasks
	const tasksWithStatus = allTasks.map(t => ({
		...t,
		agentStatus: t.assigneeAgentId ? (agentStatusMap[t.assigneeAgentId] ?? null) : null
	}));

	return { project, columns: cols, tasks: tasksWithStatus };
};
