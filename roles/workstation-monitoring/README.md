# workstation-monitoring

Deploy node_exporter and monitoring agents on the workstation

## Rôle

Rôle Ansible du projet VPAI. Deploy node_exporter and monitoring agents on the workstation

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `node_exporter_version`
- `node_exporter_port`
- `node_exporter_user`
- `node_exporter_binary_dir`
- `node_exporter_textfile_dir`
- `workstation_metrics_port`
- `workstation_metrics_interval`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: workstation-monitoring
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
