# CouchDB Obsidian LiveSync — Migration Seko-VPN → Sese-AI

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Déplacer CouchDB de Seko-VPN vers Sese-AI (VPAI), conformément au PRD `docs/08-prd-obsidian-livesync-sese.md` du repo Seko-VPN.

**Architecture:** CouchDB tourne dans le stack Docker de Sese-AI (réseau `backend`, interne). Caddy proxifie `biki.ewutelo.cloud → couchdb:5984` via le nom de conteneur Docker (pas de Tailscale cross-server). Le CORS est géré uniquement dans `local.ini` de CouchDB — jamais dans Caddy (double CORS = sync mobile silencieusement cassée).

**Tech Stack:** Ansible, Docker Compose, CouchDB 3.3.3, Caddy, obsidian-livesync plugin

---

## Contexte — Pourquoi cette migration

L'implémentation précédente (commit `92b8935`) a placé CouchDB sur Seko-VPN avec un proxy Tailscale cross-server. Ceci est incorrect pour deux raisons :

1. **PRD explicite** (`Seko-VPN/docs/08-prd-obsidian-livesync-sese.md`, section 11) : *"❌ Modification du playbook Seko-VPN IONOS (aucun nouveau rôle côté IONOS)"*
2. **Architecture** : CouchDB doit être dans le même réseau Docker que Caddy sur Sese-AI → `reverse_proxy couchdb:5984` (interne), pas via Tailscale
3. **CORS** : Headers CORS dans Caddy causent des headers dupliqués → sync mobile cassée. CORS uniquement dans `local.ini` CouchDB

**Piège CORS critique (PRD section 5.1) :**
```
# ✅ Correct — pas d'espace après virgule
origins = app://obsidian.md,capacitor://localhost,http://localhost

# ❌ Incorrect — espace après virgule → sync mobile silencieusement cassée
origins = app://obsidian.md, capacitor://localhost, http://localhost
```

---

## Fichiers à supprimer

- `playbooks/obsidian.yml` — ciblait Seko-VPN (hosts: vpn)
- `roles/obsidian/` — rôle CouchDB pour Seko-VPN (remplacé par roles/couchdb/)

## Fichiers à créer

- `roles/couchdb/defaults/main.yml`
- `roles/couchdb/tasks/main.yml`
- `roles/couchdb/handlers/main.yml`
- `roles/couchdb/templates/couchdb-local.ini.j2`
- `roles/couchdb/templates/dump-vault.py.j2`

## Fichiers à modifier

- `roles/docker-stack/templates/docker-compose-infra.yml.j2` — ajouter service couchdb
- `roles/caddy/templates/Caddyfile.j2` — corriger proxy + supprimer CORS
- `playbooks/site.yml` — ajouter rôle couchdb en Phase 2
- `inventory/group_vars/all/main.yml` — corriger variables
- `inventory/group_vars/all/versions.yml` — vérifier image CouchDB
- `roles/obsidian-collector/defaults/main.yml` — corriger URL CouchDB
- `roles/obsidian-collector-pi/defaults/main.yml` — corriger URL CouchDB
- `Makefile` — remplacer deploy-obsidian par deploy-couchdb
- `docs/ARCHITECTURE.md` — corriger architecture section 8.5

---

## Task 1 : Supprimer les fichiers Seko-VPN incorrects

**Files:**
- Delete: `playbooks/obsidian.yml`
- Delete: `roles/obsidian/` (tout le répertoire)

**Step 1: Supprimer**

```bash
rm playbooks/obsidian.yml
rm -rf roles/obsidian/
```

**Step 2: Vérifier**

```bash
ls playbooks/obsidian.yml 2>&1   # → No such file
ls roles/obsidian/ 2>&1          # → No such file
```

**Step 3: Commit**

```bash
git rm playbooks/obsidian.yml
git rm -rf roles/obsidian/
git commit -m "chore(obsidian): remove Seko-VPN targeted role — CouchDB moves to sese"
```

---

## Task 2 : Créer roles/couchdb/defaults/main.yml

**Files:**
- Create: `roles/couchdb/defaults/main.yml`

