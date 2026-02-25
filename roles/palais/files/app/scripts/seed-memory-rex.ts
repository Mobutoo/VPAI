#!/usr/bin/env tsx
/**
 * seed-memory-rex.ts — Import REX documents + TROUBLESHOOTING.md into Palais Knowledge Graph
 *
 * Usage:
 *   npx tsx scripts/seed-memory-rex.ts [--dry-run] [--verbose]
 *
 * Env vars required:
 *   PALAIS_URL    — e.g. https://palais.ewutelo.cloud
 *   PALAIS_API_KEY — API key for X-API-Key header
 */
import * as fs from 'fs';
import * as path from 'path';

const DRY_RUN = process.argv.includes('--dry-run');
const VERBOSE = process.argv.includes('--verbose') || DRY_RUN;

function log(...args: unknown[]) {
	if (VERBOSE) console.log(...args);
}

// ── Configuration ─────────────────────────────────────────────────────────────

const PALAIS_URL = process.env.PALAIS_URL ?? 'http://localhost:3300';
const API_KEY = process.env.PALAIS_API_KEY ?? '';

const REX_FILES = [
	{
		filePath: 'docs/REX-FIRST-DEPLOY-2026-02-15.md',
		title: 'REX Premier Déploiement (2026-02-15)',
		tags: ['rex', 'deployment', 'first-deploy'],
	},
	{
		filePath: 'docs/REX-SESSION-2026-02-18.md',
		title: 'REX Session 8 — Split DNS, Budget IA, VPN-only',
		tags: ['rex', 'deployment', 'dns', 'budget', 'vpn'],
	},
	{
		filePath: 'docs/REX-SESSION-2026-02-23.md',
		title: 'REX Session 9 — Creative Stack Pi, OpenCut, Error Pages',
		tags: ['rex', 'deployment', 'workstation', 'comfyui', 'remotion'],
	},
	{
		filePath: 'docs/REX-SESSION-2026-02-23b.md',
		title: 'REX Session 10 — OpenClaw v2026.2.22 Breaking Changes',
		tags: ['rex', 'deployment', 'openclaw', 'breaking-changes'],
	},
];

// ── Helpers ───────────────────────────────────────────────────────────────────

async function postNode(payload: Record<string, unknown>): Promise<void> {
	if (DRY_RUN) {
		log(`  [DRY] POST /api/v1/memory/nodes — ${payload.summary}`);
		return;
	}
	const res = await fetch(`${PALAIS_URL}/api/v1/memory/nodes`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-API-Key': API_KEY,
		},
		body: JSON.stringify(payload),
	});
	if (!res.ok) {
		const text = await res.text();
		throw new Error(`POST /api/v1/memory/nodes failed (${res.status}): ${text}`);
	}
	const data = await res.json() as { id: number };
	log(`  + Node created (id=${data.id}): ${payload.summary}`);
}

function parseSections(markdown: string): Array<{ title: string; content: string; service: string }> {
	const sections: Array<{ title: string; content: string; service: string }> = [];
	const lines = markdown.split('\n');
	let currentTitle = '';
	let currentLines: string[] = [];

	for (const line of lines) {
		if (line.startsWith('## ') || line.startsWith('### ')) {
			if (currentTitle && currentLines.length > 0) {
				const content = currentLines.join('\n').trim();
				if (content.length > 50) { // Skip near-empty sections
					// Extract service from title (first word after number)
					const serviceMatch = currentTitle.match(/[\d.]+\s+(\w[\w-]*)/);
					sections.push({
						title: currentTitle,
						content,
						service: serviceMatch?.[1]?.toLowerCase() ?? 'general',
					});
				}
			}
			currentTitle = line.replace(/^#{2,3}\s+/, '');
			currentLines = [];
		} else {
			currentLines.push(line);
		}
	}
	// Don't forget the last section
	if (currentTitle && currentLines.length > 0) {
		const content = currentLines.join('\n').trim();
		if (content.length > 50) {
			const serviceMatch = currentTitle.match(/[\d.]+\s+(\w[\w-]*)/);
			sections.push({
				title: currentTitle,
				content,
				service: serviceMatch?.[1]?.toLowerCase() ?? 'general',
			});
		}
	}

	return sections;
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
	if (!API_KEY && !DRY_RUN) throw new Error('PALAIS_API_KEY not set');

	console.log(`\n🧠 Palais Knowledge Graph Seeder ${DRY_RUN ? '(DRY RUN)' : ''}`);
	console.log(`   Target: ${PALAIS_URL}`);
	console.log('─'.repeat(55));

	// ── Part 1: REX documents (episodic nodes) ────────────────────────────
	console.log('\n[1] Importing REX documents as episodic nodes...');
	let rexCount = 0;

	for (const rex of REX_FILES) {
		if (!fs.existsSync(rex.filePath)) {
			console.warn(`  ⚠ File not found: ${rex.filePath} — skipped`);
			continue;
		}
		const content = fs.readFileSync(rex.filePath, 'utf-8');
		log(`  → ${rex.title} (${content.length} chars)`);

		await postNode({
			type: 'episodic',
			content: content.slice(0, 2000),
			summary: rex.title,
			entityType: 'deployment',
			tags: rex.tags,
			createdBy: 'seed-rex',
		});
		rexCount++;
	}
	console.log(`  ✓ ${rexCount} REX documents imported`);

	// ── Part 2: TROUBLESHOOTING.md sections (procedural nodes) ───────────
	console.log('\n[2] Importing TROUBLESHOOTING.md sections as procedural nodes...');
	const tsPath = 'docs/TROUBLESHOOTING.md';

	if (!fs.existsSync(tsPath)) {
		console.warn(`  ⚠ ${tsPath} not found — skipped`);
	} else {
		const content = fs.readFileSync(tsPath, 'utf-8');
		const sections = parseSections(content);
		log(`  Found ${sections.length} sections to import`);

		// Skip archive/meta sections
		const filtered = sections.filter(
			(s) => !s.title.includes('ARCHIVÉ') && !s.title.startsWith('99.')
		);
		log(`  Filtered to ${filtered.length} active sections`);

		let sectionCount = 0;
		for (const section of filtered) {
			await postNode({
				type: 'procedural',
				content: section.content.slice(0, 2000),
				summary: section.title,
				entityType: 'error',
				tags: ['troubleshooting', section.service],
				createdBy: 'seed-troubleshooting',
			});
			sectionCount++;
		}
		console.log(`  ✓ ${sectionCount} sections imported`);
	}

	// ── Summary ───────────────────────────────────────────────────────────
	console.log('\n' + '─'.repeat(55));
	console.log('✅ Knowledge Graph seeding complete!');
	if (DRY_RUN) console.log('\n   ℹ️  DRY RUN — nothing was written to Palais');
}

main().catch((err) => {
	console.error('\n❌ Seeding failed:', err);
	process.exit(1);
});
