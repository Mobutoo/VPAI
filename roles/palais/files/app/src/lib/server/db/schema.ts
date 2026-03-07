import {
	pgTable, serial, text, varchar, integer, timestamp,
	real, jsonb, pgEnum, boolean, index
} from 'drizzle-orm/pg-core';
import { relations } from 'drizzle-orm';

// ============ ENUMS ============

export const agentStatusEnum = pgEnum('agent_status', ['idle', 'busy', 'error', 'offline']);
export const sessionStatusEnum = pgEnum('session_status', ['running', 'completed', 'failed', 'timeout']);
export const spanTypeEnum = pgEnum('span_type', ['llm_call', 'tool_call', 'decision', 'delegation']);
export const priorityEnum = pgEnum('priority', ['none', 'low', 'medium', 'high', 'urgent']);
export const creatorTypeEnum = pgEnum('creator_type', ['user', 'agent', 'system']);
export const memoryNodeTypeEnum = pgEnum('memory_node_type', ['episodic', 'semantic', 'procedural']);
export const memoryEntityTypeEnum = pgEnum('memory_entity_type', [
	'agent', 'service', 'task', 'error', 'deployment', 'decision'
]);
export const memoryEdgeRelEnum = pgEnum('memory_edge_rel', [
	'caused_by', 'resolved_by', 'related_to', 'learned_from', 'supersedes'
]);
export const nodeStatusEnum = pgEnum('node_status', ['online', 'offline', 'busy', 'degraded']);
export const backupStatusEnum = pgEnum('backup_status_type', ['ok', 'failed', 'running']);

// v2 enums
export const deployStatusEnum = pgEnum('deploy_status', [
	'pending', 'running', 'success', 'failed', 'cancelled', 'rolled_back'
]);
export const providerTypeEnum = pgEnum('provider_type', ['hetzner', 'ovh', 'ionos', 'local']);
export const registrarTypeEnum = pgEnum('registrar_type', ['namecheap', 'ovh', 'other']);
export const serverRoleEnum = pgEnum('server_role', [
	'ai_brain', 'vpn_hub', 'workstation', 'app_prod', 'storage'
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
	totalTokens30d: integer('total_tokens_30d').default(0),
	totalSpend30d: real('total_spend_30d').default(0),
	avgQualityScore: real('avg_quality_score'),
	lastSeenAt: timestamp('last_seen_at'),
	createdAt: timestamp('created_at').defaultNow().notNull()
});