**Step 1: Créer le fichier**

```yaml
---
# roles/couchdb/defaults/main.yml
# CouchDB 3.x — Backend Obsidian LiveSync
# Déployé sur Sese-AI (réseau backend Docker, même stack que Caddy)

couchdb_port: 5984
couchdb_data_dir: "/opt/{{ project_name }}/data/couchdb"
couchdb_config_dir: "/opt/{{ project_name }}/configs/couchdb"
couchdb_uid: 5984
couchdb_gid: 5984

# Credentials (depuis vault)
couchdb_admin_user: "{{ vault_couchdb_admin_user }}"
couchdb_admin_password: "{{ vault_couchdb_admin_password }}"

# Base de données Obsidian LiveSync
couchdb_obsidian_db: "{{ couchdb_db_name | default('obsidian-vault') }}"

# Resource limits
couchdb_memory_limit: "512M"
couchdb_memory_reservation: "128M"
couchdb_cpu_limit: "0.5"

# Git versioning du vault (dump nightly CouchDB → filesystem → git)
couchdb_dump_dir: "/opt/{{ project_name }}/data/obsidian-vault"
couchdb_dump_cron_hour: "2"
couchdb_dump_cron_minute: "0"
couchdb_git_repo: "{{ obsidian_git_repo | default('') }}"
```

**Step 2: Vérifier YAML**

```bash
source .venv/bin/activate && python3 -c "import yaml; yaml.safe_load(open('roles/couchdb/defaults/main.yml'))" && echo OK
```

Expected: `OK`

---

## Task 3 : Créer roles/couchdb/handlers/main.yml

**Files:**
- Create: `roles/couchdb/handlers/main.yml`

**Step 1: Créer le fichier**

```yaml
---
# roles/couchdb/handlers/main.yml

- name: Restart CouchDB
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose-infra.yml
    services:
      - couchdb
    state: restarted
  become: true
```

---

## Task 4 : Créer roles/couchdb/templates/couchdb-local.ini.j2

**Files:**
- Create: `roles/couchdb/templates/couchdb-local.ini.j2`

**Step 1: Créer le template**

```ini
; {{ ansible_managed }}
; couchdb-local.ini — Configuration CouchDB pour Obsidian LiveSync
; CRITIQUE : CORS géré ICI uniquement. Jamais dans Caddy (double headers → sync mobile cassée)

[couchdb]
users_db_security_editable = true
max_document_size = 50000000

[chttpd]
require_valid_user = true
max_http_request_size = 4294967296
enable_cors = true

[chttpd_auth]
require_valid_user = true

[httpd]
WWW-Authenticate = Basic realm="couchdb"
enable_cors = true

[cors]
; PIÈGE : pas d'espace après les virgules (sync mobile silencieusement cassée sinon)
origins = app://obsidian.md,capacitor://localhost,http://localhost
credentials = true
headers = accept, authorization, content-type, origin, referer, cache-control, x-requested-with
methods = GET, PUT, POST, HEAD, DELETE, OPTIONS, PATCH
max_age = 3600

[admins]
; Admin créé par variable d'env COUCHDB_USER/COUCHDB_PASSWORD au premier démarrage
; Ne pas mettre de credentials ici — géré par Docker env

[log]
level = warning
```

**Pourquoi ces origins et pas `*` :**
- `app://obsidian.md` — Obsidian Desktop
- `capacitor://localhost` — Obsidian iOS/Android (Capacitor)
- `http://localhost` — Dev local
- `*` causerait un conflit de headers CORS avec Caddy si mal configuré

---

## Task 5 : Créer roles/couchdb/templates/dump-vault.py.j2

**Files:**
- Create: `roles/couchdb/templates/dump-vault.py.j2`

**Step 1: Créer le script**

