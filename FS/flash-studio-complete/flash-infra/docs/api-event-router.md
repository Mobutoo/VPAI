# Event Router — API Reference

Base URL: `https://portail.<domain>/api` (proxied via Caddy)
Internal: `http://event-router:8092/api`

---

## Events

### POST /api/events

Receive events from flash-agent instances. Stores in PostgreSQL, broadcasts via SSE,
and optionally routes to Zammad / Brevo / Telegram based on severity.

**Request body:**

```json
{
  "client_id": "client-42",
  "type": "warning",
  "category": "backup",
  "title": "Backup failed",
  "message": "Daily backup to S3 failed after 3 retries",
  "metadata": {
    "host": "srv-prod-01",
    "error_code": "TIMEOUT"
  }
}
```

| Field      | Type   | Required | Description                            |
|------------|--------|----------|----------------------------------------|
| client_id  | string | yes      | Client identifier                      |
| type       | string | yes      | `info`, `warning`, `critical`          |
| category   | string | yes      | Free-text category (backup, security…) |
| title      | string | yes      | Short summary                          |
| message    | string | yes      | Detailed description                   |
| metadata   | object | no       | Arbitrary key-value pairs              |

**Response:** `201 Created`

```json
{
  "id": 1,
  "client_id": "client-42",
  "type": "warning",
  "category": "backup",
  "title": "Backup failed",
  "message": "Daily backup to S3 failed after 3 retries",
  "metadata": {"host": "srv-prod-01", "error_code": "TIMEOUT"},
  "read": false,
  "created_at": "2026-03-10T14:30:00Z"
}
```

---

### GET /api/events

List events for a client. Supports filtering and pagination.

**Query parameters:**

| Param     | Type   | Default | Description                     |
|-----------|--------|---------|---------------------------------|
| client_id | string | —       | Filter by client (required)     |
| type      | string | —       | Filter by severity level        |
| limit     | int    | 50      | Max results (1–200)             |
| offset    | int    | 0       | Pagination offset               |

**Response:** `200 OK` — JSON array of events.

---

### GET /api/events/stream

SSE (Server-Sent Events) endpoint for real-time notifications.

**Query parameters:**

| Param     | Type   | Required | Description          |
|-----------|--------|----------|----------------------|
| client_id | string | yes      | Client to subscribe  |

**Usage:**

```bash
curl -N "http://event-router:8092/api/events/stream?client_id=client-42"
```

Each event is sent as `data: <JSON>\n\n`.

---

## Announcements

Status page announcements displayed on Gatus. Stored in PostgreSQL,
synced to Gatus config file, and container is restarted automatically.

### POST /api/announcements

Create a new announcement. Triggers Gatus config sync.

**Request body:**

```json
{
  "type": "outage",
  "message": "Scheduled maintenance on PostgreSQL — March 12, 22:00–23:00 UTC"
}
```

| Field   | Type   | Required | Default       | Description                                          |
|---------|--------|----------|---------------|------------------------------------------------------|
| type    | string | no       | `information` | `information`, `warning`, `outage`, `operational`    |
| message | string | yes      | —             | Announcement text displayed on the status page       |

**Response:** `201 Created`

```json
{
  "id": 1,
  "type": "outage",
  "message": "Scheduled maintenance on PostgreSQL — March 12, 22:00–23:00 UTC",
  "archived": false,
  "created_at": "2026-03-10T15:00:00Z"
}
```

---

### GET /api/announcements

List announcements. By default returns only active (non-archived).

**Query parameters:**

| Param | Type   | Default | Description                         |
|-------|--------|---------|-------------------------------------|
| all   | string | —       | Set to `true` to include archived   |

**Response:** `200 OK`

```json
[
  {
    "id": 1,
    "type": "outage",
    "message": "Scheduled maintenance on PostgreSQL — March 12, 22:00–23:00 UTC",
    "archived": false,
    "created_at": "2026-03-10T15:00:00Z"
  }
]
```

