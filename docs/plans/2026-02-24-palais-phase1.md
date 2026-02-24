# Palais Phase 1 — Fondations + Design System

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Initialize the Palais SvelteKit 5 application with the complete Afrofuturist design system, full database schema, Ansible role, API health + CRUD, and auth — ready to build on in Phase 2.

**Architecture:** SvelteKit 5 app in `roles/palais/files/app/`, built as Docker image (Node.js 22 Alpine), deployed via Ansible alongside existing stack. PostgreSQL shared instance (DB `palais`), Qdrant shared (collection `palais_memory`). Auth: cookie for browser, API key for agents/n8n.

**Tech Stack:** SvelteKit 5 (runes), Drizzle ORM, PostgreSQL, shadcn-svelte, Tailwind CSS 4, Node.js 22 Alpine

**PRD Reference:** `docs/PRD-PALAIS.md` — read this for full context on modules, data models, design system.

---

## Task 1: Initialize SvelteKit Project

**Files:**
- Create: `roles/palais/files/app/` (entire SvelteKit project)

**Step 1: Create project skeleton**

```bash
cd roles/palais/files
npx sv create app --template minimal --types ts
```

Select options:
- Template: minimal (SvelteKit)
- TypeScript: Yes
- Add-ons: Tailwind CSS, ESLint, Prettier

**Step 2: Install core dependencies**

```bash
cd roles/palais/files/app
npm install drizzle-orm postgres
npm install -D drizzle-kit @sveltejs/adapter-node
npx sv add shadcn-svelte
```

When shadcn prompts:
- Style: Default
- Base color: Slate
- CSS variables: Yes

**Step 3: Configure adapter-node**

Modify `roles/palais/files/app/svelte.config.js`:
```javascript
import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({
			out: 'build',
			precompress: false,
			envPrefix: ''
		})
	},
	preprocess: [vitePreprocess()]
};

export default config;
```

**Step 4: Create drizzle.config.ts**

Create `roles/palais/files/app/drizzle.config.ts`:
```typescript
import { defineConfig } from 'drizzle-kit';

export default defineConfig({
	dialect: 'postgresql',
	schema: './src/lib/server/db/schema.ts',
	out: './drizzle',
	dbCredentials: {
		url: process.env.DATABASE_URL!
	}
});
```

**Step 5: Create DB client**

Create `roles/palais/files/app/src/lib/server/db/index.ts`:
```typescript
import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema';
import { env } from '$env/dynamic/private';

const client = postgres(env.DATABASE_URL);
export const db = drizzle(client, { schema });
```

**Step 6: Commit**

```bash
git add roles/palais/files/app/
git commit -m "feat(palais): init SvelteKit 5 project with Drizzle + shadcn-svelte"
```

---

## Task 2: Design System — Palais Theme

**Files:**
- Modify: `roles/palais/files/app/src/app.css`
- Create: `roles/palais/files/app/src/lib/styles/theme.css`

**Step 1: Create Palais theme CSS variables**

Create `roles/palais/files/app/src/lib/styles/theme.css`:
```css
/*
 * Palais Design System — Afrofuturist Theme
 * Inspired by Wakanda HQ, Shuri's Lab, Kuba patterns
 */

:root {
	/* Core palette */
	--palais-bg: #0A0A0F;
	--palais-surface: #111118;
	--palais-surface-hover: #1A1A24;
	--palais-border: #2A2A3A;

	/* Accent colors */
	--palais-gold: #D4A843;
	--palais-gold-glow: rgba(212, 168, 67, 0.2);
	--palais-amber: #E8833A;
	--palais-cyan: #4FC3F7;
	--palais-green: #4CAF50;
	--palais-red: #E53935;

	/* Text */
	--palais-text: #E8E6E3;
	--palais-text-muted: #8A8A9A;

	/* Shadows */
	--palais-glow-sm: 0 0 8px rgba(212, 168, 67, 0.15);
	--palais-glow-md: 0 0 16px rgba(212, 168, 67, 0.2);
	--palais-glow-lg: 0 0 32px rgba(212, 168, 67, 0.25);

	/* Radii */
	--palais-radius-sm: 6px;
	--palais-radius-md: 10px;
	--palais-radius-lg: 16px;

	/* Transitions */
	--palais-transition: 200ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

**Step 2: Override shadcn-svelte theme in app.css**

Replace `roles/palais/files/app/src/app.css` content. Keep Tailwind imports at top, then override shadcn variables:
```css
@import 'tailwindcss';
@import '$lib/styles/theme.css';

