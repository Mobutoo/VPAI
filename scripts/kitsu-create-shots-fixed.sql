-- Create shots under sequence "Video by santeanime"
-- Real sequence ID: edb8375a-0e5d-4516-9d6e-34d08e7217cc

INSERT INTO entity (id, name, project_id, entity_type_id, parent_id, data, status, created_at, updated_at)
VALUES (
    gen_random_uuid(), 'SH0010',
    '19b9faf4-f7c4-4829-9739-cbf7c3181941',
    '7a1b7c9e-74eb-40a3-95fe-ce0f6967a989',
    'edb8375a-0e5d-4516-9d6e-34d08e7217cc',
    '{"style": "3D Animation", "mood": "Playful and Fun", "colors": "#d1c8b4, #3b312e", "motion": "low", "ai_prompt": "A playful and vibrant scene featuring an animated character designed as a shoe"}'::jsonb,
    'running', now(), now()
);

INSERT INTO entity (id, name, project_id, entity_type_id, parent_id, data, status, created_at, updated_at)
VALUES (
    gen_random_uuid(), 'SH0020',
    '19b9faf4-f7c4-4829-9739-cbf7c3181941',
    '7a1b7c9e-74eb-40a3-95fe-ce0f6967a989',
    'edb8375a-0e5d-4516-9d6e-34d08e7217cc',
    '{"style": "Cartoonish", "mood": "Playful with irony", "colors": "#3b312e, #6d6a66", "motion": "medium", "ai_prompt": "A cartoon scene with animated objects in an industrial setting"}'::jsonb,
    'running', now(), now()
);

INSERT INTO entity (id, name, project_id, entity_type_id, parent_id, data, status, created_at, updated_at)
VALUES (
    gen_random_uuid(), 'SH0030',
    '19b9faf4-f7c4-4829-9739-cbf7c3181941',
    '7a1b7c9e-74eb-40a3-95fe-ce0f6967a989',
    'edb8375a-0e5d-4516-9d6e-34d08e7217cc',
    '{"style": "3D Animation", "mood": "Humorous", "colors": "#bb4430, #d1c8b4", "motion": "low", "ai_prompt": "A cartoon scene featuring a sandal character on a sunny beach"}'::jsonb,
    'running', now(), now()
);

-- Verify
SELECT e.id, e.name, e.data::text
FROM entity e
WHERE e.entity_type_id = '7a1b7c9e-74eb-40a3-95fe-ce0f6967a989'
ORDER BY e.name;
