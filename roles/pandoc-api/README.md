# pandoc-api

Pandoc HTTP microservice — HTML to DOCX conversion

## Rôle

Rôle Ansible du projet VPAI. Pandoc HTTP microservice — HTML to DOCX conversion

## Structure

`tasks`, `templates`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `pandoc_api_port`
- `pandoc_api_docker_dir`
- `pandoc_api_container_name`
- `pandoc_api_network`
- `pandoc_api_memory_limit`
- `pandoc_api_memory_reservation`
- `pandoc_api_cpu_limit`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags pandoc-api
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
