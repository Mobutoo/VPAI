# typebot

Typebot chatbot builder+viewer for MOP form authoring

## Rôle

Rôle Ansible du projet VPAI. Typebot chatbot builder+viewer for MOP form authoring

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `typebot_config_dir`
- `typebot_data_dir`
- `typebot_db_name`
- `typebot_db_user`
- `typebot_builder_subdomain`
- `typebot_viewer_subdomain`
- `typebot_builder_url`
- `typebot_viewer_url`
- `mailhog_subdomain`
- `mailhog_url`
- `typebot_memory_limit`
- `typebot_memory_reservation`
- … (+4 autres)

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags typebot
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
