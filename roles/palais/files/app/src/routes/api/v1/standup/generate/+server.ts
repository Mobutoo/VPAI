import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { generateAndStoreStandup } from '$lib/server/standup/scheduler';

export const POST: RequestHandler = async () => {
	try {
		await generateAndStoreStandup();
		return json({ success: true, message: 'Standup generated' });
	} catch (err) {
		const message = err instanceof Error ? err.message : 'Unknown error';
		return json({ success: false, error: message }, { status: 500 });
	}
};
