import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { projects, columns, tasks, timeEntries, taskIterations, memoryNodes } from '$lib/server/db/schema';
import { eq, inArray } from 'drizzle-orm';
import { chatCompletion } from '$lib/server/llm/client';
import { env } from '$env/dynamic/private';

export const POST: RequestHandler = async ({ params }) => {
	const projectId = parseInt(params.id);

	const [project] = await db.select().from(projects).where(eq(projects.id, projectId));
	if (!project) return json({ error: 'Project not found' }, { status: 404 });

	const cols = await db.select().from(columns).where(eq(columns.projectId, projectId));
	const allTasks = await db.select().from(tasks).where(eq(tasks.projectId, projectId));
	const taskIds = allTasks.map((t) => t.id);

	const entries = taskIds.length
		? await db.select().from(timeEntries).where(inArray(timeEntries.taskId, taskIds))
		: [];
	const iterations = taskIds.length
		? await db.select().from(taskIterations).where(inArray(taskIterations.taskId, taskIds))
		: [];

	// ── Compute stats ────────────────────────────────────────────────────────
	const totalTimeSeconds = entries.reduce((s, e) => s + (e.durationSeconds ?? 0), 0);
	const totalEstimated = allTasks.reduce((s, t) => s + (t.estimatedCost ?? 0), 0);
	const totalActual = allTasks.reduce((s, t) => s + (t.actualCost ?? 0), 0);
	const finalColIds = new Set(cols.filter((c) => c.isFinal).map((c) => c.id));
	const completedCount = allTasks.filter((t) => finalColIds.has(t.columnId)).length;

	const statsBlock = `
Projet : "${project.name}"
Tâches total : ${allTasks.length} | Terminées : ${completedCount}
Temps total travaillé : ${Math.round(totalTimeSeconds / 3600 * 10) / 10}h
Coût estimé : $${totalEstimated.toFixed(3)} | Coût réel : $${totalActual.toFixed(3)}
Itérations (réouvertures) : ${iterations.length}
Tâches avec itérations : ${new Set(iterations.map((i) => i.taskId)).size}
  `.trim();

	// ── Generate post-mortem via LiteLLM ────────────────────────────────────
	let postMortem = '';
	try {
		postMortem = await chatCompletion([
			{
				role: 'system',
				content: `Tu es Mobutoo, Général d'État-Major. Génère un post-mortem de projet concis et structuré.
Format:
## Résumé exécutif (2-3 phrases)
## Points forts
## Points d'amélioration
## Leçons retenues
Sois direct, factuel. Max 300 mots.`
			},
			{
				role: 'user',
				content: `Génère le post-mortem pour ce projet terminé :\n\n${statsBlock}`
			}
		]);
	} catch (err) {
		console.error('LiteLLM post-mortem error:', err);
		postMortem = `Post-mortem automatique\n\n${statsBlock}\n\n(Rapport LLM indisponible)`;
	}

	// ── Store as memory node ─────────────────────────────────────────────────
	const [node] = await db.insert(memoryNodes).values({
		type: 'episodic',
		content: postMortem,
		summary: `Post-mortem : ${project.name}`,
		entityType: 'task',
		entityId: String(projectId),
		tags: ['post-mortem', 'projet', project.slug],
		createdBy: 'system'
	}).returning();

	// ── Send n8n webhook ─────────────────────────────────────────────────────
	const webhookUrl = `${env.N8N_WEBHOOK_BASE}/palais-post-mortem`;
	try {
		await fetch(webhookUrl, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				project: { id: project.id, name: project.name, slug: project.slug },
				stats: { totalTimeSeconds, totalEstimated, totalActual, completedCount, totalTasks: allTasks.length, iterations: iterations.length },
				postMortem,
				memoryNodeId: node.id
			})
		});
	} catch (err) {
		console.error('n8n webhook error (non-blocking):', err);
	}

	// ── Update project completedAt ───────────────────────────────────────────
	await db.update(projects)
		.set({ updatedAt: new Date() })
		.where(eq(projects.id, projectId));

	return json({
		ok: true,
		postMortem,
		memoryNodeId: node.id,
		stats: { totalTimeSeconds, totalEstimated, totalActual, completedCount }
	});
};
