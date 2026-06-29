# grocy

Deploy Grocy household management and stock tracking

## Rôle

Rôle Ansible du projet VPAI. Deploy Grocy household management and stock tracking

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `grocy_config_dir`
- `grocy_data_dir`
- `grocy_web_port`
- `grocy_subdomain`
- `caddy_grocy_domain`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: grocy
```

## Tests

```bash
cd roles/grocy && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
