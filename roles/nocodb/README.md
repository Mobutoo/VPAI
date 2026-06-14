# nocodb

NocoDB project management — Airtable alternative on PostgreSQL

## Rôle

Rôle Ansible du projet VPAI. NocoDB project management — Airtable alternative on PostgreSQL

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `nocodb_config_dir`
- `nocodb_data_dir`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags nocodb
```

## Tests

```bash
cd roles/nocodb && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