@layer base {
	:root {
		--background: 240 20% 3.9%;
		--foreground: 30 5% 90%;
		--card: 240 15% 6.7%;
		--card-foreground: 30 5% 90%;
		--popover: 240 15% 6.7%;
		--popover-foreground: 30 5% 90%;
		--primary: 42 60% 55%;
		--primary-foreground: 240 20% 3.9%;
		--secondary: 240 10% 15%;
		--secondary-foreground: 30 5% 90%;
		--muted: 240 10% 15%;
		--muted-foreground: 240 10% 55%;
		--accent: 240 10% 15%;
		--accent-foreground: 30 5% 90%;
		--destructive: 0 72% 51%;
		--destructive-foreground: 30 5% 90%;
		--border: 240 15% 18%;
		--input: 240 15% 18%;
		--ring: 42 60% 55%;
		--radius: 0.625rem;
	}

	* {
		border-color: hsl(var(--border));
	}

	body {
		background-color: var(--palais-bg);
		color: var(--palais-text);
		font-family: 'Inter', 'Plus Jakarta Sans', system-ui, sans-serif;
		font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
	}

	h1, h2, h3, h4, h5, h6, nav {
		font-family: 'Orbitron', 'Exo 2', system-ui, sans-serif;
		letter-spacing: 0.02em;
	}

	code, pre, .mono {
		font-family: 'JetBrains Mono', 'Fira Code', monospace;
	}

	.tabular-nums {
		font-variant-numeric: tabular-nums;
	}
}
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/
git commit -m "feat(palais): add Afrofuturist design system theme"
```

---

## Task 3: Adinkra SVG Icons

**Files:**
- Create: `roles/palais/files/app/src/lib/components/icons/` (8 SVG components)

**Step 1: Create Adinkra icon components**

Create `roles/palais/files/app/src/lib/components/icons/index.ts`:
```typescript
export { default as GyeNyame } from './GyeNyame.svelte';
export { default as Dwennimmen } from './Dwennimmen.svelte';
export { default as Nkyinkyim } from './Nkyinkyim.svelte';
export { default as Sankofa } from './Sankofa.svelte';
export { default as Aya } from './Aya.svelte';
export { default as Akoma } from './Akoma.svelte';
export { default as Fawohodie } from './Fawohodie.svelte';
export { default as AnanseNtontan } from './AnanseNtontan.svelte';
```

Create each icon as a Svelte 5 component. Example for `GyeNyame.svelte` (Dashboard/Home):
```svelte
<script lang="ts">
	let { size = 24, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.5"
	stroke-linecap="round"
	stroke-linejoin="round"
	class={className}
>
	<!-- Gye Nyame: omnipotence symbol — stylized spiral -->
	<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
	<path d="M12 6c-1.5 0-3 1.5-3 3s1.5 3 3 3 3 1.5 3 3-1.5 3-3 3" />
	<path d="M12 6v0" stroke-width="3" stroke-linecap="round" />
</svg>
```

**Note for implementation:** Research accurate SVG path data for each Adinkra symbol. Simplified geometric versions are acceptable — these can be refined later. The 8 symbols are:
- `GyeNyame` (omnipotence) → Dashboard
- `Dwennimmen` (humility + strength) → Agents
- `Nkyinkyim` (adaptability) → Projects
- `Sankofa` (learn from past) → Memory
- `Aya` (endurance) → Budget
- `Akoma` (patience) → Ideas
- `Fawohodie` (freedom) → Missions
- `AnanseNtontan` (spider web, wisdom) → Insights

All icons follow the same component pattern: `$props()` with `size` and `class`, SVG with `currentColor`.

**Step 2: Commit**

```bash
git add roles/palais/files/app/src/lib/components/icons/
git commit -m "feat(palais): add Adinkra SVG icon components"
```

---

## Task 4: Database Schema (Complete)

**Files:**
- Create: `roles/palais/files/app/src/lib/server/db/schema.ts`

**Step 1: Define the complete schema**

This file defines ALL tables from the PRD. Read `docs/PRD-PALAIS.md` section "Donnees" for each module.

Create `roles/palais/files/app/src/lib/server/db/schema.ts`:
```typescript
import {
	pgTable, serial, text, varchar, integer, boolean, timestamp,
	real, jsonb, pgEnum, uniqueIndex, index
} from 'drizzle-orm/pg-core';
import { relations } from 'drizzle-orm';

// ============ ENUMS ============

export const agentStatusEnum = pgEnum('agent_status', ['idle', 'busy', 'error', 'offline']);
export const sessionStatusEnum = pgEnum('session_status', ['running', 'completed', 'failed', 'timeout']);
export const spanTypeEnum = pgEnum('span_type', ['llm_call', 'tool_call', 'decision', 'delegation']);
export const priorityEnum = pgEnum('priority', ['none', 'low', 'medium', 'high', 'urgent']);
export const creatorTypeEnum = pgEnum('creator_type', ['user', 'agent', 'system']);
export const depTypeEnum = pgEnum('dep_type', ['finish-to-start', 'start-to-start', 'finish-to-finish']);
export const memoryNodeTypeEnum = pgEnum('memory_node_type', ['episodic', 'semantic', 'procedural']);
export const memoryEntityTypeEnum = pgEnum('memory_entity_type', [
	'agent', 'service', 'task', 'error', 'deployment', 'decision'
]);
export const memoryEdgeRelEnum = pgEnum('memory_edge_rel', [
	'caused_by', 'resolved_by', 'related_to', 'learned_from', 'supersedes'
]);
export const ideaStatusEnum = pgEnum('idea_status', [
	'draft', 'brainstorming', 'planned', 'approved', 'dispatched', 'archived'
]);
export const missionStatusEnum = pgEnum('mission_status', [
	'briefing', 'brainstorming', 'planning', 'co_editing',
	'approved', 'executing', 'review', 'completed', 'failed'
]);
export const insightTypeEnum = pgEnum('insight_type', [
	'agent_stuck', 'budget_warning', 'error_pattern', 'dependency_blocked', 'standup'
]);
export const insightSeverityEnum = pgEnum('insight_severity', ['info', 'warning', 'critical']);
export const entityTypeEnum = pgEnum('entity_type_generic', ['task', 'project', 'mission']);
export const timeEntryTypeEnum = pgEnum('time_entry_type', ['auto', 'manual']);
export const nodeStatusEnum = pgEnum('node_status', ['online', 'offline']);
export const backupStatusEnum = pgEnum('backup_status_type', ['ok', 'failed', 'running']);
export const budgetSourceEnum = pgEnum('budget_source', [
	'litellm', 'openai_direct', 'anthropic_direct', 'openrouter_direct'
]);

// ============ MODULE 1: AGENTS ============

export const agents = pgTable('agents', {
	id: varchar('id', { length: 50 }).primaryKey(),
	name: varchar('name', { length: 100 }).notNull(),
	persona: text('persona'),
	avatar_url: text('avatar_url'),
	model: varchar('model', { length: 100 }),
	status: agentStatusEnum('status').default('offline').notNull(),
	currentTaskId: integer('current_task_id'),
	totalTokens30d: integer('total_tokens_30d').default(0),
	totalSpend30d: real('total_spend_30d').default(0),
	avgQualityScore: real('avg_quality_score'),
	lastSeenAt: timestamp('last_seen_at'),
	createdAt: timestamp('created_at').defaultNow().notNull()
});

export const agentSessions = pgTable('agent_sessions', {
	id: serial('id').primaryKey(),
	agentId: varchar('agent_id', { length: 50 }).notNull().references(() => agents.id),
	taskId: integer('task_id'),
	missionId: integer('mission_id'),
	startedAt: timestamp('started_at').defaultNow().notNull(),
	endedAt: timestamp('ended_at'),
	status: sessionStatusEnum('status').default('running').notNull(),
	totalTokens: integer('total_tokens').default(0),
	totalCost: real('total_cost').default(0),
	model: varchar('model', { length: 100 }),
	summary: text('summary'),
	confidenceScore: real('confidence_score'),
});

export const agentSpans = pgTable('agent_spans', {
	id: serial('id').primaryKey(),
	sessionId: integer('session_id').notNull().references(() => agentSessions.id),
	parentSpanId: integer('parent_span_id'),
	type: spanTypeEnum('type').notNull(),
	name: varchar('name', { length: 200 }).notNull(),
	input: jsonb('input'),
	output: jsonb('output'),
	model: varchar('model', { length: 100 }),
	tokensIn: integer('tokens_in').default(0),
	tokensOut: integer('tokens_out').default(0),
	cost: real('cost').default(0),
	startedAt: timestamp('started_at').defaultNow().notNull(),
	endedAt: timestamp('ended_at'),
	durationMs: integer('duration_ms'),
	error: jsonb('error')
});

// ============ MODULE 2: KNOWLEDGE GRAPH ============

export const memoryNodes = pgTable('memory_nodes', {
	id: serial('id').primaryKey(),
	type: memoryNodeTypeEnum('type').notNull(),
	content: text('content').notNull(),
	summary: text('summary'),
	entityType: memoryEntityTypeEnum('entity_type'),
	entityId: varchar('entity_id', { length: 100 }),
	tags: jsonb('tags').$type<string[]>().default([]),
	metadata: jsonb('metadata'),
	embeddingId: varchar('embedding_id', { length: 100 }),
	validFrom: timestamp('valid_from').defaultNow(),
	validUntil: timestamp('valid_until'),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	createdBy: creatorTypeEnum('created_by').default('system').notNull()
});

export const memoryEdges = pgTable('memory_edges', {
	id: serial('id').primaryKey(),
	sourceNodeId: integer('source_node_id').notNull().references(() => memoryNodes.id),
	targetNodeId: integer('target_node_id').notNull().references(() => memoryNodes.id),
	relation: memoryEdgeRelEnum('relation').notNull(),
	weight: real('weight').default(0.5),
	createdAt: timestamp('created_at').defaultNow().notNull()
});

// ============ MODULE 3: IDEAS ============

export const ideas = pgTable('ideas', {
	id: serial('id').primaryKey(),
	title: varchar('title', { length: 300 }).notNull(),
	description: text('description'),
	status: ideaStatusEnum('status').default('draft').notNull(),
	priority: priorityEnum('priority').default('none'),
	tags: jsonb('tags').$type<string[]>().default([]),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	updatedAt: timestamp('updated_at').defaultNow().notNull()
});

export const ideaVersions = pgTable('idea_versions', {
	id: serial('id').primaryKey(),
	ideaId: integer('idea_id').notNull().references(() => ideas.id),
	versionNumber: integer('version_number').notNull(),
	contentSnapshot: jsonb('content_snapshot'),
	taskBreakdown: jsonb('task_breakdown'),
	brainstormingLog: jsonb('brainstorming_log'),
	memoryContext: jsonb('memory_context'),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	createdBy: creatorTypeEnum('created_by').default('user').notNull()
});

export const ideaLinks = pgTable('idea_links', {
	id: serial('id').primaryKey(),
	sourceIdeaId: integer('source_idea_id').notNull().references(() => ideas.id),
	targetIdeaId: integer('target_idea_id').notNull().references(() => ideas.id),
	linkType: varchar('link_type', { length: 20 }).notNull()
});

// ============ MODULE 4: MISSIONS ============

export const missions = pgTable('missions', {
	id: serial('id').primaryKey(),
	title: varchar('title', { length: 300 }).notNull(),
	ideaId: integer('idea_id').references(() => ideas.id),
	projectId: integer('project_id'),
	status: missionStatusEnum('status').default('briefing').notNull(),
	briefText: text('brief_text'),
	planSnapshot: jsonb('plan_snapshot'),
	totalEstimatedCost: real('total_estimated_cost'),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	completedAt: timestamp('completed_at'),
	actualCost: real('actual_cost')
});

export const missionConversations = pgTable('mission_conversations', {
	id: serial('id').primaryKey(),
	missionId: integer('mission_id').notNull().references(() => missions.id),
	role: varchar('role', { length: 20 }).notNull(),
	content: text('content').notNull(),
	memoryRefs: jsonb('memory_refs'),
	createdAt: timestamp('created_at').defaultNow().notNull()
});

// ============ MODULE 5: PROJECTS & TASKS ============

export const workspaces = pgTable('workspaces', {
	id: serial('id').primaryKey(),
	name: varchar('name', { length: 100 }).notNull(),
	slug: varchar('slug', { length: 100 }).notNull().unique(),
	createdAt: timestamp('created_at').defaultNow().notNull()
});

export const projects = pgTable('projects', {
	id: serial('id').primaryKey(),
	workspaceId: integer('workspace_id').notNull().references(() => workspaces.id),
	name: varchar('name', { length: 200 }).notNull(),
	slug: varchar('slug', { length: 200 }).notNull(),
	icon: varchar('icon', { length: 50 }),
	description: text('description'),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	updatedAt: timestamp('updated_at').defaultNow().notNull()
});

export const columns = pgTable('columns', {
	id: serial('id').primaryKey(),
	projectId: integer('project_id').notNull().references(() => projects.id),
	name: varchar('name', { length: 100 }).notNull(),
	position: integer('position').notNull().default(0),
	isFinal: boolean('is_final').default(false),
	color: varchar('color', { length: 20 })
});

export const tasks = pgTable('tasks', {
	id: serial('id').primaryKey(),
	projectId: integer('project_id').notNull().references(() => projects.id),
	columnId: integer('column_id').notNull().references(() => columns.id),
	title: varchar('title', { length: 500 }).notNull(),
	description: text('description'),
	status: varchar('status', { length: 30 }).default('backlog'),
	priority: priorityEnum('priority').default('none'),
	assigneeAgentId: varchar('assignee_agent_id', { length: 50 }).references(() => agents.id),
	creator: creatorTypeEnum('creator').default('user').notNull(),
	startDate: timestamp('start_date'),
	endDate: timestamp('end_date'),
	dueDate: timestamp('due_date'),
	position: integer('position').default(0),
	estimatedCost: real('estimated_cost'),
	actualCost: real('actual_cost'),
	confidenceScore: real('confidence_score'),
	missionId: integer('mission_id').references(() => missions.id),
	sessionId: integer('session_id'),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	updatedAt: timestamp('updated_at').defaultNow().notNull()
});

export const taskDependencies = pgTable('task_dependencies', {
	id: serial('id').primaryKey(),
	taskId: integer('task_id').notNull().references(() => tasks.id),
	dependsOnTaskId: integer('depends_on_task_id').notNull().references(() => tasks.id),
	dependencyType: depTypeEnum('dependency_type').default('finish-to-start').notNull()
}, (table) => [
	uniqueIndex('task_dep_unique').on(table.taskId, table.dependsOnTaskId)
]);

export const labels = pgTable('labels', {
	id: serial('id').primaryKey(),
	workspaceId: integer('workspace_id').notNull().references(() => workspaces.id),
	name: varchar('name', { length: 50 }).notNull(),
	color: varchar('color', { length: 20 }).notNull()
});

export const taskLabels = pgTable('task_labels', {
	taskId: integer('task_id').notNull().references(() => tasks.id),
	labelId: integer('label_id').notNull().references(() => labels.id)
}, (table) => [
	uniqueIndex('task_label_pk').on(table.taskId, table.labelId)
]);

export const comments = pgTable('comments', {
	id: serial('id').primaryKey(),
	taskId: integer('task_id').notNull().references(() => tasks.id),
	authorType: creatorTypeEnum('author_type').default('user').notNull(),
	authorAgentId: varchar('author_agent_id', { length: 50 }),
	content: text('content').notNull(),
	createdAt: timestamp('created_at').defaultNow().notNull()
});

export const activityLog = pgTable('activity_log', {
	id: serial('id').primaryKey(),
	entityType: varchar('entity_type', { length: 30 }).notNull(),
	entityId: integer('entity_id').notNull(),
	actorType: creatorTypeEnum('actor_type').default('system').notNull(),
	actorAgentId: varchar('actor_agent_id', { length: 50 }),
	action: varchar('action', { length: 100 }).notNull(),
	oldValue: text('old_value'),
	newValue: text('new_value'),
	createdAt: timestamp('created_at').defaultNow().notNull()
}, (table) => [
	index('activity_entity_idx').on(table.entityType, table.entityId)
]);

// ============ MODULE 6: TIME TRACKING ============

export const timeEntries = pgTable('time_entries', {
	id: serial('id').primaryKey(),
	taskId: integer('task_id').notNull().references(() => tasks.id),
	agentId: varchar('agent_id', { length: 50 }),
	startedAt: timestamp('started_at').defaultNow().notNull(),
	endedAt: timestamp('ended_at'),
	durationSeconds: integer('duration_seconds'),
	type: timeEntryTypeEnum('type').default('auto').notNull(),
	notes: text('notes')
});

export const taskIterations = pgTable('task_iterations', {
	id: serial('id').primaryKey(),
	taskId: integer('task_id').notNull().references(() => tasks.id),
	iterationNumber: integer('iteration_number').notNull(),
	reopenedAt: timestamp('reopened_at').defaultNow().notNull(),
	reason: text('reason'),
	resolvedAt: timestamp('resolved_at')
});

// ============ MODULE 7: DELIVERABLES ============

export const deliverables = pgTable('deliverables', {
	id: serial('id').primaryKey(),
	entityType: entityTypeEnum('entity_type').notNull(),
	entityId: integer('entity_id').notNull(),
	filename: varchar('filename', { length: 500 }).notNull(),
	mimeType: varchar('mime_type', { length: 100 }),
	sizeBytes: integer('size_bytes'),
	storagePath: text('storage_path').notNull(),
	downloadToken: varchar('download_token', { length: 36 }).notNull().unique(),
	uploadedByType: creatorTypeEnum('uploaded_by_type').default('user').notNull(),
	uploadedByAgentId: varchar('uploaded_by_agent_id', { length: 50 }),
	createdAt: timestamp('created_at').defaultNow().notNull()
}, (table) => [
	index('deliverable_token_idx').on(table.downloadToken)
]);

// ============ MODULE 8: BUDGET ============

export const budgetSnapshots = pgTable('budget_snapshots', {
	id: serial('id').primaryKey(),
	date: timestamp('date').notNull(),
	source: budgetSourceEnum('source').notNull(),
	provider: varchar('provider', { length: 50 }),
	agentId: varchar('agent_id', { length: 50 }),
	spendAmount: real('spend_amount').default(0),
	tokenCount: integer('token_count').default(0),
	requestCount: integer('request_count').default(0),
	capturedAt: timestamp('captured_at').defaultNow().notNull()
});

export const budgetForecasts = pgTable('budget_forecasts', {
	id: serial('id').primaryKey(),
	date: timestamp('date').notNull(),
	predictedSpend: real('predicted_spend'),
	predictedExhaustionTime: timestamp('predicted_exhaustion_time'),
	remainingBudget: real('remaining_budget'),
	computedAt: timestamp('computed_at').defaultNow().notNull()
});

// ============ MODULE 9: INSIGHTS ============

export const insights = pgTable('insights', {
	id: serial('id').primaryKey(),
	type: insightTypeEnum('type').notNull(),
	severity: insightSeverityEnum('severity').default('info').notNull(),
	title: varchar('title', { length: 300 }).notNull(),
	description: text('description'),
	suggestedActions: jsonb('suggested_actions'),
	entityType: varchar('entity_type', { length: 30 }),
	entityId: integer('entity_id'),
	memoryRefs: jsonb('memory_refs'),
	acknowledged: boolean('acknowledged').default(false),
	createdAt: timestamp('created_at').defaultNow().notNull()
});

// ============ MODULE 11: NODES / HEALTH ============

export const nodes = pgTable('nodes', {
	id: serial('id').primaryKey(),
	name: varchar('name', { length: 50 }).notNull().unique(),
	tailscaleIp: varchar('tailscale_ip', { length: 50 }),
	status: nodeStatusEnum('status').default('offline'),
	lastSeenAt: timestamp('last_seen_at'),
	cpuPercent: real('cpu_percent'),
	ramPercent: real('ram_percent'),
	diskPercent: real('disk_percent'),
	temperature: real('temperature')
});

export const healthChecks = pgTable('health_checks', {
	id: serial('id').primaryKey(),
	nodeId: integer('node_id').notNull().references(() => nodes.id),
	serviceName: varchar('service_name', { length: 100 }).notNull(),
	status: varchar('status', { length: 20 }).notNull(),
	responseTimeMs: integer('response_time_ms'),
	checkedAt: timestamp('checked_at').defaultNow().notNull(),
	details: jsonb('details')
});

export const backupStatus = pgTable('backup_status', {
	id: serial('id').primaryKey(),
	nodeId: integer('node_id').notNull().references(() => nodes.id),
	lastBackupAt: timestamp('last_backup_at'),
	nextBackupAt: timestamp('next_backup_at'),
	sizeBytes: integer('size_bytes'),
	status: backupStatusEnum('status').default('ok'),
	details: jsonb('details')
});
```

**Step 2: Generate migration**

```bash
cd roles/palais/files/app
DATABASE_URL="postgresql://palais:palais@localhost:5432/palais" npx drizzle-kit generate
```

This creates SQL migration files in `drizzle/` folder.

**Step 3: Commit**

```bash
git add roles/palais/files/app/src/lib/server/db/schema.ts roles/palais/files/app/drizzle/
git commit -m "feat(palais): complete database schema — all 15 modules"
```

---

## Task 5: Auth — Cookie + API Key

**Files:**
- Create: `roles/palais/files/app/src/hooks.server.ts`
- Create: `roles/palais/files/app/src/routes/login/+page.svelte`
- Create: `roles/palais/files/app/src/routes/login/+page.server.ts`
- Create: `roles/palais/files/app/src/routes/api/auth/login/+server.ts`

**Step 1: Create auth hook**

Create `roles/palais/files/app/src/hooks.server.ts`:
```typescript
import type { Handle } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

const API_KEY = env.PALAIS_API_KEY || 'dev-key';
const SESSION_SECRET = env.SESSION_SECRET || 'dev-secret';

export const handle: Handle = async ({ event, resolve }) => {
	// API key auth (agents, n8n, MCP)
	const apiKey = event.request.headers.get('x-api-key');
	if (apiKey && apiKey === API_KEY) {
		event.locals.user = { authenticated: true, source: 'api' };
		return resolve(event);
	}

	// Cookie auth (browser)
	const session = event.cookies.get('palais_session');
	if (session) {
		event.locals.user = { authenticated: true, source: 'cookie' };
		return resolve(event);
	}

	// Public routes
	const publicPaths = ['/login', '/api/health', '/dl/'];
	const isPublic = publicPaths.some((p) => event.url.pathname.startsWith(p));

	if (!isPublic && event.url.pathname.startsWith('/api/')) {
		return new Response(JSON.stringify({ error: 'Unauthorized' }), {
			status: 401,
			headers: { 'Content-Type': 'application/json' }
		});
	}

	if (!isPublic) {
		return new Response(null, {
			status: 302,
			headers: { Location: '/login' }
		});
	}

	event.locals.user = { authenticated: false, source: 'none' };
	return resolve(event);
};
```

Create `roles/palais/files/app/src/app.d.ts`:
```typescript
declare global {
	namespace App {
		interface Locals {
			user: {
				authenticated: boolean;
				source: 'api' | 'cookie' | 'none';
			};
		}
	}
}

export {};
```

**Step 2: Create login API route**

Create `roles/palais/files/app/src/routes/api/auth/login/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

const ADMIN_PASSWORD = env.PALAIS_ADMIN_PASSWORD || 'admin';

export const POST: RequestHandler = async ({ request, cookies }) => {
	const { password } = await request.json();

	if (password !== ADMIN_PASSWORD) {
		return json({ error: 'Invalid password' }, { status: 401 });
	}

	cookies.set('palais_session', `s_${Date.now()}_${crypto.randomUUID()}`, {
		httpOnly: true,
		secure: true,
		sameSite: 'strict',
		maxAge: 60 * 60 * 24 * 7,
		path: '/'
	});

	return json({ success: true });
};
```

**Step 3: Create login page**

Create `roles/palais/files/app/src/routes/login/+page.svelte`:
```svelte
<script lang="ts">
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleLogin(e: Event) {
		e.preventDefault();
		loading = true;
		error = '';

		const res = await fetch('/api/auth/login', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ password })
		});

		if (res.ok) {
			window.location.href = '/';
		} else {
			error = 'Invalid password';
		}
		loading = false;
	}
