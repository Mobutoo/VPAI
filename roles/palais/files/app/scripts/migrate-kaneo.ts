#!/usr/bin/env tsx
/**
 * migrate-kaneo.ts — One-shot migration: Kaneo → Palais
 *
 * Usage:
 *   npx tsx scripts/migrate-kaneo.ts [--dry-run] [--verbose]
 *
 * Env vars required:
 *   KANEO_DATABASE_URL  — PostgreSQL URL of the Kaneo DB
 *   DATABASE_URL        — PostgreSQL URL of the Palais DB
 */
import postgres from 'postgres';

const DRY_RUN = process.argv.includes('--dry-run');
const VERBOSE = process.argv.includes('--verbose') || DRY_RUN;

function log(...args: unknown[]) {
	if (VERBOSE) console.log(...args);
}

function slugify(name: string): string {
	return name
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-|-$/g, '')
		.slice(0, 100);
}

// Kaneo status → Palais status (varchar column)
function mapStatus(kaneoStatus: string): string {
	const map: Record<string, string> = {
		backlog: 'backlog',
		todo: 'backlog',
		'in-progress': 'in-progress',
		'in_progress': 'in-progress',
		done: 'done',
		review: 'review',
		cancelled: 'done',
	};
	return map[kaneoStatus?.toLowerCase()] ?? 'backlog';
}

const DEFAULT_COLUMNS = [
	{ name: 'Backlog', statuses: ['backlog', 'todo'], position: 0 },
	{ name: 'Planning', statuses: ['planning'], position: 1 },
	{ name: 'Assigned', statuses: ['assigned'], position: 2 },
	{ name: 'In Progress', statuses: ['in-progress', 'in_progress'], position: 3 },
	{ name: 'Review', statuses: ['review'], position: 4 },
	{ name: 'Done', statuses: ['done', 'cancelled'], position: 5, isFinal: true },
];

