# n8n-provision

Provisionne le compte owner n8n via API après docker-stack

## Rôle

Rôle Ansible du projet VPAI. Provisionne le compte owner n8n via API après docker-stack

## Structure

`tasks`, `templates`, `files`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `memory_bot_webhook_url`
- `memory_bot_commands`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags n8n-provision
```

## Tests

```bash
cd roles/n8n-provision && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
