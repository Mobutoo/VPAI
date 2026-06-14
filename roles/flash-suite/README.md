# flash-suite

Deploy Flash Suite (unified shell with gamification engine)

## Rôle

Rôle Ansible du projet VPAI. Deploy Flash Suite (unified shell with gamification engine)

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `flash_suite_base_dir`
- `flash_suite_config_dir`
- `flash_suite_docker_dir`
- `flash_suite_shell_port`
- `flash_suite_postgres_port`
- `flash_suite_postgres_user`
- `flash_suite_postgres_db`
- `flash_suite_event_cron_interval`
- `flash_suite_compose_project`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags flash-suite
```

## Tests

```bash
cd roles/flash-suite && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
