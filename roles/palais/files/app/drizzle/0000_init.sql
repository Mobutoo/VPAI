-- Palais Phase 1 — Initial schema
-- Generated from src/lib/server/db/schema.ts

-- ============ ENUMS ============

CREATE TYPE agent_status AS ENUM ('idle', 'busy', 'error', 'offline');
CREATE TYPE session_status AS ENUM ('running', 'completed', 'failed', 'timeout');
CREATE TYPE span_type AS ENUM ('llm_call', 'tool_call', 'decision', 'delegation');
CREATE TYPE priority AS ENUM ('none', 'low', 'medium', 'high', 'urgent');
CREATE TYPE creator_type AS ENUM ('user', 'agent', 'system');
CREATE TYPE dep_type AS ENUM ('finish-to-start', 'start-to-start', 'finish-to-finish');
CREATE TYPE memory_node_type AS ENUM ('episodic', 'semantic', 'procedural');
CREATE TYPE memory_entity_type AS ENUM ('agent', 'service', 'task', 'error', 'deployment', 'decision');
CREATE TYPE memory_edge_rel AS ENUM ('caused_by', 'resolved_by', 'related_to', 'learned_from', 'supersedes');
CREATE TYPE idea_status AS ENUM ('draft', 'brainstorming', 'planned', 'approved', 'dispatched', 'archived');
CREATE TYPE mission_status AS ENUM (
    'briefing', 'brainstorming', 'planning', 'co_editing',
    'approved', 'executing', 'review', 'completed', 'failed'
);
CREATE TYPE insight_type AS ENUM ('agent_stuck', 'budget_warning', 'error_pattern', 'dependency_blocked', 'standup');
CREATE TYPE insight_severity AS ENUM ('info', 'warning', 'critical');
CREATE TYPE entity_type_generic AS ENUM ('task', 'project', 'mission');
CREATE TYPE time_entry_type AS ENUM ('auto', 'manual');
CREATE TYPE node_status AS ENUM ('online', 'offline');
CREATE TYPE backup_status_type AS ENUM ('ok', 'failed', 'running');
CREATE TYPE budget_source AS ENUM ('litellm', 'openai_direct', 'anthropic_direct', 'openrouter_direct');

-- ============ MODULE 1: AGENTS ============

