# Role: monitoring

## Description

Deploys the complete observability stack: VictoriaMetrics (metrics storage), Loki (log aggregation), Grafana Alloy (metrics/logs collection), and Grafana (visualization & alerting). All services run on the Docker `monitoring` network (internal). Alloy bridges `backend` and `monitoring` networks to scrape all containers.

## Components

| Component | Purpose | Port | Network |
|-----------|---------|------|---------|
| VictoriaMetrics | Metrics TSDB (Prometheus-compatible) | 8428 | monitoring |
| Loki | Log aggregation | 3100 | monitoring |
| Grafana Alloy | Metrics scraper + log collector | 12345 | backend + monitoring |
| Grafana | Visualization & alerting | 3000 | frontend + monitoring |

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `victoriametrics_retention_period` | `30d` | Metrics retention period |
| `loki_retention_period` | `336h` | Logs retention (14 days) |
| `loki_max_query_length` | `721h` | Max query range |
| `grafana_admin_user` | `admin` | Grafana admin username |
| `grafana_admin_password` | (vault) | Grafana admin password |
| `grafana_root_url` | `https://admin.{{ domain_name }}/grafana/` | Grafana external URL |
| `grafana_serve_from_sub_path` | `true` | Serve Grafana from sub-path |

## Provisioned Dashboards

- **System Overview** — CPU, RAM, Disk, Load, Network
- **Docker Containers** — Container CPU/RAM/Network/Restarts
- **LiteLLM Proxy** — Requests, latency, cost, tokens
- **PostgreSQL** — Container resources, network, disk I/O
- **Logs Explorer** — All container logs, filterable by container

## Alert Rules

- CPU > 80% for 5 min
- RAM > 85% for 5 min
- Disk > 90%
- Container restarts > 3 in 15 min

## Dependencies

- `docker` role