---

### PUT /api/announcements/{id}/archive

Archive an announcement. Removes it from the status page. Triggers Gatus config sync.

**Path parameters:**

| Param | Type | Description      |
|-------|------|------------------|
| id    | int  | Announcement ID  |

**Response:** `200 OK`

```json
{"status": "archived"}
```

**Error:** `404` if not found or already archived.

---

## Gatus Endpoints

Dynamic monitoring endpoint management. Endpoints created via this API are
appended to the Gatus config after the `# --- Dynamic (API-managed) ---` marker.
Static endpoints defined in the Ansible template are preserved.

### POST /api/gatus/endpoints

Add a new monitoring endpoint. Triggers Gatus config sync.

**Request body:**

```json
{
  "name": "Client Portal API",
  "group": "Client Services",
  "url": "https://api.client.example.com/health",
  "interval": "30s",
  "conditions": ["[STATUS] == 200", "[RESPONSE_TIME] < 3000"]
}
```

| Field      | Type     | Required | Default              | Description                              |
|------------|----------|----------|----------------------|------------------------------------------|
| name       | string   | yes      | —                    | Display name in Gatus dashboard          |
| group      | string   | no       | `Custom`             | Group name for organizing endpoints      |
| url        | string   | yes      | —                    | URL to monitor (http/https/tcp)          |
| interval   | string   | no       | `60s`                | Check interval (e.g. `30s`, `5m`)        |
| conditions | string[] | no       | `["[STATUS] == 200"]`| Gatus condition expressions              |

**Response:** `201 Created`

```json
{
  "id": 1,
  "name": "Client Portal API",
  "group": "Client Services",
  "url": "https://api.client.example.com/health",
  "interval": "30s",
  "conditions": ["[STATUS] == 200", "[RESPONSE_TIME] < 3000"],
  "enabled": true,
  "created_at": "2026-03-10T16:00:00Z"
}
```

---

### GET /api/gatus/endpoints

List all dynamic endpoints (both enabled and disabled).

**Response:** `200 OK`

```json
[
  {
    "id": 1,
    "name": "Client Portal API",
    "group": "Client Services",
    "url": "https://api.client.example.com/health",
    "interval": "30s",
    "conditions": ["[STATUS] == 200", "[RESPONSE_TIME] < 3000"],
    "enabled": true,
    "created_at": "2026-03-10T16:00:00Z"
  }
]
```

---

### PUT /api/gatus/endpoints/{id}

Update an existing endpoint. Supports partial updates — only include fields to change.
Triggers Gatus config sync.

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| id    | int  | Endpoint ID |

**Request body (all fields optional):**

```json
{
  "name": "Client Portal API v2",
  "interval": "15s",
  "enabled": false
}
```

| Field      | Type     | Description                              |
|------------|----------|------------------------------------------|
| name       | string   | Updated display name                     |
| group      | string   | Updated group name                       |
| url        | string   | Updated monitoring URL                   |
| interval   | string   | Updated check interval                   |
| conditions | string[] | Updated condition list (replaces all)    |
| enabled    | bool     | `false` to pause monitoring              |

**Response:** `200 OK` — full updated endpoint object.

**Note:** Disabled endpoints (`enabled: false`) are excluded from the Gatus config
but remain in the database for re-enabling.

---

### DELETE /api/gatus/endpoints/{id}

Permanently delete a monitoring endpoint. Triggers Gatus config sync.

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| id    | int  | Endpoint ID |

**Response:** `200 OK`

```json
{"status": "deleted"}
```

**Error:** `404` if not found.

---

## Smart Ticket Creation

Intelligent ticket creation pipeline with LLM extraction, deduplication,
and automatic Zammad routing. Used by agents (openclaw, Go VPS, Claude)
and voice interfaces.

### Authentication

