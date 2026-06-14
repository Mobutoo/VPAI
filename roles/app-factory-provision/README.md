# app-factory-provision

Provision NocoDB tables and Qdrant collections for App Factory

## Rôle

Rôle Ansible du projet VPAI. Provision NocoDB tables and Qdrant collections for App Factory

## Structure

`tasks`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `app_factory_config_dir`
- `app_factory_nocodb_base_url`
- `app_factory_nocodb_base_name`
- `app_factory_qdrant_base_url`
- `app_factory_qdrant_rex_collection`
- `app_factory_qdrant_patterns_collection`
- `app_factory_qdrant_vector_size`
- `app_factory_qdrant_distance`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags app-factory-provision
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