async function main() {
	if (!process.env.KANEO_DATABASE_URL) throw new Error('KANEO_DATABASE_URL not set');
	if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL not set');

	const kaneoDb = postgres(process.env.KANEO_DATABASE_URL, { max: 1 });
	const palaisDb = postgres(process.env.DATABASE_URL, { max: 1 });

	console.log(`\n🚀 Kaneo → Palais Migration ${DRY_RUN ? '(DRY RUN)' : ''}`);
	console.log('─'.repeat(50));

	// ── Step 0: Ensure target workspace exists ──────────────────────────────
	console.log('\n[0] Ensuring "Kaneo Import" workspace...');
	let workspaceId: number;
	if (!DRY_RUN) {
		const [existing] = await palaisDb`
			SELECT id FROM workspaces WHERE slug = 'kaneo-import'
		`;
		if (existing) {
			workspaceId = existing.id;
			log(`  ✓ Workspace already exists (id=${workspaceId})`);
		} else {
			const [ws] = await palaisDb`
				INSERT INTO workspaces (name, slug)
				VALUES ('Kaneo Import', 'kaneo-import')
				RETURNING id
			`;
			workspaceId = ws.id;
			log(`  + Created workspace (id=${workspaceId})`);
		}
	} else {
		workspaceId = 0; // placeholder for dry run
		log('  [DRY] Would create/find "Kaneo Import" workspace');
	}

	// ── Step 1: Migrate projects ────────────────────────────────────────────
	console.log('\n[1] Migrating projects...');
	const kaneoProjects = await kaneoDb`SELECT * FROM project`;
	log(`  Found ${kaneoProjects.length} projects in Kaneo`);

	const projectMapping: Record<number, number> = {};
	const columnMapping: Record<number, Record<string, number>> = {}; // projectId → status → columnId

	for (const p of kaneoProjects) {
		const slug = slugify(p.name);
		log(`  → ${p.name} (slug: ${slug})`);

		if (!DRY_RUN) {
			// Upsert project
			const [existing] = await palaisDb`
				SELECT id FROM projects WHERE workspace_id = ${workspaceId} AND slug = ${slug}
			`;
			let projectId: number;
			if (existing) {
				projectId = existing.id;
				log(`    ✓ Already exists (id=${projectId})`);
			} else {
				const [proj] = await palaisDb`
					INSERT INTO projects (workspace_id, name, slug, created_at)
					VALUES (${workspaceId}, ${p.name}, ${slug}, ${p.created_at ?? new Date()})
					RETURNING id
				`;
				projectId = proj.id;
				log(`    + Created project (id=${projectId})`);
			}
			projectMapping[p.id] = projectId;

			// Create default columns for this project
			columnMapping[projectId] = {};
			for (const col of DEFAULT_COLUMNS) {
				const [existingCol] = await palaisDb`
					SELECT id FROM columns WHERE project_id = ${projectId} AND name = ${col.name}
				`;
				let colId: number;
				if (existingCol) {
					colId = existingCol.id;
				} else {
					const [newCol] = await palaisDb`
						INSERT INTO columns (project_id, name, position, is_final)
						VALUES (${projectId}, ${col.name}, ${col.position}, ${col.isFinal ?? false})
						RETURNING id
					`;
					colId = newCol.id;
					log(`    + Column "${col.name}" (id=${colId})`);
				}
				for (const st of col.statuses) {
					columnMapping[projectId][st] = colId;
				}
			}
		} else {
			log(`  [DRY] Would create project "${p.name}" + 6 columns`);
		}
	}
	console.log(`  ✓ ${kaneoProjects.length} projects processed`);

	// ── Step 2: Migrate tasks ───────────────────────────────────────────────
	console.log('\n[2] Migrating tasks...');
	const kaneoTasks = await kaneoDb`SELECT * FROM task`;
	log(`  Found ${kaneoTasks.length} tasks in Kaneo`);

	const taskMapping: Record<number, number> = {};
	let taskCreated = 0;
	let taskSkipped = 0;

	for (const t of kaneoTasks) {
		const palaisProjectId = projectMapping[t.project_id];
		if (!palaisProjectId && !DRY_RUN) {
			log(`  ⚠ Task "${t.title}" — project_id ${t.project_id} not found, skipping`);
			taskSkipped++;
			continue;
		}

		const status = mapStatus(t.status);
		log(`  → [${status}] ${t.title}`);

		if (!DRY_RUN) {
			// Find the column that matches this status
			const colId = columnMapping[palaisProjectId]?.[status]
				?? columnMapping[palaisProjectId]?.['backlog'];

			const [existing] = await palaisDb`
				SELECT id FROM tasks
				WHERE project_id = ${palaisProjectId} AND title = ${t.title}
				LIMIT 1
			`;
			if (existing) {
				taskMapping[t.id] = existing.id;
				taskSkipped++;
				log(`    ✓ Already exists (id=${existing.id})`);
			} else {
				const [task] = await palaisDb`
					INSERT INTO tasks (project_id, column_id, title, description, status, priority, created_at, updated_at)
					VALUES (
						${palaisProjectId},
						${colId},
						${t.title},
						${t.description ?? null},
						${status},
						${t.priority ?? 'none'},
						${t.created_at ?? new Date()},
						${t.updated_at ?? new Date()}
					)
					RETURNING id
				`;
				taskMapping[t.id] = task.id;
				taskCreated++;
				log(`    + Created task (id=${task.id})`);
			}
		} else {
			log(`  [DRY] Would create task "${t.title}" (status: ${status})`);
		}
	}
	console.log(`  ✓ Tasks: ${taskCreated} created, ${taskSkipped} skipped/existing`);

	// ── Step 3: Migrate comments ────────────────────────────────────────────
	console.log('\n[3] Migrating comments...');
	const kaneoComments = await kaneoDb`SELECT * FROM comment`;
	log(`  Found ${kaneoComments.length} comments in Kaneo`);

	let commentCreated = 0;
	let commentSkipped = 0;

	for (const c of kaneoComments) {
		const palaisTaskId = taskMapping[c.task_id];
		if (!palaisTaskId && !DRY_RUN) {
			log(`  ⚠ Comment — task_id ${c.task_id} not mapped, skipping`);
			commentSkipped++;
			continue;
		}

		if (!DRY_RUN) {
			await palaisDb`
				INSERT INTO comments (task_id, author_type, content, created_at)
				VALUES (${palaisTaskId}, 'system', ${c.content ?? ''}, ${c.created_at ?? new Date()})
			`;
			commentCreated++;
		} else {
			log(`  [DRY] Would create comment for task_id ${c.task_id}`);
		}
	}
	console.log(`  ✓ Comments: ${commentCreated} created, ${commentSkipped} skipped`);

	// ── Summary ─────────────────────────────────────────────────────────────
	console.log('\n' + '─'.repeat(50));
	console.log('✅ Migration complete!');
	console.log(`   Projects : ${kaneoProjects.length}`);
	console.log(`   Tasks    : ${taskCreated} created`);
	console.log(`   Comments : ${commentCreated} created`);
	if (DRY_RUN) console.log('\n   ℹ️  DRY RUN — nothing was written to Palais DB');

	await kaneoDb.end();
	await palaisDb.end();
}

main().catch((err) => {
	console.error('\n❌ Migration failed:', err);
	process.exit(1);
});
