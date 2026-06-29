# plane

Deploy Plane project management platform

## Rôle

Rôle Ansible du projet VPAI. Deploy Plane project management platform

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `plane_config_dir`
- `plane_data_dir`
- `plane_web_memory_limit`
- `plane_web_cpu_limit`
- `plane_api_memory_limit`
- `plane_api_cpu_limit`
- `plane_worker_memory_limit`
- `plane_worker_cpu_limit`
- `plane_beat_memory_limit`
- `plane_beat_cpu_limit`
- `plane_admin_memory_limit`
- `plane_admin_cpu_limit`
- … (+10 autres)

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags plane
```

## Tests

```bash
cd roles/plane && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
