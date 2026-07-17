# Role: uptime-config

## Description

Generates a reference document for Uptime Kuma monitor configuration. Uptime Kuma runs on Seko-VPN and monitors are created manually using the generated documentation as a guide.

This role deploys a rendered Markdown file at `/opt/{{ project_name }}/docs/uptime-kuma-monitors.md` with all 6 monitors preconfigured with correct URLs, intervals, and thresholds.

## Monitors

| Monitor | Type | Interval | Description |
|---------|------|----------|-------------|
| HTTPS | HTTP | 60s | Public health endpoint |
| n8n | HTTP | 60s | n8n healthz via VPN |
| Grafana | HTTP | 120s | Grafana health API via VPN |
| PostgreSQL | TCP Port | 120s | Port 5432 via Headscale IP |
| TLS Certificate | HTTP | 24h | Certificate expiry check |
| Backup Heartbeat | Push | 24h | Pre-backup script ping |

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `uptime_kuma_monitors` | (see defaults) | List of monitor definitions ready for manual creation |
| `uptime_kuma_monitors_api_level_blocked` | (see defaults) | Plane/LiteLLM/Qdrant API-level defs — **do not create yet**, see below |

## Blocked: API-level monitors (2026-07-17)

Kuma runs on Seko-VPN, which is not a tailnet client — every VPN-gated vhost (Plane,
LiteLLM, Qdrant, n8n) returns Caddy's 403 to any public request from Seko-VPN before
the backend is ever reached. `accepted_statuscodes` tuned for the backend (e.g. 401)
would therefore read "UP" via the 403 regardless of the app's real state. Definitions
for these are in `uptime_kuma_monitors_api_level_blocked` and rendered into a clearly
separate "Blocked" section of the generated doc — do not move them into
`uptime_kuma_monitors` until the routing gap is fixed. Full writeup, curl evidence and
the two proposed fixes: `~/work/infra/Seko-VPN/docs/09-uptime-kuma-monitors.md`.

## Dependencies

None.
