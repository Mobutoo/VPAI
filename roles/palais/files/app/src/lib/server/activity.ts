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