</script>

<div class="min-h-screen flex items-center justify-center" style="background: var(--palais-bg);">
	<div class="w-full max-w-sm p-8 rounded-lg" style="background: var(--palais-surface); border: 1px solid var(--palais-border);">
		<h1 class="text-2xl font-bold text-center mb-8" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
			PALAIS
		</h1>
		<form onsubmit={handleLogin}>
			<input
				type="password"
				bind:value={password}
				placeholder="Enter password"
				class="w-full px-4 py-3 rounded-md mb-4 outline-none focus:ring-2"
				style="background: var(--palais-bg); color: var(--palais-text); border: 1px solid var(--palais-border);"
			/>
			{#if error}
				<p class="text-sm mb-4" style="color: var(--palais-red);">{error}</p>
			{/if}
			<button
				type="submit"
				disabled={loading}
				class="w-full py-3 rounded-md font-semibold transition-all"
				style="background: var(--palais-gold); color: var(--palais-bg);"
			>
				{loading ? '...' : 'Enter'}
			</button>
		</form>
	</div>
</div>
```

**Step 4: Commit**

```bash
git add roles/palais/files/app/src/hooks.server.ts roles/palais/files/app/src/app.d.ts roles/palais/files/app/src/routes/
git commit -m "feat(palais): add auth — cookie + API key with login page"
```

---

## Task 6: API Routes — Health + Agents + Projects + Tasks

**Files:**
- Create: `roles/palais/files/app/src/routes/api/health/+server.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/agents/+server.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/projects/+server.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/projects/[id]/tasks/+server.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/tasks/[id]/+server.ts`

**Step 1: Health endpoint**

Create `roles/palais/files/app/src/routes/api/health/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { sql } from 'drizzle-orm';

export const GET: RequestHandler = async () => {
	try {
		await db.execute(sql`SELECT 1`);
		return json({ status: 'ok', timestamp: new Date().toISOString() });
	} catch {
		return json({ status: 'error', message: 'Database unreachable' }, { status: 503 });
	}
};
```

**Step 2: Agents CRUD**

Create `roles/palais/files/app/src/routes/api/v1/agents/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { agents } from '$lib/server/db/schema';

export const GET: RequestHandler = async () => {
	const result = await db.select().from(agents).orderBy(agents.name);
	return json(result);
};
```

**Step 3: Projects CRUD**

Create `roles/palais/files/app/src/routes/api/v1/projects/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { projects, columns, workspaces } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const GET: RequestHandler = async () => {
	const result = await db.select().from(projects).orderBy(projects.updatedAt);
	return json(result);
};

export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	const { name, description, workspaceId } = body;

	if (!name || !workspaceId) {
		return json({ error: 'name and workspaceId required' }, { status: 400 });
	}

	const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

	const [project] = await db.insert(projects).values({
		workspaceId,
		name,
		slug,
		description
	}).returning();

	// Create default columns
	const defaultCols = ['Backlog', 'Planning', 'Assigned', 'In Progress', 'Review', 'Done'];
	for (let i = 0; i < defaultCols.length; i++) {
		await db.insert(columns).values({
			projectId: project.id,
			name: defaultCols[i],
			position: i,
			isFinal: i === defaultCols.length - 1
		});
	}

	return json(project, { status: 201 });
};
```

**Step 4: Tasks CRUD**

Create `roles/palais/files/app/src/routes/api/v1/projects/[id]/tasks/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { tasks } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const GET: RequestHandler = async ({ params }) => {
	const projectId = parseInt(params.id);
	const result = await db.select().from(tasks).where(eq(tasks.projectId, projectId)).orderBy(tasks.position);
	return json(result);
};

