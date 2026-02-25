import { getComfyUIStatus, getComfyUIQueue, getComfyUIHistory } from '$lib/server/creative/comfyui';
import { db } from '$lib/server/db';
import { deliverables } from '$lib/server/db/schema';
import { eq, desc } from 'drizzle-orm';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	// ComfyUI data — non-blocking
	const [statusResult, queueResult, historyResult] = await Promise.allSettled([
		getComfyUIStatus(),
		getComfyUIQueue(),
		getComfyUIHistory(30)
	]);

	const status  = statusResult.status  === 'fulfilled' ? statusResult.value  : null;
	const queue   = queueResult.status   === 'fulfilled' ? queueResult.value   : null;
	const history = historyResult.status === 'fulfilled' ? historyResult.value : [];
	const comfyError = statusResult.status === 'rejected'
		? String((statusResult as PromiseRejectedResult).reason)
		: null;

	// Creative deliverables gallery
	const gallery = await db
		.select()
		.from(deliverables)
		.where(eq(deliverables.uploadedByType, 'agent'))
		.orderBy(desc(deliverables.createdAt))
		.limit(50);

	return { status, queue, history, comfyError, gallery };
};
