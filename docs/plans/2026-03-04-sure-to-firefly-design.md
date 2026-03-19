# Design — Remplacement Sure → Firefly III + Seko-Finance Dashboard

**Date** : 2026-03-04
**Auteur** : Claude Opus 4.6 + Sekoul
**Statut** : Approuvé
**Scope** : Infra Ansible uniquement (le code Next.js du dashboard vit dans un repo séparé)

---

## 1. Contexte

Sure (fork Maybe Finance) est déployé sur Sese-AI (OVH VPS) comme 2 containers (sure-web Rails + sure-worker Sidekiq). Il est en **crash-loop connu** sur CX22 preprod (REX-76/77) et n'a jamais fonctionné de manière stable.

Le remplacement par **Firefly III** (moteur comptable) + **Seko-Finance Dashboard** (cockpit visuel Next.js + IA) apporte une stack plus mature et mieux adaptée au besoin.

### Documents de référence

- `D:\Erwin\Downloads\PRD_1.md` — PRD complet Seko-Finance (vision, fonctionnalités, design system)
- `D:\Erwin\Downloads\README_1.md` — README du repo dashboard

---

## 2. Décisions

| Décision | Choix | Raison |
|----------|-------|--------|
| Serveur | Sese-AI (OVH VPS) | Accès direct LiteLLM, PG, Redis sur le réseau backend |
| Base de données | PostgreSQL partagé | Convention VPAI : un seul PG, password unique partagé |
| Sous-domaine dashboard | `nzimbu` | Réutilise le slot DNS existant de Sure |
| Sous-domaine Firefly III | `lola` | Nouveau sous-domaine, créé via API OVH |
| Accès | VPN-only (les deux) | Données financières personnelles |
| Code dashboard | Image Docker pré-buildée (GHCR) | Repo séparé, séparation des concerns |
| Scope | Infra Ansible uniquement | Le code Next.js est hors scope |

---

## 3. Architecture

```
                    VPN-only (Caddy ACL)
                           │
          ┌────────────────┼────────────────┐
          │                │                │
  nzimbu.ewutelo.cloud   lola.ewutelo.cloud
  (Dashboard Next.js)    (Firefly III Admin)
          │                │
          ▼                ▼
  ┌──────────────┐  ┌──────────────┐
  │ seko-finance │  │  firefly-iii │
  │  (port 3000) │  │  (port 8080) │
  │  Next.js 15  │  │  Laravel/PHP │
  └──────┬───────┘  └──────┬───────┘
         │                 │
         │  /api/firefly/* │
         └────────┬────────┘
                  │
         ┌────────┴────────┐
         │   backend net   │
         │  (172.20.2.0/24)│
         └────────┬────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
┌───┴───┐   ┌────┴────┐   ┌────┴────┐
│  PG   │   │  Redis  │   │ LiteLLM │
│shared │   │ shared  │   │ (chat)  │
└───────┘   └─────────┘   └─────────┘
```

---

## 4. Containers

| Container | Image | Réseaux | Port | Mémoire (prod/preprod) |
|-----------|-------|---------|------|----------------------|
| `firefly-iii` | `fireflyiii/core:<pinned>` | backend, frontend | 8080 | 512M / 256M |
| `seko-finance` | `ghcr.io/mobutoo/seko-finance:<pinned>` | backend, frontend, egress | 3000 | 384M / 256M |

### Justification réseaux

- **firefly-iii** : `backend` (accès PG/Redis) + `frontend` (exposé via Caddy sur `lola`)
- **seko-finance** : `backend` (proxy API vers firefly-iii) + `frontend` (exposé via Caddy sur `nzimbu`) + `egress` (appels LiteLLM, APIs externes optionnelles)

---

## 5. Base de données

### Supprimer

- DB `sure_production`, user `sure`

### Créer

- DB `firefly`, user `firefly`
- Password : `{{ postgresql_password }}` (convention partagée VPAI)
- Extensions : aucune requise par Firefly III sur PostgreSQL