Ticket creation endpoints require an API key via `Authorization: Bearer <key>` header.
Keys are stored as SHA-256 hashes in the `api_keys` table. The `client_id` in the token
must match the `client_id` in the request payload (agents can only create tickets for their own client).

Admin endpoints (`POST /api/client-customers`) require the `ADMIN_API_KEY` environment variable.

### POST /api/tickets

Create a structured support ticket from an agent message. Runs through a 10-step pipeline:
idempotency check, rate limiting, LLM extraction, category cooldown, hash dedup,
semantic dedup, Zammad customer resolution, enrichment, ticket creation, and mapping storage.

**Headers:**

| Header        | Required | Description                |
|---------------|----------|----------------------------|
| Authorization | yes      | `Bearer <api-key>`         |

**Request body:**

```json
{
  "client_id": "client-42",
  "message": "Mon backup echoue chaque nuit depuis 3 jours",
  "source": "agent",
  "language": "fr",
  "event_id": "evt-20260310-001",
  "metadata": {
    "host": "srv-prod-01",
    "agent_version": "1.2.0"
  }
}
```

| Field     | Type   | Required | Default   | Description                                         |
|-----------|--------|----------|-----------|-----------------------------------------------------|
| client_id | string | yes      | —         | Client identifier                                   |
| message   | string | yes      | —         | Free-text description (max 10,000 chars)             |
| source    | string | no       | `agent`   | Origin: `agent`, `voice`, `monitor`, `openclaw`      |
| language  | string | no       | auto      | ISO 639-1 language hint (auto-detected by LLM)       |
| event_id  | string | no       | —         | Idempotency key (prevents duplicate processing)      |
| metadata  | object | no       | —         | Arbitrary key-value context                          |

**Response:** `201 Created`

```json
{
  "status": "created",
  "ticket_id": 42,
  "zammad_ticket_id": 1234,
  "correlation_id": "a1b2c3d4e5f6"
}
```

**Error responses:**

| Code | Condition | Body |
|------|-----------|------|
| 400  | Missing fields or message > 10,000 chars | `{"error": "message is required"}` |
| 401  | Invalid or missing API key | `{"error": "unauthorized"}` |
| 409  | Duplicate (idempotency or semantic) | `{"status": "duplicate", "duplicate_of": 1233}` |
| 429  | Rate limit exceeded (10/hour/client) | `{"error": "rate limit exceeded"}` |

---

### POST /api/voice-ticket

Create a ticket from a voice transcription. Same pipeline as `/api/tickets`
but with LLM prompt optimized for speech patterns (informal phrasing, minor errors).

**Headers:**

| Header        | Required | Description                |
|---------------|----------|----------------------------|
| Authorization | yes      | `Bearer <api-key>`         |

**Request body:**

```json
{
  "client_id": "client-42",
  "message": "Bonjour je narrive pas a me connecter depuis ce matin ca me dit mot de passe incorrect",
  "language": "fr"
}
```

| Field     | Type   | Required | Default | Description                                   |
|-----------|--------|----------|---------|-----------------------------------------------|
| client_id | string | yes      | —       | Client identifier                             |
| message   | string | yes      | —       | Raw voice transcription (max 10,000 chars)     |
| language  | string | no       | auto    | Language hint for better LLM extraction        |

**Response:** `201 Created` — Same format as `POST /api/tickets`.

---

### GET /api/tickets/{clientID}

List ticket mappings for a client. Returns correlation between internal events
and Zammad tickets.

**Path parameters:**

| Param    | Type   | Description     |
|----------|--------|-----------------|
| clientID | string | Client ID       |

**Query parameters:**

| Param  | Type | Default | Description             |
|--------|------|---------|-------------------------|
| limit  | int  | 50      | Max results (1-200)     |
| offset | int  | 0       | Pagination offset       |

**Response:** `200 OK`

