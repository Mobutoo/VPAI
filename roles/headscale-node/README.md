# Role: headscale-node

## Description

Installs the Tailscale client and registers the node with the Headscale control server. Saves the assigned Tailscale IP as a cached fact for use by other roles (SSH binding, VPN ACLs).

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `headscale_login_server` | `{{ vpn_headscale_url }}` | Headscale server URL |
| `headscale_auth_key_value` | `{{ headscale_auth_key }}` | Pre-authentication key |
| `headscale_vpn_ip` | `{{ vpn_headscale_ip }}` | VPN server IP for connectivity check |
| `headscale_hostname` | `{{ prod_hostname }}` | Hostname to register |
| `headscale_advertise_routes` | `[]` | Routes to advertise |
| `headscale_accept_routes` | `true` | Accept routes from other nodes |

## Dependencies

- `common`

## Example

```yaml
- role: headscale-node
  tags: [headscale-node]
```
