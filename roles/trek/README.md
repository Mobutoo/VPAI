# trek

Deploy TREK self-hosted travel planner (public, native auth)

## Rôle

Rôle Ansible du projet VPAI. Deploy TREK self-hosted travel planner (public, native auth)

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `trek_config_dir`
- `trek_data_dir`
- `trek_uploads_dir`
- `trek_public_dir`
- `trek_brand_marker`
- `trek_branding_files`
- `trek_web_port`
- `trek_subdomain`
- `caddy_trek_domain`
- `trek_admin_email`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags trek
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
