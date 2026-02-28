---
wave: 2
depends_on: ["01-01a"]
files_modified:
  - roles/caddy/templates/Caddyfile.j2
  - playbooks/site.yml
autonomous: true
---

# Plan 01-01b: Caddy Reverse Proxy & Playbook Integration

**Goal**: Configure Caddy reverse proxy for VPN-only access to Plane UI with public webhook endpoint exception, and integrate role into site.yml playbook.

**Requirements**: INFRA-04

## Context

Plane requires two distinct access patterns:
1. **VPN-only UI access**: work.ewutelo.cloud main interface accessible only via Headscale VPN
2. **Public webhook endpoint**: work.ewutelo.cloud/webhooks/plane must be publicly accessible for n8n webhook delivery

This creates a critical ordering requirement in Caddy configuration: the public webhook handle MUST appear BEFORE the VPN-only matcher, otherwise webhooks will return 403.

**Critical constraints:**
- Caddy VPN ACL: ALL `not client_ip` rules must include BOTH CIDRs: `{{ caddy_vpn_cidr }}` AND `{{ caddy_docker_frontend_cidr }}`
- Handle ordering: Public exceptions BEFORE VPN blocks (Caddy processes handles sequentially)
- HTTP/3 QUIC traffic has source IP replaced by Docker gateway (172.20.1.1) - requires dual-CIDR matcher

## Tasks

<task id="01-01b-T1" name="configure-caddy-vpn-access">
Add Plane subdomain to roles/caddy/templates/Caddyfile.j2:

```caddyfile
work.{{ domain_name }} {
    # CRITICAL: Public webhook endpoint for n8n integration (INFRA-04)
    # Must be BEFORE VPN-only block to avoid 403 on webhook delivery
    handle /webhooks/plane {
        reverse_proxy n8n:5678
    }

    # VPN-only access with 2-CIDR rule (CRITICAL: both VPN and Docker frontend)
    @blocked_plane {
        not client_ip {{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }}
    }
    handle @blocked_plane {
        import vpn_error_page
    }

    # Plane web UI (VPN-only)
    handle {
        reverse_proxy plane-web:3000
    }

    import tls_config
}
```

CRITICAL ORDERING: The /webhooks/plane handle MUST appear BEFORE the @blocked_plane matcher. Caddy processes handles in order - if VPN block comes first, webhooks will return 403.

The @blocked_plane matcher MUST include BOTH CIDRs (VPN client range + Docker frontend gateway) to avoid HTTP/3 QUIC 403 errors (documented in docs/GUIDE-CADDY-VPN-ONLY.md).

Use heredoc syntax in Caddyfile handler to ensure HTTP status code on same line as heredoc marker.
</task>

<task id="01-01b-T2" name="update-playbook-site">
Add plane role to playbooks/site.yml in Phase 3 (Applications):

```yaml
# Phase 3: Applications (configs only)
- name: Deploy Plane configuration
  hosts: prod
  roles:
    - role: plane
      tags: [plane]
```

Add after nocodb role, before Phase 4 (Observability).
</task>

## Verification Criteria

After execution:

1. **Caddy configuration correct**:
   - Caddyfile.j2 has `work.{{ domain_name }}` block
   - Public /webhooks/plane handle appears FIRST (before VPN matcher)
   - /webhooks/plane proxies to n8n:5678
   - @blocked_plane matcher includes BOTH `{{ caddy_vpn_cidr }}` and `{{ caddy_docker_frontend_cidr }}` (2 CIDRs)
   - Default handle reverse proxies to plane-web:3000

2. **Playbook integration**:
   - playbooks/site.yml includes plane role in Phase 3 with [plane] tag
   - Role appears after nocodb, before monitoring

3. **Code quality**:
   - All variables use Jinja2 syntax ({{ domain_name }}, {{ caddy_vpn_cidr }}, etc.)
   - Handle ordering documented in comments
   - Heredoc syntax used correctly for error pages

## Must-Haves

Derived from phase goal: "Plane UI accessible at work.ewutelo.cloud from VPN, public webhook endpoint functional"

1. **VPN-only access enforced**: Plane UI returns 403 from public internet, 200 from VPN clients
2. **Webhook endpoint public**: /webhooks/plane accessible without VPN (returns 200 or appropriate n8n response)
3. **Handle ordering correct**: Public webhook handle appears before VPN matcher in Caddyfile
4. **Dual-CIDR matcher present**: @blocked_plane includes both VPN and Docker frontend CIDRs
5. **Playbook integration complete**: make deploy-role ROLE=plane ENV=prod executes without errors
