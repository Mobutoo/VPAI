-- Palais v2 teardown — drop modules: ideas, missions, projects/tasks, budget, insights, deliverables
-- Run order matters: child tables first, parent tables last

-- Drop indexes first
DROP INDEX IF EXISTS task_dep_unique;
DROP INDEX IF EXISTS task_label_pk;
DROP INDEX IF EXISTS activity_entity_idx;
DROP INDEX IF EXISTS deliverable_token_idx;

-- Deliverables (references tasks)
DROP TABLE IF EXISTS deliverables CASCADE;

-- Time tracking (references tasks)
DROP TABLE IF EXISTS time_entries CASCADE;
DROP TABLE IF EXISTS task_iterations CASCADE;

-- Task relations
DROP TABLE IF EXISTS task_labels CASCADE;
DROP TABLE IF EXISTS comments CASCADE;
DROP TABLE IF EXISTS task_dependencies CASCADE;
DROP TABLE IF EXISTS activity_log CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS columns CASCADE;
DROP TABLE IF EXISTS labels CASCADE;
DROP TABLE IF EXISTS projects CASCADE;
DROP TABLE IF EXISTS workspaces CASCADE;

-- Missions
DROP TABLE IF EXISTS mission_conversations CASCADE;
DROP TABLE IF EXISTS missions CASCADE;

-- Ideas
DROP TABLE IF EXISTS idea_links CASCADE;
DROP TABLE IF EXISTS idea_versions CASCADE;
DROP TABLE IF EXISTS ideas CASCADE;

-- Budget
DROP TABLE IF EXISTS budget_forecasts CASCADE;
DROP TABLE IF EXISTS budget_snapshots CASCADE;

-- Insights
DROP TABLE IF EXISTS insights CASCADE;

-- Remove dropped columns from kept tables
ALTER TABLE agents DROP COLUMN IF EXISTS current_task_id;
ALTER TABLE agent_sessions DROP COLUMN IF EXISTS mission_id;
ALTER TABLE agent_sessions DROP COLUMN IF EXISTS task_id;

-- Drop unused enums
DROP TYPE IF EXISTS idea_status CASCADE;
DROP TYPE IF EXISTS mission_status CASCADE;
DROP TYPE IF EXISTS insight_type CASCADE;
DROP TYPE IF EXISTS insight_severity CASCADE;
DROP TYPE IF EXISTS entity_type_generic CASCADE;
DROP TYPE IF EXISTS time_entry_type CASCADE;
DROP TYPE IF EXISTS dep_type CASCADE;
DROP TYPE IF EXISTS budget_source CASCADE;
