# Role: caddy

## Description

Caddy reverse proxy with automatic TLS, security headers, VPN-only ACL for admin UIs, rate limiting, and health endpoint.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `caddy_domain` | `{{ domain_name }}` | Public domain |
| `caddy_admin_domain` | `admin.{{ domain_name }}` | Admin subdomain (VPN-only) |
| `caddy_vpn_cidr` | `{{ vpn_network_cidr }}` | VPN CIDR for ACL |

## Dependencies

- `docker`

## Example

```yaml
- role: caddy
  tags: [caddy]
```
