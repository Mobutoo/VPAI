# grapesjs

Deploy GrapesJS web page builder

## Rôle

Rôle Ansible du projet VPAI. Deploy GrapesJS web page builder

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `grapesjs_docker_dir`
- `grapesjs_port`
- `grapesjs_subdomain`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags grapesjs
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
