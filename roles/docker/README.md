# Role: docker

## Description

Installs Docker CE from the official repository (not snap), Docker Compose V2 plugin, configures daemon.json with log rotation and overlay2, creates 4 named Docker networks (frontend, backend, monitoring, egress), and sets up a weekly cleanup cron.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `docker_user` | `{{ prod_user }}` | User to add to docker group |
| `docker_log_max_size` | `10m` | Max log file size per container |
| `docker_log_max_file` | `3` | Max log files per container |
| `docker_storage_driver` | `overlay2` | Docker storage driver |
| `docker_live_restore` | `true` | Keep containers running during daemon downtime |
| `docker_networks` | See defaults | List of Docker networks to create |
| `docker_cleanup_cron_weekday` | `0` | Cleanup cron day (0=Sunday) |

## Dependencies

- `common`

## Example

```yaml
- role: docker
  tags: [docker]
```
