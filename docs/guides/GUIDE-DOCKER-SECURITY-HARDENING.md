# Guide — Docker Security Hardening

**Projet** : VPAI (template portable)
**Version** : v2.4.0 — Audit securite complet
**Applicable a** : Tout projet Docker Compose auto-heberge

---

## 1. Principe de moindre privilege

### 1.1 Capabilities

```yaml
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
cap_add:
  # Ajouter UNIQUEMENT les capabilities necessaires
  - CHOWN      # si le container change l'ownership de fichiers
  - SETGID     # si le container change de groupe
  - SETUID     # si le container change d'utilisateur
  - DAC_OVERRIDE  # si le container ecrit dans des volumes root-owned
  - FOWNER     # si le container modifie des permissions
  - NET_BIND_SERVICE  # si le container bind sur port < 1024 (ex: Caddy 80/443)
  - SYS_PTRACE  # si le container lit /proc (ex: node_exporter)
  - DAC_READ_SEARCH  # si le container lit des fichiers sans permission
```

**Regle** : Commencer avec `cap_drop: ALL`, ajouter une par une en testant. Si le container crash avec `Operation not permitted`, identifier la capability manquante via `strace` ou les logs.

### 1.2 Utilisateur non-root

```yaml
# Images qui le supportent (UID connu et stable)
user: "65534:65534"   # nobody:nobody (VictoriaMetrics, Prometheus)
user: "1000:1000"     # application user (MinIO, certains Node.js)

# Prerequis : chown les donnees existantes
- name: Fix data directory ownership
  ansible.builtin.file:
    path: "{{ data_dir }}"
    owner: "65534"
    group: "65534"
    recurse: true
  become: true
```

**Piege** : Changer le user sur un container existant ne suffit pas. Les fichiers de donnees appartiennent a l'ancien user (souvent root). `recurse: true` dans la tache Ansible est obligatoire.

**Quand ne pas forcer non-root** : Images tierces (NocoDB, Plane) qui ne documentent pas de support non-root. Preferer `no-new-privileges` + `cap_drop: ALL` comme mitigation.

### 1.3 Filesystem read-only

```yaml
read_only: true
tmpfs:
  - /tmp:size=10M       # quasi universel — toute app ecrit dans /tmp
  - /run:size=1M        # HAProxy, nginx, supervisord (PID files)
  - /data-alloy:size=50M  # Grafana Alloy etat interne
```

**Methode de diagnostic** :
1. Activer `read_only: true`
2. Demarrer le container, observer les logs
3. Chercher : `Read-only file system`, `mkdir ... failed`, `can't create`
4. Ajouter un tmpfs pour chaque path identifie
5. Retester

**Containers valides en production** : Redis, VictoriaMetrics, Alloy, docker-socket-proxy.

**Containers incompatibles read_only** : LiteLLM (ecrit des migrations dans site-packages au demarrage), NocoDB, Plane (images tierces).

---

## 2. Docker Socket Proxy

### 2.1 Pourquoi

Le socket Docker (`/var/run/docker.sock`) donne un acces **root equivalent** a l'hote. Un container compromis avec le socket peut :
- Creer un container privilege avec tous les volumes de l'hote
- Executer des commandes arbitraires sur l'hote
- Exfiltrer des secrets depuis d'autres containers

### 2.2 Architecture

```
                  +------------------+
                  | Docker Socket    |
                  | (/var/run/...)   |
                  +--------+---------+
                           |
              +------------+------------+
              |                         |
    +---------v----------+    +---------v-----------+
    | socket-proxy       |    | OpenClaw            |
    | (HAProxy read-only)|    | (DooD: besoin write)|
    | POST=0             |    | socket direct :ro   |
    +--------+-----------+    +---------------------+
             |
    +--------+--------+--------+
    |        |        |        |
  cAdvisor Alloy    DIUN    (futurs)
  (metrics) (logs) (updates)
```

### 2.3 Configuration socket-proxy

```yaml
socket-proxy:
  image: tecnativa/docker-socket-proxy:v0.4.2
  restart: unless-stopped
  read_only: true
  tmpfs:
    - /run:size=1M
    - /tmp:size=5M    # CRITIQUE: entrypoint genere haproxy.cfg dans /tmp
  security_opt:
    - no-new-privileges:true
  cap_drop:
    - ALL
  environment:
    POST: "0"          # Bloque TOUTES les ecritures
    CONTAINERS: "1"    # Requis par cAdvisor, Alloy, DIUN
    IMAGES: "1"        # Requis par DIUN (detection mises a jour)
    INFO: "1"          # Requis par cAdvisor (info Docker)
    VERSION: "1"       # Requis par cAdvisor
    EVENTS: "1"        # Requis par Alloy (decouverte containers)
    NETWORKS: "1"      # Requis par Alloy (labels reseau)
    PING: "1"          # Healthcheck
    # Tout le reste a 0
    AUTH: "0"
    BUILD: "0"
    COMMIT: "0"
    EXEC: "0"          # CRITIQUE: empeche docker exec via le proxy
    SECRETS: "0"
    VOLUMES: "0"
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
  networks:
    - monitoring       # Reseau interne, accessible par les consommateurs
  healthcheck:
    test: ["CMD-SHELL", "wget -q --spider http://127.0.0.1:2375/_ping || exit 1"]
```

### 2.4 Migration des consommateurs

**cAdvisor** : Variable d'environnement
```yaml
environment:
  DOCKER_HOST: "tcp://socket-proxy:2375"
# Retirer le volume docker.sock
# Garder /sys et /var/lib/docker pour les metriques cgroup
```

