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
| `uptime_kuma_monitors` | (see defaults) | List of monitor definitions |

## Dependencies

None.
