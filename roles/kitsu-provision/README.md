# kitsu-provision

Initialize Zou database, create admin, and provision Kitsu project structure

## Rôle

Rôle Ansible du projet VPAI. Initialize Zou database, create admin, and provision Kitsu project structure

## Structure

`tasks`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `kitsu_provision_config_dir`
- `kitsu_admin_email`
- `kitsu_admin_password`
- `kitsu_secret_key`
- `kitsu_container_name`
- `kitsu_health_retries`
- `kitsu_health_delay`
- `kitsu_project_name`
- `kitsu_episode_name`
- `kitsu_sequences`
- `kitsu_task_types`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags kitsu-provision
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
