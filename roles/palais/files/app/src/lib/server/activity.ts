import { db } from '$lib/server/db';
import { activityLog } from '$lib/server/db/schema';
import { ingestActivityAsMemory } from './memory/ingest';

export async function logActivity(params: {
	entityType: string;
	entityId: number;
	action: string;
	actorType?: 'user' | 'agent' | 'system';
	actorAgentId?: string;
	oldValue?: string;
	newValue?: string;
}): Promise<void> {
	try {
		await db.insert(activityLog).values({
			entityType: params.entityType,
			entityId: params.entityId,
			action: params.action,
			actorType: (params.actorType ?? 'system') as 'user' | 'agent' | 'system',
			actorAgentId: params.actorAgentId ?? null,
			oldValue: params.oldValue ?? null,
			newValue: params.newValue ?? null
		});
	} catch {
		// Non-blocking — log failure silently to avoid breaking the main request
	}

	// Auto-ingest important events as episodic memory nodes (non-blocking)
	ingestActivityAsMemory({
		entityType: params.entityType,
		entityId: params.entityId,
		action: params.action,
		actorAgentId: params.actorAgentId,
		oldValue: params.oldValue,
		newValue: params.newValue
	}).catch(() => {});
}
