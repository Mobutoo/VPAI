# msg2md

msg2md — Outlook MSG to markdown sidecar (FastAPI)

## Rôle

Rôle Ansible du projet VPAI. msg2md — Outlook MSG to markdown sidecar (FastAPI)

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `msg2md_port`
- `msg2md_memory_limit`
- `msg2md_cpu_limit`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags msg2md
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