```python
#!/usr/bin/env python3
# {{ ansible_managed }}
# dump-vault.py — Dump nightly CouchDB → filesystem → git commit
# Cron : {{ couchdb_dump_cron_hour }}:{{ couchdb_dump_cron_minute | zfill(2) }} daily
#
# Utilise l'URL publique (même serveur, loop via Caddy)
# Note : si E2E activé dans LiveSync, les docs sont des blobs chiffrés — ce script
# les écrit tels quels (chiffrés). Pour lire le contenu, désactiver E2E dans LiveSync.

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

COUCHDB_URL = "https://{{ obsidian_subdomain }}.{{ domain_name }}"
COUCHDB_USER = "{{ couchdb_admin_user }}"
COUCHDB_PASSWORD = "{{ couchdb_admin_password }}"
COUCHDB_DB = "{{ couchdb_obsidian_db }}"
VAULT_DIR = "{{ couchdb_dump_dir }}"
GIT_REPO = "{{ couchdb_git_repo }}"
LOG_FILE = "/var/log/couchdb-dump.log"


def log(msg):
    print(msg, flush=True)


def couch_get(path):
    url = f"{COUCHDB_URL}/{COUCHDB_DB}/{path}"
    req = urllib.request.Request(url)
    creds = base64.b64encode(f"{COUCHDB_USER}:{COUCHDB_PASSWORD}".encode()).decode()
    req.add_header("Authorization", f"Basic {creds}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log(f"HTTP error {e.code} on {url}")
        raise


def livesync_decode_path(doc_id):
    """Decode LiveSync v2 document ID → file path.
    Format: 'v2:plain:<base64(path)>' ou '_design/...' (ignorer)
    """
    if not doc_id.startswith("v2:plain:"):
        return None
    try:
        encoded = doc_id[len("v2:plain:"):]
        # Compléter le padding base64
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += "=" * padding
        return base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return None


def dump():
    log(f"=== CouchDB dump start — {COUCHDB_DB} → {VAULT_DIR} ===")

    # Récupérer tous les docs
    result = couch_get("_all_docs?include_docs=true")
    rows = result.get("rows", [])
    log(f"Found {len(rows)} documents")

    os.makedirs(VAULT_DIR, exist_ok=True)
    written_paths = set()
    errors = 0

    for row in rows:
        doc = row.get("doc", {})
        doc_id = doc.get("_id", "")

        file_path = livesync_decode_path(doc_id)
        if not file_path:
            continue  # ignorer _design docs, etc.

        # Extraire le contenu (champ 'data' pour LiveSync v2)
        content = doc.get("data", "")
        if not isinstance(content, str):
            continue

        full_path = os.path.join(VAULT_DIR, file_path.lstrip("/"))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            written_paths.add(full_path)
        except Exception as e:
            log(f"ERROR writing {full_path}: {e}")
            errors += 1

    # Supprimer les fichiers orphelins (.md non présents dans CouchDB)
    for root, dirs, files in os.walk(VAULT_DIR):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            if fpath not in written_paths:
                os.remove(fpath)
                log(f"Deleted orphan: {fpath}")

    log(f"Written: {len(written_paths)} files, errors: {errors}")

    # Git commit si repo configuré
    if GIT_REPO:
        git_commit()

    return errors


def git_commit():
    if not os.path.isdir(os.path.join(VAULT_DIR, ".git")):
        subprocess.run(
            ["git", "init", VAULT_DIR], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", VAULT_DIR, "remote", "add", "origin", GIT_REPO],
            check=True, capture_output=True
        )

    subprocess.run(
        ["git", "-C", VAULT_DIR, "add", "-A"],
        check=True, capture_output=True
    )
    result = subprocess.run(
        ["git", "-C", VAULT_DIR, "diff", "--cached", "--quiet"],
        capture_output=True
    )
    if result.returncode == 0:
        log("Git: nothing to commit")
        return

    import datetime
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    subprocess.run(
        ["git", "-C", VAULT_DIR, "commit", "-m", f"chore: nightly vault dump {date_str}"],
        check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", VAULT_DIR, "push", "origin", "main"],
        check=False, capture_output=True
    )
    log("Git: committed and pushed")


if __name__ == "__main__":
    errors = dump()
    sys.exit(1 if errors > 0 else 0)
```

---

## Task 6 : Créer roles/couchdb/tasks/main.yml

