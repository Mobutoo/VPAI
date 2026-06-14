# mop-templates

MOP (Method of Procedure) template distribution and jinja2-cli installation

## Rôle

Rôle Ansible du projet VPAI. MOP (Method of Procedure) template distribution and jinja2-cli installation

## Structure

`tasks`, `templates`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `mop_data_dir`
- `mop_templates_dir`
- `mop_pdf_dir`
- `mop_docx_dir`
- `mop_index_dir`
- `mop_dead_letter_dir`
- `mop_scripts_dir`
- `mop_cli_bin_dir`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags mop-templates
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
