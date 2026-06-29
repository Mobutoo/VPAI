# firefly

Deploy Firefly III personal finance engine

## Rôle

Rôle Ansible du projet VPAI. Deploy Firefly III personal finance engine

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `firefly_config_dir`
- `firefly_data_dir`
- `firefly_web_port`
- `firefly_db_name`
- `firefly_db_user`
- `firefly_redis_db`
- `firefly_redis_cache_db`
- `firefly_subdomain`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: firefly
```

## Tests

```bash
cd roles/firefly && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
