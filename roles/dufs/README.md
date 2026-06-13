# dufs

Deploy DUFS — HTTP file server (sharing/WebDAV)

## Rôle

Rôle Ansible du projet VPAI. Deploy DUFS — HTTP file server (sharing/WebDAV)

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `dufs_data_dir`
- `dufs_docker_dir`
- `dufs_port`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags dufs
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
