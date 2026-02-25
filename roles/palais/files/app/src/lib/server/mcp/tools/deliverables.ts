import type { McpToolDefinition } from '../types';
import { db } from '$lib/server/db';
import { deliverables } from '$lib/server/db/schema';
import { eq, and } from 'drizzle-orm';

export const deliverableToolDefs: McpToolDefinition[] = [
	{
		name: 'palais.deliverables.upload',
		description: 'Register a deliverable file for a task or project (file must already exist on disk)',
		inputSchema: {
			type: 'object',
			properties: {
				entityType: { type: 'string', description: 'task, project, or mission' },
				entityId: { type: 'number', description: 'ID of the task/project/mission' },
				filename: { type: 'string', description: 'Filename' },
				storagePath: { type: 'string', description: 'Relative path in deliverables directory' },
				mimeType: { type: 'string', description: 'MIME type' },
				sizeBytes: { type: 'number', description: 'File size in bytes' },
				agentId: { type: 'string', description: 'Agent ID uploading the file' }
			},
			required: ['entityType', 'entityId', 'filename', 'storagePath']
		}
	},
	{
		name: 'palais.deliverables.list',
		description: 'List deliverables for a task, project, or mission',
		inputSchema: {
			type: 'object',
			properties: {
				entityType: { type: 'string', description: 'task, project, or mission' },
				entityId: { type: 'number', description: 'ID of the entity' }
			},
			required: ['entityType', 'entityId']
		}
	}
];

export async function handleDeliverablesTool(
	method: string,
	args: Record<string, unknown>
): Promise<unknown> {
	switch (method) {
		case 'upload': {
			const downloadToken = crypto.randomUUID();
			const [deliverable] = await db.insert(deliverables).values({
				entityType: args.entityType as any,
				entityId: args.entityId as number,
				filename: args.filename as string,
				storagePath: args.storagePath as string,
				mimeType: (args.mimeType as string) ?? 'application/octet-stream',
				sizeBytes: (args.sizeBytes as number) ?? null,
				downloadToken,
				uploadedByType: args.agentId ? 'agent' : 'system',
				uploadedByAgentId: (args.agentId as string) ?? null
			}).returning();
			return { ...deliverable, downloadUrl: `/dl/${downloadToken}` };
		}

		case 'list': {
			return db.select().from(deliverables)
				.where(and(
					eq(deliverables.entityType, args.entityType as any),
					eq(deliverables.entityId, args.entityId as number)
				));
		}

		default:
			throw new Error(`Unknown deliverables method: ${method}`);
	}
}