export const POST: RequestHandler = async ({ params, request }) => {
	const projectId = parseInt(params.id);
	const body = await request.json();

	const [task] = await db.insert(tasks).values({
		projectId,
		columnId: body.columnId,
		title: body.title,
		description: body.description,
		priority: body.priority || 'none',
		assigneeAgentId: body.assigneeAgentId,
		creator: body.creator || 'user'
	}).returning();

	return json(task, { status: 201 });
};
```

Create `roles/palais/files/app/src/routes/api/v1/tasks/[id]/+server.ts`:
```typescript
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/server/db';
import { tasks } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export const PUT: RequestHandler = async ({ params, request }) => {
	const taskId = parseInt(params.id);
	const body = await request.json();

	const [updated] = await db.update(tasks)
		.set({ ...body, updatedAt: new Date() })
		.where(eq(tasks.id, taskId))
		.returning();

	if (!updated) {
		return json({ error: 'Task not found' }, { status: 404 });
	}

	return json(updated);
};
```

**Step 5: Commit**

```bash
git add roles/palais/files/app/src/routes/api/
git commit -m "feat(palais): add API routes — health, agents, projects, tasks CRUD"
```

---

## Task 7: Dashboard Layout

**Files:**
- Create: `roles/palais/files/app/src/routes/+layout.svelte`
- Create: `roles/palais/files/app/src/routes/+page.svelte`
- Create: `roles/palais/files/app/src/lib/components/layout/Sidebar.svelte`

**Step 1: Create sidebar navigation**

Create `roles/palais/files/app/src/lib/components/layout/Sidebar.svelte`:
```svelte
<script lang="ts">
	import { page } from '$app/stores';
	import {
		GyeNyame, Dwennimmen, Nkyinkyim, Sankofa,
		Aya, Akoma, Fawohodie, AnanseNtontan
	} from '$lib/components/icons';

	const nav = [
		{ href: '/', label: 'Dashboard', icon: GyeNyame },
		{ href: '/agents', label: 'Agents', icon: Dwennimmen },
		{ href: '/projects', label: 'Projects', icon: Nkyinkyim },
		{ href: '/missions', label: 'Missions', icon: Fawohodie },
		{ href: '/ideas', label: 'Ideas', icon: Akoma },
		{ href: '/memory', label: 'Memory', icon: Sankofa },
		{ href: '/budget', label: 'Budget', icon: Aya },
		{ href: '/insights', label: 'Insights', icon: AnanseNtontan },
	];

	let currentPath = $derived($page.url.pathname);
