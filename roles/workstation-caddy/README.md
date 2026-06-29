# workstation-caddy

Configure the Caddy reverse proxy on the workstation (xcaddy build)

## Rôle

Rôle Ansible du projet VPAI. Configure the Caddy reverse proxy on the workstation (xcaddy build)

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `workstation_caddy_config_dir`
- `workstation_caddy_data_dir`
- `workstation_caddy_version`
- `workstation_go_official_version`
- `workstation_xcaddy_version`
- `workstation_xcaddy_gopath`
- `workstation_xcaddy_gobin`
- `workstation_oc_domain`
- `workstation_caddy_admin_port`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: workstation-caddy
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
