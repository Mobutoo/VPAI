# opencut

Deploy OpenCut video editor (PostgreSQL-backed)

## Rôle

Rôle Ansible du projet VPAI. Deploy OpenCut video editor (PostgreSQL-backed)

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `opencut_install_dir`
- `opencut_data_dir`
- `opencut_version`
- `opencut_port`
- `opencut_memory_limit`
- `opencut_memory_reservation`
- `opencut_cpu_limit`
- `opencut_subdomain`
- `opencut_db_name`
- `opencut_db_user`
- `opencut_redis_port`
- `opencut_autostart`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: opencut
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
