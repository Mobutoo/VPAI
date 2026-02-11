# Role: redis

## Description

Redis 8.0 with password auth, maxmemory with LRU eviction, RDB persistence, and I/O threading.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `redis_maxmemory` | `384mb/192mb` | Max memory (prod/preprod) |
| `redis_maxmemory_policy` | `allkeys-lru` | Eviction policy |
| `redis_io_threads` | `2` | Redis 8.0 I/O threads |

## Dependencies

- `docker`
