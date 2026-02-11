# Role: diun

## Description

Deploys DIUN (Docker Image Update Notifier) to watch for new Docker image versions. DIUN monitors all running containers and sends notifications when newer image versions are available. It has read-only access to the Docker socket.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `diun_config_dir` | `/opt/{{ project_name }}/configs/diun` | DIUN config directory |
| `diun_data_dir` | `/opt/{{ project_name }}/data/diun` | DIUN data directory |
| `diun_watch_schedule` | `0 */6 * * *` | Cron schedule (every 6 hours) |
| `diun_watch_first_check_notif` | `false` | Notify on first check |
| `diun_watch_by_default` | `true` | Watch all containers by default |

## Notification

Uses `{{ notification_method }}` webhook from the wizard configuration. Supports telegram, discord, slack, and generic webhook.

## Dependencies

- `docker` role