**Files:**
- Create: `roles/couchdb/tasks/main.yml`

**Step 1: Créer les tâches**

```yaml
---
# roles/couchdb/tasks/main.yml
# Phase 2 (config) : création dirs + deploy configs
# Phase 4.6 (init) : initialisation système DBs (tag: couchdb-init)

- name: Create CouchDB data directory
  ansible.builtin.file:
    path: "{{ couchdb_data_dir }}"
    state: directory
    owner: "{{ couchdb_uid }}"
    group: "{{ couchdb_gid }}"
    mode: "0755"
  become: true
  tags: [couchdb]

- name: Create CouchDB config directory
  ansible.builtin.file:
    path: "{{ couchdb_config_dir }}"
    state: directory
    owner: "{{ couchdb_uid }}"
    group: "{{ couchdb_gid }}"
    mode: "0755"
  become: true
  tags: [couchdb]

- name: Create obsidian vault dump directory
  ansible.builtin.file:
    path: "{{ couchdb_dump_dir }}"
    state: directory
    owner: "root"
    group: "root"
    mode: "0755"
  become: true
  tags: [couchdb]

- name: Deploy CouchDB local.ini
  ansible.builtin.template:
    src: couchdb-local.ini.j2
    dest: "{{ couchdb_config_dir }}/obsidian-livesync.ini"
    owner: "{{ couchdb_uid }}"
    group: "{{ couchdb_gid }}"
    mode: "0640"
  become: true
  notify: Restart CouchDB
  tags: [couchdb]

- name: Deploy vault dump script
  ansible.builtin.template:
    src: dump-vault.py.j2
    dest: "/usr/local/bin/couchdb-dump-vault.py"
    owner: root
    group: root
    mode: "0750"
  become: true
  tags: [couchdb]

- name: Create dump log file
  ansible.builtin.file:
    path: /var/log/couchdb-dump.log
    state: touch
    owner: root
    group: root
    mode: "0640"
    modification_time: preserve
    access_time: preserve
  become: true
  tags: [couchdb]

- name: Schedule nightly vault dump cron
  ansible.builtin.cron:
    name: "CouchDB vault dump → git"
    hour: "{{ couchdb_dump_cron_hour }}"
    minute: "{{ couchdb_dump_cron_minute }}"
    job: >-
      /usr/bin/python3 /usr/local/bin/couchdb-dump-vault.py
      >> /var/log/couchdb-dump.log 2>&1
    user: root
    state: present
  become: true
  tags: [couchdb]

# ─── Init CouchDB (tag: couchdb-init) ────────────────────────────────────────
# À exécuter APRÈS docker-stack (Phase 4.5) : make deploy-role ROLE=couchdb-init ENV=prod
# Utilise docker exec pour éviter l'exposition de port et dépendance DNS

- name: Wait for CouchDB to be healthy
  ansible.builtin.shell:
    cmd: |
      set -euo pipefail
      for i in $(seq 1 30); do
        if docker exec {{ project_name }}_couchdb curl -sf http://localhost:5984/_up >/dev/null 2>&1; then
          echo "CouchDB ready after $i attempts"
          exit 0
        fi
        sleep 2
      done
      echo "CouchDB not ready after 60s" >&2
      exit 1
    executable: /bin/bash
  register: couchdb_wait
  changed_when: false
  become: true
  tags: [couchdb-init]

- name: Initialize CouchDB system databases
  ansible.builtin.shell:
    cmd: |
      set -euo pipefail
      CURL="docker exec {{ project_name }}_couchdb curl -sf"
      USER="{{ couchdb_admin_user }}"
      PASS="{{ couchdb_admin_password }}"
      created=0
      for db in _users _replicator _global_changes {{ couchdb_obsidian_db }}; do
        code=$(docker exec {{ project_name }}_couchdb \
          curl -so /dev/null -w "%{http_code}" \
          -X PUT "http://${USER}:${PASS}@localhost:5984/${db}")
        if [ "$code" = "201" ]; then
          echo "created: ${db}"
          created=$((created + 1))
        elif [ "$code" = "412" ]; then
          echo "exists: ${db}"
        else
          echo "ERROR ${code} on ${db}" >&2
          exit 1
        fi
      done
      [ "$created" -gt 0 ] && echo "CHANGED" || echo "UNCHANGED"
    executable: /bin/bash
  register: couchdb_init
  changed_when: "'CHANGED' in couchdb_init.stdout"
  failed_when: couchdb_init.rc != 0
  become: true
  tags: [couchdb-init]

- name: Show CouchDB init result
  ansible.builtin.debug:
    msg: "{{ couchdb_init.stdout_lines }}"
  tags: [couchdb-init]
```

