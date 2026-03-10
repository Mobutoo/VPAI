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
```
