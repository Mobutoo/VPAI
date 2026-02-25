import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import {
	getComfyUIStatus,
	getComfyUIQueue,
	getComfyUIHistory,
	submitComfyUIPrompt
} from '$lib/server/creative/comfyui';

// GET /api/v1/creative/comfyui — status + queue + recent history
export const GET: RequestHandler = async () => {
	try {
		const [status, queue, history] = await Promise.allSettled([
			getComfyUIStatus(),
			getComfyUIQueue(),
			getComfyUIHistory(20)
		]);

		return json({
			status:  status.status  === 'fulfilled' ? status.value  : null,
			queue:   queue.status   === 'fulfilled' ? queue.value   : null,
			history: history.status === 'fulfilled' ? history.value : [],
			errors: {
				status:  status.status  === 'rejected' ? String(status.reason)  : null,
				queue:   queue.status   === 'rejected' ? String(queue.reason)   : null,
				history: history.status === 'rejected' ? String(history.reason) : null
			}
		});
	} catch (err) {
		return json({ error: String(err) }, { status: 502 });
	}
};

// POST /api/v1/creative/comfyui — submit a generation prompt
export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	const { workflow, task_id } = body;

	if (!workflow || typeof workflow !== 'object') {
		return json({ error: 'Missing workflow object' }, { status: 400 });
	}

	try {
		const result = await submitComfyUIPrompt({
			workflow,
			taskId: task_id ?? undefined
		});
		return json(result);
	} catch (err) {
		return json({ error: String(err) }, { status: 502 });
	}
};
