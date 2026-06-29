# kitsu

Deploy CGWire Kitsu production tracker

## Rôle

Rôle Ansible du projet VPAI. Deploy CGWire Kitsu production tracker

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `kitsu_config_dir`
- `kitsu_data_dir`
- `kitsu_previews_dir`
- `kitsu_memory_limit`
- `kitsu_memory_reservation`
- `kitsu_cpu_limit`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags kitsu
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
