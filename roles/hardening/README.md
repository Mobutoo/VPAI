# Role: hardening

## Description

Security hardening for the VPS. Configures SSH (custom port, key-only auth, 0.0.0.0 bind), Fail2ban, CrowdSec, UFW firewall (VPN-only SSH access control), unattended-upgrades, and auditd.

**Architecture**: sshd always listens on `0.0.0.0` to prevent lockout. Access control is enforced at the UFW firewall level — when VPN is ready, UFW restricts SSH to the VPN network CIDR only.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `hardening_ssh_port` | `{{ prod_ssh_port }}` | SSH listen port |
| `hardening_ssh_allowed_user` | `{{ prod_user }}` | Allowed SSH user |
| `hardening_ssh_force_open` | `true` | UFW allows SSH from anywhere (set false for VPN-only) |
| `hardening_fail2ban_bantime` | `3600` | Fail2ban ban duration (seconds) |
| `hardening_fail2ban_maxretry` | `3` | Max failed attempts before ban |
| `hardening_ufw_vpn_network` | `{{ vpn_network_cidr }}` | VPN CIDR for SSH UFW restriction |
| `hardening_crowdsec_collections` | See defaults | CrowdSec collections to install |

## Dependencies

- `common`

## Example

```yaml
- role: hardening
  tags: [hardening]
```
