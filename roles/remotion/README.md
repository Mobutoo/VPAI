# remotion

Deploy the Remotion programmatic video rendering service

## Rôle

Rôle Ansible du projet VPAI. Deploy the Remotion programmatic video rendering service

## Structure

`tasks`, `handlers`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `remotion_install_dir`
- `remotion_data_dir`
- `remotion_version`
- `remotion_port`
- `remotion_memory_limit`
- `remotion_memory_reservation`
- `remotion_cpu_limit`
- `remotion_subdomain`
- `creative_assets_dir`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: remotion
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
