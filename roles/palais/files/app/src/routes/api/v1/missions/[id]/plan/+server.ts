import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { missions, missionConversations } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { chatCompletion } from '$lib/server/llm/client';

const PLAN_PROMPT = `À partir de la conversation ci-dessus, génère un plan de mission structuré en JSON.
Le JSON doit avoir exactement ce format :
{
  "tasks": [
    {
      "title": "string",
      "description": "string (1-2 phrases)",
      "estimatedCost": number (en USD, ex: 0.05),
      "assigneeAgentId": null,
      "dependencies": [],
      "priority": "medium"
    }
  ]
}
Génère entre 3 et 8 tâches. Réponds UNIQUEMENT avec le JSON, sans texte autour.`;

export const GET: RequestHandler = async ({ params }) => {
	const id = parseInt(params.id);
	const [mission] = await db.select().from(missions).where(eq(missions.id, id));
	if (!mission) return json({ error: 'Not found' }, { status: 404 });
	return json(mission.planSnapshot ?? { tasks: [] });
};

export const POST: RequestHandler = async ({ params }) => {
	const id = parseInt(params.id);

	const [mission] = await db.select().from(missions).where(eq(missions.id, id));
	if (!mission) return json({ error: 'Not found' }, { status: 404 });

	// Load conversation for context
	const history = await db.select()
		.from(missionConversations)
		.where(eq(missionConversations.missionId, id))
		.orderBy(asc(missionConversations.createdAt));

	const conversationText = history
		.map((m) => `${m.role === 'user' ? 'Human' : 'AI'}: ${m.content}`)
		.join('\n\n');

	let planSnapshot: { tasks: unknown[] } = { tasks: [] };
	try {
		const llmResponse = await chatCompletion([
			{
				role: 'system',
				content: `Mission: "${mission.title}"\nBrief: ${mission.briefText ?? '(aucun brief)'}\n\nConversation de brainstorming:\n${conversationText || '(aucune conversation)'}`
			},
			{ role: 'user', content: PLAN_PROMPT }
		]);

		// Parse JSON from response
		const jsonMatch = llmResponse.match(/\{[\s\S]*\}/);
		if (jsonMatch) {
			planSnapshot = JSON.parse(jsonMatch[0]);
		}
	} catch (err) {
		console.error('Plan generation error:', err);
		// Return a default plan structure on error
		planSnapshot = {
			tasks: [
				{
					title: `Plan ${mission.title}`,
					description: 'Tâche générée automatiquement',
					estimatedCost: 0.05,
					assigneeAgentId: null,
					dependencies: [],
					priority: 'medium'
				}
			]
		};
	}

	// Save plan and advance status to co_editing
	const [updated] = await db.update(missions)
		.set({ planSnapshot, status: 'co_editing' })
		.where(eq(missions.id, id))
		.returning();

	return json(updated, { status: 201 });
};

export const PUT: RequestHandler = async ({ params, request }) => {
	const id = parseInt(params.id);
	const body = await request.json();

	const [updated] = await db.update(missions)
		.set({ planSnapshot: body })
		.where(eq(missions.id, id))
		.returning();

	if (!updated) return json({ error: 'Not found' }, { status: 404 });
	return json(updated.planSnapshot);
};
