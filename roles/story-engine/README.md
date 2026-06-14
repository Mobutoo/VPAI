# story-engine

Deploy StoryEngine narrative IDE (dedicated host)

## Rôle

Rôle Ansible du projet VPAI. Deploy StoryEngine narrative IDE (dedicated host)

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `story_engine_base_dir`
- `story_engine_config_dir`
- `story_engine_data_dir`
- `story_engine_repo_url`
- `story_engine_repo_branch`
- `story_engine_src_dir`
- `story_engine_ghcr_user`
- `story_engine_ghcr_token`
- `story_engine_domain`
- `story_engine_db_name`
- `story_engine_db_user`
- `story_engine_db_password`
- … (+23 autres)

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: story-engine
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