### Dans `roles/postgresql/defaults/main.yml`

```yaml
# Remplacer le bloc sure_production par :
- name: firefly
  user: firefly
  extensions: []
```

---

## 6. Sous-domaines & DNS

| Service | Sous-domaine | Variable | DNS |
|---------|-------------|----------|-----|
| Dashboard | `nzimbu.ewutelo.cloud` | `seko_finance_subdomain: nzimbu` | Existant (ex-Sure) |
| Firefly III | `lola.ewutelo.cloud` | `firefly_subdomain: lola` | **Nouveau** — créer via API OVH |

### DNS OVH

Ajouter un enregistrement A `lola` pointant vers l'IP du VPS dans le playbook de provisioning ou via une tâche dédiée dans le role `firefly`.

---

## 7. Roles Ansible

### 7.1 — Supprimer `roles/sure/` (5 fichiers)

```
roles/sure/
├── tasks/main.yml
├── defaults/main.yml
├── templates/sure.env.j2
├── handlers/main.yml
└── meta/main.yml
```

### 7.2 — Créer `roles/firefly/`

```
roles/firefly/
├── tasks/main.yml          # Crée dirs, déploie env file, Dockerfile optionnel
├── defaults/main.yml       # Variables avec defaults
├── templates/firefly.env.j2  # Variables d'environnement Laravel
├── handlers/main.yml       # Restart handler (state: present, recreate: always)
├── meta/main.yml           # dependencies: []
└── molecule/default/
    ├── converge.yml
    └── molecule.yml
```

### 7.3 — Créer `roles/seko-finance/`

```
roles/seko-finance/
├── tasks/main.yml
├── defaults/main.yml
├── templates/seko-finance.env.j2
├── handlers/main.yml
├── meta/main.yml
└── molecule/default/
    ├── converge.yml
    └── molecule.yml
```

---

## 8. Variables d'environnement

### firefly.env.j2

```env
APP_ENV=production
APP_KEY={{ vault_firefly_app_key }}
APP_URL=https://{{ firefly_subdomain }}.{{ domain_name }}
TRUSTED_PROXIES=**
LOG_CHANNEL=stdout
APP_LOG_LEVEL=warning

DB_CONNECTION=pgsql
DB_HOST=postgresql
DB_PORT=5432
DB_DATABASE=firefly
DB_USERNAME=firefly
DB_PASSWORD={{ postgresql_password }}

CACHE_DRIVER=redis
SESSION_DRIVER=redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD={{ redis_password }}
REDIS_DB=2
REDIS_CACHE_DB=3

TZ={{ timezone }}
DEFAULT_LANGUAGE=fr_FR
DEFAULT_LOCALE=fr_FR
```

### seko-finance.env.j2

```env
NODE_ENV=production
FIREFLY_URL=http://firefly-iii:8080
FIREFLY_PAT={{ vault_firefly_pat }}
LITELLM_URL=http://litellm:4000
LITELLM_KEY={{ litellm_master_key }}
LLM_MODEL={{ seko_finance_llm_model | default('deepseek-v3-free') }}
NEXT_PUBLIC_APP_NAME=Seko-Finance
NEXT_PUBLIC_CURRENCY=EUR
TZ={{ timezone }}
```

---

## 9. Secrets Vault

### Supprimer

- `vault_sure_secret_key_base`
- `vault_sure_db_password`
- `vault_sure_api_key`

### Ajouter

- `vault_firefly_app_key` — Générer : `php artisan key:generate --show` ou `echo "base64:$(openssl rand -base64 32)"`
- `vault_firefly_pat` — Créer après premier démarrage de Firefly III, via l'UI admin sur `lola`

---

## 10. Caddy Configuration

### Supprimer (Caddyfile.j2)

Bloc `{{ caddy_sure_domain }}` (lignes 249-264)

### Ajouter

