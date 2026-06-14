# obsidian

Deploy CouchDB and Obsidian vault sync

## Rôle

Rôle Ansible du projet VPAI. Deploy CouchDB and Obsidian vault sync

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `couchdb_image`
- `couchdb_port`
- `couchdb_data_dir`
- `couchdb_config_dir`
- `couchdb_scripts_dir`
- `obsidian_vault_dir`
- `couchdb_db_name`
- `couchdb_admin_user`
- `couchdb_admin_password`
- `couchdb_obsidian_user`
- `couchdb_obsidian_password`
- `couchdb_memory_limit`
- … (+7 autres)

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: obsidian
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