**Grafana Alloy** : Configuration HCL
```hcl
discovery.docker "containers" {
  host = "tcp://socket-proxy:2375"   # etait unix:///var/run/docker.sock
}
loki.source.docker "containers" {
  host = "tcp://socket-proxy:2375"   # etait unix:///var/run/docker.sock
}
```

**DIUN** : Variable d'environnement
```yaml
environment:
  DOCKER_HOST: "tcp://socket-proxy:2375"
networks:
  - monitoring  # Pour atteindre socket-proxy
  - egress      # Pour verifier les registres + notifications
```

### 2.5 Exceptions documentees

Le socket direct reste necessaire pour :
- **OpenClaw** : Docker-outside-of-Docker (DooD). Spawn des sandbox containers via dockerode SDK. Necessite POST /containers/create, start, stop, delete.
- **Future CI runner** : Si un runner Docker est ajoute a la stack.

Documenter chaque exception dans le docker-compose avec un commentaire expliquant le besoin.

---

## 3. Secrets et env_file

### 3.1 Regles

1. **Jamais de secrets dans docker-compose.yml** : Utiliser `env_file` pointe vers un fichier template .j2
2. **env_file lu cote hote** : Owner = utilisateur qui lance `docker compose`, pas le UID du container
3. **Mode 0600** : Seul le proprietaire peut lire le fichier de secrets
4. **Ansible Vault** : Toutes les valeurs sensibles dans `secrets.yml` chiffre

### 3.2 Pattern env_file

```yaml
# docker-compose.yml
services:
  myapp:
    env_file:
      - /opt/{{ project_name }}/configs/myapp/myapp.env

# Ansible task
- name: Deploy myapp env file
  ansible.builtin.template:
    src: myapp.env.j2
    dest: "/opt/{{ project_name }}/configs/myapp/myapp.env"
    owner: "{{ prod_user }}"    # PAS le UID du container!
    group: "{{ prod_user }}"
    mode: "0600"
  become: true
  notify: Restart myapp stack

# Handler CRITIQUE
- name: Restart myapp stack
  community.docker.docker_compose_v2:
    project_src: "{{ compose_dir }}"
    state: present
    recreate: always     # PAS 'restart' — restart ne recharge PAS l'env_file
```

**Piege** : `docker compose restart` ne relit PAS les env_file. Seul `recreate: always` (qui fait un `docker compose up -d --force-recreate`) recharge les variables d'environnement.

---

## 4. Caddy Security Headers

### 4.1 Snippet DRY

```caddyfile
(security_headers) {
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()"
        -Server
    }
}

# Usage dans chaque site block
mon.domaine.com {
    import security_headers
    reverse_proxy mon-service:8080
}
```

### 4.2 Override pour le domaine principal

```caddyfile
domaine.com {
    import security_headers
    # Override : HSTS avec preload + DENY framing
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    header X-Frame-Options "DENY"
}
```

**Principe** : Les headers individuels apres l'import ecrasent ceux du snippet (dernier gagne pour un meme nom de header).

---

## 5. Reseaux Docker

### 5.1 Segmentation

| Reseau | Internal | Usage |
|---|---|---|
| `frontend` | Non | Reverse proxy, Grafana (acces externe) |
| `backend` | **Oui** | BDD, apps, communication inter-services |
| `monitoring` | **Oui** | Observabilite (cAdvisor, VM, Loki, Alloy, socket-proxy) |
| `egress` | Non | Services necessitant Internet (n8n, LiteLLM, OpenClaw, DIUN) |
| `sandbox` | **Oui** | Containers ephemeres isoles (OpenClaw sandboxes) |

### 5.2 Regles

1. **Tout container sur reseau(x) explicite(s)** : Jamais le default Docker Compose
2. **Internal = true** pour les reseaux sans besoin Internet
3. **Minimum de reseaux par service** : Seuls ceux necessaires a la communication
4. **Reseaux crees en amont** par le role Ansible `docker`, declares `external: true` dans les compose files

---

## 6. Healthchecks

### 6.1 Patterns par type de service

```yaml
# HTTP endpoint (prefere)
healthcheck:
  test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:8080/healthz || exit 1"]

# TCP port check (si pas d'endpoint health)
healthcheck:
  test: ["CMD-SHELL", "bash -c ':> /dev/tcp/localhost/6333' || exit 1"]

# Process check (dernier recours — ne valide pas l'etat fonctionnel)
healthcheck:
  test: ["CMD-SHELL", "kill -0 1 || exit 1"]

# Commande specifique (BDD)
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U postgres"]
```

**Piege VPS 8GB** : Eviter les healthchecks lourds (ex: `celery inspect ping` fait un roundtrip complet via Redis → timeout sur serveur contraint). Preferer `kill -0 1` pour les workers.

---

## 7. Checklist pre-deploy

- [ ] `cap_drop: ALL` + `no-new-privileges:true` sur chaque service
- [ ] `cap_add` minimal et documente
- [ ] Pas de `:latest` ni `:stable` — images pinnees dans versions.yml
- [ ] `env_file` pour les secrets, owner = prod_user, mode 0600
- [ ] Reseaux explicites sur chaque service
- [ ] Healthcheck sur chaque service
- [ ] Limites memoire/CPU definies
- [ ] `restart: unless-stopped`
- [ ] Docker socket monte UNIQUEMENT via socket-proxy (sauf exception documentee)
- [ ] `read_only: true` quand possible (avec tmpfs pour paths writables)
- [ ] Log rotation configuree dans daemon.json (max-size 10m, max-file 3)
- [ ] PGPASSWORD dans tous les `docker exec psql` commands
