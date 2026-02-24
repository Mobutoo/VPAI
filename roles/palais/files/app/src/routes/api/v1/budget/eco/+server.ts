import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

// POST /api/v1/budget/eco — toggle eco mode via n8n webhook
export const POST: RequestHandler = async ({ request }) => {
	const { enabled } = await request.json();
	const webhookUrl = `${env.N8N_WEBHOOK_BASE}/budget-eco-mode`;

	try {
		await fetch(webhookUrl, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ eco_mode: enabled, timestamp: new Date().toISOString() })
		});
	} catch (err) {
		console.error('[Budget] Eco mode webhook error:', err);
		// Non-blocking — still return success to UI
	}

	return json({ ok: true, ecoMode: enabled });
};
