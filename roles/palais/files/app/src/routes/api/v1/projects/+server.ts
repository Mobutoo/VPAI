import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { projects, columns } from '$lib/server/db/schema';

export const GET: RequestHandler = async () => {
	const result = await db.select().from(projects).orderBy(projects.updatedAt);
	return json(result);
};

export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	const { name, description, workspaceId } = body;

	if (!name || !workspaceId) {
		return json({ error: 'name and workspaceId required' }, { status: 400 });
	}

	const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

	const [project] = await db.insert(projects).values({
		workspaceId,
		name,
		slug,
		description
	}).returning();

	// Create default columns
	const defaultCols = ['Backlog', 'Planning', 'Assigned', 'In Progress', 'Review', 'Done'];
	for (let i = 0; i < defaultCols.length; i++) {
		await db.insert(columns).values({
			projectId: project.id,
			name: defaultCols[i],
			position: i,
			isFinal: i === defaultCols.length - 1
		});
	}

	return json(project, { status: 201 });
};
