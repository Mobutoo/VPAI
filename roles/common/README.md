# Role: common

## Description

Base OS configuration for the AI stack VPS. Installs common packages, configures locale, timezone, NTP, sysctl parameters, and creates project directories.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `common_packages` | See defaults | List of apt packages to install |
| `common_locale` | `{{ locale }}` | System locale |
| `common_timezone` | `{{ timezone }}` | System timezone |
| `common_hostname` | `{{ prod_hostname }}` | System hostname |
| `common_headscale_ip` | `{{ vpn_headscale_ip }}` | Headscale VPN server IP |
| `common_headscale_hostname` | `{{ vpn_hostname }}` | Headscale VPN hostname |
| `common_project_base` | `/opt/{{ project_name }}` | Project base directory |
| `common_project_dirs` | configs, data, backups, logs | Subdirectories to create |
| `common_sysctl_settings` | See defaults | Sysctl kernel parameters |
| `common_ntp_servers` | pool.ntp.org | NTP servers |

## Dependencies

None.

## Example

```yaml
- role: common
  tags: [common]
```