```caddyfile
{% if firefly_subdomain | default('') | length > 0 %}
{{ caddy_firefly_domain }} {
    import vpn_only
    import vpn_error_page

    reverse_proxy firefly-iii:{{ firefly_web_port | default(8080) }}

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        -Server
    }
}
{% endif %}

{% if seko_finance_subdomain | default('') | length > 0 %}
{{ caddy_seko_finance_domain }} {
    import vpn_only
    import vpn_error_page

    reverse_proxy seko-finance:{{ seko_finance_port | default(3000) }}

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        -Server
    }
}
{% endif %}
```

### Caddy defaults

```yaml
# Remplacer :
# caddy_sure_domain: "{{ sure_subdomain | default('nzimbu') }}.{{ domain_name }}"
# Par :
caddy_firefly_domain: "{{ firefly_subdomain | default('lola') }}.{{ domain_name }}"
caddy_seko_finance_domain: "{{ seko_finance_subdomain | default('nzimbu') }}.{{ domain_name }}"
```

---

## 11. Docker Compose (Phase B)

### Supprimer

Blocs `sure-web` et `sure-worker` dans `docker-compose.yml.j2`

### Ajouter

```yaml
  firefly-iii:
    image: {{ firefly_image }}
    container_name: {{ project_name }}_firefly
    env_file: /opt/{{ project_name }}/configs/firefly/firefly.env
    volumes:
      - /opt/{{ project_name }}/data/firefly/upload:/var/www/html/storage/upload
    networks:
      - backend
      - frontend
    cap_drop:
      - ALL
    cap_add:
      - DAC_OVERRIDE
      - FOWNER
      - SETUID
      - SETGID
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://127.0.0.1:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: {{ firefly_memory_limit }}
          cpus: "{{ firefly_cpu_limit }}"
        reservations:
          memory: {{ firefly_memory_reservation }}
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  seko-finance:
    image: {{ seko_finance_image }}
    container_name: {{ project_name }}_seko_finance
    env_file: /opt/{{ project_name }}/configs/seko-finance/seko-finance.env
    networks:
      - backend
      - frontend
      - egress
    cap_drop:
      - ALL
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: {{ seko_finance_memory_limit }}
          cpus: "{{ seko_finance_cpu_limit }}"
        reservations:
          memory: {{ seko_finance_memory_reservation }}
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 12. Smoke Tests

### Supprimer

Tous les blocs `{% if sure_subdomain %}` dans `smoke-test.sh.j2`

### Ajouter

```bash
{% if firefly_subdomain | default('') | length > 0 %}
FIREFLY_URL="https://{{ firefly_subdomain }}.{{ domain_name }}"
{% endif %}
{% if seko_finance_subdomain | default('') | length > 0 %}
SEKO_FINANCE_URL="https://{{ seko_finance_subdomain }}.{{ domain_name }}"
{% endif %}

# Container checks
{% if firefly_subdomain | default('') | length > 0 %}
check_container "Firefly III" "firefly"
check_container_health "Firefly III" "firefly"
{% endif %}
{% if seko_finance_subdomain | default('') | length > 0 %}
check_container "Seko-Finance" "seko_finance"
check_container_health "Seko-Finance" "seko_finance"
{% endif %}

# Health checks (VPN-only, via curl --resolve)
{% if firefly_subdomain | default('') | length > 0 %}
check_internal_health "Firefly III" "${FIREFLY_URL}/health" "200"
{% endif %}
{% if seko_finance_subdomain | default('') | length > 0 %}
check_internal_health "Seko-Finance" "${SEKO_FINANCE_URL}/api/health" "200"
{% endif %}
```

---

## 13. CI/CD

### `.github/workflows/integration.yml`

- TLS pre-warm : remplacer `"nzimbu"` par `"nzimbu" "lola"` dans la boucle de sous-domaines
- External smoke tests : remplacer le check Sure par Firefly + Seko-Finance (expected 403 car VPN-only)
- Internal smoke tests : les checks sont auto-générés par le template `smoke-test.sh.j2`

### Molecule

- `roles/common/molecule/default/converge.yml` : remplacer `sure_subdomain: nzimbu` par `seko_finance_subdomain: nzimbu` + `firefly_subdomain: lola`
- `roles/smoke-tests/molecule/default/converge.yml` : idem
- Créer `roles/firefly/molecule/default/` et `roles/seko-finance/molecule/default/`

---

## 14. Inventory Variables (résumé)

### `inventory/group_vars/all/main.yml`

```yaml
# Supprimer :
# sure_secret_key_base: "{{ vault_sure_secret_key_base }}"
# sure_db_password: "{{ vault_sure_db_password | default(postgresql_password) }}"
# sure_api_key: "{{ vault_sure_api_key | default('') }}"
# sure_subdomain: "nzimbu"

