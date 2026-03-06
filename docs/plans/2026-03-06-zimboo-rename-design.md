# Design — Renommage Seko-Finance → Zimboo

**Date** : 2026-03-06
**Auteur** : Claude Opus 4.6 + Sekoul
**Statut** : Approuvé
**Scope** : Infra Ansible (renommage complet) + DNS OVH (nouveau sous-domaine)

---

## 1. Contexte

Le dashboard financier Next.js déployé sous le nom "Seko-Finance" (sous-domaine `nzimbu`) est renommé en **Zimboo**. La version v1.10.0 est disponible sur GitHub (`Mobutoo/zimboo`). L'image Docker migre vers `ghcr.io/mobutoo/zimboo:v1.10.0`.

Le sous-domaine change de `nzimbu.ewutelo.cloud` vers `zimboo.ewutelo.cloud`.

---

## 2. Décisions

| Décision | Choix | Raison |
|----------|-------|--------|
| Sous-domaine | `zimboo.ewutelo.cloud` | Aligné avec le nom du produit |
| Image Docker | `ghcr.io/mobutoo/zimboo:v1.10.0` | Nouveau repo GitHub, version pinnée |
| Container name | `javisi_zimboo` | Convention projet `{{ project_name }}_<service>` |
| Role Ansible | `roles/zimboo/` | Renomme `roles/seko-finance/` |
| Variables prefix | `zimboo_*` | Remplace `seko_finance_*` |
| DNS | A record via API OVH | Credentials dans vault |
| Firefly III | Inchangé (`lola.ewutelo.cloud`) | Pas dans le scope |

---

## 3. Changements

### 3.1 DNS OVH

Créer un A record `zimboo.ewutelo.cloud` → `137.74.114.167` via l'API OVH (`https://eu.api.ovh.com`).

### 3.2 Role Ansible

**Renommer** `roles/seko-finance/` → `roles/zimboo/`

Fichiers impactés dans le role :
- `defaults/main.yml` : `zimboo_subdomain`, `zimboo_firefly_pat`, `zimboo_llm_model`
- `tasks/main.yml` : paths `/opt/javisi/configs/zimboo/`
- `templates/seko-finance.env.j2` → `zimboo.env.j2` : `NEXT_PUBLIC_APP_NAME=Zimboo`
- `handlers/main.yml` : container `javisi_zimboo`, service `zimboo`
- `meta/main.yml` : `zimboo`
- `molecule/default/` : variables renommées

### 3.3 Inventory

- `main.yml` : `zimboo_subdomain: "zimboo"`, `zimboo_firefly_pat`, etc.
- `versions.yml` : `zimboo_image: "ghcr.io/mobutoo/zimboo:v1.10.0"`
- `docker.yml` : `zimboo_memory_limit`, `zimboo_memory_reservation`, `zimboo_cpu_limit`

### 3.4 Docker Compose

`roles/docker-stack/templates/docker-compose.yml.j2` :
- Service `seko-finance` → `zimboo`
- Container `javisi_seko_finance` → `javisi_zimboo`
- Image `{{ zimboo_image }}`
- Env file `/opt/javisi/configs/zimboo/zimboo.env`

### 3.5 Caddy

- `roles/caddy/defaults/main.yml` : `caddy_zimboo_domain`
- `roles/caddy/templates/Caddyfile.j2` : section renommée, `reverse_proxy zimboo:3000`

### 3.6 Playbook

`playbooks/site.yml` : `role: zimboo`, tag `zimboo`

### 3.7 CI/CD

`.github/workflows/integration.yml` : subdomain loop `"nzimbu"` → `"zimboo"`

### 3.8 Smoke tests + Molecule

~30 fichiers `converge.yml` : `seko_finance_subdomain` → `zimboo_subdomain`

### 3.9 Documentation

- `CLAUDE.md` : stack table, structure repo, sous-domaines
- `docs/TROUBLESHOOTING.md` : références Seko-Finance
- `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`

### 3.10 OpenClaw

- CFO agent `IDENTITY.md.j2` : références dashboard
- Skills finance-personal `SKILL.md.j2` si applicable

---

## 4. Ce qui ne change PAS

- Firefly III (sous-domaine `lola`, role `firefly`, variables `firefly_*`)
- PostgreSQL (database `firefly`, user `firefly`)
- Redis (db2/db3 pour Firefly)
- Réseaux Docker (backend, frontend, egress)
- VPN-only access (Caddy ACL)

---

## 5. Risque

| Risque | Mitigation |
|--------|------------|
| Oubli de référence `seko_finance` | grep exhaustif post-renommage |
| Image v1.10.0 non disponible sur GHCR | Vérifier avant deploy |
| DNS propagation | TTL court (300s) + vérifier avec `dig` |
