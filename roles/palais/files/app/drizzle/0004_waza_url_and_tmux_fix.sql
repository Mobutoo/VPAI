-- 0004_waza_url_and_tmux_fix.sql
-- Adds url column to waza_services for displaying service URLs on cards.
-- Fixes tmux start/stop commands to be idempotent (no error if session missing/exists).

-- ============ SCHEMA: add url column ============

ALTER TABLE waza_services ADD COLUMN IF NOT EXISTS url VARCHAR(253);

-- ============ FIX: idempotent tmux commands for Flash Studio ============
-- stop_cmd: kill session if exists, never error
-- start_cmd: kill any stale session first, then create new one

UPDATE waza_services SET
    start_cmd = 'tmux kill-session -t flash 2>/dev/null; tmux new-session -d -s flash ''cd ~/flash-studio/flash-infra && bash scripts/flash-daemon.sh 2>&1 | tee /tmp/daemon-v5.log''',
    stop_cmd = 'tmux kill-session -t flash 2>/dev/null || true'
WHERE slug = 'flash-daemon';

-- ============ FIX: idempotent tmux commands for Macgyver ============

UPDATE waza_services SET
    start_cmd = 'tmux kill-session -t macgyver 2>/dev/null; tmux new-session -d -s macgyver ''cd ~/macgyver && bash macgyver-daemon.sh 2>&1 | tee /tmp/macgyver.log''',
    stop_cmd = 'tmux kill-session -t macgyver 2>/dev/null || true'
WHERE slug = 'macgyver-daemon';

-- ============ SEED: service URLs ============

UPDATE waza_services SET url = 'https://studio.ewutelo.cloud' WHERE slug = 'workstation_comfyui';
UPDATE waza_services SET url = 'https://re.ewutelo.cloud' WHERE slug = 'workstation_remotion';
UPDATE waza_services SET url = 'https://cut.ewutelo.cloud' WHERE slug = 'opencut';
-- flash-daemon, macgyver-daemon, n8n-mcp: no URL (daemons, not web services)
