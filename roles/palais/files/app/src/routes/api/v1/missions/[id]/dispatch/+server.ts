import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { missions, projects, columns, tasks, taskDependencies, workspaces } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';

type PlanTask = {
	title: string;
	description?: string;
	estimatedCost?: number;
	assigneeAgentId?: string | null;
	priority?: string;
	dependencies?: number[]; // 0-based indices in the plan tasks array
};

export const POST: RequestHandler = async ({ params }) => {
	const missionId = parseInt(params.id);

	const [mission] = await db.select().from(missions).where(eq(missions.id, missionId));
	if (!mission) return json({ error: 'Mission not found' }, { status: 404 });

	if (mission.status !== 'approved') {
		return json({ error: 'Mission must be approved before dispatch' }, { status: 400 });
	}

	const plan = mission.planSnapshot as { tasks: PlanTask[] } | null;
	if (!plan?.tasks?.length) {
		return json({ error: 'No plan to dispatch' }, { status: 400 });
	}

	// Get or create default workspace
	let [workspace] = await db.select().from(workspaces).orderBy(asc(workspaces.id)).limit(1);
	if (!workspace) {
		[workspace] = await db.insert(workspaces).values({
			name: 'Default',
			slug: 'default'
		}).returning();
	}

	// Create project from mission title
	const slug = mission.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
	const [project] = await db.insert(projects).values({
		workspaceId: workspace.id,
		name: mission.title,
		slug: `${slug}-${missionId}`,
		description: mission.briefText ?? undefined
	}).returning();

	// Create default columns
	const defaultCols = ['Backlog', 'Planning', 'Assigned', 'In Progress', 'Review', 'Done'];
	const createdCols = [];
	for (let i = 0; i < defaultCols.length; i++) {
		const [col] = await db.insert(columns).values({
			projectId: project.id,
			name: defaultCols[i],
			position: i,
			isFinal: i === defaultCols.length - 1
		}).returning();
		createdCols.push(col);
	}

	const backlogColumn = createdCols[0]; // All tasks start in Backlog

	// Create tasks from plan
	const createdTasks = [];
	for (let i = 0; i < plan.tasks.length; i++) {
		const pt = plan.tasks[i];
		const [task] = await db.insert(tasks).values({
			projectId: project.id,
			columnId: backlogColumn.id,
			missionId,
			title: pt.title,
			description: pt.description ?? null,
			priority: (pt.priority as 'none' | 'low' | 'medium' | 'high' | 'urgent') ?? 'medium',
			assigneeAgentId: pt.assigneeAgentId ?? null,
			estimatedCost: pt.estimatedCost ?? null,
			creator: 'system',
			position: i
		}).returning();
		createdTasks.push(task);
	}

	// Create dependencies (plan deps are 0-based indices)
	for (let i = 0; i < plan.tasks.length; i++) {
		const deps = plan.tasks[i].dependencies ?? [];
		for (const depIndex of deps) {
			if (depIndex >= 0 && depIndex < createdTasks.length && depIndex !== i) {
				await db.insert(taskDependencies).values({
					taskId: createdTasks[i].id,
					dependsOnTaskId: createdTasks[depIndex].id,
					dependencyType: 'finish-to-start'
				}).onConflictDoNothing();
			}
		}
	}

	// Update mission: status → executing, link projectId
	const totalCost = plan.tasks.reduce((s, t) => s + (t.estimatedCost ?? 0), 0);
	await db.update(missions)
		.set({
			status: 'executing',
			projectId: project.id,
			totalEstimatedCost: totalCost
		})
		.where(eq(missions.id, missionId));

	return json({
		projectId: project.id,
		tasksCreated: createdTasks.length,
		message: `Dispatched: project #${project.id} with ${createdTasks.length} tasks`
	}, { status: 201 });
};
