# penpot

Deploy Penpot open-source design and prototyping platform

## Rôle

Rôle Ansible du projet VPAI. Deploy Penpot open-source design and prototyping platform

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `penpot_server_name`
- `penpot_server_type`
- `penpot_location`
- `penpot_os_image`
- `penpot_ssh_key_name`
- `penpot_ssh_key_pub_path`
- `penpot_subdomain`
- `penpot_domain`
- `penpot_image_frontend`
- `penpot_image_backend`
- `penpot_image_exporter`
- `penpot_image_valkey`
- … (+18 autres)

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: penpot
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
