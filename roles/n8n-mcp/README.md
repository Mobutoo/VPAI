# n8n-mcp

Deploy the n8n MCP server (Model Context Protocol bridge for n8n)

## Rôle

Rôle Ansible du projet VPAI. Deploy the n8n MCP server (Model Context Protocol bridge for n8n)

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `n8n_mcp_user`
- `n8n_mcp_image`
- `n8n_mcp_image_version`
- `n8n_mcp_port`
- `n8n_mcp_log_level`
- `n8n_mcp_auth_token`
- `n8n_mcp_memory_limit`
- `n8n_mcp_cpu_limit`
- `n8n_mcp_management_enabled`
- `n8n_mcp_api_url`
- `n8n_mcp_api_key`
- `n8n_mcp_extra_host`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: n8n-mcp
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