CREATE TABLE agents (
    id          VARCHAR(50) PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    persona     TEXT,
    avatar_url  TEXT,
    model       VARCHAR(100),
    status      agent_status NOT NULL DEFAULT 'offline',
    current_task_id     INTEGER,
    total_tokens_30d    INTEGER DEFAULT 0,
    total_spend_30d     REAL DEFAULT 0,
    avg_quality_score   REAL,
    last_seen_at        TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE agent_sessions (
    id          SERIAL PRIMARY KEY,
    agent_id    VARCHAR(50) NOT NULL REFERENCES agents(id),
    task_id     INTEGER,
    mission_id  INTEGER,
    started_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMP,
    status      session_status NOT NULL DEFAULT 'running',
    total_tokens    INTEGER DEFAULT 0,
    total_cost      REAL DEFAULT 0,
    model           VARCHAR(100),
    summary         TEXT,
    confidence_score REAL
);

CREATE TABLE agent_spans (
    id              SERIAL PRIMARY KEY,
    session_id      INTEGER NOT NULL REFERENCES agent_sessions(id),
    parent_span_id  INTEGER,
    type            span_type NOT NULL,
    name            VARCHAR(200) NOT NULL,
    input           JSONB,
    output          JSONB,
    model           VARCHAR(100),
    tokens_in       INTEGER DEFAULT 0,
    tokens_out      INTEGER DEFAULT 0,
    cost            REAL DEFAULT 0,
    started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMP,
    duration_ms     INTEGER,
    error           JSONB
);

-- ============ MODULE 2: KNOWLEDGE GRAPH ============

CREATE TABLE memory_nodes (
    id              SERIAL PRIMARY KEY,
    type            memory_node_type NOT NULL,
    content         TEXT NOT NULL,
    summary         TEXT,
    entity_type     memory_entity_type,
    entity_id       VARCHAR(100),
    tags            JSONB DEFAULT '[]'::JSONB,
    metadata        JSONB,
    embedding_id    VARCHAR(100),
    valid_from      TIMESTAMP DEFAULT NOW(),
    valid_until     TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by      creator_type NOT NULL DEFAULT 'system'
);

CREATE TABLE memory_edges (
    id              SERIAL PRIMARY KEY,
    source_node_id  INTEGER NOT NULL REFERENCES memory_nodes(id),
    target_node_id  INTEGER NOT NULL REFERENCES memory_nodes(id),
    relation        memory_edge_rel NOT NULL,
    weight          REAL DEFAULT 0.5,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============ MODULE 3: IDEAS ============

CREATE TABLE ideas (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(300) NOT NULL,
    description TEXT,
    status      idea_status NOT NULL DEFAULT 'draft',
    priority    priority DEFAULT 'none',
    tags        JSONB DEFAULT '[]'::JSONB,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE idea_versions (
    id                  SERIAL PRIMARY KEY,
    idea_id             INTEGER NOT NULL REFERENCES ideas(id),
    version_number      INTEGER NOT NULL,
    content_snapshot    JSONB,
    task_breakdown      JSONB,
    brainstorming_log   JSONB,
    memory_context      JSONB,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by          creator_type NOT NULL DEFAULT 'user'
);

CREATE TABLE idea_links (
    id              SERIAL PRIMARY KEY,
    source_idea_id  INTEGER NOT NULL REFERENCES ideas(id),
    target_idea_id  INTEGER NOT NULL REFERENCES ideas(id),
    link_type       VARCHAR(20) NOT NULL
);

-- ============ MODULE 4: MISSIONS ============

CREATE TABLE missions (
    id                      SERIAL PRIMARY KEY,
    title                   VARCHAR(300) NOT NULL,
    idea_id                 INTEGER REFERENCES ideas(id),
    project_id              INTEGER,
    status                  mission_status NOT NULL DEFAULT 'briefing',
    brief_text              TEXT,
    plan_snapshot           JSONB,
    total_estimated_cost    REAL,
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMP,
    actual_cost             REAL
);

CREATE TABLE mission_conversations (
    id          SERIAL PRIMARY KEY,
    mission_id  INTEGER NOT NULL REFERENCES missions(id),
    role        VARCHAR(20) NOT NULL,
    content     TEXT NOT NULL,
    memory_refs JSONB,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============ MODULE 5: PROJECTS & TASKS ============

CREATE TABLE workspaces (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    slug        VARCHAR(100) NOT NULL UNIQUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE projects (
    id              SERIAL PRIMARY KEY,
    workspace_id    INTEGER NOT NULL REFERENCES workspaces(id),
    name            VARCHAR(200) NOT NULL,
    slug            VARCHAR(200) NOT NULL,
    icon            VARCHAR(50),
    description     TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE columns (
    id          SERIAL PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id),
    name        VARCHAR(100) NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    is_final    BOOLEAN DEFAULT FALSE,
    color       VARCHAR(20)
);

CREATE TABLE tasks (
    id                  SERIAL PRIMARY KEY,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    column_id           INTEGER NOT NULL REFERENCES columns(id),
    title               VARCHAR(500) NOT NULL,
    description         TEXT,
    status              VARCHAR(30) DEFAULT 'backlog',
    priority            priority DEFAULT 'none',
    assignee_agent_id   VARCHAR(50) REFERENCES agents(id),
    creator             creator_type NOT NULL DEFAULT 'user',
    start_date          TIMESTAMP,
    end_date            TIMESTAMP,
    due_date            TIMESTAMP,
    position            INTEGER DEFAULT 0,
    estimated_cost      REAL,
    actual_cost         REAL,
    confidence_score    REAL,
    mission_id          INTEGER REFERENCES missions(id),
    session_id          INTEGER,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE task_dependencies (
    id                  SERIAL PRIMARY KEY,
    task_id             INTEGER NOT NULL REFERENCES tasks(id),
    depends_on_task_id  INTEGER NOT NULL REFERENCES tasks(id),
    dependency_type     dep_type NOT NULL DEFAULT 'finish-to-start'
);
CREATE UNIQUE INDEX task_dep_unique ON task_dependencies(task_id, depends_on_task_id);

CREATE TABLE labels (
    id              SERIAL PRIMARY KEY,
    workspace_id    INTEGER NOT NULL REFERENCES workspaces(id),
    name            VARCHAR(50) NOT NULL,
    color           VARCHAR(20) NOT NULL
);

CREATE TABLE task_labels (
    task_id     INTEGER NOT NULL REFERENCES tasks(id),
    label_id    INTEGER NOT NULL REFERENCES labels(id)
);
CREATE UNIQUE INDEX task_label_pk ON task_labels(task_id, label_id);

CREATE TABLE comments (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER NOT NULL REFERENCES tasks(id),
    author_type     creator_type NOT NULL DEFAULT 'user',
    author_agent_id VARCHAR(50),
    content         TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE activity_log (
    id              SERIAL PRIMARY KEY,
    entity_type     VARCHAR(30) NOT NULL,
    entity_id       INTEGER NOT NULL,
    actor_type      creator_type NOT NULL DEFAULT 'system',
    actor_agent_id  VARCHAR(50),
    action          VARCHAR(100) NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX activity_entity_idx ON activity_log(entity_type, entity_id);

-- ============ MODULE 6: TIME TRACKING ============

CREATE TABLE time_entries (
    id                  SERIAL PRIMARY KEY,
    task_id             INTEGER NOT NULL REFERENCES tasks(id),
    agent_id            VARCHAR(50),
    started_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMP,
    duration_seconds    INTEGER,
    type                time_entry_type NOT NULL DEFAULT 'auto',
    notes               TEXT
);

CREATE TABLE task_iterations (
    id                  SERIAL PRIMARY KEY,
    task_id             INTEGER NOT NULL REFERENCES tasks(id),
    iteration_number    INTEGER NOT NULL,
    reopened_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    reason              TEXT,
    resolved_at         TIMESTAMP
);

-- ============ MODULE 7: DELIVERABLES ============

CREATE TABLE deliverables (
    id                      SERIAL PRIMARY KEY,
    entity_type             entity_type_generic NOT NULL,
    entity_id               INTEGER NOT NULL,
    filename                VARCHAR(500) NOT NULL,
    mime_type               VARCHAR(100),
    size_bytes              INTEGER,
    storage_path            TEXT NOT NULL,
    download_token          VARCHAR(36) NOT NULL UNIQUE,
    uploaded_by_type        creator_type NOT NULL DEFAULT 'user',
    uploaded_by_agent_id    VARCHAR(50),
    created_at              TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX deliverable_token_idx ON deliverables(download_token);

-- ============ MODULE 8: BUDGET ============

CREATE TABLE budget_snapshots (
    id              SERIAL PRIMARY KEY,
    date            TIMESTAMP NOT NULL,
    source          budget_source NOT NULL,
    provider        VARCHAR(50),
    agent_id        VARCHAR(50),
    spend_amount    REAL DEFAULT 0,
    token_count     INTEGER DEFAULT 0,
    request_count   INTEGER DEFAULT 0,
    captured_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE budget_forecasts (
    id                          SERIAL PRIMARY KEY,
    date                        TIMESTAMP NOT NULL,
    predicted_spend             REAL,
    predicted_exhaustion_time   TIMESTAMP,
    remaining_budget            REAL,
    computed_at                 TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============ MODULE 9: INSIGHTS ============

CREATE TABLE insights (
    id                  SERIAL PRIMARY KEY,
    type                insight_type NOT NULL,
    severity            insight_severity NOT NULL DEFAULT 'info',
    title               VARCHAR(300) NOT NULL,
    description         TEXT,
    suggested_actions   JSONB,
    entity_type         VARCHAR(30),
    entity_id           INTEGER,
    memory_refs         JSONB,
    acknowledged        BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============ MODULE 11: NODES / HEALTH ============

CREATE TABLE nodes (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(50) NOT NULL UNIQUE,
    tailscale_ip    VARCHAR(50),
    status          node_status DEFAULT 'offline',
    last_seen_at    TIMESTAMP,
    cpu_percent     REAL,
    ram_percent     REAL,
    disk_percent    REAL,
    temperature     REAL
);

CREATE TABLE health_checks (
    id              SERIAL PRIMARY KEY,
    node_id         INTEGER NOT NULL REFERENCES nodes(id),
    service_name    VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    response_time_ms INTEGER,
    checked_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    details         JSONB
);

CREATE TABLE backup_status (
    id              SERIAL PRIMARY KEY,
    node_id         INTEGER NOT NULL REFERENCES nodes(id),
    last_backup_at  TIMESTAMP,
    next_backup_at  TIMESTAMP,
    size_bytes      INTEGER,
    status          backup_status_type DEFAULT 'ok',
    details         JSONB
);
