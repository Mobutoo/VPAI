# app-scaffold

Base infrastructure for App Factory apps on Hetzner

## Rôle

Rôle Ansible du projet VPAI. Base infrastructure for App Factory apps on Hetzner

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `app_scaffold_ghcr_user`
- `app_scaffold_ghcr_token`
- `app_scaffold_docker_config_dir`
- `app_scaffold_apps_dir`
- `app_scaffold_default_memory_limit`
- `app_scaffold_default_cpu_limit`
- `app_scaffold_frontend_network`
- `app_scaffold_backend_network`
- `app_scaffold_frontend_subnet`
- `app_scaffold_backend_subnet`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: app-scaffold
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
