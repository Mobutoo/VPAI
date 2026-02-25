import { runAllDetectors } from './detector';
import { env } from '$env/dynamic/private';

let schedulerStarted = false;

export function startInsightScheduler(): void {
	if (schedulerStarted) return;
	schedulerStarted = true;

	// Run detection every 10 minutes
	setInterval(async () => {
		try {
			const newInsights = await runAllDetectors();
			if (newInsights.length > 0) {
				console.log(`[Palais] Detected ${newInsights.length} new insight(s)`);

				// Push critical insights to n8n for Telegram
				for (const insight of newInsights) {
					if (insight.severity === 'critical') {
						await pushInsightToN8n(insight);
					}
				}
			}
		} catch (err) {
			console.error('[Palais] Insight detection failed:', err);
		}
	}, 10 * 60 * 1000);

	// Run once on startup after 30s delay (let DB settle)
	setTimeout(() => {
		runAllDetectors().catch(console.error);
	}, 30000);

	console.log('[Palais] Insight scheduler started — checks every 10 minutes');
}

async function pushInsightToN8n(insight: {
	type: string;
	severity: string;
	title: string;
	description: string;
}): Promise<void> {
	const n8nBase = env.N8N_WEBHOOK_BASE || 'http://n8n:5678/webhook';

	try {
		await fetch(`${n8nBase}/palais-insight-alert`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				type: insight.type,
				severity: insight.severity,
				title: insight.title,
				description: insight.description,
				timestamp: new Date().toISOString()
			})
		});
	} catch {
		console.warn('[Palais] Failed to push insight to n8n webhook');
	}
}