</script>

<aside class="fixed left-0 top-0 h-screen w-16 flex flex-col items-center py-6 gap-2 z-50"
	style="background: var(--palais-surface); border-right: 1px solid var(--palais-border);">

	<div class="mb-6" style="color: var(--palais-gold);">
		<span class="text-lg font-bold" style="font-family: 'Orbitron', sans-serif;">P</span>
	</div>

	{#each nav as item}
		{@const active = currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))}
		<a
			href={item.href}
			class="w-10 h-10 flex items-center justify-center rounded-lg transition-all group relative"
			style:background={active ? 'var(--palais-gold-glow)' : 'transparent'}
			style:color={active ? 'var(--palais-gold)' : 'var(--palais-text-muted)'}
			style:box-shadow={active ? 'var(--palais-glow-sm)' : 'none'}
		>
			<item.icon size={20} />
			<span class="absolute left-14 px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap transition-opacity"
				style="background: var(--palais-surface); color: var(--palais-text); border: 1px solid var(--palais-border);">
				{item.label}
			</span>
		</a>
	{/each}
</aside>
```

**Step 2: Create root layout**

Create `roles/palais/files/app/src/routes/+layout.svelte`:
```svelte
<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/layout/Sidebar.svelte';
	let { children } = $props();
</script>

