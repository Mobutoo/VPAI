# Role: hardening

## Description

Security hardening for the VPS. Configures SSH (custom port, VPN-only binding, key-only auth), Fail2ban, CrowdSec, UFW firewall, unattended-upgrades, and auditd.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `hardening_ssh_port` | `{{ prod_ssh_port }}` | SSH listen port |
| `hardening_ssh_listen_address` | `{{ vpn_headscale_ip }}` | SSH bind address (VPN only) |
| `hardening_ssh_allowed_user` | `{{ prod_user }}` | Allowed SSH user |
| `hardening_fail2ban_bantime` | `3600` | Fail2ban ban duration (seconds) |
| `hardening_fail2ban_maxretry` | `3` | Max failed attempts before ban |
| `hardening_ufw_vpn_network` | `{{ vpn_network_cidr }}` | VPN CIDR for SSH access |
| `hardening_crowdsec_collections` | See defaults | CrowdSec collections to install |

## Dependencies

- `common`

## Example

```yaml
- role: hardening
  tags: [hardening]
```