**Step 2: Vérifier YAML**

```bash
source .venv/bin/activate && python3 -c "import yaml; yaml.safe_load(open('roles/couchdb/tasks/main.yml'))" && echo OK
```

Expected: `OK`

**Step 3: Commit**

```bash
git add roles/couchdb/
git commit -m "feat(couchdb): new role for sese — CouchDB 3.3.3 backend Obsidian LiveSync"
```

---

## Task 7 : Ajouter CouchDB dans docker-compose-infra.yml.j2

**Files:**
- Modify: `roles/docker-stack/templates/docker-compose-infra.yml.j2`

**Step 1: Ajouter le service CouchDB après Qdrant et avant Caddy**

Après le bloc `qdrant:` (ligne ~116) et avant le commentaire `# === REVERSE PROXY ===`, ajouter :

```yaml
  couchdb:
    image: {{ couchdb_image }}
    container_name: {{ project_name }}_couchdb
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
    environment:
      COUCHDB_USER: "{{ couchdb_admin_user }}"
      COUCHDB_PASSWORD: "{{ couchdb_admin_password }}"
    volumes:
      - /opt/{{ project_name }}/data/couchdb:/opt/couchdb/data
      # Config local.d : fichiers .ini déployés par le rôle couchdb
      - /opt/{{ project_name }}/configs/couchdb:/opt/couchdb/etc/local.d:ro
    networks:
      - backend
    deploy:
      resources:
        limits:
          memory: {{ couchdb_memory_limit }}
          cpus: "{{ couchdb_cpu_limit }}"
        reservations:
          memory: {{ couchdb_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:5984/_up || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

**Pourquoi réseau `backend` (pas `frontend`) :**
- Caddy est sur `frontend` ET `backend` → peut atteindre `couchdb:5984`
- CouchDB n'a pas besoin d'accès direct à Internet
- Même pattern que PostgreSQL, Redis, Qdrant

**Step 2: Vérifier Jinja2**

```bash
source .venv/bin/activate && python3 -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('.'))
t = env.get_template('roles/docker-stack/templates/docker-compose-infra.yml.j2')
print('Jinja2 OK')
" && echo OK
```

Expected: `Jinja2 OK`

**Step 3: Commit**

```bash
git add roles/docker-stack/templates/docker-compose-infra.yml.j2
git commit -m "feat(docker-stack): add CouchDB 3.3.3 to infra stack (backend network)"
```

---

## Task 8 : Corriger le Caddyfile.j2

**Files:**
- Modify: `roles/caddy/templates/Caddyfile.j2`

**Problèmes à corriger :**
1. `reverse_proxy {{ vpn_tailscale_ip }}:5984` → `reverse_proxy couchdb:5984` (interne Docker)
2. Supprimer les headers CORS du bloc Caddy (cause double headers → sync mobile cassée)
3. Garder uniquement les headers de sécurité standards

**Step 1: Remplacer le bloc CouchDB dans Caddyfile.j2**

Localiser le bloc actuel (après Sure) :
```caddyfile
# === CouchDB (Obsidian LiveSync) — Public HTTPS, auth CouchDB ===
...
{{ obsidian_subdomain }}.{{ domain_name }} {
{% if couchdb_vpn_enforce | default(false) | bool %}
    @blocked_couch not client_ip {{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }}
    error @blocked_couch 403
{% endif %}
    reverse_proxy {{ vpn_tailscale_ip }}:{{ couchdb_port | default(5984) }} {
        header_up Host {host}
    }
    header {
        Access-Control-Allow-Origin *
        Access-Control-Allow-Methods "GET, PUT, POST, HEAD, DELETE, OPTIONS"
        Access-Control-Allow-Headers "accept, authorization, content-type, origin, referer, x-csrf-token"
        Access-Control-Allow-Credentials true
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        -Server
    }
}
{% endif %}
```

Remplacer par :
```caddyfile
# === CouchDB (Obsidian LiveSync) — Public HTTPS, auth CouchDB ===
# CRITIQUE : PAS de headers CORS ici — géré uniquement dans couchdb-local.ini.
# Double CORS (Caddy + CouchDB) = headers dupliqués → sync mobile silencieusement cassée.
# CouchDB sur réseau backend Docker — Caddy l'atteint via le nom de conteneur.
{% if obsidian_subdomain | default('') | length > 0 %}
{{ obsidian_subdomain }}.{{ domain_name }} {
{% if couchdb_vpn_enforce | default(false) | bool %}
    # Mode VPN-only : restreindre aux IPs Tailscale + gateway Docker (HTTP/3 QUIC)
    @blocked_couch not client_ip {{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }}
    error @blocked_couch 403
{% endif %}
    reverse_proxy couchdb:{{ couchdb_port | default(5984) }}
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        -Server
    }
}
{% endif %}
```

**Step 2: Vérifier aucun doublon CORS**

```bash
grep -n "Access-Control" roles/caddy/templates/Caddyfile.j2
```

Expected: **aucun résultat** (CORS uniquement dans local.ini CouchDB)

**Step 3: Commit**

```bash
git add roles/caddy/templates/Caddyfile.j2
git commit -m "fix(caddy): CouchDB → container name + remove CORS headers (CORS in local.ini only)"
```

---

## Task 9 : Mettre à jour playbooks/site.yml

**Files:**
- Modify: `playbooks/site.yml`

**Step 1: Ajouter le rôle couchdb en Phase 2**

Après `qdrant` et avant `caddy` :

```yaml
    # Phase 2 — Données & Reverse Proxy
    - role: postgresql
      tags: [postgresql, phase2]
    - role: redis
      tags: [redis, phase2]
    - role: qdrant
      tags: [qdrant, phase2]
    - role: couchdb          # ← AJOUTER ICI
      tags: [couchdb, phase2]
    - role: caddy
      tags: [caddy, phase2]
