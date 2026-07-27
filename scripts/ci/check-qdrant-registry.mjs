#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

import { parse } from 'yaml';

import {
	readRegistry,
	registryCanonicalBytes,
	registrySha256
} from '../qdrant-registry-canonicalize.mjs';

const root = resolve(import.meta.dirname, '../..');
const registry = await readRegistry(
	resolve(root, 'inventory/group_vars/all/qdrant_collections.yml')
);
const names = registry.collections.map(({ name }) => name);
assert.equal(new Set(names).size, names.length);
assert.equal(registry.aliases.knowledge_current, 'knowledge_v1');
assert.equal(registry.test_targets.prefix, 'prisme_test_');
assert.equal(registry.test_targets.alias_prefix, 'prisme_test_alias_');
assert.equal(
	registry.collections.find(({ name }) => name === 'trading_v1').mutation_policy,
	'deny-from-prisme'
);
assert.ok(
	registry.collections
		.filter(({ name }) => name !== 'knowledge_v1')
		.every(({ mutation_policy }) => mutation_policy === 'deny-from-prisme')
);

const fixtureA = parse(
	'yes: \"yes\"\nno: \"no\"\non: \"on\"\noff: \"off\"\nnumber: 1.5\ndate: \"2026-07-27\"\n'
);
const fixtureB = parse(
	'date: \"2026-07-27\"\nnumber: 1.5\noff: \"off\"\non: \"on\"\nno: \"no\"\nyes: \"yes\"\n'
);
assert.deepEqual(registryCanonicalBytes(fixtureA), registryCanonicalBytes(fixtureB));
assert.equal(
	registrySha256({ ...fixtureA, source_commit: 'a', prisme_registry_ref: 'b' }),
	registrySha256(fixtureA)
);

const canonicalizer = await readFile(resolve(root, 'scripts/qdrant-registry-canonicalize.mjs'));
assert.ok(canonicalizer.length > 0);
console.log('Qdrant registry gate: PASS');
