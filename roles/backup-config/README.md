# Role: backup-config

## Description

Prepares the backup infrastructure on the production VPS (Seko-AI). This includes:
- Creating backup directories for all services
- Deploying the `pre-backup.sh` script that dumps PostgreSQL, snapshots Redis/Qdrant, exports n8n workflows and Grafana dashboards
- Configuring a cron job to run pre-backup at 02:55 (before Zerobyte at 03:00)
- Deploying a cleanup script to remove old local backups
- Optional heartbeat ping to Uptime Kuma after successful backup

**Note**: Zerobyte itself runs on Seko-VPN and is configured manually. See `docs/RUNBOOK.md` for the full Zerobyte setup procedure.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `backup_base_dir` | `/opt/{{ project_name }}/backups` | Base backup directory |
| `backup_pre_script_cron_minute` | `55` | Cron minute for pre-backup |
| `backup_pre_script_cron_hour` | `2` | Cron hour for pre-backup |
| `backup_heartbeat_url` | `(vault)` | Uptime Kuma push URL for heartbeat |
| `backup_local_retention_days` | `3` | Days to keep local backup files |

## Backup Flow

```
02:55  pre-backup.sh runs on Seko-AI (pg_dump, redis save, qdrant snapshot, n8n export)
03:00  Zerobyte on Seko-VPN pulls data via VPN mount → pushes to Hetzner S3
03:00  Heartbeat ping sent to Uptime Kuma (if configured)
04:00  backup-cleanup.sh removes local files older than retention period
```

## Dependencies

- `docker` role
