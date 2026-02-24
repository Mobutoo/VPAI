import { generateStandupBriefing } from './generate';
import { db } from '$lib/server/db';
import { insights } from '$lib/server/db/schema';
import { env } from '$env/dynamic/private';

let schedulerStarted = false;

export function startStandupScheduler(): void {
	if (schedulerStarted) return;
	schedulerStarted = true;

	const standupHour = parseInt(env.STANDUP_HOUR || '08', 10);

	// Check every 15 minutes if it's time for the standup
	setInterval(async () => {
		const now = new Date();
		if (now.getHours() === standupHour && now.getMinutes() < 15) {
			await generateAndStoreStandup();
		}
	}, 15 * 60 * 1000);

	console.log(`[Palais] Standup scheduler started — will generate at ${standupHour}:00`);
}

export async function generateAndStoreStandup(): Promise<void> {
	try {
		const briefing = await generateStandupBriefing();

		// Store as insight with type 'standup'
		await db.insert(insights).values({
			type: 'standup',
			severity: 'info',
			title: briefing.title,
			description: briefing.description,
			suggestedActions: briefing.suggestedActions,
			acknowledged: false
		});

		console.log(`[Palais] Standup generated: ${briefing.title}`);

		// Push to n8n webhook for Telegram relay (non-fatal)
		await pushStandupToN8n(briefing);
	} catch (err) {
		console.error('[Palais] Standup generation failed:', err);
	}
}

async function pushStandupToN8n(briefing: { title: string; description: string }): Promise<void> {
	const n8nBase = env.N8N_WEBHOOK_BASE || 'http://n8n:5678/webhook';

	try {
		await fetch(`${n8nBase}/palais-standup`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				title: briefing.title,
				content: briefing.description,
				timestamp: new Date().toISOString()
			})
		});
	} catch {
		// n8n webhook failure is non-fatal
		console.warn('[Palais] Failed to push standup to n8n webhook');
	}
}