```

**Step 2: Vérifier YAML**

```bash
source .venv/bin/activate && python3 -c "import yaml; yaml.safe_load(open('playbooks/site.yml'))" && echo OK
```

Expected: `OK`

---

## Task 10 : Corriger les URLs collector (Tailscale → public HTTPS)

**Files:**
- Modify: `roles/obsidian-collector/defaults/main.yml`
- Modify: `roles/obsidian-collector-pi/defaults/main.yml`

**Problème :** Les collectors utilisent `http://{{ vpn_tailscale_ip }}:5984` (Tailscale cross-server). Désormais CouchDB est sur Sese-AI → utiliser l'URL publique.

**Step 1: Modifier roles/obsidian-collector/defaults/main.yml**

```yaml
# Avant :
obsidian_collector_couchdb_url: "http://{{ vpn_tailscale_ip }}:5984"

# Après :
obsidian_collector_couchdb_url: "https://{{ obsidian_subdomain }}.{{ domain_name }}"
```

**Step 2: Modifier roles/obsidian-collector-pi/defaults/main.yml**

Même correction :
```yaml
obsidian_collector_couchdb_url: "https://{{ obsidian_subdomain }}.{{ domain_name }}"
```

**Pourquoi l'URL publique et pas un accès direct :**
- Sese-AI collector : loopback via Caddy (même serveur) — TLS valide, auth CouchDB
- Pi collector : réseau différent — DOIT passer par l'URL publique
- CouchDB n'expose PAS de port sur l'hôte (sécurité, conformité PRD)

**Step 3: Commit**

```bash
git add roles/obsidian-collector/defaults/main.yml roles/obsidian-collector-pi/defaults/main.yml
git commit -m "fix(collectors): use public HTTPS URL for CouchDB (was Tailscale IP)"
```

