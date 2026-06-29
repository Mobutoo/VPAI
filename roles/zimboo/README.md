# zimboo

Deploy Zimboo Dashboard (Next.js financial cockpit)

## Rôle

Rôle Ansible du projet VPAI. Deploy Zimboo Dashboard (Next.js financial cockpit)

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `zimboo_config_dir`
- `zimboo_port`
- `zimboo_llm_model`
- `zimboo_subdomain`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: zimboo
```

## Tests

```bash
cd roles/zimboo && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
