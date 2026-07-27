# Qdrant collection manifest

The authoritative registry is
`inventory/group_vars/all/qdrant_collections.yml`. It inventories the single production instance
on Sese without granting Prisme access to foreign points, vectors or payloads.

Rules:

- `knowledge_v1` is the only physical collection mutable by Prisme;
- `knowledge_current` is the only runtime alias;
- `prisme_test_*` requires both test mode and an attested loopback/ephemeral endpoint;
- every foreign collection is `deny-from-prisme`;
- incompatible schemas fail with a migration report; no bootstrap deletes or recreates;
- PostgreSQL plus `tank/knowledge` remain authoritative and Qdrant is reconstructible.

Generate the cross-repository snapshot:

```bash
pnpm install --frozen-lockfile
scripts/generate-prisme-qdrant-registry /home/mobuone/work/saas/prisme
```

The generator removes only `source_commit` and `prisme_registry_ref` before RFC 8785/JCS
canonicalization. The SHA-256 covers the resulting UTF-8 JSON bytes. The trace refs are audit
metadata, not integrity inputs.

Production inventory is read-only. A Prisme bootstrap may mutate only `knowledge_v1` and its
alias after the capacity, schema, ACL and before/after-diff gates are green.