---

## Task 11 : Mettre à jour group_vars/all/main.yml

**Files:**
- Modify: `inventory/group_vars/all/main.yml`

**Step 1: Vérifier/corriger la section OBSIDIAN VAULT**

La section actuelle contient des variables correctes (`obsidian_subdomain: "biki"`, etc.) mais le commentaire d'architecture mentionne encore Seko-VPN. Corriger le commentaire :

```yaml
# === OBSIDIAN VAULT ===
# CouchDB backend pour obsidian-livesync (sync iOS + PC en temps réel)
# CouchDB sur Sese-AI (réseau backend Docker, même stack que Caddy)
# Exposé publiquement via HTTPS Caddy (pas de restriction VPN) pour sync iOS sans Tailscale
obsidian_subdomain: "biki"
couchdb_db_name: "obsidian-vault"
couchdb_obsidian_user: "obsidian"      # utilisateur applicatif (legacy — admin utilisé directement)
couchdb_memory_limit: "512M"
obsidian_git_repo: "git@github-seko:Mobutoo/obsidian-vault.git"
obsidian_collector_max_session_messages: 20
couchdb_vpn_enforce: false
```

**Note :** Ajouter les secrets dans le vault :
```bash
ansible-vault edit inventory/group_vars/all/secrets.yml
# Ajouter :
# vault_couchdb_admin_user: "admin"
# vault_couchdb_admin_password: "<openssl rand -base64 32 | tr -d '='>"
```

---

## Task 12 : Mettre à jour le Makefile

**Files:**
- Modify: `Makefile`

**Step 1: Remplacer les targets Obsidian par CouchDB**

```makefile
.PHONY: deploy-couchdb
deploy-couchdb: ## Deployer CouchDB Obsidian LiveSync sur Sese-AI
	@echo "$(GREEN)>>> Deploying CouchDB on Sese-AI...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/site.yml -e "target_env=prod" --tags couchdb --diff

.PHONY: deploy-couchdb-init
deploy-couchdb-init: ## Initialiser les bases CouchDB (après docker-stack)
	@echo "$(GREEN)>>> Initializing CouchDB system databases...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/site.yml -e "target_env=prod" --tags couchdb-init --diff

.PHONY: deploy-obsidian-collectors
deploy-obsidian-collectors: ## Deployer les collectors Obsidian (Sese-AI + Pi)
	@echo "$(GREEN)>>> Deploying Obsidian collectors on Sese-AI + Pi...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/site.yml --tags obsidian-collector -e "target_env=prod" --diff
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags obsidian-collector-pi --diff
```

Supprimer l'ancien target `deploy-obsidian` (ciblait Seko-VPN).

---

## Task 13 : Mettre à jour docs/ARCHITECTURE.md

**Files:**
- Modify: `docs/ARCHITECTURE.md`

**Step 1: Corriger la table DNS (section 0)**

```markdown
| `biki.ewutelo.cloud` | 137.74.114.167 | Sese-AI Caddy → couchdb:5984 (Docker interne) | **Public** (auth CouchDB) |
```

**Step 2: Retirer CouchDB du tableau Seko-VPN (section 8.1)**

Supprimer la ligne :
```
| **CouchDB** | **3.3.3** | **5984** | **Backend sync Obsidian LiveSync** |
```

**Step 3: Ajouter CouchDB dans le tableau Sese-AI (section 8.1)**

```markdown
| **Sync notes** | CouchDB | 3.3.3 | 5984 | backend interne |
```

**Step 4: Corriger le schéma ASCII (section 8.2)**

- Retirer CouchDB du bloc Seko-VPN
- Ajouter CouchDB dans le bloc Sese-AI (section DONNÉES)

**Step 5: Corriger la section 8.5**

Remplacer l'architecture actuelle (Seko-VPN + Tailscale) par :

