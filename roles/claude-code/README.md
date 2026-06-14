# claude-code

Install and configure the Claude Code CLI

## Rôle

Rôle Ansible du projet VPAI. Install and configure the Claude Code CLI

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `claude_code_user`
- `claude_code_config_dir`
- `claude_code_npm_prefix`
- `claude_code_npm_version`
- `claude_code_auth_mode`
- `claude_code_default_model`
- `claude_code_mcp_context7_enabled`
- `claude_code_mcp_context7_version`
- `claude_code_mcp_filesystem_enabled`
- `claude_code_mcp_filesystem_workspace`
- `claude_code_mcp_n8n_enabled`
- `claude_code_mcp_n8n_url`
- … (+15 autres)

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: claude-code
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
