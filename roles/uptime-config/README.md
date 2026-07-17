# Role: uptime-config

## Description

Generates a reference document for Uptime Kuma monitor configuration. Uptime Kuma runs on Seko-VPN and monitors are created manually using the generated documentation as a guide.

This role deploys a rendered Markdown file at `/opt/{{ project_name }}/docs/uptime-kuma-monitors.md` with all 9 monitors preconfigured with correct URLs, intervals, and thresholds.

## Monitors

| Monitor | Type | Interval | Description |
|---------|------|----------|-------------|
| HTTPS | HTTP | 60s | Public health endpoint |
| n8n | HTTP | 60s | n8n healthz via VPN |
| Grafana | HTTP | 120s | Grafana health API via VPN |
| PostgreSQL | TCP Port | 120s | Port 5432 via Headscale IP |
| TLS Certificate | HTTP | 24h | Certificate expiry check |
| Backup Heartbeat | Push | 24h | Pre-backup script ping |
| Plane API (401-as-up) | HTTP | 60s | `/api/v1/users/me/` — 401 proves routing+auth alive |
| LiteLLM /v1/models | HTTP | 60s | 401 or 200 both prove LiteLLM answered |
| Qdrant health | HTTP | 60s | `/healthz` |

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `uptime_kuma_monitors` | (see defaults) | List of monitor definitions ready for manual creation |

## API-level monitors — unblocked 2026-07-17

Kuma runs on Seko-VPN. Every VPN-gated vhost (Plane, LiteLLM, Qdrant, n8n) used to
return Caddy's 403 to any public request from Seko-VPN before the backend was ever
reached, because Seko-VPN was the Headscale control server but not itself a tailnet
client. Fixed by enrolling Seko-VPN as a tailnet client via `roles/headscale-node`
(`playbooks/utils/vpn-node-enroll.yml`, Tailscale IP 100.64.0.5) — the Headscale
extra_records already live on Seko now resolve correctly from the box and from inside
the `uptime-kuma` container, no Caddyfile change needed. The Plane/LiteLLM/Qdrant defs
are merged into `uptime_kuma_monitors` above (live-verified 401/401/200, 2026-07-17).
Full writeup: `~/work/infra/Seko-VPN/docs/09-uptime-kuma-monitors.md`.

## Dependencies

None.
