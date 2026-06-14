# obsidian-collector

Deploy Sese-AI collectors syncing to CouchDB/Obsidian

## Rôle

Rôle Ansible du projet VPAI. Deploy Sese-AI collectors syncing to CouchDB/Obsidian

## Structure

`tasks`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `obsidian_collector_couchdb_url`
- `obsidian_collector_couchdb_user`
- `obsidian_collector_couchdb_password`
- `obsidian_collector_couchdb_db`
- `obsidian_collector_cron_hour`
- `obsidian_collector_cron_minute`
- `obsidian_collector_openclaw_system`
- `obsidian_collector_openclaw_sessions`
- `obsidian_collector_n8n_backup_dir`
- `obsidian_collector_docs_dir`
- `obsidian_collector_script_dir`
- `obsidian_collector_max_session_messages`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags obsidian-collector
```

## Tests

```bash
cd roles/obsidian-collector && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
