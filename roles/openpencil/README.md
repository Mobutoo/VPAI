# openpencil

Deploy OpenPencil — AI-native open-source design editor

## Rôle

Rôle Ansible du projet VPAI. Deploy OpenPencil — AI-native open-source design editor

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `openpencil_repo`
- `openpencil_version`
- `openpencil_install_dir`
- `openpencil_data_dir`
- `openpencil_port`
- `openpencil_mcp_port`
- `openpencil_service_name`
- `openpencil_user`
- `openpencil_subdomain`
- `openpencil_bun_version`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: openpencil
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
