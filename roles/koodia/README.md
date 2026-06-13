# koodia

Deploy Koodia food cockpit (Next.js — Mealie + Grocy + AI)

## Rôle

Rôle Ansible du projet VPAI. Deploy Koodia food cockpit (Next.js — Mealie + Grocy + AI)

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `koodia_config_dir`
- `koodia_data_dir`
- `koodia_port`
- `koodia_llm_model`
- `koodia_subdomain`
- `caddy_koodia_domain`

## Utilisation

```yaml
- hosts: <cible>
  roles:
    - role: koodia
```

## Tests

```bash
cd roles/koodia && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
