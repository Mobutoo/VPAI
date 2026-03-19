-- Debug Kitsu DB
\pset format unaligned
\pset fieldsep |

-- All entities
SELECT id, name, entity_type_id, parent_id FROM entity ORDER BY name;

-- All entity types
SELECT id, name FROM entity_type ORDER BY name;

-- Check if sequences are in entity table
SELECT e.id, e.name, et.name as type_name
FROM entity e
JOIN entity_type et ON e.entity_type_id = et.id
WHERE et.name = 'Sequence';

-- Check sequence ID we used
SELECT id, name FROM entity WHERE id = 'edb8375a-0e5e-4ed3-9e90-59f6e63cf3e9';
