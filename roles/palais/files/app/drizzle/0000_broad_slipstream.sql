CREATE TYPE "public"."agent_status" AS ENUM('idle', 'busy', 'error', 'offline');--> statement-breakpoint
CREATE TYPE "public"."backup_status_type" AS ENUM('ok', 'failed', 'running');--> statement-breakpoint
CREATE TYPE "public"."budget_source" AS ENUM('litellm', 'openai_direct', 'anthropic_direct', 'openrouter_direct');--> statement-breakpoint
CREATE TYPE "public"."creator_type" AS ENUM('user', 'agent', 'system');--> statement-breakpoint
CREATE TYPE "public"."dep_type" AS ENUM('finish-to-start', 'start-to-start', 'finish-to-finish');--> statement-breakpoint
CREATE TYPE "public"."entity_type_generic" AS ENUM('task', 'project', 'mission');--> statement-breakpoint
CREATE TYPE "public"."idea_status" AS ENUM('draft', 'brainstorming', 'planned', 'approved', 'dispatched', 'archived');--> statement-breakpoint
CREATE TYPE "public"."insight_severity" AS ENUM('info', 'warning', 'critical');--> statement-breakpoint
CREATE TYPE "public"."insight_type" AS ENUM('agent_stuck', 'budget_warning', 'error_pattern', 'dependency_blocked', 'standup');--> statement-breakpoint
CREATE TYPE "public"."memory_edge_rel" AS ENUM('caused_by', 'resolved_by', 'related_to', 'learned_from', 'supersedes');--> statement-breakpoint
CREATE TYPE "public"."memory_entity_type" AS ENUM('agent', 'service', 'task', 'error', 'deployment', 'decision');--> statement-breakpoint
CREATE TYPE "public"."memory_node_type" AS ENUM('episodic', 'semantic', 'procedural');--> statement-breakpoint
CREATE TYPE "public"."mission_status" AS ENUM('briefing', 'brainstorming', 'planning', 'co_editing', 'approved', 'executing', 'review', 'completed', 'failed');--> statement-breakpoint
CREATE TYPE "public"."node_status" AS ENUM('online', 'offline');--> statement-breakpoint
CREATE TYPE "public"."priority" AS ENUM('none', 'low', 'medium', 'high', 'urgent');--> statement-breakpoint
CREATE TYPE "public"."session_status" AS ENUM('running', 'completed', 'failed', 'timeout');--> statement-breakpoint
CREATE TYPE "public"."span_type" AS ENUM('llm_call', 'tool_call', 'decision', 'delegation');--> statement-breakpoint
CREATE TYPE "public"."time_entry_type" AS ENUM('auto', 'manual');--> statement-breakpoint
CREATE TABLE "activity_log" (
	"id" serial PRIMARY KEY NOT NULL,
	"entity_type" varchar(30) NOT NULL,
	"entity_id" integer NOT NULL,
	"actor_type" "creator_type" DEFAULT 'system' NOT NULL,
	"actor_agent_id" varchar(50),
	"action" varchar(100) NOT NULL,
	"old_value" text,
	"new_value" text,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "agent_sessions" (
	"id" serial PRIMARY KEY NOT NULL,
	"agent_id" varchar(50) NOT NULL,
	"task_id" integer,
	"mission_id" integer,
	"started_at" timestamp DEFAULT now() NOT NULL,
	"ended_at" timestamp,
	"status" "session_status" DEFAULT 'running' NOT NULL,
	"total_tokens" integer DEFAULT 0,
	"total_cost" real DEFAULT 0,
	"model" varchar(100),
	"summary" text,
	"confidence_score" real
);
--> statement-breakpoint
CREATE TABLE "agent_spans" (
	"id" serial PRIMARY KEY NOT NULL,
	"session_id" integer NOT NULL,
	"parent_span_id" integer,
	"type" "span_type" NOT NULL,
	"name" varchar(200) NOT NULL,
	"input" jsonb,
	"output" jsonb,
	"model" varchar(100),
	"tokens_in" integer DEFAULT 0,
	"tokens_out" integer DEFAULT 0,
	"cost" real DEFAULT 0,
	"started_at" timestamp DEFAULT now() NOT NULL,
	"ended_at" timestamp,
	"duration_ms" integer,
	"error" jsonb
);
--> statement-breakpoint
CREATE TABLE "agents" (
	"id" varchar(50) PRIMARY KEY NOT NULL,
	"name" varchar(100) NOT NULL,
	"persona" text,
	"avatar_url" text,
	"model" varchar(100),
	"status" "agent_status" DEFAULT 'offline' NOT NULL,
	"current_task_id" integer,
	"total_tokens_30d" integer DEFAULT 0,
	"total_spend_30d" real DEFAULT 0,
	"avg_quality_score" real,
	"last_seen_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "backup_status" (
	"id" serial PRIMARY KEY NOT NULL,
	"node_id" integer NOT NULL,
	"last_backup_at" timestamp,
	"next_backup_at" timestamp,
	"size_bytes" integer,
	"status" "backup_status_type" DEFAULT 'ok',
	"details" jsonb
);
--> statement-breakpoint
CREATE TABLE "budget_forecasts" (
	"id" serial PRIMARY KEY NOT NULL,
	"date" timestamp NOT NULL,
	"predicted_spend" real,
	"predicted_exhaustion_time" timestamp,
	"remaining_budget" real,
	"computed_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "budget_snapshots" (
	"id" serial PRIMARY KEY NOT NULL,
	"date" timestamp NOT NULL,
	"source" "budget_source" NOT NULL,
	"provider" varchar(50),
	"agent_id" varchar(50),
	"spend_amount" real DEFAULT 0,
	"token_count" integer DEFAULT 0,
	"request_count" integer DEFAULT 0,
	"captured_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "columns" (
	"id" serial PRIMARY KEY NOT NULL,
	"project_id" integer NOT NULL,
	"name" varchar(100) NOT NULL,
	"position" integer DEFAULT 0 NOT NULL,
	"is_final" boolean DEFAULT false,
	"color" varchar(20)
);
--> statement-breakpoint
CREATE TABLE "comments" (
	"id" serial PRIMARY KEY NOT NULL,
	"task_id" integer NOT NULL,
	"author_type" "creator_type" DEFAULT 'user' NOT NULL,
	"author_agent_id" varchar(50),
	"content" text NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "deliverables" (
	"id" serial PRIMARY KEY NOT NULL,
	"entity_type" "entity_type_generic" NOT NULL,
	"entity_id" integer NOT NULL,
	"filename" varchar(500) NOT NULL,
	"mime_type" varchar(100),
	"size_bytes" integer,
	"storage_path" text NOT NULL,
	"download_token" varchar(36) NOT NULL,
	"uploaded_by_type" "creator_type" DEFAULT 'user' NOT NULL,
	"uploaded_by_agent_id" varchar(50),
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "deliverables_download_token_unique" UNIQUE("download_token")
);
--> statement-breakpoint
CREATE TABLE "health_checks" (
	"id" serial PRIMARY KEY NOT NULL,
	"node_id" integer NOT NULL,
	"service_name" varchar(100) NOT NULL,
	"status" varchar(20) NOT NULL,
	"response_time_ms" integer,
	"checked_at" timestamp DEFAULT now() NOT NULL,
	"details" jsonb
);
--> statement-breakpoint
CREATE TABLE "idea_links" (
	"id" serial PRIMARY KEY NOT NULL,
	"source_idea_id" integer NOT NULL,
	"target_idea_id" integer NOT NULL,
	"link_type" varchar(20) NOT NULL
);
--> statement-breakpoint
CREATE TABLE "idea_versions" (
	"id" serial PRIMARY KEY NOT NULL,
	"idea_id" integer NOT NULL,
	"version_number" integer NOT NULL,
	"content_snapshot" jsonb,
	"task_breakdown" jsonb,
	"brainstorming_log" jsonb,
	"memory_context" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"created_by" "creator_type" DEFAULT 'user' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "ideas" (
	"id" serial PRIMARY KEY NOT NULL,
	"title" varchar(300) NOT NULL,
	"description" text,
	"status" "idea_status" DEFAULT 'draft' NOT NULL,
	"priority" "priority" DEFAULT 'none',
	"tags" jsonb DEFAULT '[]'::jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "insights" (
	"id" serial PRIMARY KEY NOT NULL,
	"type" "insight_type" NOT NULL,
	"severity" "insight_severity" DEFAULT 'info' NOT NULL,
	"title" varchar(300) NOT NULL,
	"description" text,
	"suggested_actions" jsonb,
	"entity_type" varchar(30),
	"entity_id" integer,
	"memory_refs" jsonb,
	"acknowledged" boolean DEFAULT false,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "labels" (
	"id" serial PRIMARY KEY NOT NULL,
	"workspace_id" integer NOT NULL,
	"name" varchar(50) NOT NULL,
	"color" varchar(20) NOT NULL
);
--> statement-breakpoint
CREATE TABLE "memory_edges" (
	"id" serial PRIMARY KEY NOT NULL,
	"source_node_id" integer NOT NULL,
	"target_node_id" integer NOT NULL,
	"relation" "memory_edge_rel" NOT NULL,
	"weight" real DEFAULT 0.5,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "memory_nodes" (
	"id" serial PRIMARY KEY NOT NULL,
	"type" "memory_node_type" NOT NULL,
	"content" text NOT NULL,
	"summary" text,
	"entity_type" "memory_entity_type",
	"entity_id" varchar(100),
	"tags" jsonb DEFAULT '[]'::jsonb,
	"metadata" jsonb,
	"embedding_id" varchar(100),
	"valid_from" timestamp DEFAULT now(),
	"valid_until" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"created_by" "creator_type" DEFAULT 'system' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "mission_conversations" (
	"id" serial PRIMARY KEY NOT NULL,
	"mission_id" integer NOT NULL,
	"role" varchar(20) NOT NULL,
	"content" text NOT NULL,
	"memory_refs" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "missions" (
	"id" serial PRIMARY KEY NOT NULL,
	"title" varchar(300) NOT NULL,
	"idea_id" integer,
	"project_id" integer,
	"status" "mission_status" DEFAULT 'briefing' NOT NULL,
	"brief_text" text,
	"plan_snapshot" jsonb,
	"total_estimated_cost" real,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"completed_at" timestamp,
	"actual_cost" real
);
--> statement-breakpoint
CREATE TABLE "nodes" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" varchar(50) NOT NULL,
	"tailscale_ip" varchar(50),
	"status" "node_status" DEFAULT 'offline',
	"last_seen_at" timestamp,
	"cpu_percent" real,
	"ram_percent" real,
	"disk_percent" real,
	"temperature" real,
	CONSTRAINT "nodes_name_unique" UNIQUE("name")
);
--> statement-breakpoint
CREATE TABLE "projects" (
	"id" serial PRIMARY KEY NOT NULL,
	"workspace_id" integer NOT NULL,
	"name" varchar(200) NOT NULL,
	"slug" varchar(200) NOT NULL,
	"icon" varchar(50),
	"description" text,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "task_dependencies" (
	"id" serial PRIMARY KEY NOT NULL,
	"task_id" integer NOT NULL,
	"depends_on_task_id" integer NOT NULL,
	"dependency_type" "dep_type" DEFAULT 'finish-to-start' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "task_iterations" (
	"id" serial PRIMARY KEY NOT NULL,
	"task_id" integer NOT NULL,
	"iteration_number" integer NOT NULL,
	"reopened_at" timestamp DEFAULT now() NOT NULL,
	"reason" text,
	"resolved_at" timestamp
);
--> statement-breakpoint
CREATE TABLE "task_labels" (
	"task_id" integer NOT NULL,
	"label_id" integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE "tasks" (
	"id" serial PRIMARY KEY NOT NULL,
	"project_id" integer NOT NULL,
	"column_id" integer NOT NULL,
	"title" varchar(500) NOT NULL,
	"description" text,
	"status" varchar(30) DEFAULT 'backlog',
	"priority" "priority" DEFAULT 'none',
	"assignee_agent_id" varchar(50),
	"creator" "creator_type" DEFAULT 'user' NOT NULL,
	"start_date" timestamp,
	"end_date" timestamp,
	"due_date" timestamp,
	"position" integer DEFAULT 0,
	"estimated_cost" real,
	"actual_cost" real,
	"confidence_score" real,
	"mission_id" integer,
	"session_id" integer,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "time_entries" (
	"id" serial PRIMARY KEY NOT NULL,
	"task_id" integer NOT NULL,
	"agent_id" varchar(50),
	"started_at" timestamp DEFAULT now() NOT NULL,
	"ended_at" timestamp,
	"duration_seconds" integer,
	"type" time_entry_type DEFAULT 'auto' NOT NULL,
	"notes" text
);
--> statement-breakpoint
CREATE TABLE "workspaces" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" varchar(100) NOT NULL,
	"slug" varchar(100) NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "workspaces_slug_unique" UNIQUE("slug")
);
--> statement-breakpoint
ALTER TABLE "agent_sessions" ADD CONSTRAINT "agent_sessions_agent_id_agents_id_fk" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent_spans" ADD CONSTRAINT "agent_spans_session_id_agent_sessions_id_fk" FOREIGN KEY ("session_id") REFERENCES "public"."agent_sessions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "backup_status" ADD CONSTRAINT "backup_status_node_id_nodes_id_fk" FOREIGN KEY ("node_id") REFERENCES "public"."nodes"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "columns" ADD CONSTRAINT "columns_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "comments" ADD CONSTRAINT "comments_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "health_checks" ADD CONSTRAINT "health_checks_node_id_nodes_id_fk" FOREIGN KEY ("node_id") REFERENCES "public"."nodes"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "idea_links" ADD CONSTRAINT "idea_links_source_idea_id_ideas_id_fk" FOREIGN KEY ("source_idea_id") REFERENCES "public"."ideas"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "idea_links" ADD CONSTRAINT "idea_links_target_idea_id_ideas_id_fk" FOREIGN KEY ("target_idea_id") REFERENCES "public"."ideas"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "idea_versions" ADD CONSTRAINT "idea_versions_idea_id_ideas_id_fk" FOREIGN KEY ("idea_id") REFERENCES "public"."ideas"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "labels" ADD CONSTRAINT "labels_workspace_id_workspaces_id_fk" FOREIGN KEY ("workspace_id") REFERENCES "public"."workspaces"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "memory_edges" ADD CONSTRAINT "memory_edges_source_node_id_memory_nodes_id_fk" FOREIGN KEY ("source_node_id") REFERENCES "public"."memory_nodes"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "memory_edges" ADD CONSTRAINT "memory_edges_target_node_id_memory_nodes_id_fk" FOREIGN KEY ("target_node_id") REFERENCES "public"."memory_nodes"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "mission_conversations" ADD CONSTRAINT "mission_conversations_mission_id_missions_id_fk" FOREIGN KEY ("mission_id") REFERENCES "public"."missions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "missions" ADD CONSTRAINT "missions_idea_id_ideas_id_fk" FOREIGN KEY ("idea_id") REFERENCES "public"."ideas"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "projects" ADD CONSTRAINT "projects_workspace_id_workspaces_id_fk" FOREIGN KEY ("workspace_id") REFERENCES "public"."workspaces"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_dependencies" ADD CONSTRAINT "task_dependencies_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_dependencies" ADD CONSTRAINT "task_dependencies_depends_on_task_id_tasks_id_fk" FOREIGN KEY ("depends_on_task_id") REFERENCES "public"."tasks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_iterations" ADD CONSTRAINT "task_iterations_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_labels" ADD CONSTRAINT "task_labels_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_labels" ADD CONSTRAINT "task_labels_label_id_labels_id_fk" FOREIGN KEY ("label_id") REFERENCES "public"."labels"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_column_id_columns_id_fk" FOREIGN KEY ("column_id") REFERENCES "public"."columns"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_assignee_agent_id_agents_id_fk" FOREIGN KEY ("assignee_agent_id") REFERENCES "public"."agents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_mission_id_missions_id_fk" FOREIGN KEY ("mission_id") REFERENCES "public"."missions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "time_entries" ADD CONSTRAINT "time_entries_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "activity_entity_idx" ON "activity_log" USING btree ("entity_type","entity_id");--> statement-breakpoint
CREATE INDEX "deliverable_token_idx" ON "deliverables" USING btree ("download_token");--> statement-breakpoint
CREATE UNIQUE INDEX "task_dep_unique" ON "task_dependencies" USING btree ("task_id","depends_on_task_id");--> statement-breakpoint
CREATE UNIQUE INDEX "task_label_pk" ON "task_labels" USING btree ("task_id","label_id");