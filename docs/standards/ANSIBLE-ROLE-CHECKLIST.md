# Checklist création de rôle Ansible — VPAI

## Objectif

Empêcher les violations de convention récurrentes mesurées en production. À utiliser
**avant de commiter** un nouveau rôle ou une modification substantielle d'un rôle existant.
Chaque item marqué **(BLOQUANT)** doit être satisfait avant tout `git push` ou exécution
Ansible sur `prod`.

Source des violations documentées : `docs/audits/2026-04-11-mop-generator-execution-audit.md`.

---

## Checklist obligatoire (bloquer si manquant)

### 1. Tags — 3 tags obligatoires : nom + phase + catégorie

**Règle :** Chaque rôle doit avoir **3 tags** : `[<role_name>, phase<N>, <catégorie>]`.
- Le tag phase permet `--tags phase3` (déploie tous les services d'une phase).
- Le tag catégorie permet `--tags apps` ou `--tags platform` (déploie toute une catégorie).
- Les rôles `workstation` ont un **4ème tag** de sous-catégorie : `tools`, `creative`, `services`, `infra`, `monitoring`.

**Violation V1** — `--tags phase3` déploie 0 tâche pour ce rôle si le tag phase est absent.

```yaml
# ✅ Correct — service applicatif (dans playbooks/stacks/site.yml)
- role: mon-service
  tags: [mon-service, phase3, apps]

# ✅ Correct — rôle workstation (dans playbooks/hosts/workstation.yml)
- role: mon-outil-pi
  tags: [mon-outil-pi, workstation, tools]

# ❌ Incorrect — tag catégorie manquant
- role: mon-service
  tags: [mon-service, phase3]

# ❌ Incorrect — aucun tag
- role: mon-service
```

Table de référence des phases :

| Phase | Rôles concernés |
|-------|----------------|
| phase1 | common, docker, headscale-node |
| phase2 | postgresql, redis, qdrant, caddy |
| phase3 | n8n, litellm, openclaw, nocodb, plane, palais, kitsu, flash-suite, mop-templates, et tout nouveau service applicatif |
| phase4 | monitoring, diun, obsidian-collector |
| phase4.6 | n8n-provision, plane-provision, kitsu-provision, content-factory-provision |
| phase5 | backup-config, uptime-config, smoke-tests |
| phase6 | hardening |

---

### 2. Logging Docker — Rotation obligatoire sur chaque service

**Règle :** Chaque service dans un template `docker-compose*.yml.j2` doit déclarer un bloc
`logging` avec `max-size: "10m"` et `max-file: "3"`. Sans rotation, les logs remplissent
le disque du VPS 8 GB.

**Violation V2** — Logs illimités → disque plein → crash stack complète.

```yaml
# ✅ Correct
services:
  mon-service:
    image: "{{ mon_service_image }}"
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

# ❌ Incorrect — bloc logging absent
services:
  mon-service:
    image: "{{ mon_service_image }}"
    restart: unless-stopped
```

---

### 3. Images Docker — Jamais `:latest`, version pinnée dans `versions.yml`

**Règle :** Les images Docker doivent référencer une variable Jinja2 dont la valeur est
définie dans `inventory/group_vars/all/versions.yml`. Jamais `:latest` ni `:stable`.

```yaml
# ✅ Correct — dans docker-compose*.yml.j2
services:
  mon-service:
    image: "{{ mon_service_image }}"

# ✅ Correct — dans inventory/group_vars/all/versions.yml
mon_service_image: "ghcr.io/org/mon-service:1.2.3"

# ❌ Incorrect — tag flottant
services:
  mon-service:
    image: "ghcr.io/org/mon-service:latest"

# ❌ Incorrect — version hardcodée dans le template
services:
  mon-service:
    image: "ghcr.io/org/mon-service:1.2.3"
```

---

### 4. FQCN Ansible — Toujours le nom complet de collection

**Règle :** Tous les modules Ansible doivent utiliser leur FQCN (Fully Qualified Collection
Name). `ansible-lint` en mode `production` bloque les noms courts.

```yaml
# ✅ Correct
- name: Créer les répertoires
  ansible.builtin.file:
    path: "{{ mon_service_base_dir }}"
    state: directory
    mode: "0755"

- name: Installer les paquets
  ansible.builtin.apt:
    name: curl
    state: present

- name: Déployer le template
  ansible.builtin.template:
    src: docker-compose.yml.j2
    dest: "{{ mon_service_base_dir }}/docker-compose.yml"

# ❌ Incorrect — noms courts
- name: Créer les répertoires
  file:
    path: "{{ mon_service_base_dir }}"
    state: directory

- name: Installer les paquets
  apt:
    name: curl
```

Modules fréquents et leur FQCN :

| Nom court | FQCN |
|-----------|------|
| `file` | `ansible.builtin.file` |
| `template` | `ansible.builtin.template` |
| `copy` | `ansible.builtin.copy` |
| `apt` | `ansible.builtin.apt` |
| `command` | `ansible.builtin.command` |
| `shell` | `ansible.builtin.shell` |
| `assert` | `ansible.builtin.assert` |
| `debug` | `ansible.builtin.debug` |
| `fail` | `ansible.builtin.fail` |
| `service` | `ansible.builtin.service` |
| `docker_compose_v2` | `community.docker.docker_compose_v2` |
| `ufw` | `community.general.ufw` |

---

### 5. `changed_when` / `failed_when` — Explicites sur `command` et `shell`

**Règle :** Toute tâche utilisant `ansible.builtin.command` ou `ansible.builtin.shell`
doit déclarer `changed_when` et `failed_when` explicites. Sans eux, `ansible-lint` en
mode `production` échoue, et les rapports de changement sont faux.

```yaml
# ✅ Correct
- name: Vérifier l'état du service
  ansible.builtin.command:
    cmd: "docker inspect --format={{ '{{' }}.State.Status{{ '}}' }} {{ mon_service_name }}"
  register: service_status
  changed_when: false
  failed_when: service_status.rc != 0

- name: Démarrer la stack
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: |
      set -euo pipefail
      cd {{ mon_service_base_dir }}
      docker compose up -d 2>&1
  register: stack_up
  changed_when: "'Started' in stack_up.stdout or 'Created' in stack_up.stdout"
  failed_when: stack_up.rc != 0

# ❌ Incorrect — changed_when / failed_when absents
- name: Démarrer la stack
  ansible.builtin.shell:
    cmd: "docker compose up -d"
```

---

### 6. `set -euo pipefail` + `executable: /bin/bash` sur les tâches `shell`

**Règle :** Toute tâche `ansible.builtin.shell` doit déclarer `executable: /bin/bash`
et commencer par `set -euo pipefail`. Debian 13 utilise `dash` par défaut — les construits
bash (`[[ ]]`, process substitution, etc.) échouent silencieusement sans cette déclaration.

```yaml
# ✅ Correct
- name: Initialiser la base de données
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: |
      set -euo pipefail
      docker exec {{ mon_service_db_container }} psql -U {{ mon_service_db_user }} \
        -c "SELECT 1" 2>&1
  register: db_check
  changed_when: false
  failed_when: db_check.rc != 0

# ❌ Incorrect — pas d'executable, pas de pipefail
- name: Initialiser la base de données
  ansible.builtin.shell:
    cmd: |
      docker exec mon_db psql -U admin -c "SELECT 1"
```

---

### 7. Healthcheck — Obligatoire sur chaque container

**Règle :** Chaque service dans un template `docker-compose*.yml.j2` doit déclarer un
bloc `healthcheck`. Cela permet à Ansible (et à Docker) de savoir quand le service est
réellement prêt, et déclenche les alertes DIUN/Grafana correctement.

```yaml
# ✅ Correct — service web générique
services:
  mon-service:
    image: "{{ mon_service_image }}"
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:{{ mon_service_port }}/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

# ✅ Correct — base PostgreSQL
services:
  postgres:
    image: "{{ mon_service_postgres_image }}"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {{ mon_service_db_user }} -d {{ mon_service_db_name }}"]
      interval: 10s
      timeout: 5s
      retries: 5

# ✅ Correct — Redis
services:
  redis:
    image: "{{ mon_service_redis_image }}"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

# ❌ Incorrect — healthcheck absent
services:
  mon-service:
    image: "{{ mon_service_image }}"
    restart: unless-stopped
```

---

### 8. Limites mémoire/CPU — `deploy.resources.limits` sur chaque container

**Règle :** Chaque service doit déclarer des limites mémoire et CPU via `deploy.resources`.
Sans limite, un service défaillant peut saturer le VPS 8 GB et tuer la stack entière.
Les valeurs sont des variables définies dans `defaults/main.yml`.

```yaml
# ✅ Correct — dans docker-compose*.yml.j2
services:
  mon-service:
    image: "{{ mon_service_image }}"
    deploy:
      resources:
        limits:
          memory: "{{ mon_service_memory_limit }}"
          cpus: "{{ mon_service_cpu_limit }}"
        reservations:
          memory: "{{ mon_service_memory_reservation }}"

# ✅ Correct — dans defaults/main.yml
mon_service_memory_limit: "512m"
mon_service_cpu_limit: "0.5"
mon_service_memory_reservation: "128m"

# ❌ Incorrect — pas de limites
services:
  mon-service:
    image: "{{ mon_service_image }}"
    restart: unless-stopped
```

---

### 9. `cap_drop: ALL` + `restart: unless-stopped` — Sécurité container

**Règle :** Chaque service doit déclarer `cap_drop: [ALL]` avec seulement les capabilities
minimales requises dans `cap_add`, ainsi que `security_opt: [no-new-privileges:true]` et
`restart: unless-stopped`.

Capabilities courantes selon le type de service :

| Type de service | `cap_add` minimal |
|-----------------|-------------------|
| Application stateless | _(vide — cap_drop seul suffit)_ |
| Service qui écrit dans des volumes | `CHOWN`, `DAC_OVERRIDE`, `FOWNER` |
| Service qui change d'utilisateur | `SETGID`, `SETUID` |
| Base de données (PostgreSQL) | `CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETGID`, `SETUID` |

```yaml
# ✅ Correct — service applicatif stateless
services:
  mon-service:
    image: "{{ mon_service_image }}"
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    restart: unless-stopped

# ✅ Correct — base de données
services:
  postgres:
    image: "{{ mon_service_postgres_image }}"
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - DAC_OVERRIDE
      - FOWNER
      - SETGID
      - SETUID
    restart: unless-stopped

# ❌ Incorrect — cap_drop absent, restart absent
services:
  mon-service:
    image: "{{ mon_service_image }}"
```

---

### 10. Handlers `env_file` — Piège critique (restart vs recreate)

**Règle :** Pour tout service utilisant `env_file` dans Docker Compose, le handler doit
utiliser `state: present` + `recreate: always` (jamais `state: restarted`).
`state: restarted` équivaut à `docker compose restart` qui **ne recharge pas** l'env_file.

**Conséquence si violation :** les nouvelles valeurs de variables d'environnement ne sont
jamais prises en compte après un déploiement Ansible — bug silencieux difficile à diagnostiquer.

```yaml
# ✅ Correct — handler dans roles/mon-service/handlers/main.yml
- name: Restart mon-service stack
  community.docker.docker_compose_v2:
    project_src: "{{ mon_service_base_dir }}"
    state: present
    recreate: always
  become: true

# ❌ Incorrect — state: restarted ne recharge pas env_file
- name: Restart mon-service stack
  community.docker.docker_compose_v2:
    project_src: "{{ mon_service_base_dir }}"
    state: restarted
  become: true
```

Pour vérifier que les variables sont bien chargées après un déploiement :

```bash
docker inspect <container> | python3 -c \
  'import sys,json; [print(e) for e in json.load(sys.stdin)[0]["Config"]["Env"] if "MA_VAR" in e]'
```

---

### 11. Variables — Pas de valeurs hardcodées, tout dans `defaults/main.yml`

**Règle :** Aucune valeur configurable ne doit être hardcodée dans les templates ou tâches.
Toutes les valeurs doivent être des variables Jinja2 définies dans `defaults/main.yml`
(overridable) ou `vars/main.yml` (fixes internes au rôle). Cela garantit la portabilité
entre prod, preprod, et nouveaux environnements.

**Violation V3** — URL hardcodée dans un workflow n8n → non portable entre prod/preprod.

```yaml
# ✅ Correct — dans un template .j2
url: "https://{{ domain_name }}/api/webhook"
webhook_url: "{{ mon_service_webhook_url }}"

# ✅ Correct — dans defaults/main.yml
mon_service_webhook_url: "https://{{ domain_name }}/mon-service/webhook"

# ❌ Incorrect — URL hardcodée dans le template
url: "https://mayi.ewutelo.cloud/api/webhook"
```

---

## Violations historiques documentées

| Code | Description | Impact mesuré | Référence |
|------|-------------|---------------|-----------|
| **V1** | Phase tags manquants dans `playbooks/site.yml` | `--tags phase3` déploie 0 tâche pour le rôle — service non déployé silencieusement | `docs/audits/2026-04-11-mop-generator-execution-audit.md` |
| **V2** | Bloc `logging` absent dans `docker-compose*.yml.j2` | Logs illimités → disque VPS 8 GB plein → crash stack complète | `docs/audits/2026-04-11-mop-generator-execution-audit.md` |
| **V3** | URL hardcodée dans template ou workflow n8n | Non portable entre prod/preprod → deploy preprod cible prod | `docs/audits/2026-04-11-mop-generator-execution-audit.md` |

---

## Commande de vérification rapide

```bash
# Depuis la racine du repo, venv activé
source .venv/bin/activate

# 1. Linting complet (ansible-lint production + yamllint)
make lint

# 2. Syntax check sans déploiement
ansible-playbook playbooks/site.yml --syntax-check

# 3. Dry run ciblé sur un rôle spécifique
ansible-playbook playbooks/site.yml --tags mon-service --check --diff

# 4. Vérifier les tags déclarés (grep dans site.yml)
grep -A1 "role: mon-service" playbooks/site.yml

# 5. Vérifier les images dans versions.yml
grep "mon_service_image" inventory/group_vars/all/versions.yml

# 6. Vérifier qu'aucune valeur n'est hardcodée (noms de domaine, IPs)
grep -r 'ewutelo\.cloud\|137\.74\.114\|87\.106\.30' roles/mon-service/
```

---

## Structure minimale d'un nouveau rôle

```
roles/mon-service/
├── defaults/
│   └── main.yml          # Variables overridables (images, ports, limites)
├── tasks/
│   └── main.yml          # Tâches (FQCN, changed_when, failed_when)
├── handlers/
│   └── main.yml          # state: present + recreate: always (jamais restarted)
├── templates/
│   ├── docker-compose.yml.j2   # logging + healthcheck + cap_drop + deploy.resources
│   └── mon-service.env.j2      # Variables d'environnement
└── meta/
    └── main.yml          # galaxy_info (optionnel mais recommandé)
```

Et dans `playbooks/stacks/site.yml` :

```yaml
- role: mon-service
  tags: [mon-service, phase3, apps]   # 3 tags obligatoires
```

Et dans `inventory/group_vars/all/versions.yml` :

```yaml
mon_service_image: "ghcr.io/org/mon-service:1.2.3"   # version pinnée
```

---

### 12. Taxonomie — Enregistrer le rôle dans `platform.yaml`

**Règle :** Tout nouveau rôle doit être ajouté dans `platform.yaml` (source de vérité de la
taxonomie) et sa description ajoutée dans `scripts/generate-structure.py`. Sans cela,
`docs/STRUCTURE.md` est désynchronisé et le rôle est invisible dans la documentation.

```bash
# 1. Ajouter le rôle dans la bonne catégorie de platform.yaml
#    Exemple — ajouter "mon-service" dans apps:
vim platform.yaml

# 2. Ajouter sa description dans ROLE_DESCRIPTIONS (scripts/generate-structure.py)
vim scripts/generate-structure.py

# 3. Régénérer docs/STRUCTURE.md
source .venv/bin/activate
python scripts/generate-structure.py

# 4. Vérifier que STRUCTURE.md est à jour
python scripts/generate-structure.py --check   # doit afficher "OK"

# 5. Committer les 3 fichiers ensemble
git add platform.yaml scripts/generate-structure.py docs/STRUCTURE.md
git commit -m "feat(taxonomy): register mon-service role"
```

**Catégories disponibles** (voir `platform.yaml` pour la liste complète) :

| Catégorie | Rôles typiques | Phase |
|-----------|---------------|-------|
| `core` | common, docker, hardening | 1 |
| `platform` | postgresql, redis, caddy | 2 |
| `apps` | n8n, litellm, nocodb, tout nouveau service | 3 |
| `provision` | *-provision | 4.6 |
| `monitoring` | monitoring, diun, smoke-tests | 4 |
| `workstation` | outils Pi (tools/creative/services/infra) | waza |
| `ops` | backup-config, vpn-dns | adhoc |
