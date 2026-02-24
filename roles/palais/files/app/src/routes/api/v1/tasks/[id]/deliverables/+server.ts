import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { deliverables, tasks, projects } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';
import { writeFile, mkdir } from 'fs/promises';
import { randomUUID } from 'crypto';
import path from 'path';

const DATA_ROOT = '/data/deliverables';

// GET — list deliverables for a task
export const GET: RequestHandler = async ({ params }) => {
	const taskId = parseInt(params.id);
	const entries = await db.select()
		.from(deliverables)
		.where(eq(deliverables.entityId, taskId));
	return json(entries);
};

// POST — multipart upload
export const POST: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);

	const [task] = await db.select().from(tasks).where(eq(tasks.id, taskId));
	if (!task) return json({ error: 'Task not found' }, { status: 404 });

	const [project] = await db.select().from(projects).where(eq(projects.id, task.projectId));
	if (!project) return json({ error: 'Project not found' }, { status: 404 });

	let formData: FormData;
	try {
		formData = await request.formData();
	} catch {
		return json({ error: 'Expected multipart/form-data' }, { status: 400 });
	}

	const file = formData.get('file');
	if (!file || !(file instanceof File)) {
		return json({ error: 'file field required' }, { status: 400 });
	}

	const token = randomUUID();
	const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
	const dir = path.join(DATA_ROOT, 'projects', project.slug, String(taskId));
	const storagePath = path.join(dir, `${token}_${safeName}`);

	await mkdir(dir, { recursive: true });
	const buffer = Buffer.from(await file.arrayBuffer());
	await writeFile(storagePath, buffer);

	const [entry] = await db.insert(deliverables).values({
		entityType: 'task',
		entityId: taskId,
		filename: file.name,
		mimeType: file.type || 'application/octet-stream',
		sizeBytes: buffer.length,
		storagePath,
		downloadToken: token,
		uploadedByType: 'user'
	}).returning();

	return json(entry, { status: 201 });
};
