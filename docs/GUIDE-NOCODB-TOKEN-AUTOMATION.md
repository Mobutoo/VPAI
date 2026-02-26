# GUIDE — Automatisation du token NocoDB (NC_API_TOKEN)

## Contexte

NocoDB expose une API REST utilisée par OpenClaw et n8n (variable `NOCODB_API_TOKEN`).
Ce token doit exister avant que ces services puissent interagir avec NocoDB.

Actuellement (session 2026-02-26) le token est créé **manuellement** via l'UI, puis stocké
dans `vault_nocodb_api_token`. Ce guide documente les deux voies d'automatisation.

---

## Procédure manuelle actuelle (Option A — suffisant)

```bash
# 1. Se connecter via Tailscale VPN
# 2. Ouvrir https://hq.ewutelo.cloud
# 3. Team & Auth → API Tokens → New Token → copier la valeur

# 4. Mettre à jour le vault
ansible-vault edit inventory/group_vars/all/secrets.yml
# → remplacer vault_nocodb_api_token: "placeholder" par la vraie valeur

# 5. Propager dans openclaw.env et n8n.env
make deploy-role ROLE=nocodb ENV=prod
```

---

## Option B-1 — Token statique via `NC_API_TOKEN` (env var)

NocoDB v0.90+ supporte la variable `NC_API_TOKEN` qui définit un token statique permanent,
sans passer par l'UI. C'est la voie **la plus simple**.

### À vérifier : compatibilité v0.301.2

```bash
# Tester si NC_API_TOKEN est bien supporté après ajout dans nocodb.env
docker exec javisi_nocodb wget -qO- \
  --header "xc-token: TON_TOKEN" \
  http://127.0.0.1:8080/api/v1/auth/user/me 2>&1
# Résultat attendu : JSON avec les infos user (pas 401)
```

### Implémentation

**1. Générer un token fort :**
```bash
openssl rand -hex 32
# → ex: a3f9e1c7b4d2e8f6a1b9c3d5e7f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0c2d4e6f8
```

**2. Ajouter au vault :**
```bash
ansible-vault edit inventory/group_vars/all/secrets.yml
# → vault_nocodb_api_token: "a3f9e1c7b4d2..."
```

**3. Activer dans `roles/nocodb/templates/nocodb.env.j2` :**

Décommenter (ou ajouter) la ligne `NC_API_TOKEN` :
```bash
# {{ ansible_managed }}
NC_DB=pg://postgresql:5432?u=nocodb&p={{ postgresql_password }}&d=nocodb
NC_PUBLIC_URL=https://{{ nocodb_subdomain }}.{{ domain_name }}
NC_AUTH_JWT_SECRET={{ nocodb_jwt_secret }}
NC_TOOL_DIR=/data
NC_DISABLE_TELE=true

# Token statique pour l'intégration OpenClaw / n8n (généré via : openssl rand -hex 32)
NC_API_TOKEN={{ nocodb_api_token }}
```

**4. Redéployer :**
```bash
make deploy-role ROLE=nocodb ENV=prod
```

### Avantages / Inconvénients

| ✅ Avantages | ⚠️ Inconvénients |
|---|---|
| Entièrement déclaratif (Ansible-native) | Token permanent (rotation = redeploy) |
| Aucune interaction UI requise | NC_API_TOKEN exposé dans les logs diff |
| Reproductible premier déploiement | À vérifier : support dans v0.301.2 |
| Pas de setup admin préalable | |

---

## Option B-2 — Token dynamique via Ansible `uri` module

Approche robuste qui **appelle l'API NocoDB** pour créer le token programmatiquement.
Requiert un compte admin NocoDB (setup UI ou env vars admin).

### Prérequis : créer l'admin de manière headless

NocoDB v0.90+ supporte `NC_ADMIN_EMAIL` et `NC_ADMIN_PASSWORD` pour créer l'admin
au premier démarrage sans passer par l'UI.

