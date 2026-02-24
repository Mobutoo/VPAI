import { db } from '$lib/server/db';
import { projects, workspaces } from '$lib/server/db/schema';
import type { PageServerLoad, Actions } from './$types';
import { json } from '@sveltejs/kit';

export const load: PageServerLoad = async () => {
	const all = await db.select({
		id: projects.id,
		name: projects.name,
		slug: projects.slug,
		icon: projects.icon,
		description: projects.description,
		workspaceId: projects.workspaceId,
		createdAt: projects.createdAt,
		updatedAt: projects.updatedAt
	}).from(projects).orderBy(projects.updatedAt);

	const ws = await db.select().from(workspaces).orderBy(workspaces.name);

	return { projects: all, workspaces: ws };
};
