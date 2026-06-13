# carbone

Carbone ODT→PDF/DOCX template engine for MOP machinery

## Rôle

Rôle Ansible du projet VPAI. Carbone ODT→PDF/DOCX template engine for MOP machinery

## Structure

`tasks`, `handlers`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `carbone_config_dir`
- `carbone_data_dir`
- `carbone_template_dir`
- `carbone_render_dir`
- `carbone_memory_limit`
- `carbone_memory_reservation`
- `carbone_cpu_limit`
- `carbone_container_url`
- `carbone_host_url`
- `carbone_source_template`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags carbone
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