```json
[
  {
    "id": 1,
    "event_id": "evt-20260310-001",
    "client_id": "client-42",
    "zammad_ticket_id": 1234,
    "correlation_id": "a1b2c3d4e5f6",
    "source": "agent",
    "category": "backup",
    "priority": "high",
    "language": "fr",
    "created_at": "2026-03-10T14:30:00Z"
  }
]
```

---

## Client-Customer Mapping

Map internal `client_id` to Zammad customer IDs. Used to route tickets
to the correct Zammad customer.

### POST /api/client-customers

Create or update a client-to-Zammad-customer mapping. Requires admin API key.

**Headers:**

| Header        | Required | Description                          |
|---------------|----------|--------------------------------------|
| Authorization | yes      | `Bearer <admin-api-key>`             |

**Request body:**

```json
{
  "client_id": "client-42",
  "zammad_customer_id": 5,
  "email": "client-42@clients.flash-studio.io",
  "name": "Client 42 — Acme Corp"
}
```

| Field              | Type   | Required | Description                     |
|--------------------|--------|----------|---------------------------------|
| client_id          | string | yes      | Internal client identifier       |
| zammad_customer_id | int    | yes      | Zammad customer ID               |
| email              | string | no       | Customer email in Zammad         |
| name               | string | no       | Customer display name            |

**Response:** `200 OK`

```json
{
  "client_id": "client-42",
  "zammad_customer_id": 5,
  "email": "client-42@clients.flash-studio.io",
  "name": "Client 42 — Acme Corp"
}
```

---

### GET /api/client-customers/{clientID}

Get the Zammad customer mapping for a client.

**Path parameters:**

| Param    | Type   | Description     |
|----------|--------|-----------------|
| clientID | string | Client ID       |

**Response:** `200 OK` — Same format as POST response.

**Error:** `404` if no mapping exists.

---

## Health

### GET /health

Health check endpoint (used by Gatus to monitor event-router itself).

**Response:** `200 OK`

```json
{"status": "ok"}
```

---

## Architecture Notes

### Gatus Config Sync

When announcements or endpoints are modified, the event-router:

1. Queries all active announcements and enabled endpoints from PostgreSQL
2. Reads the current Gatus config file (`GATUS_CONFIG_PATH`)
3. Strips the existing `announcements:` section (if any)
4. Strips everything after the `# --- Dynamic (API-managed) ---` marker
5. Rebuilds both sections from database state
6. Writes the updated config file
7. Restarts the Gatus container via Docker Engine API (`/var/run/docker.sock`)

Static endpoints defined in the Ansible template (before the marker) are never modified.

### Environment Variables

| Variable               | Default                | Description                        |
|------------------------|------------------------|------------------------------------|
| DATABASE_URL           | —                      | PostgreSQL connection string       |
| REDIS_URL              | —                      | Redis connection string            |
| GATUS_CONFIG_PATH      | —                      | Path to Gatus config.yaml          |
| GATUS_CONTAINER_NAME   | `sd_gatus`             | Docker container name for restart  |
| DOCKER_SOCKET          | `/var/run/docker.sock` | Docker Engine API socket path      |
| ZAMMAD_URL             | —                      | Zammad API base URL                |
| ZAMMAD_TOKEN           | —                      | Zammad API token                   |
| BREVO_API_KEY          | —                      | Brevo transactional email API key  |
| TELEGRAM_BOT_TOKEN     | —                      | Telegram bot token                 |
| TELEGRAM_CHAT_ID       | —                      | Telegram chat/channel ID           |
| LITELLM_URL            | —                      | LiteLLM proxy URL for LLM calls   |
| LITELLM_API_KEY        | —                      | LiteLLM API key                    |
| LLM_MODEL              | `claude-sonnet-4-6`    | Model for ticket extraction        |
| ADMIN_API_KEY          | —                      | Admin API key for protected routes |
| PORT                   | `8092`                 | HTTP server port                   |

### Gatus Condition Syntax

Common conditions used in endpoint monitoring:

