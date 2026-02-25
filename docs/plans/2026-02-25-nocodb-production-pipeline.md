# Plan : Intégration NocoDB sur Sese-AI

## Contexte

NocoDB est ajouté comme base de données structurée pour la **gestion de production IA** (séries manga, campagnes ComfyUI, grands travaux). Il remplace Airtable/Notion et sera au cœur d'un pipeline hybride :
- **OpenClaw** → API NocoDB directe (updates temps-réel des jobs, statuts)
- **n8n** → orchestration automatisée (batch workflows, alertes, futurs seeds)
- **Toi** → édition manuelle dans NocoDB UI (scripts, validation, annotations)

**Périmètre de ce plan : infrastructure uniquement.** Le schéma (tables Séries/Épisodes/Scènes/Assets) sera défini avec OpenClaw dans une session dédiée, puis seedé via un workflow n8n. Ce plan prépare les hooks d'intégration (token API NocoDB exposé à OpenClaw et n8n).

---

## Architecture pipeline (vue d'ensemble)

```
Toi (NocoDB UI)
    ↕ édition manuelle (scripts, validation, annotations)
NocoDB ──────────────────── Source de vérité
    ↑ API directe              ↑ batch/webhooks
OpenClaw                     n8n
(updates temps-réel,         (workflows automatisés,
 génération prompts)          alertes, seeding schéma)

NocoDB ←── Palais (optionnel : afficher KPIs depuis NocoDB API)
```

### Use case principal : production IA manga

- Planifier 8 épisodes × 20 min chacun
- Rédiger et réviser les scripts directement dans NocoDB
- OpenClaw décompose les scripts en scènes, génère les prompts ComfyUI
- n8n orchestre les jobs ComfyUI, met à jour les statuts dans NocoDB
- Vue Kanban NocoDB pour suivre l'avancement de toute la saison

---

## Fichiers à créer / modifier

### Nouveaux fichiers (role nocodb)
- `roles/nocodb/defaults/main.yml`
- `roles/nocodb/tasks/main.yml`
- `roles/nocodb/handlers/main.yml`
- `roles/nocodb/meta/main.yml`
- `roles/nocodb/templates/nocodb.env.j2`

### Fichiers modifiés
| Fichier | Modification |
|---|---|
| `inventory/group_vars/all/versions.yml` | Ajouter `nocodb_image` |
| `inventory/group_vars/all/docker.yml` | Ajouter `nocodb_memory_limit/reservation/cpu_limit` |
| `inventory/group_vars/all/main.yml` | Ajouter `nocodb_subdomain` + refs secrets |
| `roles/postgresql/defaults/main.yml` | Ajouter `nocodb` dans `postgresql_databases` |
| `roles/docker-stack/templates/docker-compose.yml.j2` | Ajouter service `nocodb` (Phase B) |
| `roles/caddy/templates/Caddyfile.j2` | Ajouter vhost VPN-only |
| `playbooks/site.yml` | Ajouter role `nocodb` Phase 3 |
| `inventory/group_vars/all/secrets.yml` (vault) | Ajouter 3 secrets nocodb |
| `roles/openclaw/templates/openclaw.env.j2` | Exposer `NOCODB_BASE_URL` + `NOCODB_API_TOKEN` |
| `roles/n8n/templates/n8n.env.j2` | Exposer `NOCODB_BASE_URL` + `NOCODB_API_TOKEN` |

---

## Détail des changements

### 1. `inventory/group_vars/all/versions.yml`
```yaml
nocodb_image: "nocodb/nocodb:0.205.3"  # Vérifier la dernière stable sur hub.docker.com/r/nocodb/nocodb/tags
```

### 2. `inventory/group_vars/all/docker.yml`
```yaml
# NocoDB (Airtable-like project management)
nocodb_memory_limit: "{{ '384M' if target_env == 'prod' else '256M' }}"
nocodb_memory_reservation: "128M"
nocodb_cpu_limit: "0.5"
```

### 3. `inventory/group_vars/all/main.yml`
Ajouter dans la section subdomains :
```yaml
nocodb_subdomain: "noco"          # → noco.<domain>
```
Ajouter dans la section secrets :
```yaml
postgresql_nocodb_password: "{{ vault_postgresql_nocodb_password }}"
nocodb_jwt_secret: "{{ vault_nocodb_jwt_secret }}"
nocodb_api_token: "{{ vault_nocodb_api_token }}"
```

### 4. `roles/postgresql/defaults/main.yml`
Ajouter dans `postgresql_databases` :
```yaml
- name: nocodb
  user: nocodb
  extensions: []
```

### 5. `roles/nocodb/defaults/main.yml`
```yaml
---
# nocodb — defaults

nocodb_config_dir: "/opt/{{ project_name }}/configs/nocodb"
nocodb_data_dir: "/opt/{{ project_name }}/data/nocodb"
```

### 6. `roles/nocodb/tasks/main.yml`
Pattern identique à n8n :
1. Créer `nocodb_config_dir` (owner: `prod_user`, mode 0755, become: true)
2. Créer `nocodb_data_dir` (owner: `1000:1000`, mode 0755, become: true — image node user)
3. Déployer `nocodb.env.j2` → `{{ nocodb_config_dir }}/nocodb.env` (mode 0600)
   - notify: `Restart nocodb stack`