export const agentSessions = pgTable('agent_sessions', {
	id: serial('id').primaryKey(),
	agentId: varchar('agent_id', { length: 50 }).notNull().references(() => agents.id),
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

// ============ MODULE: FLEET (servers) ============

export const servers = pgTable('servers', {
	id: serial('id').primaryKey(),
	name: varchar('name', { length: 100 }).notNull().unique(),
	slug: varchar('slug', { length: 100 }).notNull().unique(),
	provider: providerTypeEnum('provider').notNull(),
	serverRole: serverRoleEnum('server_role').notNull().default('app_prod'),
	location: varchar('location', { length: 50 }),
	publicIp: varchar('public_ip', { length: 50 }),
	tailscaleIp: varchar('tailscale_ip', { length: 50 }),
	status: nodeStatusEnum('status').notNull().default('offline'),
	cpuCores: integer('cpu_cores'),
	ramMb: integer('ram_mb'),
	diskGb: integer('disk_gb'),
	os: varchar('os', { length: 100 }),
	sshPort: integer('ssh_port').default(22),
	sshUser: varchar('ssh_user', { length: 50 }),
	sshKeyPath: text('ssh_key_path'),
	metadata: jsonb('metadata').$type<Record<string, unknown>>().default({}),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	updatedAt: timestamp('updated_at').defaultNow().notNull()
});

export const serverMetrics = pgTable('server_metrics', {
	id: serial('id').primaryKey(),
	serverId: integer('server_id').notNull().references(() => servers.id),
	cpuPercent: real('cpu_percent'),
	ramUsedMb: integer('ram_used_mb'),
	ramTotalMb: integer('ram_total_mb'),
	diskUsedGb: real('disk_used_gb'),
	diskTotalGb: real('disk_total_gb'),
	containerCount: integer('container_count').default(0),
	loadAvg1m: real('load_avg_1m'),
	recordedAt: timestamp('recorded_at').defaultNow().notNull()
}, (t) => [
	index('server_metrics_server_idx').on(t.serverId, t.recordedAt)
]);

// ============ MODULE: WORKSPACES (project registry) ============

export const projectRegistry = pgTable('project_registry', {
	id: serial('id').primaryKey(),
	name: varchar('name', { length: 200 }).notNull(),
	slug: varchar('slug', { length: 200 }).notNull().unique(),
	description: text('description'),
	repoUrl: text('repo_url'),
	repoType: varchar('repo_type', { length: 20 }).default('github'),
	stack: varchar('stack', { length: 100 }),
	playbookPath: text('playbook_path'),
	primaryServerId: integer('primary_server_id').references(() => servers.id),
	domainPattern: varchar('domain_pattern', { length: 200 }),
	envTemplate: jsonb('env_template').$type<Record<string, unknown>>().default({}),
	healthcheckUrl: text('healthcheck_url'),
	onDemand: boolean('on_demand').default(false),
	composeFile: varchar('compose_file', { length: 200 }).default('docker-compose.yml'),
	minRamMb: integer('min_ram_mb'),
	minCpuCores: integer('min_cpu_cores'),
	minDiskGb: integer('min_disk_gb'),
	currentVersion: varchar('current_version', { length: 100 }),
	latestVersion: varchar('latest_version', { length: 100 }),
	lastDeployedAt: timestamp('last_deployed_at'),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	updatedAt: timestamp('updated_at').defaultNow().notNull()
});

// ============ MODULE: DEPLOY ============

export const deployments = pgTable('deployments', {
	id: serial('id').primaryKey(),
	workspaceId: integer('workspace_id').notNull().references(() => projectRegistry.id),
	serverId: integer('server_id').references(() => servers.id),
	version: varchar('version', { length: 100 }),
	status: deployStatusEnum('status').notNull().default('pending'),
	startedAt: timestamp('started_at').defaultNow().notNull(),
	completedAt: timestamp('completed_at'),
	triggeredBy: varchar('triggered_by', { length: 50 }).notNull().default('user'),
	deployType: varchar('deploy_type', { length: 30 }).notNull().default('update'),
	rollbackOf: integer('rollback_of'),
	n8nExecutionId: varchar('n8n_execution_id', { length: 100 }),
	errorSummary: text('error_summary')
}, (t) => [
	index('deploy_workspace_idx').on(t.workspaceId, t.startedAt)
]);

export const deploymentSteps = pgTable('deployment_steps', {
	id: serial('id').primaryKey(),
	deploymentId: integer('deployment_id').notNull().references(() => deployments.id),
	stepName: varchar('step_name', { length: 200 }).notNull(),
	status: deployStatusEnum('status').notNull().default('pending'),
	startedAt: timestamp('started_at'),
	completedAt: timestamp('completed_at'),
	output: text('output'),
	error: text('error'),
	position: integer('position').notNull().default(0)
});

// ============ MODULE: COSTS ============

export const costEntries = pgTable('cost_entries', {
	id: serial('id').primaryKey(),
	provider: varchar('provider', { length: 50 }).notNull(),
	category: varchar('category', { length: 50 }).notNull(),
	amountEur: real('amount_eur').notNull().default(0),
	periodStart: timestamp('period_start').notNull(),
	periodEnd: timestamp('period_end').notNull(),
	workspaceId: integer('workspace_id').references(() => projectRegistry.id),
	description: text('description'),
	rawData: jsonb('raw_data').$type<Record<string, unknown>>().default({}),
	recordedAt: timestamp('recorded_at').defaultNow().notNull()
}, (t) => [
	index('cost_entries_period_idx').on(t.periodStart, t.provider)
]);

// ============ MODULE: DOMAINS ============

export const domains = pgTable('domains', {
	id: serial('id').primaryKey(),
	name: varchar('name', { length: 253 }).notNull().unique(),
	registrar: registrarTypeEnum('registrar').notNull().default('namecheap'),
	apiProvider: varchar('api_provider', { length: 50 }),
	expiryDate: timestamp('expiry_date'),
	autoRenew: boolean('auto_renew').default(true),
	sslStatus: varchar('ssl_status', { length: 30 }),
	sslExpiry: timestamp('ssl_expiry'),
	nameservers: jsonb('nameservers').$type<string[]>().default([]),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	updatedAt: timestamp('updated_at').defaultNow().notNull()
});

export const dnsRecords = pgTable('dns_records', {
	id: serial('id').primaryKey(),
	domainId: integer('domain_id').notNull().references(() => domains.id),
	recordType: varchar('record_type', { length: 10 }).notNull(),
	host: varchar('host', { length: 253 }).notNull(),
	value: text('value').notNull(),
	ttl: integer('ttl').default(1800),
	mxPref: integer('mx_pref'),
	createdAt: timestamp('created_at').defaultNow().notNull(),
	updatedAt: timestamp('updated_at').defaultNow().notNull()
});

// ============ MODULE: WAZA ============

export const wazaServices = pgTable('waza_services', {
	id: serial('id').primaryKey(),
	name: varchar('name', { length: 100 }).notNull(),
	slug: varchar('slug', { length: 100 }).notNull().unique(),
	composeFile: varchar('compose_file', { length: 200 }),
	alwaysOn: boolean('always_on').default(false),
	ramLimitMb: integer('ram_limit_mb'),
	cpuLimit: real('cpu_limit'),
	status: varchar('status', { length: 20 }).default('stopped'),
	profile: varchar('profile', { length: 50 }),
	startCmd: text('start_cmd'),
	stopCmd: text('stop_cmd'),
	statusCmd: text('status_cmd'),
	startedAt: timestamp('started_at'),
	lastStoppedAt: timestamp('last_stopped_at')
});

// ============ RELATIONS ============

export const agentsRelations = relations(agents, ({ many }) => ({
	sessions: many(agentSessions)
}));

export const agentSessionsRelations = relations(agentSessions, ({ one, many }) => ({
	agent: one(agents, { fields: [agentSessions.agentId], references: [agents.id] }),
	spans: many(agentSpans)
}));

export const agentSpansRelations = relations(agentSpans, ({ one }) => ({
	session: one(agentSessions, { fields: [agentSpans.sessionId], references: [agentSessions.id] })
}));

export const nodesRelations = relations(nodes, ({ many }) => ({
	healthChecks: many(healthChecks),
	backupStatuses: many(backupStatus)
}));

export const healthChecksRelations = relations(healthChecks, ({ one }) => ({
	node: one(nodes, { fields: [healthChecks.nodeId], references: [nodes.id] })
}));

export const backupStatusRelations = relations(backupStatus, ({ one }) => ({
	node: one(nodes, { fields: [backupStatus.nodeId], references: [nodes.id] })
}));

export const memoryNodesRelations = relations(memoryNodes, ({ many }) => ({
	outgoingEdges: many(memoryEdges, { relationName: 'sourceNode' }),
	incomingEdges: many(memoryEdges, { relationName: 'targetNode' })
}));

export const memoryEdgesRelations = relations(memoryEdges, ({ one }) => ({
	sourceNode: one(memoryNodes, {
		fields: [memoryEdges.sourceNodeId],
		references: [memoryNodes.id],
		relationName: 'sourceNode'
	}),
	targetNode: one(memoryNodes, {
		fields: [memoryEdges.targetNodeId],
		references: [memoryNodes.id],
		relationName: 'targetNode'
	})
}));

// v2 relations

export const serversRelations = relations(servers, ({ many }) => ({
	metrics: many(serverMetrics),
	deployments: many(deployments),
	projects: many(projectRegistry)
}));

export const serverMetricsRelations = relations(serverMetrics, ({ one }) => ({
	server: one(servers, { fields: [serverMetrics.serverId], references: [servers.id] })
}));

export const projectRegistryRelations = relations(projectRegistry, ({ one, many }) => ({
	primaryServer: one(servers, {
		fields: [projectRegistry.primaryServerId],
		references: [servers.id]
	}),
	deployments: many(deployments),
	costEntries: many(costEntries)
}));

export const deploymentsRelations = relations(deployments, ({ one, many }) => ({
	workspace: one(projectRegistry, {
		fields: [deployments.workspaceId],
		references: [projectRegistry.id]
	}),
	server: one(servers, { fields: [deployments.serverId], references: [servers.id] }),
	rollbackSource: one(deployments, {
		fields: [deployments.rollbackOf],
		references: [deployments.id],
		relationName: 'rollback'
	}),
	steps: many(deploymentSteps)
}));

export const deploymentStepsRelations = relations(deploymentSteps, ({ one }) => ({
	deployment: one(deployments, {
		fields: [deploymentSteps.deploymentId],
		references: [deployments.id]
	})
}));

export const costEntriesRelations = relations(costEntries, ({ one }) => ({
	workspace: one(projectRegistry, {
		fields: [costEntries.workspaceId],
		references: [projectRegistry.id]
	})
}));

export const domainsRelations = relations(domains, ({ many }) => ({
	dnsRecords: many(dnsRecords)
}));

export const dnsRecordsRelations = relations(dnsRecords, ({ one }) => ({
	domain: one(domains, { fields: [dnsRecords.domainId], references: [domains.id] })
}));