**Ajouter au vault :**
```yaml
vault_nocodb_admin_email: "admin@ewutelo.cloud"
vault_nocodb_admin_password: "mot-de-passe-fort"
```

**Ajouter à `inventory/group_vars/all/main.yml` :**
```yaml
# NocoDB (pipeline production IA manga)
nocodb_jwt_secret: "{{ vault_nocodb_jwt_secret }}"
nocodb_api_token: "{{ vault_nocodb_api_token }}"
nocodb_admin_email: "{{ vault_nocodb_admin_email }}"
nocodb_admin_password: "{{ vault_nocodb_admin_password }}"
```

**Ajouter à `roles/nocodb/templates/nocodb.env.j2` :**
```bash
# Credentials admin pour setup headless (premier démarrage uniquement)
# NocoDB crée l'admin si aucun user n'existe encore.
NC_ADMIN_EMAIL={{ nocodb_admin_email }}
NC_ADMIN_PASSWORD={{ nocodb_admin_password }}
```

### Tâches Ansible à ajouter dans `roles/nocodb/tasks/provision-token.yml`

```yaml
---
# nocodb/tasks/provision-token.yml
# Provisionne le NC_API_TOKEN via l'API NocoDB.
# Pré-requis : NocoDB doit être healthy (start_period écoulé).
# À appeler via include_tasks depuis main.yml avec un tag dédié.

- name: Wait for NocoDB to be healthy before token provisioning
  ansible.builtin.command:
    cmd: >-
      docker inspect --format='{{ '{{' }}.State.Health.Status{{ '}}' }}'
      {{ project_name }}_nocodb
  register: nocodb_health
  changed_when: false
  retries: 20
  delay: 10
  until: nocodb_health.stdout | default('') == 'healthy'
  become: true

- name: Sign in to NocoDB as admin to get JWT token
  ansible.builtin.uri:
    url: "http://localhost:8080/api/v1/auth/user/signin"
    method: POST
    body_format: json
    body:
      email: "{{ nocodb_admin_email }}"
      password: "{{ nocodb_admin_password }}"
    headers:
      Content-Type: "application/json"
    status_code: [200]
    return_content: true
  register: nocodb_signin
  no_log: true
  # NOTE: le module uri tourne en localhost sur le controller, pas sur le VPS.
  # Pour appeler l'API NocoDB depuis le controller, il faudrait :
  # a) Exposer NocoDB publiquement (non — VPN-only)
  # b) Utiliser delegate_to + SSH tunnel
  # c) Lancer la tâche uri via docker exec curl (voir ci-dessous)
  #
  # ALTERNATIVE RECOMMANDÉE : utiliser community.docker.docker_container_exec
  # avec curl pour appeler l'API depuis l'intérieur du réseau Docker.

# Alternative via docker exec curl (API appelée depuis le réseau interne)
- name: Sign in to NocoDB via docker exec (internal network)
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: |
      set -euo pipefail
      docker exec {{ project_name }}_nocodb \
        wget -qO- \
        --header "Content-Type: application/json" \
        --post-data '{"email":"{{ nocodb_admin_email }}","password":"{{ nocodb_admin_password }}"}' \
        http://127.0.0.1:8080/api/v1/auth/user/signin 2>&1
  register: nocodb_signin_raw
  changed_when: false
  no_log: true
  become: true

- name: Parse JWT from signin response
  ansible.builtin.set_fact:
    nocodb_jwt: "{{ (nocodb_signin_raw.stdout | from_json).token }}"
  no_log: true

- name: Create NocoDB API token via internal API
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: |
      set -euo pipefail
      docker exec {{ project_name }}_nocodb \
        wget -qO- \
        --header "Content-Type: application/json" \
        --header "xc-auth: {{ nocodb_jwt }}" \
        --post-data '{"description":"ansible-automation-{{ ansible_date_time.date }}"}' \
        http://127.0.0.1:8080/api/v1/api-token 2>&1
  register: nocodb_token_raw
  changed_when: true
  no_log: true
  become: true

- name: Parse API token from response
  ansible.builtin.set_fact:
    nocodb_provisioned_token: "{{ (nocodb_token_raw.stdout | from_json).token }}"
  no_log: true

# Le token ne peut pas être écrit directement dans le vault (vault est chiffré localement).
# → Affichage pour stockage manuel OU écriture dans un fichier de staging.
- name: Display provisioned token for vault storage
  ansible.builtin.debug:
    msg: |
      ============================================================
      NC_API_TOKEN provisionné avec succès.
      Stocke cette valeur dans le vault et redéploie :

        ansible-vault edit inventory/group_vars/all/secrets.yml
        → vault_nocodb_api_token: "{{ nocodb_provisioned_token }}"

        make deploy-role ROLE=nocodb ENV=prod
      ============================================================
  # no_log: false intentionnel — le token doit être visible pour stockage
```