<svelte:head>
	<title>Palais</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
</svelte:head>

<div class="min-h-screen" style="background: var(--palais-bg);">
	<Sidebar />
	<main class="ml-16 p-6">
		{@render children()}
	</main>
</div>
```

**Step 3: Create dashboard page**

Create `roles/palais/files/app/src/routes/+page.server.ts`:
```typescript
import { db } from '$lib/server/db';
import { agents } from '$lib/server/db/schema';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const allAgents = await db.select().from(agents).orderBy(agents.name);
	return { agents: allAgents };
};
```

Create `roles/palais/files/app/src/routes/+page.svelte`:
```svelte
<script lang="ts">
	let { data } = $props();
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold" style="color: var(--palais-gold); font-family: 'Orbitron', sans-serif;">
			PALAIS
		</h1>
		<span class="text-sm tabular-nums" style="color: var(--palais-text-muted);">
			{new Date().toLocaleDateString('fr-FR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
		</span>
	</div>

	<!-- Agent Grid -->
	<section>
		<h2 class="text-sm font-semibold uppercase tracking-wider mb-4" style="color: var(--palais-text-muted);">
			Agents
		</h2>
		<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
			{#each data.agents as agent}
				<div class="p-4 rounded-lg transition-all hover:scale-[1.02]"
					style="background: var(--palais-surface); border: 1px solid var(--palais-border);"
					style:box-shadow={agent.status === 'busy' ? 'var(--palais-glow-md)' : 'none'}
					style:border-color={agent.status === 'busy' ? 'var(--palais-gold)' : 'var(--palais-border)'}
				>
					<!-- Avatar placeholder -->
					<div class="w-10 h-10 rounded-full flex items-center justify-center mb-3"
						style="background: linear-gradient(135deg, var(--palais-gold), var(--palais-amber)); color: var(--palais-bg);">
						<span class="text-sm font-bold">{agent.name.substring(0, 2).toUpperCase()}</span>
					</div>
					<h3 class="text-sm font-semibold" style="color: var(--palais-text);">{agent.name}</h3>
					<p class="text-xs mt-1 capitalize"
						style:color={
							agent.status === 'idle' ? 'var(--palais-green)' :
							agent.status === 'busy' ? 'var(--palais-gold)' :
							agent.status === 'error' ? 'var(--palais-red)' :
							'var(--palais-text-muted)'
						}
					>
						{agent.status}
					</p>
				</div>
			{/each}
		</div>
	</section>
</div>
```

**Step 4: Commit**

```bash
git add roles/palais/files/app/src/routes/ roles/palais/files/app/src/lib/components/layout/
git commit -m "feat(palais): add dashboard layout with Afrofuturist sidebar + agent grid"
```

---

## Task 8: Dockerfile

**Files:**
- Create: `roles/palais/files/app/Dockerfile`

**Step 1: Create multi-stage Dockerfile**

Create `roles/palais/files/app/Dockerfile`:
```dockerfile
# Stage 1: Builder
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build
RUN npm prune --omit=dev

# Stage 2: Runtime
FROM node:22-alpine

RUN apk add --no-cache dumb-init

WORKDIR /app

COPY --from=builder /app/build ./build
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/drizzle ./drizzle

RUN addgroup -g 1000 palais && adduser -u 1000 -G palais -s /bin/sh -D palais
RUN mkdir -p /data/deliverables /data/avatars && chown -R palais:palais /data

USER palais

EXPOSE 3300

ENV PORT=3300
ENV HOST=0.0.0.0

ENTRYPOINT ["dumb-init", "--"]
CMD ["node", "build"]
```

Create `roles/palais/files/app/.dockerignore`:
```
node_modules
.svelte-kit
build
.env
.env.*
```

**Step 2: Commit**

```bash
git add roles/palais/files/app/Dockerfile roles/palais/files/app/.dockerignore
git commit -m "feat(palais): add multi-stage Dockerfile for Node.js 22 Alpine"
```

---

## Task 9: Ansible Role — defaults + vars + handlers

**Files:**
- Create: `roles/palais/defaults/main.yml`
- Create: `roles/palais/vars/main.yml`
- Create: `roles/palais/handlers/main.yml`

**Step 1: Create defaults**

Create `roles/palais/defaults/main.yml`:
```yaml
---
# Palais — Defaults (overridable)

# Directories
palais_config_dir: "/opt/{{ project_name }}/configs/palais"
palais_data_dir: "/opt/{{ project_name }}/data/palais"
palais_app_dir: "{{ role_path }}/files/app"

# Network
palais_port: 3300
palais_subdomain: "palais"

# Database
palais_db_name: "palais"
palais_db_user: "palais"
palais_db_password: "{{ vault_palais_db_password | default(postgresql_password) }}"

# Qdrant
palais_qdrant_collection: "palais_memory"
palais_qdrant_vector_size: 1536

# Auth
palais_api_key: "{{ vault_palais_api_key | default('changeme') }}"
palais_admin_password: "{{ vault_palais_admin_password | default('admin') }}"
palais_session_secret: "{{ vault_palais_session_secret | default('changeme') }}"

# Resources
palais_memory_limit: "192M"
palais_memory_reservation: "128M"
palais_cpu_limit: "0.75"

# Standup
palais_standup_hour: "08"

# Agents (same as OpenClaw)
palais_agents:
  - { id: "concierge", name: "Mobutoo", persona: "Chef d'orchestre" }
  - { id: "builder", name: "Imhotep", persona: "Architecte & Ingenieur" }
  - { id: "writer", name: "Thot", persona: "Redacteur & Scribe" }
  - { id: "artist", name: "Basquiat", persona: "Directeur Artistique" }
  - { id: "tutor", name: "Piccolo", persona: "Tuteur & Formateur" }
  - { id: "explorer", name: "R2D2", persona: "Explorateur & Recherche" }
  - { id: "marketer", name: "Marketer", persona: "Marketing & Growth" }
  - { id: "cfo", name: "CFO", persona: "Directeur Financier" }
  - { id: "maintainer", name: "Maintainer", persona: "DevOps & Maintenance" }
  - { id: "messenger", name: "Hermes", persona: "Pont inter-systemes" }
```

**Step 2: Create vars**

Create `roles/palais/vars/main.yml`:
```yaml
---
# Palais — Fixed vars (not overridable)
palais_container_name: "{{ project_name }}_palais"
```

**Step 3: Create handlers**

Create `roles/palais/handlers/main.yml`:
```yaml
---
- name: Check palais service is in compose file
  ansible.builtin.command:
    cmd: grep -q "palais" /opt/{{ project_name }}/docker-compose.yml
  register: _palais_in_compose
  failed_when: false
  changed_when: false
  listen: Restart palais

- name: Restart palais container
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - palais
    state: restarted
  become: true
  when:
    - not ansible_check_mode
    - _palais_in_compose.rc | default(1) == 0
  listen: Restart palais
```

**Step 4: Commit**

```bash
git add roles/palais/defaults/ roles/palais/vars/ roles/palais/handlers/
git commit -m "feat(palais): add Ansible role defaults, vars, handlers"
```

---

## Task 10: Ansible Role — tasks/main.yml + templates

**Files:**
- Create: `roles/palais/tasks/main.yml`
- Create: `roles/palais/templates/palais.env.j2`

**Step 1: Create env template**

Create `roles/palais/templates/palais.env.j2`:
```bash
# Palais Environment — Generated by Ansible
# Do not edit manually

# Database
DATABASE_URL=postgresql://{{ palais_db_user }}:{{ palais_db_password }}@postgresql:5432/{{ palais_db_name }}

# OpenClaw
OPENCLAW_WS_URL=ws://openclaw:18789

# LiteLLM
LITELLM_URL=http://litellm:4000
LITELLM_KEY={{ litellm_master_key }}

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION={{ palais_qdrant_collection }}

# n8n Webhooks
N8N_WEBHOOK_BASE=http://n8n:5678/webhook

# Auth
PALAIS_API_KEY={{ palais_api_key }}
PALAIS_ADMIN_PASSWORD={{ palais_admin_password }}
SESSION_SECRET={{ palais_session_secret }}

# Server
PORT={{ palais_port }}
HOST=0.0.0.0
ORIGIN=https://{{ palais_subdomain }}.{{ domain_name }}
NODE_ENV=production
TZ={{ timezone }}

# Standup
STANDUP_HOUR={{ palais_standup_hour }}
```

**Step 2: Create tasks**

Create `roles/palais/tasks/main.yml`:
```yaml
---
# Palais — Main tasks

- name: Create palais config directory
  ansible.builtin.file:
    path: "{{ palais_config_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0750"
  become: true
  tags: [palais]

- name: Create palais data directories
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: "1000"
    group: "1000"
    mode: "0750"
  become: true
  loop:
    - "{{ palais_data_dir }}"
    - "{{ palais_data_dir }}/deliverables"
    - "{{ palais_data_dir }}/avatars"
  tags: [palais]

- name: Deploy palais environment file
  ansible.builtin.template:
    src: palais.env.j2
    dest: "{{ palais_config_dir }}/palais.env"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0640"
  become: true
  notify: Restart palais
  tags: [palais]

- name: Copy palais application source
  ansible.posix.synchronize:
    src: "{{ palais_app_dir }}/"
    dest: "/opt/{{ project_name }}/palais-app/"
    delete: true
    rsync_opts:
      - "--exclude=node_modules"
      - "--exclude=.svelte-kit"
      - "--exclude=build"
  become: true
  notify: Restart palais
  tags: [palais]
```

**Step 3: Commit**

```bash
git add roles/palais/tasks/ roles/palais/templates/
git commit -m "feat(palais): add Ansible tasks and env template"
```

---

## Task 11: Ansible Integration — PostgreSQL, Docker Compose, Caddy, Playbook

**Files:**
- Modify: `roles/postgresql/defaults/main.yml` — add palais DB
- Modify: `roles/docker-stack/templates/docker-compose.yml.j2` — add palais service
- Modify: `roles/caddy/templates/Caddyfile.j2` — add palais subdomain
- Modify: `roles/caddy/defaults/main.yml` — add palais domain variable
- Modify: `playbooks/site.yml` — add palais role
- Modify: `inventory/group_vars/all/main.yml` — add palais variables

**Step 1: Add DB to PostgreSQL**

In `roles/postgresql/defaults/main.yml`, add to `postgresql_databases`:
```yaml
  - name: palais
    user: palais
    extensions:
      - uuid-ossp
```

**Step 2: Add Docker Compose service**

In `roles/docker-stack/templates/docker-compose.yml.j2`, add the `palais` service in the apps section (after openclaw, before monitoring):
```yaml
  palais:
    build:
      context: /opt/{{ project_name }}/palais-app
      dockerfile: Dockerfile
    container_name: {{ project_name }}_palais
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
    env_file:
      - {{ palais_config_dir }}/palais.env
    networks:
      - frontend
      - backend
    volumes:
      - {{ palais_data_dir }}/deliverables:/data/deliverables
      - {{ palais_data_dir }}/avatars:/data/avatars
    deploy:
      resources:
        limits:
          memory: {{ palais_memory_limit }}
          cpus: "{{ palais_cpu_limit }}"
        reservations:
          memory: {{ palais_memory_reservation }}
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://localhost:{{ palais_port }}/api/health').then(r=>{if(!r.ok)throw 1})"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

**Step 3: Add Caddy subdomain**

In `roles/caddy/defaults/main.yml`, add:
```yaml
caddy_palais_domain: "{{ palais_subdomain | default('palais') }}.{{ domain_name }}"
```

In `roles/caddy/templates/Caddyfile.j2`, add the Palais block (after existing services):
```caddyfile
{{ caddy_palais_domain }} {
    import vpn_only
    import vpn_error_page
    import security_headers

    reverse_proxy palais:{{ palais_port }}
}
```

**Step 4: Add to playbook**

In `playbooks/site.yml`, add `palais` role in Phase 3 (Applications), after `kaneo`:
```yaml
    - role: palais
      tags: [palais, phase3]
```

**Step 5: Add variables to main.yml**

In `inventory/group_vars/all/main.yml`, add a Palais section:
```yaml
# === PALAIS ===
palais_subdomain: "palais"
```

**Step 6: Commit**

```bash
git add roles/postgresql/defaults/main.yml roles/docker-stack/templates/docker-compose.yml.j2 roles/caddy/ playbooks/site.yml inventory/group_vars/all/main.yml
git commit -m "feat(palais): integrate Ansible — PostgreSQL, Docker Compose, Caddy, playbook"
```

---

## Task 12: Agent Seed Script

**Files:**
- Create: `roles/palais/files/app/scripts/seed-agents.ts`

**Step 1: Create seed script**

Create `roles/palais/files/app/scripts/seed-agents.ts`:
```typescript
import postgres from 'postgres';

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
	console.error('DATABASE_URL required');
	process.exit(1);
}

const sql = postgres(DATABASE_URL);

const agentsSeed = [
	{ id: 'concierge', name: 'Mobutoo', persona: "Chef d'orchestre — coordonne, delegue, supervise" },
	{ id: 'builder', name: 'Imhotep', persona: 'Architecte & Ingenieur — code, deploie, construit' },
	{ id: 'writer', name: 'Thot', persona: 'Redacteur & Scribe — contenu, docs, briefings' },
	{ id: 'artist', name: 'Basquiat', persona: 'Directeur Artistique — visuels, design, creative' },
	{ id: 'tutor', name: 'Piccolo', persona: 'Tuteur & Formateur — enseigne, explique, guide' },
	{ id: 'explorer', name: 'R2D2', persona: 'Explorateur & Recherche — explore, analyse, decouvre' },
	{ id: 'marketer', name: 'Marketer', persona: 'Marketing & Growth — campagnes, SEO, social' },
	{ id: 'cfo', name: 'CFO', persona: 'Directeur Financier — budget, couts, optimisation' },
	{ id: 'maintainer', name: 'Maintainer', persona: 'DevOps & Maintenance — infra, monitoring, fixes' },
	{ id: 'messenger', name: 'Hermes', persona: 'Pont inter-systemes — relais, communication, sync' },
];

async function seed() {
	console.log('Seeding agents...');

	// Create default workspace
	const [ws] = await sql`
		INSERT INTO workspaces (name, slug)
		VALUES ('Palais', 'palais')
		ON CONFLICT (slug) DO UPDATE SET name = 'Palais'
		RETURNING id
	`;

	// Seed agents
	for (const agent of agentsSeed) {
		await sql`
			INSERT INTO agents (id, name, persona, status)
			VALUES (${agent.id}, ${agent.name}, ${agent.persona}, 'offline')
			ON CONFLICT (id) DO UPDATE SET
				name = EXCLUDED.name,
				persona = EXCLUDED.persona
		`;
		console.log(`  ✓ ${agent.name} (${agent.id})`);
	}

	console.log(`Seeded ${agentsSeed.length} agents + workspace (id=${ws.id})`);
	await sql.end();
}

seed().catch((err) => {
	console.error('Seed failed:', err);
	process.exit(1);
});
```

**Step 2: Add seed script to package.json**

In `roles/palais/files/app/package.json`, add to `"scripts"`:
```json
"db:seed": "tsx scripts/seed-agents.ts",
"db:push": "drizzle-kit push",
"db:generate": "drizzle-kit generate",
"db:migrate": "drizzle-kit migrate"
```

**Step 3: Commit**

```bash
git add roles/palais/files/app/scripts/ roles/palais/files/app/package.json
git commit -m "feat(palais): add agent seed script + DB scripts"
```

---

## Task 13: Final Verification

**Step 1: Verify project structure**

Expected structure:
```
roles/palais/
├── defaults/main.yml
├── vars/main.yml
├── tasks/main.yml
├── handlers/main.yml
├── templates/
│   └── palais.env.j2
└── files/
    └── app/
        ├── Dockerfile
        ├── .dockerignore
        ├── drizzle.config.ts
        ├── svelte.config.js
        ├── package.json
        ├── scripts/
        │   └── seed-agents.ts
        ├── drizzle/
        │   └── *.sql
        └── src/
            ├── app.css
            ├── app.d.ts
            ├── hooks.server.ts
            ├── lib/
            │   ├── styles/theme.css
            │   ├── server/db/
            │   │   ├── index.ts
            │   │   └── schema.ts
            │   └── components/
            │       ├── icons/*.svelte
            │       └── layout/Sidebar.svelte
            └── routes/
                ├── +layout.svelte
                ├── +page.svelte
                ├── +page.server.ts
                ├── login/
                │   └── +page.svelte
                └── api/
                    ├── health/+server.ts
                    ├── auth/login/+server.ts
                    └── v1/
                        ├── agents/+server.ts
                        ├── projects/+server.ts
                        ├── projects/[id]/tasks/+server.ts
                        └── tasks/[id]/+server.ts
```

**Step 2: Run linting**

```bash
cd roles/palais/files/app
npm run lint
npm run check
```

**Step 3: Run Ansible lint**

```bash
cd /home/asus/seko/VPAI/.claude/worktrees/jolly-nightingale
source .venv/bin/activate
make lint
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(palais): Phase 1 complete — foundations + design system"
```

---

## Verification Checklist

After implementation, verify:

- [ ] `npm run dev` starts without errors (in `roles/palais/files/app/`)
- [ ] `GET /api/health` returns `{"status":"ok"}`
- [ ] Login page renders at `/login` with Afrofuturist theme
- [ ] Dashboard renders at `/` with agent grid (10 agents after seed)
- [ ] Sidebar shows Adinkra icons with hover tooltips
- [ ] `GET /api/v1/agents` returns 10 agents (with API key)
- [ ] `POST /api/v1/projects` creates project with default columns
- [ ] Theme uses gold (#D4A843), dark bg (#0A0A0F), Orbitron for headings
- [ ] `make lint` passes (Ansible + YAML)
- [ ] Docker build succeeds: `docker build -t palais:test roles/palais/files/app/`
- [ ] Drizzle migrations generated in `drizzle/` folder
