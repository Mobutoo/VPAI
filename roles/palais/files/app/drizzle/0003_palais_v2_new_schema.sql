-- Palais v2 new schema — Fleet, Workspaces, Services, Deploy, Costs, Domains, Waza

-- ============ NEW ENUMS ============
DO $$ BEGIN
    CREATE TYPE deploy_status AS ENUM ('pending', 'running', 'success', 'failed', 'cancelled', 'rolled_back');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE provider_type AS ENUM ('hetzner', 'ovh', 'ionos', 'local');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE registrar_type AS ENUM ('namecheap', 'ovh', 'other');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE server_role AS ENUM ('ai_brain', 'vpn_hub', 'workstation', 'app_prod', 'storage');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============ MODULE: FLEET (servers) ============

CREATE TABLE IF NOT EXISTS servers (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    slug            VARCHAR(100) NOT NULL UNIQUE,
    provider        provider_type NOT NULL,
    server_role     server_role NOT NULL DEFAULT 'app_prod',
    location        VARCHAR(50),
    public_ip       VARCHAR(50),
    tailscale_ip    VARCHAR(50),
    status          node_status NOT NULL DEFAULT 'offline',
    cpu_cores       INTEGER,
    ram_mb          INTEGER,
    disk_gb         INTEGER,
    os              VARCHAR(100),
    ssh_port        INTEGER DEFAULT 22,
    ssh_user        VARCHAR(50),
    ssh_key_path    TEXT,
    metadata        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS server_metrics (
    id              SERIAL PRIMARY KEY,
    server_id       INTEGER NOT NULL REFERENCES servers(id),
    cpu_percent     REAL,
    ram_used_mb     INTEGER,
    ram_total_mb    INTEGER,
    disk_used_gb    REAL,
    disk_total_gb   REAL,
    container_count INTEGER DEFAULT 0,
    load_avg_1m     REAL,
    recorded_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS server_metrics_server_idx ON server_metrics(server_id, recorded_at DESC);

-- ============ MODULE: WORKSPACES (project registry) ============

CREATE TABLE IF NOT EXISTS project_registry (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    slug            VARCHAR(200) NOT NULL UNIQUE,
    description     TEXT,
    repo_url        TEXT,
    repo_type       VARCHAR(20) DEFAULT 'github',
    stack           VARCHAR(100),
    playbook_path   TEXT,
    primary_server_id INTEGER REFERENCES servers(id),
    domain_pattern  VARCHAR(200),
    env_template    JSONB DEFAULT '{}'::JSONB,
    healthcheck_url TEXT,
    on_demand       BOOLEAN DEFAULT false,
    compose_file    VARCHAR(200) DEFAULT 'docker-compose.yml',
    min_ram_mb      INTEGER,
    min_cpu_cores   INTEGER,
    min_disk_gb     INTEGER,
    current_version VARCHAR(100),
    latest_version  VARCHAR(100),
    last_deployed_at TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============ MODULE: DEPLOY ============

CREATE TABLE IF NOT EXISTS deployments (
    id              SERIAL PRIMARY KEY,
    workspace_id    INTEGER NOT NULL REFERENCES project_registry(id),
    server_id       INTEGER REFERENCES servers(id),
    version         VARCHAR(100),
    status          deploy_status NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP,
    triggered_by    VARCHAR(50) NOT NULL DEFAULT 'user',
    deploy_type     VARCHAR(30) NOT NULL DEFAULT 'update',
    rollback_of     INTEGER REFERENCES deployments(id),
    n8n_execution_id VARCHAR(100),
    error_summary   TEXT
);

CREATE TABLE IF NOT EXISTS deployment_steps (
    id              SERIAL PRIMARY KEY,
    deployment_id   INTEGER NOT NULL REFERENCES deployments(id),
    step_name       VARCHAR(200) NOT NULL,
    status          deploy_status NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    output          TEXT,
    error           TEXT,
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS deploy_workspace_idx ON deployments(workspace_id, started_at DESC);

-- ============ MODULE: COSTS ============

CREATE TABLE IF NOT EXISTS cost_entries (
    id              SERIAL PRIMARY KEY,
    provider        VARCHAR(50) NOT NULL,
    category        VARCHAR(50) NOT NULL,
    amount_eur      REAL NOT NULL DEFAULT 0,
    period_start    TIMESTAMP NOT NULL,
    period_end      TIMESTAMP NOT NULL,
    workspace_id    INTEGER REFERENCES project_registry(id),
    description     TEXT,
    raw_data        JSONB DEFAULT '{}'::JSONB,
    recorded_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS cost_entries_period_idx ON cost_entries(period_start DESC, provider);

-- ============ MODULE: DOMAINS ============

CREATE TABLE IF NOT EXISTS domains (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(253) NOT NULL UNIQUE,
    registrar       registrar_type NOT NULL DEFAULT 'namecheap',
    api_provider    VARCHAR(50),
    expiry_date     TIMESTAMP,
    auto_renew      BOOLEAN DEFAULT true,
    ssl_status      VARCHAR(30),
    ssl_expiry      TIMESTAMP,
    nameservers     JSONB DEFAULT '[]'::JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dns_records (
    id              SERIAL PRIMARY KEY,
    domain_id       INTEGER NOT NULL REFERENCES domains(id),
    record_type     VARCHAR(10) NOT NULL,
    host            VARCHAR(253) NOT NULL,
    value           TEXT NOT NULL,
    ttl             INTEGER DEFAULT 1800,
    mx_pref         INTEGER,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============ MODULE: WAZA ============

CREATE TABLE IF NOT EXISTS waza_services (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    slug            VARCHAR(100) NOT NULL UNIQUE,
    compose_file    VARCHAR(200),
    always_on       BOOLEAN DEFAULT false,
    ram_limit_mb    INTEGER,
    cpu_limit       REAL,
    status          VARCHAR(20) DEFAULT 'stopped',
    profile         VARCHAR(50),
    start_cmd       TEXT,
    stop_cmd        TEXT,
    status_cmd      TEXT,
    started_at      TIMESTAMP,
    last_stopped_at TIMESTAMP
);

-- ============ SEED: initial servers from nodes table ============

INSERT INTO servers (name, slug, provider, server_role, tailscale_ip, public_ip, status, ssh_port, ssh_user, created_at)
SELECT
    name,
    lower(regexp_replace(name, '[^a-zA-Z0-9]', '-', 'gi')),
    CASE
        WHEN name = 'sese-ai'  THEN 'ovh'::provider_type
        WHEN name = 'seko-vpn' THEN 'ionos'::provider_type
        WHEN name IN ('rpi5', 'waza') THEN 'local'::provider_type
        ELSE 'ovh'::provider_type
    END,
    CASE
        WHEN name = 'sese-ai'  THEN 'ai_brain'::server_role
        WHEN name = 'seko-vpn' THEN 'vpn_hub'::server_role
        WHEN name IN ('rpi5', 'waza') THEN 'workstation'::server_role
        ELSE 'app_prod'::server_role
    END,
    tailscale_ip,
    local_ip,
    COALESCE(status, 'offline')::text::node_status,
    CASE WHEN name IN ('rpi5', 'waza') THEN 22 ELSE 804 END,
    'mobuone',
    created_at
FROM nodes
ON CONFLICT (slug) DO UPDATE SET
    provider = EXCLUDED.provider,
    server_role = EXCLUDED.server_role,
    ssh_port = EXCLUDED.ssh_port;

-- ============ SEED: initial Waza services ============

INSERT INTO waza_services (name, slug, always_on, ram_limit_mb, cpu_limit, profile, start_cmd, stop_cmd, status_cmd) VALUES
    ('ComfyUI', 'workstation_comfyui', false, 4096, 2.0, 'art', NULL, NULL, NULL),
    ('Remotion', 'workstation_remotion', false, 512, 0.5, 'video', NULL, NULL, NULL),
    ('n8n MCP Bridge', 'n8n-mcp', true, 512, 0.5, 'dev', NULL, NULL, NULL),
    ('OpenCut', 'opencut', false, 1536, 2.0, 'video',
        'docker compose -f /opt/workstation/docker-compose-opencut.yml up -d',
        'docker compose -f /opt/workstation/docker-compose-opencut.yml down',
        'docker compose -f /opt/workstation/docker-compose-opencut.yml ps --format json'),
    ('Flash Studio', 'flash-daemon', false, 256, 0.5, 'dev',
        'tmux new-session -d -s flash ''cd ~/flash-studio/flash-infra && bash scripts/flash-daemon.sh 2>&1 | tee /tmp/daemon-v5.log''',
        'tmux kill-session -t flash',
        'tmux has-session -t flash 2>/dev/null && echo running || echo stopped'),
    ('Macgyver', 'macgyver-daemon', false, 256, 0.5, 'dev',
        'tmux new-session -d -s macgyver ''cd ~/macgyver && bash macgyver-daemon.sh 2>&1 | tee /tmp/macgyver.log''',
        'tmux kill-session -t macgyver',
        'tmux has-session -t macgyver 2>/dev/null && echo running || echo stopped')
ON CONFLICT (slug) DO NOTHING;
