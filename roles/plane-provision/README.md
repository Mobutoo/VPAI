# plane-provision

Provision Plane workspaces and projects post-deploy

## Rôle

Rôle Ansible du projet VPAI. Provision Plane workspaces and projects post-deploy

## Structure

`tasks`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `plane_workspace_slug`
- `plane_workspace_name`
- `plane_admin_email`
- `plane_concierge_email`
- `plane_concierge_password`
- `plane_agent_names`
- `plane_custom_fields`
- `plane_api_url`
- `plane_api_health_retries`
- `plane_api_health_delay`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags plane-provision
```

## Tests

```bash
cd roles/plane-provision && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
