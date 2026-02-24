import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { missions, missionConversations } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { chatCompletion } from '$lib/server/llm/client';

const SYSTEM_PROMPT = `Tu es un planificateur de missions expert. Ton rôle est d'aider l'utilisateur à affiner son idée en une mission claire et actionnable.
Pose une question à la fois pour comprendre : le contexte, les contraintes techniques, les critères de succès, et les ressources disponibles.
Quand tu as assez d'informations, propose un plan en 3-7 tâches avec des estimations de durée.
Réponds toujours en français. Sois concis et structuré.`;

export const GET: RequestHandler = async ({ params }) => {
	const missionId = parseInt(params.id);
	const messages = await db.select()
		.from(missionConversations)
		.where(eq(missionConversations.missionId, missionId))
		.orderBy(asc(missionConversations.createdAt));
	return json(messages);
};

export const POST: RequestHandler = async ({ params, request }) => {
	const missionId = parseInt(params.id);
	const body = await request.json();
	const userContent = body.content?.trim();
	if (!userContent) return json({ error: 'Content required' }, { status: 400 });

	// Fetch mission for context
	const [mission] = await db.select().from(missions).where(eq(missions.id, missionId));
	if (!mission) return json({ error: 'Mission not found' }, { status: 404 });

	// Save user message
	await db.insert(missionConversations).values({
		missionId,
		role: 'user',
		content: userContent
	});

	// Load full conversation history for context
	const history = await db.select()
		.from(missionConversations)
		.where(eq(missionConversations.missionId, missionId))
		.orderBy(asc(missionConversations.createdAt));

	// Build messages array for LiteLLM
	const contextSystem = `${SYSTEM_PROMPT}\n\nMission: "${mission.title}"${mission.briefText ? `\nBrief initial: ${mission.briefText}` : ''}`;

	const llmMessages = [
		{ role: 'system' as const, content: contextSystem },
		...history.map((m) => ({
			role: m.role as 'user' | 'assistant',
			content: m.content
		}))
	];

	// Call LiteLLM
	let assistantContent: string;
	try {
		assistantContent = await chatCompletion(llmMessages);
	} catch (err) {
		console.error('LiteLLM error:', err);
		assistantContent = "Désolé, le service LLM est temporairement indisponible. Veuillez réessayer.";
	}

	// Save assistant response
	const [saved] = await db.insert(missionConversations).values({
		missionId,
		role: 'assistant',
		content: assistantContent
	}).returning();

	// Move mission to brainstorming if still at briefing
	if (mission.status === 'briefing') {
		await db.update(missions)
			.set({ status: 'brainstorming' })
			.where(eq(missions.id, missionId));
	}

	return json(saved, { status: 201 });
};
