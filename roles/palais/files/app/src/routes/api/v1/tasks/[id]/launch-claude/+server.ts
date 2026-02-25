import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { db } from '$lib/server/db';
import { tasks, projects, workspaces } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

function buildClaudeCodePrompt(
	task: typeof tasks.$inferSelect,
	project: typeof projects.$inferSelect | null,
	workspace: typeof workspaces.$inferSelect | null
): string {
	return [
		`# Mission Palais — Tâche #${task.id}`,
		``,
		`**Projet :** ${project?.name ?? 'Non défini'} (workspace: ${workspace?.name ?? '—'})`,
		`**Titre :** ${task.title}`,
		`**Priorité :** ${task.priority ?? 'none'}`,
		`**Statut courant :** ${task.status ?? 'backlog'}`,
		``,
		task.description ? `## Description\n${task.description}\n` : '',
		`## Instructions`,
		`Tu es un agent de code autonome. Réalise cette tâche de façon complète et propre :`,
		`1. Analyse le dépôt courant et comprends le contexte`,
		`2. Implémente la fonctionnalité décrite`,
		`3. Écris des tests si applicable`,
		`4. Crée un commit clair et un PR si le dépôt le permet`,
		`5. Rappelle le résultat via le webhook Palais : POST ${env.PALAIS_URL ?? ''}/api/v1/tasks/${task.id}/launch-claude/callback`,
		``
	].filter(Boolean).join('\n');
}

// POST /api/v1/tasks/:id/launch-claude — trigger Claude Code session on Pi
export const POST: RequestHandler = async ({ params }) => {
	const taskId = parseInt(params.id);
	if (isNaN(taskId)) {
		return json({ error: 'Invalid task ID' }, { status: 400 });
	}

	const [task] = await db.select().from(tasks).where(eq(tasks.id, taskId));
	if (!task) {
		return json({ error: 'Task not found' }, { status: 404 });
	}

	const [project] = task.projectId
		? await db.select().from(projects).where(eq(projects.id, task.projectId))
		: [null];

	const [workspace] = project?.workspaceId
		? await db.select().from(workspaces).where(eq(workspaces.id, project.workspaceId))
		: [null];

	const prompt = buildClaudeCodePrompt(task, project ?? null, workspace ?? null);

	// Fire n8n webhook — async (don't wait)
	const n8nBase = env.N8N_WEBHOOK_BASE ?? 'http://n8n:5678/webhook';
	try {
		await fetch(`${n8nBase}/launch-claude-code`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				task_id: task.id,
				project_id: task.projectId,
				prompt,
				priority: task.priority
			}),
			signal: AbortSignal.timeout(5000)
		});
	} catch (err) {
		// Log but don't fail — n8n may be temporarily unavailable
		console.error('[launch-claude] n8n webhook failed:', err);
		return json({ error: 'Could not reach n8n webhook' }, { status: 502 });
	}

	// Update task status to in-progress
	await db.update(tasks)
		.set({ status: 'in-progress', updatedAt: new Date() })
		.where(eq(tasks.id, taskId));

	return json({ ok: true, task_id: taskId, message: 'Claude Code session launched on Pi' });
};

// PUT /api/v1/tasks/:id/launch-claude — callback from Pi when done
export const PUT: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	if (isNaN(taskId)) {
		return json({ error: 'Invalid task ID' }, { status: 400 });
	}

	const body = await request.json() as {
		status?: string;
		commit_sha?: string;
		pr_url?: string;
		summary?: string;
	};

	const newStatus = body.status ?? 'review';

	await db.update(tasks)
		.set({ status: newStatus, updatedAt: new Date() })
		.where(eq(tasks.id, taskId));

	return json({ ok: true, task_id: taskId, status: newStatus });
};
