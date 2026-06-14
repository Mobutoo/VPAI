# gemini-cli

Install and configure the Google Gemini CLI

## Rôle

Rôle Ansible du projet VPAI. Install and configure the Google Gemini CLI

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `gemini_cli_user`
- `gemini_cli_config_dir`
- `gemini_cli_npm_prefix`
- `gemini_cli_npm_version`
- `gemini_cli_api_key`
- `gemini_cli_default_model`
- `gemini_cli_sandbox_enabled`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: gemini-cli
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
