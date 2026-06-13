# comfyui

Deploy the ComfyUI image/video generation stack (local build)

## Rôle

Rôle Ansible du projet VPAI. Deploy the ComfyUI image/video generation stack (local build)

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `comfyui_install_dir`
- `comfyui_data_dir`
- `comfyui_version`
- `comfyui_port`
- `comfyui_memory_limit`
- `comfyui_memory_reservation`
- `comfyui_cpu_limit`
- `comfyui_subdomain`
- `comfyui_models`
- `comfyui_custom_nodes`
- `comfyui_fal_key`
- `comfyui_gemini_key`
- … (+12 autres)

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: comfyui
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
