# workstation-common

Common base configuration for workstation hosts

## Rôle

Rôle Ansible du projet VPAI. Common base configuration for workstation hosts

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `workstation_packages`
- `workstation_hostname`
- `workstation_user`
- `workstation_locale`
- `workstation_timezone`
- `workstation_docker_log_max_size`
- `workstation_docker_log_max_file`
- `workstation_nodejs_major`
- `workstation_claude_code_version`
- `workstation_projects_dir`
- `workstation_base_dir`
- `workstation_base_dirs`
- … (+16 autres)

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: workstation-common
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
