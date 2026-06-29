# mealie

Deploy Mealie recipe manager

## Rôle

Rôle Ansible du projet VPAI. Deploy Mealie recipe manager

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `mealie_config_dir`
- `mealie_data_dir`
- `mealie_web_port`
- `mealie_db_name`
- `mealie_db_user`
- `mealie_subdomain`
- `caddy_mealie_domain`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: mealie
```

## Tests

```bash
cd roles/mealie && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
