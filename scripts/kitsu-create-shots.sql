-- Create test shots in Kitsu DB directly
-- Workaround for Zou 1.0.18 missing POST /data/projects/{id}/shots

-- Verify current state
SELECT count(*) as entity_count FROM entity;
SELECT count(*) as shot_count FROM entity WHERE entity_type_id = '7a1b7c9e-74eb-40a3-95fe-ce0f6967a989';

-- Create shot SH0010 under sequence "Video by santeanime"
INSERT INTO entity (id, name, project_id, entity_type_id, parent_id, data, status, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'SH0010',
    '19b9faf4-f7c4-4829-9739-cbf7c3181941',
    '7a1b7c9e-74eb-40a3-95fe-ce0f6967a989',
    'edb8375a-0e5e-4ed3-9e90-59f6e63cf3e9',
    '{"style": "3D Animation", "mood": "Playful", "colors": "#d1c8b4, #3b312e", "motion": "low", "ai_prompt": "A playful 3D animated scene"}'::jsonb,
    'running',
    now(),
    now()
);

-- Create shot SH0020
INSERT INTO entity (id, name, project_id, entity_type_id, parent_id, data, status, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'SH0020',
    '19b9faf4-f7c4-4829-9739-cbf7c3181941',
    '7a1b7c9e-74eb-40a3-95fe-ce0f6967a989',
    'edb8375a-0e5e-4ed3-9e90-59f6e63cf3e9',
    '{"style": "Cartoonish", "mood": "Ironic", "colors": "#3b312e, #6d6a66", "motion": "medium", "ai_prompt": "Industrial cartoon scene with animated objects"}'::jsonb,
    'running',
    now(),
    now()
);

-- Verify
SELECT id, name, data::text FROM entity WHERE entity_type_id = '7a1b7c9e-74eb-40a3-95fe-ce0f6967a989' ORDER BY name;
