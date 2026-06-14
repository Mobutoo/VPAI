# content-factory-provision

Provision NocoDB tables, Qdrant collection, and seed data for Content Factory

## Rôle

Rôle Ansible du projet VPAI. Provision NocoDB tables, Qdrant collection, and seed data for Content Factory

## Structure

`tasks`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `content_factory_config_dir`
- `content_factory_nocodb_base_url`
- `content_factory_nocodb_base_name`
- `content_factory_qdrant_base_url`
- `content_factory_qdrant_collection`
- `content_factory_qdrant_vector_size`
- `content_factory_qdrant_distance`
- `content_factory_litellm_base_url`
- `content_factory_embedding_model`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags content-factory-provision
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
