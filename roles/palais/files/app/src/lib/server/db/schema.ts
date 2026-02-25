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
	bio: text('bio'),
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
	localIp: varchar('local_ip', { length: 50 }),
	description: text('description'),
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

// ============ RELATIONS ============

export const agentsRelations = relations(agents, ({ many }) => ({
	sessions: many(agentSessions),
	tasks: many(tasks, { relationName: 'assignedTasks' })
}));

export const agentSessionsRelations = relations(agentSessions, ({ one, many }) => ({
	agent: one(agents, { fields: [agentSessions.agentId], references: [agents.id] }),
	spans: many(agentSpans)
}));

export const agentSpansRelations = relations(agentSpans, ({ one }) => ({
	session: one(agentSessions, { fields: [agentSpans.sessionId], references: [agentSessions.id] })
}));

export const workspacesRelations = relations(workspaces, ({ many }) => ({
	projects: many(projects),
	labels: many(labels)
}));

export const projectsRelations = relations(projects, ({ one, many }) => ({
	workspace: one(workspaces, { fields: [projects.workspaceId], references: [workspaces.id] }),
	columns: many(columns),
	tasks: many(tasks)
}));

export const columnsRelations = relations(columns, ({ one, many }) => ({
	project: one(projects, { fields: [columns.projectId], references: [projects.id] }),
	tasks: many(tasks)
}));

export const tasksRelations = relations(tasks, ({ one, many }) => ({
	project: one(projects, { fields: [tasks.projectId], references: [projects.id] }),
	column: one(columns, { fields: [tasks.columnId], references: [columns.id] }),
	assigneeAgent: one(agents, { fields: [tasks.assigneeAgentId], references: [agents.id], relationName: 'assignedTasks' }),
	dependencies: many(taskDependencies, { relationName: 'taskDeps' }),
	dependents: many(taskDependencies, { relationName: 'dependentDeps' }),
	labels: many(taskLabels),
	comments: many(comments),
	timeEntries: many(timeEntries),
	iterations: many(taskIterations)
}));

export const ideasRelations = relations(ideas, ({ many }) => ({
	versions: many(ideaVersions),
	linksFrom: many(ideaLinks, { relationName: 'sourceLinks' }),
	linksTo: many(ideaLinks, { relationName: 'targetLinks' })
}));

export const missionsRelations = relations(missions, ({ one, many }) => ({
	idea: one(ideas, { fields: [missions.ideaId], references: [ideas.id] }),
	conversations: many(missionConversations)
}));
