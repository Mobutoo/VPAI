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

	const allAgents = await db.select({
		id: agents.id,
		name: agents.name
	}).from(agents);

	return { project, columns: cols, tasks: allTasks, agents: allAgents };
};
