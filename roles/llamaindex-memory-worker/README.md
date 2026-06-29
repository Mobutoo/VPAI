# llamaindex-memory-worker

Deploy the LlamaIndex memory worker (Qdrant-backed RAG)

## Rôle

Rôle Ansible du projet VPAI. Deploy the LlamaIndex memory worker (Qdrant-backed RAG)

## Structure

`tasks`, `handlers`, `templates`, `files`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `memory_worker_service_name`
- `memory_worker_timer_name`
- `memory_worker_user`
- `memory_worker_install_dir`
- `memory_worker_config_dir`
- `memory_worker_data_dir`
- `memory_worker_state_dir`
- `memory_worker_spool_dir`
- `memory_worker_log_dir`
- `memory_worker_venv_dir`
- `memory_worker_hf_home`
- `memory_worker_config_file`
- … (+67 autres)

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: llamaindex-memory-worker
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
