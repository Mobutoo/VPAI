# gotenberg

Gotenberg HTML/CSS→PDF service for MOP machinery

## Rôle

Rôle Ansible du projet VPAI. Gotenberg HTML/CSS→PDF service for MOP machinery

## Structure

`tasks`, `handlers`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `gotenberg_config_dir`
- `gotenberg_memory_limit`
- `gotenberg_memory_reservation`
- `gotenberg_cpu_limit`
- `gotenberg_chromium_max_conversions`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags gotenberg
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
