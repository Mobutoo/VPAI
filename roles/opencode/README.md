# opencode

Install and configure the OpenCode CLI

## Rôle

Rôle Ansible du projet VPAI. Install and configure the OpenCode CLI

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `opencode_port`
- `opencode_install_dir`
- `opencode_workspace_dir`
- `opencode_config_dir`
- `opencode_user`
- `opencode_litellm_base_url`
- `opencode_litellm_api_key`
- `opencode_default_model`
- `opencode_npm_version`
- `opencode_service_name`
- `opencode_npm_prefix`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: opencode
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
