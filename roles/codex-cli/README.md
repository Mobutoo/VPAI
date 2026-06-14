# codex-cli

Install and configure the OpenAI Codex CLI

## Rôle

Rôle Ansible du projet VPAI. Install and configure the OpenAI Codex CLI

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `codex_cli_user`
- `codex_cli_config_dir`
- `codex_cli_npm_prefix`
- `codex_cli_npm_version`
- `codex_cli_credential_storage`
- `codex_cli_default_model`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: codex-cli
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
