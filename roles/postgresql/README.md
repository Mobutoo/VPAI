# Role: postgresql

## Description

Deploys PostgreSQL 18.1 with multi-database init (n8n, openclaw, litellm), memory tuning, pg_hba.conf for backend network only.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `postgresql_shared_buffers` | `256MB/128MB` | Shared buffers (prod/preprod) |
| `postgresql_effective_cache_size` | `512MB/256MB` | Effective cache size |
| `postgresql_databases` | See defaults | Databases and users to create |

## Dependencies

- `docker`
