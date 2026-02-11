# Role: qdrant

## Description

Qdrant vector database with API key authentication and HNSW index tuning for text embeddings.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `qdrant_api_key` | Vault | API authentication key |
| `qdrant_hnsw_m` | `16` | HNSW M parameter |
| `qdrant_hnsw_ef_construct` | `100` | HNSW ef_construct parameter |

## Dependencies

- `docker`
