# obsidian-collector-pi

Deploy Raspberry Pi collectors syncing to CouchDB/Obsidian

## Rôle

Rôle Ansible du projet VPAI. Deploy Raspberry Pi collectors syncing to CouchDB/Obsidian

## Structure

`tasks`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `obsidian_pi_couchdb_url`
- `obsidian_pi_couchdb_user`
- `obsidian_pi_couchdb_password`
- `obsidian_pi_couchdb_db`
- `obsidian_pi_collector_cron_hour`
- `obsidian_pi_collector_cron_minute`
- `obsidian_pi_comfyui_output`
- `obsidian_pi_remotion_output`
- `obsidian_pi_script_dir`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: obsidian-collector-pi
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