### 7. `roles/nocodb/templates/nocodb.env.j2`
```bash
# {{ ansible_managed }}
NC_DB=pg://postgresql:5432?u=nocodb&p={{ postgresql_nocodb_password }}&d=nocodb
NC_PUBLIC_URL=https://{{ nocodb_subdomain }}.{{ domain_name }}
NC_AUTH_JWT_SECRET={{ nocodb_jwt_secret }}
NC_TOOL_DIR=/data
NC_DISABLE_TELE=true
```

### 8. `roles/nocodb/handlers/main.yml`
```yaml
---
# nocodb — handlers

- name: Restart nocodb stack
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - nocodb
    state: restarted
  become: true
  failed_when: false
```

### 9. `roles/nocodb/meta/main.yml`
```yaml
---
galaxy_info:
  role_name: nocodb
  author: VPAI
  description: NocoDB project management — Airtable alternative on PostgreSQL
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions: [bookworm, trixie]

dependencies:
  - role: docker
  - role: postgresql
```

### 10. `roles/docker-stack/templates/docker-compose.yml.j2`
Ajouter le service (Phase B, networks `backend` + `frontend`) :
```yaml
{% if nocodb_subdomain | default('') | length > 0 %}
  nocodb:
    image: {{ nocodb_image }}
    container_name: {{ project_name }}_nocodb
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
      - DAC_OVERRIDE
      - FOWNER
    env_file:
      - /opt/{{ project_name }}/configs/nocodb/nocodb.env
    volumes:
      - /opt/{{ project_name }}/data/nocodb:/data
    networks:
      - backend
      - frontend
    deploy:
      resources:
        limits:
          memory: {{ nocodb_memory_limit }}
          cpus: "{{ nocodb_cpu_limit }}"
        reservations:
          memory: {{ nocodb_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:8080/api/v1/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
{% endif %}
```

### 11. `roles/caddy/templates/Caddyfile.j2`
Ajouter vhost VPN-only (pattern identique aux autres admin UIs) :
```caddyfile
# === NocoDB - project management (AI production pipeline) ===
{% if nocodb_subdomain | default('') | length > 0 %}
{{ nocodb_subdomain }}.{{ domain_name }} {
    import vpn_only
    import vpn_error_page

    reverse_proxy nocodb:8080

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        -Server
    }
}
{% endif %}
```

### 12. `playbooks/site.yml`
Ajouter après `litellm` en Phase 3 :
```yaml
  - role: nocodb
    tags: [nocodb, phase3]
```

### 13. `inventory/group_vars/all/secrets.yml` (vault)
Ajouter via `ansible-vault edit` :
```yaml
vault_nocodb_jwt_secret: "<generated_random_32chars>"
vault_postgresql_nocodb_password: "<generated_random_password>"
vault_nocodb_api_token: "<generated_random_token>"  # Token API pour OpenClaw + n8n
```

### 14. Exposer le token NocoDB à OpenClaw et n8n

**`roles/openclaw/templates/openclaw.env.j2`** — ajouter :
```bash
# NocoDB integration (pipeline production IA)
NOCODB_BASE_URL=http://nocodb:8080
NOCODB_API_TOKEN={{ nocodb_api_token }}
```

**`roles/n8n/templates/n8n.env.j2`** — ajouter :
```bash
# NocoDB integration
NOCODB_BASE_URL=https://{{ nocodb_subdomain }}.{{ domain_name }}
NOCODB_API_TOKEN={{ nocodb_api_token }}
```

> Ces variables sont disponibles dès le premier deploy. Le workflow n8n de seeding du schéma sera créé lors de la session design du pipeline.

---

## Points d'attention

- **`cap_add: [DAC_OVERRIDE, FOWNER]`** nécessaires — NocoDB écrit dans `/data` (volume monté)
- **Port interne** : NocoDB écoute sur `8080` — vérifier avec la version pinnée
- **Version** : Vérifier le tag exact `nocodb/nocodb:0.205.3` sur DockerHub avant deploy
- **Mémoire** : 384M est conservateur — monitorer via Grafana/cAdvisor après deploy
- **NC_API_TOKEN** : à créer manuellement dans NocoDB UI après le premier démarrage (Team & Auth → API Tokens), puis stocker dans vault et redéployer

---

## Prochaines étapes (hors scope ce plan)

1. **Session design pipeline** : définir le schéma exact (tables + colonnes + vues) avec OpenClaw
2. **n8n workflow seed** : créer les tables via API NocoDB (déclenché manuellement une fois)
3. **OpenClaw tools** : configurer les HTTP tools avec `NOCODB_BASE_URL` + `NOCODB_API_TOKEN`
4. **(Optionnel)** Palais : widget KPIs production depuis NocoDB API

---

## Vérification post-deploy

```bash
# Déployer le role
make deploy-role ROLE=nocodb ENV=prod

# Vérifier le container
ssh -i ~/.ssh/seko-vpn-deploy -p <SSH_PORT> <SSH_USER>@<VPS_IP> \
  'docker ps | grep nocodb && docker logs <project>_nocodb --tail 50'

# Tester l'accès (depuis VPN)
curl -s https://noco.<domain>/api/v1/health

# Vérifier la DB PostgreSQL
ssh [...] 'docker exec <project>_postgresql psql -U postgres -c "\l" | grep nocodb'
```