### Intégrer dans `roles/nocodb/tasks/main.yml`

```yaml
# À ajouter en fin de main.yml, conditionné sur une variable opt-in
- name: Provision NocoDB API token (one-shot — run only when token is absent)
  ansible.builtin.include_tasks: provision-token.yml
  when: nocodb_provision_token | default(false) | bool
  tags: [nocodb, nocodb-provision-token]
```

### Invocation ciblée

```bash
# Provisionner le token une seule fois après le premier setup
make deploy-role ROLE=nocodb ENV=prod EXTRA_VARS="nocodb_provision_token=true"

# OU via ansible-playbook directement
ansible-playbook playbooks/site.yml \
  --tags nocodb-provision-token \
  -e "nocodb_provision_token=true"
```

---

## Comparaison des options

| Critère | Manuelle (A) | Static NC_API_TOKEN (B-1) | Dynamic API (B-2) |
|---|---|---|---|
| Complexité | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| Automation | ❌ | ✅ | ✅ |
| Premier deploy | UI requise | Aucune UI | UI ou `NC_ADMIN_EMAIL` |
| Token statique | Oui | Oui | Non (créé en DB) |
| Rotation token | Manuelle | Redeploy | Tâche dédiée |
| Compatible v0.301.2 | ✅ | À vérifier | ✅ |

---

## REX & Pièges

### Piège 1 : `NC_API_TOKEN` vs token DB

`NC_API_TOKEN` (env var) = token statique global, bypass la DB.
Token créé via UI/API = stocké en DB, lié à un user, révocable individuellement.
Pour l'intégration n8n/OpenClaw, les deux fonctionnent — préférer env var si B-1 est supporté.

### Piège 2 : NocoDB ne réinitialise pas les tokens admin à chaque restart

Si `NC_ADMIN_EMAIL/PASSWORD` sont définis mais qu'un admin existe déjà en DB,
NocoDB ignore ces vars. Les credentials sont ceux créés au **premier démarrage**.
→ Ne jamais supprimer la DB NocoDB sans avoir noté les credentials admin.

### Piège 3 : Token visible dans les logs Ansible

Les tâches de provisioning utilisent `no_log: true` pour masquer JWT et token.
La tâche de debug finale est intentionnellement `no_log: false` pour afficher le token.
→ Ce log est visible dans l'output ansible mais **pas dans les fichiers de log persistants**
si `log_path` n'est pas configuré dans `ansible.cfg`.

### Piège 4 : Appel API depuis le controller vs réseau Docker

Le module `uri` d'Ansible s'exécute sur le **controller** (workstation Pi),
pas sur le VPS. NocoDB étant VPN-only, l'appel direct échouerait.
→ Utiliser `docker exec ... wget` via `ansible.builtin.shell` pour rester
dans le réseau Docker interne (172.20.2.x → backend).

---

## Statut implementation

- [x] Option A : documentée et opérationnelle
- [ ] Option B-1 : à tester (vérifier support `NC_API_TOKEN` en v0.301.2)
- [ ] Option B-2 : tâches écrites dans ce guide, à intégrer dans le role si besoin