```
iPhone 13 (iOS)                    PC Windows (VPN ou non)
  Obsidian App                       Obsidian App
  livesync plugin                    livesync plugin
       │ HTTPS :443                       │ HTTPS :443
       ▼                                  ▼
biki.ewutelo.cloud ◄────── Caddy (Sese-AI, réseau backend) ──────►
(Public — auth CouchDB)    reverse_proxy couchdb:5984
                                  │ réseau Docker backend (172.20.2.0/24)
                                  ▼
                     CouchDB 3.3.3 :5984 (container javisi_couchdb)
                     /opt/javisi/data/couchdb/
                     DB: obsidian-vault
                     CORS: app://obsidian.md,capacitor://localhost
                          │
                     cron 02:00 (sur hôte sese)
                          │
                     dump-vault.py → https://biki.ewutelo.cloud → dump
                          │
                     /opt/javisi/data/obsidian-vault/ (.md files)
                          │
                     git commit → github-seko:Mobutoo/obsidian-vault.git
```

---

## Task 14 : Commit final et push

**Step 1: Vérifier lint**

```bash
source .venv/bin/activate && make lint
```

Expected: `All linting passed`

**Step 2: Staged commit global**

```bash
git add playbooks/site.yml Makefile docs/ARCHITECTURE.md \
    inventory/group_vars/all/main.yml \
    roles/caddy/templates/Caddyfile.j2 \
    roles/obsidian-collector/defaults/main.yml \
    roles/obsidian-collector-pi/defaults/main.yml
git commit -m "fix(obsidian): migrate CouchDB from Seko-VPN to sese (VPAI)

- CouchDB now on sese backend network (reverse_proxy couchdb:5984)
- Remove CORS headers from Caddy (CORS only in local.ini — no double headers)
- Fix CORS origins: specific (app://obsidian.md,capacitor://localhost)
- Fix collector CouchDB URL: Tailscale → public HTTPS biki.ewutelo.cloud
- Update site.yml: add couchdb role in Phase 2
- Update Makefile: deploy-couchdb + deploy-couchdb-init targets
- Update ARCHITECTURE.md: correct section 8.5 and ASCII schema

Ref: Seko-VPN/docs/08-prd-obsidian-livesync-sese.md (section 11)"
```

**Step 3: Push**

```bash
git push origin main
```

---

## Ordre de déploiement (post-implémentation)

```bash
# 1. Ajouter secrets dans vault
ansible-vault edit inventory/group_vars/all/secrets.yml
# vault_couchdb_admin_user: "admin"
# vault_couchdb_admin_password: "$(openssl rand -base64 32 | tr -d '=')"

# 2. Déployer CouchDB (config dirs + local.ini)
make deploy-couchdb

# 3. Déployer Caddy (nouveau bloc biki.ewutelo.cloud)
make deploy-role ROLE=caddy ENV=prod

# 4. Déployer le docker stack (Phase A : infra avec CouchDB)
make deploy-role ROLE=docker-stack ENV=prod

# 5. Initialiser les bases CouchDB (après container up)
make deploy-couchdb-init

# 6. Vérifier
curl https://biki.ewutelo.cloud/_up
# → {"status":"ok"}
curl -u admin:PASSWORD https://biki.ewutelo.cloud/_all_dbs
# → ["_global_changes","_replicator","_users","obsidian-vault"]

# 7. Déployer les collectors (après validation CouchDB)
make deploy-obsidian-collectors
```

---

## Tests de validation

```bash
# CouchDB health
curl https://biki.ewutelo.cloud/_up
# → {"status":"ok"}

# CORS mobile (Obsidian iOS)
curl -v -H "Origin: app://obsidian.md" \
  -H "Access-Control-Request-Method: PUT" \
  -X OPTIONS https://biki.ewutelo.cloud/obsidian-vault
# → 200 OK + Access-Control-Allow-Origin: app://obsidian.md
# → PAS de duplication du header (une seule valeur)

# Auth CouchDB
curl -u admin:WRONG_PASS https://biki.ewutelo.cloud/_all_dbs
# → 401 Unauthorized

# Accès sans auth
curl https://biki.ewutelo.cloud/obsidian-vault
# → 401 Unauthorized (require_valid_user=true)
```
