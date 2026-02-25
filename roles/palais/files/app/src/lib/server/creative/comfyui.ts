import { env } from '$env/dynamic/private';
import { db } from '$lib/server/db';
import { deliverables } from '$lib/server/db/schema';
import { randomUUID } from 'crypto';
import { writeFile, mkdir } from 'fs/promises';
import { join } from 'path';

function comfyUrl() {
	return env.COMFYUI_URL || 'http://127.0.0.1:8188';
}

// ─── Status ──────────────────────────────────────────────────────────────────

export async function getComfyUIStatus() {
	const res = await fetch(`${comfyUrl()}/system_stats`, {
		signal: AbortSignal.timeout(5000)
	});
	if (!res.ok) throw new Error(`ComfyUI /system_stats → ${res.status}`);
	return res.json();
}

// ─── Queue ────────────────────────────────────────────────────────────────────

export async function getComfyUIQueue() {
	const res = await fetch(`${comfyUrl()}/queue`, {
		signal: AbortSignal.timeout(5000)
	});
	if (!res.ok) throw new Error(`ComfyUI /queue → ${res.status}`);
	return res.json();
}

// ─── History ─────────────────────────────────────────────────────────────────

export async function getComfyUIHistory(limit = 20) {
	const res = await fetch(`${comfyUrl()}/history`, {
		signal: AbortSignal.timeout(5000)
	});
	if (!res.ok) throw new Error(`ComfyUI /history → ${res.status}`);
	const data = await res.json() as Record<string, unknown>;
	// ComfyUI returns a map { promptId: { ... } }
	return Object.entries(data)
		.slice(0, limit)
		.map(([id, entry]) => ({ id, ...(entry as Record<string, unknown>) }));
}

// ─── Submit prompt ────────────────────────────────────────────────────────────

export interface GenerateOptions {
	workflow: Record<string, unknown>;
	taskId?: number;
}

export async function submitComfyUIPrompt(options: GenerateOptions) {
	const { workflow, taskId } = options;
	const clientId = randomUUID();

	const body = {
		prompt: workflow,
		client_id: clientId,
		extra_data: taskId ? { task_id: taskId } : {}
	};

	const res = await fetch(`${comfyUrl()}/prompt`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body),
		signal: AbortSignal.timeout(10000)
	});
	if (!res.ok) {
		const err = await res.text();
		throw new Error(`ComfyUI /prompt → ${res.status}: ${err}`);
	}
	return res.json() as Promise<{ prompt_id: string; number: number; node_errors: Record<string, unknown> }>;
}

// ─── Image fetch ──────────────────────────────────────────────────────────────

export async function fetchComfyUIImage(filename: string, subfolder = '', type = 'output') {
	const params = new URLSearchParams({ filename, subfolder, type });
	const res = await fetch(`${comfyUrl()}/view?${params}`, {
		signal: AbortSignal.timeout(15000)
	});
	if (!res.ok) throw new Error(`ComfyUI /view → ${res.status}`);
	return res.arrayBuffer();
}

// ─── Task 9: Auto-attach completed ComfyUI output as deliverable ──────────────

export async function attachOutputAsDeliverable(
	filename: string,
	taskId: number,
	subfolder = '',
	mimeType = 'image/png'
): Promise<string> {
	const imageData = await fetchComfyUIImage(filename, subfolder);

	// Storage path under palais data dir
	const storageDir = join(process.env.PALAIS_DATA_DIR ?? '/data/palais', 'deliverables', 'creative');
	await mkdir(storageDir, { recursive: true });
	const storagePath = join(storageDir, filename);
	await writeFile(storagePath, Buffer.from(imageData));

	const token = randomUUID();
	await db.insert(deliverables).values({
		entityType: 'task',
		entityId: taskId,
		filename,
		mimeType,
		sizeBytes: imageData.byteLength,
		storagePath,
		downloadToken: token,
		uploadedByType: 'agent'
	});

	return token;
}
