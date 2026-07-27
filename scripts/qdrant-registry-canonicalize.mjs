#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

import { parse } from 'yaml';

function normalize(value) {
	if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
	if (typeof value === 'number') {
		if (!Number.isFinite(value)) throw new TypeError('JCS rejects non-finite numbers');
		return Object.is(value, -0) ? 0 : value;
	}
	if (Array.isArray(value)) return value.map(normalize);
	if (typeof value === 'object') {
		return Object.fromEntries(
			Object.keys(value)
				.sort()
				.map((key) => [key, normalize(value[key])])
		);
	}
	throw new TypeError(`JCS rejects ${typeof value}`);
}

export function registryCanonicalBytes(document) {
	const clean = structuredClone(document);
	delete clean.source_commit;
	delete clean.prisme_registry_ref;
	return Buffer.from(JSON.stringify(normalize(clean)), 'utf8');
}

export function registrySha256(document) {
	return createHash('sha256').update(registryCanonicalBytes(document)).digest('hex');
}

export async function readRegistry(path) {
	return parse(await readFile(path, 'utf8'), {
		schema: 'core',
		uniqueKeys: true
	});
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
	const [mode, path] = process.argv.slice(2);
	if (!path || !['canonicalize', 'sha256'].includes(mode)) {
		throw new Error('usage: qdrant-registry-canonicalize.mjs canonicalize|sha256 FILE');
	}
	const document = await readRegistry(path);
	process.stdout.write(
		mode === 'sha256' ? `${registrySha256(document)}\n` : registryCanonicalBytes(document)
	);
}
