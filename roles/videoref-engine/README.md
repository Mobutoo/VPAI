# videoref-engine

Video reference analysis pipeline + ComfyUI workflow generator on Workstation Pi

## Rôle

Rôle Ansible du projet VPAI. Video reference analysis pipeline + ComfyUI workflow generator on Workstation Pi

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `videoref_install_dir`
- `videoref_data_dir`
- `videoref_version`
- `videoref_port`
- `videoref_memory_limit`
- `videoref_memory_reservation`
- `videoref_cpu_limit`
- `videoref_subdomain`
- `videoref_watch_dir`
- `videoref_output_dir`
- `videoref_comfyui_workflows_dir`
- `videoref_litellm_url`
- … (+8 autres)

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: videoref-engine
```

## Tests

```bash
cd roles/videoref-engine && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