| Condition                  | Description                           |
|----------------------------|---------------------------------------|
| `[STATUS] == 200`          | HTTP status code is 200               |
| `[STATUS] < 400`           | HTTP status code below 400            |
| `[RESPONSE_TIME] < 5000`   | Response time under 5 seconds (ms)    |
| `[CONNECTED] == true`      | TCP connection successful             |
| `[BODY] == pat(*ok*)`      | Response body contains "ok"           |

### cURL Examples

```bash
# Create an outage announcement
curl -X POST http://event-router:8092/api/announcements \
  -H "Content-Type: application/json" \
  -d '{"type":"outage","message":"Database maintenance in progress"}'

# List active announcements
curl http://event-router:8092/api/announcements

# Archive an announcement
curl -X PUT http://event-router:8092/api/announcements/1/archive

# Add a monitoring endpoint
curl -X POST http://event-router:8092/api/gatus/endpoints \
  -H "Content-Type: application/json" \
  -d '{"name":"Google DNS","group":"External","url":"https://dns.google/resolve?name=google.com","interval":"60s"}'

# List all dynamic endpoints
curl http://event-router:8092/api/gatus/endpoints

# Disable an endpoint (keep in DB)
curl -X PUT http://event-router:8092/api/gatus/endpoints/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled":false}'

# Delete an endpoint permanently
curl -X DELETE http://event-router:8092/api/gatus/endpoints/1

# --- Smart Ticket Creation ---

# Create a ticket from an agent
curl -X POST http://event-router:8092/api/tickets \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api-key>" \
  -d '{"client_id":"client-42","message":"Mon backup echoue chaque nuit","source":"agent","event_id":"evt-001"}'

# Create a ticket from voice transcription
curl -X POST http://event-router:8092/api/voice-ticket \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api-key>" \
  -d '{"client_id":"client-42","message":"Bonjour je narrive pas a me connecter","language":"fr"}'

# List ticket mappings for a client
curl http://event-router:8092/api/tickets/client-42

# Upsert client-customer mapping (admin)
curl -X POST http://event-router:8092/api/client-customers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-api-key>" \
  -d '{"client_id":"client-42","zammad_customer_id":5,"email":"client-42@clients.flash-studio.io","name":"Acme Corp"}'

# Get client-customer mapping
curl http://event-router:8092/api/client-customers/client-42
```

### Ticket Pipeline Architecture

When a ticket is created via `POST /api/tickets` or `POST /api/voice-ticket`,
it goes through a 10-step pipeline:

| Step | Name              | Mechanism                         | Protection              |
|------|-------------------|-----------------------------------|-------------------------|
| 1    | Idempotency       | Redis SETNX on event_id (1h TTL)  | Replay attacks          |
| 2    | Rate Limit        | Redis sorted set (10/h per client)| Flood attacks           |
| 3    | LLM Extraction    | LiteLLM structured prompt         | Extracts title/category |
| 4    | Category Cooldown | Redis SET (5 min per category)    | Category spam           |
| 5    | Hash Dedup        | SHA-256 of message (24h Redis)    | Identical messages      |
| 6    | Semantic Dedup    | Embedding cosine similarity >=0.92| Reformulated duplicates |
| 7    | Customer Resolve  | DB cache -> Zammad search/create  | Customer mapping        |
| 8    | Enrichment        | Health score + recent events      | Context for support     |
| 9    | Zammad Create     | POST /api/v1/tickets with routing | Ticket creation         |
| 10   | Store Mapping     | PostgreSQL + Redis cache          | Audit trail             |

**Resilience features:**
- Circuit breaker on LiteLLM (opens after 3 failures, 60s reset)
- Dead-letter queue for failed Zammad creations (retry every 5 min, max 5 retries)
- Fallback extraction when LLM is unavailable (truncated title, "general" category)
- Priority capping by source (only "monitor" can create "urgent" tickets)
- Body sanitization (strips token/key/password patterns before sending to Zammad)
