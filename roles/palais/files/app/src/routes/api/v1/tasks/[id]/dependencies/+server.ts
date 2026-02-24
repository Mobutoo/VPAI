import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { taskDependencies, tasks } from '$lib/server/db/schema';
import { eq, and } from 'drizzle-orm';
import { hasCycle } from '$lib/server/utils/graph';
import { logActivity } from '$lib/server/activity';

export const GET: RequestHandler = async ({ params }) => {
	const taskId = parseInt(params.id);
	const deps = await db.select({
		id: taskDependencies.id,
		dependsOnTaskId: taskDependencies.dependsOnTaskId,
		dependencyType: taskDependencies.dependencyType,
		title: tasks.title
	})
		.from(taskDependencies)
		.leftJoin(tasks, eq(tasks.id, taskDependencies.dependsOnTaskId))
		.where(eq(taskDependencies.taskId, taskId));
	return json(deps);
};

export const POST: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	const { dependsOnTaskId, dependencyType = 'finish-to-start' } = await request.json();

	if (!dependsOnTaskId) return json({ error: 'dependsOnTaskId required' }, { status: 400 });
	if (taskId === dependsOnTaskId) return json({ error: 'Task cannot depend on itself' }, { status: 400 });

	if (await hasCycle(taskId, dependsOnTaskId)) {
		return json({ error: 'Circular dependency detected' }, { status: 400 });
	}

	const [dep] = await db.insert(taskDependencies)
		.values({ taskId, dependsOnTaskId, dependencyType })
		.returning();

	await logActivity({ entityType: 'task', entityId: taskId, action: 'dependency_added', newValue: String(dependsOnTaskId) });
	return json(dep, { status: 201 });
};

export const DELETE: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	const { dependsOnTaskId } = await request.json();

	await db.delete(taskDependencies)
		.where(and(eq(taskDependencies.taskId, taskId), eq(taskDependencies.dependsOnTaskId, dependsOnTaskId)));

	return json({ ok: true });
};
