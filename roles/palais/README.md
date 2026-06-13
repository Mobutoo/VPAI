# palais

Deploy Palais — SvelteKit app with Claude MCP gateway

## Rôle

Rôle Ansible du projet VPAI. Deploy Palais — SvelteKit app with Claude MCP gateway

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `vars`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `palais_config_dir`
- `palais_data_dir`
- `palais_app_dir`
- `palais_port`
- `palais_subdomain`
- `palais_db_name`
- `palais_db_user`
- `palais_db_password`
- `palais_qdrant_collection`
- `palais_qdrant_vector_size`
- `palais_api_key`
- `palais_admin_password`
- … (+9 autres)

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags palais
```

## Tests

```bash
cd roles/palais && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
