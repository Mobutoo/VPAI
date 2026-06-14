# metube

MeTube video downloader (yt-dlp web UI) on Workstation Pi

## Rôle

Rôle Ansible du projet VPAI. MeTube video downloader (yt-dlp web UI) on Workstation Pi

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `metube_install_dir`
- `metube_data_dir`
- `metube_port`
- `metube_memory_limit`
- `metube_memory_reservation`
- `metube_cpu_limit`
- `metube_subdomain`
- `metube_download_dir`
- `metube_output_template`
- `metube_max_quality`
- `metube_cookies_enabled`
- `metube_cookies_dir`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: metube
```

## Tests

```bash
cd roles/metube && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
