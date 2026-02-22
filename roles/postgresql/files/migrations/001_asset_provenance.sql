-- Migration 001: Asset Provenance table
-- Tracks all AI-generated assets (images, videos, audio) with full provenance
-- Applied by: roles/postgresql/tasks/main.yml (idempotent via IF NOT EXISTS)

CREATE TABLE IF NOT EXISTS asset_provenance (
    asset_id        TEXT        PRIMARY KEY,
    type            TEXT        NOT NULL CHECK (type IN ('image', 'video', 'audio')),
    provider        TEXT        NOT NULL,  -- comfyui | seedream | dalle | remotion | seedance | veo
    model           TEXT        NOT NULL,
    prompt          TEXT,
    output_name     TEXT        NOT NULL,
    result_url      TEXT,
    render_id       TEXT,
    agent_id        TEXT        NOT NULL DEFAULT 'artist',
    cost_usd        NUMERIC(10, 6) NOT NULL DEFAULT 0,
    storage_path    TEXT,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_asset_provenance_type
    ON asset_provenance (type);

CREATE INDEX IF NOT EXISTS idx_asset_provenance_provider
    ON asset_provenance (provider);

CREATE INDEX IF NOT EXISTS idx_asset_provenance_agent_id
    ON asset_provenance (agent_id);

CREATE INDEX IF NOT EXISTS idx_asset_provenance_generated_at
    ON asset_provenance (generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_asset_provenance_cost
    ON asset_provenance (cost_usd DESC);

-- GIN index for JSONB metadata queries
CREATE INDEX IF NOT EXISTS idx_asset_provenance_metadata
    ON asset_provenance USING gin (metadata);

-- View: daily cost per provider (for CFO agent budget-monitor)
CREATE OR REPLACE VIEW asset_cost_daily AS
SELECT
    DATE_TRUNC('day', generated_at)  AS day,
    provider,
    type,
    COUNT(*)                          AS asset_count,
    SUM(cost_usd)                     AS total_cost_usd,
    AVG(cost_usd)                     AS avg_cost_usd
FROM asset_provenance
WHERE generated_at >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 4 DESC;