# Ajouter :
firefly_subdomain: "lola"
firefly_app_key: "{{ vault_firefly_app_key }}"
seko_finance_subdomain: "nzimbu"
seko_finance_firefly_pat: "{{ vault_firefly_pat | default('') }}"
```

### `inventory/group_vars/all/versions.yml`

```yaml
# Supprimer :
# sure_image: "ghcr.io/we-promise/sure:nightly"

# Ajouter :
firefly_image: "fireflyiii/core:version-6.2.1"
seko_finance_image: "ghcr.io/mobutoo/seko-finance:latest"
# TODO: pinner les deux sur un tag/SHA après validation
```

### `inventory/group_vars/all/docker.yml`

```yaml
# Supprimer les 6 lignes sure_*

# Ajouter :
firefly_memory_limit: "{{ '512M' if target_env == 'prod' else '256M' }}"
firefly_memory_reservation: "128M"
firefly_cpu_limit: "1.0"
seko_finance_memory_limit: "{{ '384M' if target_env == 'prod' else '256M' }}"
seko_finance_memory_reservation: "128M"
seko_finance_cpu_limit: "0.5"
```

---

## 15. Fichiers impactés (exhaustif)

| Action | Fichier |
|--------|---------|
| **Supprimer** | `roles/sure/` (5 fichiers) |
| **Créer** | `roles/firefly/` (tasks, defaults, templates, handlers, meta, molecule) |
| **Créer** | `roles/seko-finance/` (tasks, defaults, templates, handlers, meta, molecule) |
| **Modifier** | `playbooks/site.yml` |
| **Modifier** | `roles/docker-stack/templates/docker-compose.yml.j2` |
| **Modifier** | `roles/caddy/templates/Caddyfile.j2` |
| **Modifier** | `roles/caddy/defaults/main.yml` |
| **Modifier** | `roles/postgresql/defaults/main.yml` |
| **Modifier** | `inventory/group_vars/all/main.yml` |
| **Modifier** | `inventory/group_vars/all/versions.yml` |
| **Modifier** | `inventory/group_vars/all/docker.yml` |
| **Modifier** | `inventory/group_vars/all/secrets.yml` (vault) |
| **Modifier** | `roles/smoke-tests/templates/smoke-test.sh.j2` |
| **Modifier** | `.github/workflows/integration.yml` |
| **Modifier** | `roles/common/molecule/default/converge.yml` |
| **Modifier** | `roles/smoke-tests/molecule/default/converge.yml` |
| **Modifier** | `docs/TROUBLESHOOTING.md` |
| **Modifier** | `CLAUDE.md` (mettre à jour la stack) |

---

## 16. Ordre de déploiement

1. Supprimer Sure (containers + configs) sur le VPS
2. Créer le record DNS `lola` via API OVH
3. Déployer Firefly III (role + docker-compose + Caddy)
4. Accéder à `lola.ewutelo.cloud` via VPN, créer le premier compte admin
5. Générer un PAT dans Firefly III → ajouter au vault (`vault_firefly_pat`)
6. Déployer Seko-Finance dashboard
7. Valider smoke tests + CI

---

*Approuvé le 2026-03-04*
