# netbox

NetBox DCIM déployé via Docker Compose pour MediaHall

## Rôle

Rôle Ansible du projet VPAI. NetBox DCIM déployé via Docker Compose pour MediaHall

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `netbox_base_dir`
- `netbox_config_dir`
- `netbox_media_dir`
- `netbox_reports_dir`
- `netbox_scripts_dir`
- `netbox_port`
- `netbox_network_name`
- `netbox_network_subnet`
- `netbox_db_name`
- `netbox_db_user`
- `netbox_db_host`
- `netbox_db_port`
- … (+18 autres)

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: netbox
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
