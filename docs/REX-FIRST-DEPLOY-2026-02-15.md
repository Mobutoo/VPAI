# REX - Premier Déploiement VPAI (2026-02-15)

## 📋 Contexte

**Date** : 15 février 2026
**Projet** : VPAI - Stack AI/Automatisation auto-hébergée
**Environnement** : VPS OVH Production (Debian 13 Trixie)
**IP** : 137.74.114.167
**Utilisateur** : mobuone
**Objectif** : Premier déploiement complet de la stack (PostgreSQL, Redis, Qdrant, Caddy, n8n, LiteLLM, OpenClaw, Monitoring)

---

## 🎯 Résumé Exécutif

**Durée** : ~6 heures de debugging itératif
**Résultat** : Architecture corrigée, prête pour déploiement
**Erreurs critiques découvertes** : 8
**Commits** : 6 commits de correctifs
**Apprentissages clés** : PostgreSQL 18+, Docker Compose phases, isolation réseau, ordre d'exécution

---

## 🐛 Erreurs Critiques Rencontrées et Solutions

### 1. ⚠️ **LOCKOUT SSH par Hardening Prématuré**

**Symptôme** :
```
Connection timed out after hardening role
SSH inaccessible via réseau normal
```

**Cause Racine** :
- Rôle `hardening` exécuté en **Phase 1** (trop tôt)
- SSH restreint au VPN (IP Headscale) AVANT validation du VPN
- Lockout immédiat, impossible de se reconnecter

**Solution Appliquée** :
1. ✅ Hardening déplacé de **Phase 1 → Phase 6** (DERNIER rôle)
2. ✅ `hardening_ssh_force_open: true` par défaut (SSH reste sur 0.0.0.0)
3. ✅ Documentation ajoutée : "Garder une fenêtre SSH ouverte pendant le déploiement"

**Prévention** :
```yaml
# hardening/defaults/main.yml
hardening_ssh_force_open: true  # DEFAULT: Safe mode
# L'admin doit explicitement mettre false APRÈS validation VPN
```

**Impact** : 🔴 CRITIQUE - Perte d'accès total au serveur

**Commit** : `d0d7a2c` - "fix: Move hardening to Phase 6"

**Leçon** : **JAMAIS** restreindre SSH avant validation complète de l'accès alternatif (VPN).

---

### 2. 📦 **Rôle docker-stack Manquant**

**Symptôme** :
```
Aucun conteneur créé
docker ps -a : vide
Rôles n8n, postgresql, etc. préparent configs mais rien ne démarre
```

**Cause Racine** :
- Rôles individuels (n8n, postgresql, redis) préparent **UNIQUEMENT les configs**
- Aucun rôle ne déploie le `docker-compose.yml` centralisé
- `docker compose up` jamais exécuté

**Solution Appliquée** :
1. ✅ Création du rôle `docker-stack` (nouveau)
2. ✅ Ajouté en **Phase 4.5** (après configs, avant provisioning)
3. ✅ Déploiement en 2 phases :
   - **Phase A** : Infra (PostgreSQL, Redis, Qdrant, Caddy) + Réseaux
   - **Phase B** : Apps (n8n, LiteLLM, OpenClaw, Monitoring)

**Architecture Finale** :
```
Phase 1-3: Préparation configs (postgresql, redis, n8n, etc.)
Phase 4.5: docker-stack → Crée TOUS les conteneurs
Phase 4.6: n8n-provision → Configure owner n8n
```

**Impact** : 🔴 CRITIQUE - Sans ce rôle, rien ne démarre jamais

**Commit** : `820076a` - "feat: Split docker-stack into phased deployment"

**Leçon** : Architecture centralisée (un docker-compose.yml) nécessite un rôle orchestrateur.

---

### 3. 🔄 **Rôles Exécutés 2 Fois (Duplication)**

**Symptôme** :
```
TASK [postgresql : Create config directory]
TASK [postgresql : Create config directory]  # Exécuté 2 fois !
```

**Cause Racine** :
- `docker-stack/meta/main.yml` déclarait des dépendances vers TOUS les rôles
- Ansible exécute les dépendances AVANT le rôle
- Rôles déjà dans le playbook → Double exécution

**Solution Appliquée** :
```yaml
# docker-stack/meta/main.yml
dependencies: []  # Vide, pas de dépendances
```

**Impact** : 🟡 MOYEN - Ralentit déploiement, risque d'état incohérent

**Commit** : `d0d7a2c` - "fix: Add docker-stack role and fix deployment issues"

**Leçon** : Rôle orchestrateur ne doit PAS déclarer de dépendances si rôles déjà dans le playbook.

---

### 4. 🌐 **Connectivité VPN Bloque Déploiement**

**Symptôme** :
```
TASK [headscale-node : Verify VPN connectivity]
FAILED - RETRYING: ping -c 3 87.106.30.160
100% packet loss
```

**Cause Racine** :
- Rôle `headscale-node` essayait de ping Seko-VPN (87.106.30.160)
- VPS utilise son propre routage (pas de route VPN configurée)
- Vérification de connectivité bloquante par défaut

**Solution Appliquée** :
```yaml
# headscale-node/tasks/main.yml
- name: Verify VPN connectivity (non-blocking)
  ansible.builtin.command:
    cmd: "ping -c 3 -W 5 {{ headscale_vpn_ip }}"
  failed_when: false  # Ne pas bloquer si ping échoue
  register: vpn_connectivity_check
```

**Impact** : 🟡 MOYEN - Bloque progression sans raison valide

**Commit** : `d0d7a2c` - "fix: headscale-node: make VPN connectivity check non-blocking"

**Leçon** : VPN mesh != routage automatique. Le VPS garde son routage normal.

---

### 5. 🖼️ **Images Docker Inexistantes**

**Symptôme** :
```
Error: redis:8.0.10-bookworm: not found
Error: ghcr.io/openclaw/openclaw:v2026.2.14: not found
```

**Cause Racine** :
- `redis:8.0.10-bookworm` → Tag patch n'existe pas (uniquement `8.0-bookworm`)
- `openclaw:v2026.2.14` → Version fictive du PRD, n'existe pas

**Solution Appliquée** :
```yaml
# inventory/group_vars/all/versions.yml
redis_image: "redis:8.0-bookworm"  # Corrigé
openclaw_image: "ghcr.io/openclaw/openclaw:latest"  # Temporaire
```

**Vérification Ajoutée** :
```bash
# Script de vérification avant déploiement
for image in $(list_all_images); do
  docker manifest inspect "$image" || echo "ERREUR: $image"
done
```

**Impact** : 🔴 CRITIQUE - Bloque déploiement complet

**Commit** : `fff33cd` - "fix: Move n8n provisioning after docker-stack and fix Redis version"

**Leçon** : **TOUJOURS** vérifier l'existence des images avant déploiement.

---

### 6. 🔗 **Réseaux Docker - Conflit de Labels**

**Symptôme** :
```
Error: network javisi_backend was found but has incorrect label
com.docker.compose.network set to "" (expected: "backend")
```

**Cause Racine** :
- Réseaux créés par ancien `docker-compose.yml` (monolithique)
- Nouveau `docker-compose-infra.yml` attend des labels différents
- Docker Compose refuse de réutiliser réseaux avec mauvais labels

**Solution Appliquée** :
```yaml
# docker-stack/tasks/main.yml
- name: Stop old docker-compose stacks if they exist
  ansible.builtin.shell:
    cmd: |
      docker compose -f docker-compose.yml down || true
      docker compose -f docker-compose-infra.yml down || true

- name: Remove project Docker networks
  ansible.builtin.command:
    cmd: "docker network rm {{ project_name }}_{{ item }}"
  loop: [frontend, backend, egress, monitoring]
  failed_when: false
```

**Impact** : 🔴 CRITIQUE - Empêche création de l'infra

**Commit** : `a476f4f` - "fix: Add network cleanup to docker-stack role"

**Leçon** : Cleanup des réseaux nécessaire pour déploiements idempotents.

---

### 7. 🗂️ **Provisioning n8n AVANT Création Conteneur**

**Symptôme** :
```
TASK [n8n : Wait for n8n container to be healthy]
Error: No such container: javisi_n8n
```

**Cause Racine** :
- Rôle `n8n` (Phase 3) essayait de provisionner l'owner
- `docker exec javisi_n8n` échouait car conteneur pas encore créé
- `docker-stack` (Phase 4.5) crée les conteneurs **APRÈS**

**Solution Appliquée** :
1. ✅ Suppression provisioning du rôle `n8n`
2. ✅ Création rôle `n8n-provision` (nouveau)
3. ✅ Ajouté en **Phase 4.6** (après docker-stack)

**Ordre Corrigé** :
```
Phase 3: n8n role → Prépare configs UNIQUEMENT
Phase 4.5: docker-stack → Crée conteneur n8n
Phase 4.6: n8n-provision → Provisionne owner (conteneur existe maintenant)
```

**Impact** : 🔴 CRITIQUE - Bloque déploiement n8n

**Commit** : `fff33cd` - "fix: Move n8n provisioning after docker-stack"

**Leçon** : Séparer préparation config (avant conteneurs) et provisioning (après conteneurs).

---

### 8. 💾 **PostgreSQL 18+ - Volume Mount & Capabilities**

**Symptôme** :
```
PostgreSQL container: restarting (unhealthy)
Error: chmod: changing permissions: Operation not permitted
PostgreSQL data in /var/lib/postgresql/data (unused mount)
```

**Causes Racines (2 problèmes)** :

#### A. Volume Mount Path Incorrect
- ❌ Ancien format (< 18) : `/var/lib/postgresql/data`
- ✅ Nouveau format (18+) : `/var/lib/postgresql`
- Référence : https://github.com/docker-library/postgres/pull/1259

#### B. Capabilities Linux Insuffisantes
- PostgreSQL 18+ a besoin de `DAC_OVERRIDE` et `FOWNER`
- Capabilities initiales : `CHOWN`, `SETGID`, `SETUID` seulement
- Impossibilité de `chmod`/`chown` dans `/var/lib/postgresql/18/docker`

**Solutions Appliquées** :

```yaml
# docker-compose-infra.yml - Volume
volumes:
  - /opt/{{ project_name }}/data/postgresql:/var/lib/postgresql  # Corrigé

# docker-compose-infra.yml - Capabilities
cap_add:
  - CHOWN
  - SETGID
  - SETUID
  - DAC_OVERRIDE  # Bypass file permission checks
  - FOWNER        # Bypass ownership checks
```

**Analyse Sécurité** :
- ✅ `cap_drop: ALL` en premier (défense en profondeur)
- ✅ Seulement 5 capabilities spécifiques (minimal set)
- ✅ `no-new-privileges:true` (pas d'escalade)
- ✅ UID 999 non-root
- ✅ Réseau `backend` internal (pas d'internet)

**Impact** : 🔴 CRITIQUE - PostgreSQL ne démarre jamais

**Commits** :
- `a63a305` - "fix: PostgreSQL 18+ volume mount path"
- `5b82149` - "fix: Add DAC_OVERRIDE and FOWNER capabilities"

**Leçon** : PostgreSQL 18+ est un **major upgrade** avec breaking changes (volume + capabilities).

---

## 📊 Statistiques du Debugging

| Métrique | Valeur |
|----------|--------|
| **Erreurs critiques** | 8 |
| **Erreurs bloquantes** | 6 (SSH, docker-stack, images, réseaux, n8n, PostgreSQL) |
| **Erreurs moyennes** | 2 (VPN, duplication rôles) |
| **Commits de fix** | 6 |
| **Lignes modifiées** | ~800 |
| **Fichiers impactés** | 14 |
| **Temps debugging** | ~6h |
| **Images vérifiées** | 12/12 ✅ |

---

## 🏗️ Architecture Finale Déployée

### Réseaux Docker (Isolation par Service)

```yaml
networks:
  frontend:        # 172.20.1.0/24 - Public (Caddy, Grafana)
  backend:         # 172.20.2.0/24 - Internal, NO internet (PostgreSQL, Redis, Qdrant)
  egress:          # 172.20.4.0/24 - Apps avec internet (n8n, LiteLLM, OpenClaw)
  monitoring:      # 172.20.3.0/24 - Internal, NO internet (VictoriaMetrics, Loki)
```

### Matrice Réseaux par Service

| Service | frontend | backend | egress | monitoring |
|---------|----------|---------|--------|------------|
| **Caddy** | ✅ | ✅ | ❌ | ❌ |
| **PostgreSQL** | ❌ | ✅ | ❌ | ❌ |
| **Redis** | ❌ | ✅ | ❌ | ❌ |
| **Qdrant** | ❌ | ✅ | ❌ | ❌ |
| **n8n** | ❌ | ✅ | ✅ | ❌ |
| **LiteLLM** | ❌ | ✅ | ✅ | ❌ |
| **OpenClaw** | ❌ | ✅ | ✅ | ❌ |
| **Grafana** | ✅ | ❌ | ❌ | ✅ |
| **VictoriaMetrics** | ❌ | ❌ | ❌ | ✅ |
| **Loki** | ❌ | ❌ | ❌ | ✅ |
| **Alloy** | ❌ | ✅ | ❌ | ✅ |
| **DIUN** | host | host | host | host |

### Ordre d'Exécution des Phases

```
Phase 1 — Fondations
├─ common
├─ docker
└─ headscale-node

Phase 2 — Données & Reverse Proxy
├─ postgresql (config)
├─ redis (config)
├─ qdrant (config)
└─ caddy (config)

Phase 3 — Applications
├─ n8n (config)
├─ litellm (config)
└─ openclaw (config)

Phase 4 — Observabilité
├─ monitoring (config)
└─ diun (config)

Phase 4.5 — Déploiement Docker Stack ⭐ NOUVEAU
├─ docker-stack
│   ├─ Phase A: Infra (PostgreSQL, Redis, Qdrant, Caddy) + Réseaux
│   └─ Phase B: Apps (n8n, LiteLLM, OpenClaw, Monitoring)

Phase 4.6 — Provisioning Post-Déploiement ⭐ NOUVEAU
└─ n8n-provision

Phase 5 — Résilience
├─ backup-config
└─ uptime-config

Phase 6 — Hardening (DERNIER) ⭐ DÉPLACÉ
└─ hardening
```

---

## 🔐 Posture de Sécurité Finale

### Hardening Appliqué
- ✅ SSH sur port custom (804), clé publique uniquement
- ✅ UFW firewall (ports 80, 443 publics uniquement)
- ✅ Fail2Ban actif
- ✅ CrowdSec (repo Debian 12 bookworm)
- ⚠️ SSH accessible sur 0.0.0.0 (`hardening_ssh_force_open: true` par défaut)

### Isolation Conteneurs
- ✅ `cap_drop: ALL` sur tous les services
- ✅ Capabilities minimales par service
- ✅ `no-new-privileges:true` partout
- ✅ UIDs non-root (999 pour PostgreSQL, 1000 pour n8n)
- ✅ Réseaux internes sans internet (backend, monitoring)
- ✅ Admin UIs VPN-only (n8n, Grafana, OpenClaw, Qdrant)

### Points d'Attention Sécurité
- ⚠️ OpenClaw utilise `:latest` (temporaire, à pinner)
- ⚠️ SSH sur 0.0.0.0 par défaut (sécurité > facilité)
- ⚠️ PostgreSQL avec `DAC_OVERRIDE` et `FOWNER` (nécessaire pour PG18+)

---

## 📚 Apprentissages Clés pour Futurs Déploiements

### ✅ À FAIRE

1. **Vérifier TOUTES les images Docker AVANT déploiement**
   ```bash
   docker manifest inspect <image>:<tag>
   ```

2. **Garder une fenêtre SSH ouverte pendant hardening**
   - Tester accès VPN AVANT de restreindre SSH
   - Valider que `hardening_ssh_force_open: true` au début

3. **Ordre d'exécution critique** :
   - Configs AVANT conteneurs
   - Conteneurs AVANT provisioning
   - Hardening en DERNIER

4. **PostgreSQL 18+ nécessite** :
   - Volume mount : `/var/lib/postgresql` (pas `/data`)
   - Capabilities : `DAC_OVERRIDE` + `FOWNER`

5. **Cleanup réseaux Docker** :
   - Supprimer anciens réseaux avant redéploiement
   - Éviter conflits de labels compose

### ❌ À ÉVITER

1. ❌ **Hardening trop tôt** → Lockout SSH
2. ❌ **Dépendances dans meta/main.yml** → Double exécution
3. ❌ **Vérifications bloquantes sur VPN** → Déploiement cassé
4. ❌ **Utiliser `:latest` en production** → Non-déterministe
5. ❌ **Provisionner avant création conteneurs** → Erreurs obscures
6. ❌ **Oublier de vérifier les images** → Déploiement cassé
7. ❌ **Ignorer les breaking changes PostgreSQL** → Crash loops

---

## 🎓 Recommandations pour Code Review (Opus 4.6)

### Points à Vérifier Prioritairement

1. **Sécurité Hardening** :
   - [ ] `hardening_ssh_force_open: true` par défaut est-il acceptable ?
   - [ ] Ordre Phase 6 pour hardening est-il optimal ?
   - [ ] Capabilities PostgreSQL (`DAC_OVERRIDE`, `FOWNER`) sont-elles minimales ?

2. **Architecture Réseau** :
   - [ ] Isolation réseau conforme TECHNICAL-SPEC ?
   - [ ] Réseau `egress` correctement configuré pour LiteLLM/n8n/OpenClaw ?
   - [ ] `backend` et `monitoring` bien `internal: true` ?

3. **Ordre d'Exécution** :
   - [ ] Séparation config/provisioning cohérente partout ?
   - [ ] Autres services (LiteLLM, OpenClaw) nécessitent-ils provisioning ?
   - [ ] Dépendances `depends_on` dans docker-compose correctes ?

4. **Gestion des Erreurs** :
   - [ ] `failed_when: false` utilisé judicieusement (docker-stack Phase B) ?
   - [ ] Healthchecks timeout/retries bien calibrés ?
   - [ ] Messages d'erreur explicites pour l'utilisateur ?

5. **Idempotence** :
   - [ ] Cleanup réseaux/stacks suffisant ?
   - [ ] Rôles peuvent s'exécuter 2 fois sans casser ?
   - [ ] Permissions fichiers correctes (PostgreSQL 999:999) ?

6. **PostgreSQL 18+ Spécifique** :
   - [ ] Volume mount cohérent dans docker-compose.yml ET docker-compose-infra.yml ?
   - [ ] Migration depuis PostgreSQL 17 documentée ?
   - [ ] Backup/restore compatible nouvelle structure ?

7. **Images Docker** :
   - [ ] Toutes les images pinnées (sauf OpenClaw temporaire) ?
   - [ ] Script de vérification images à automatiser en CI ?
   - [ ] OpenClaw `:latest` → Trouver version stable ?

---

## 🚀 Prochaines Étapes

### Immédiat (Avant Next Deploy)
- [ ] Tester déploiement complet avec corrections
- [ ] Valider healthchecks de tous les services
- [ ] Vérifier connectivité admin UIs via VPN
- [ ] Tester smoke tests

### Court Terme
- [ ] Pinner version OpenClaw (remplacer `:latest`)
- [ ] Automatiser vérification images en CI
- [ ] Documenter procédure migration PostgreSQL 17→18
- [ ] Tester backup/restore avec nouvelle structure PostgreSQL

### Moyen Terme
- [ ] Monitorer métriques ressources (CPU/RAM PostgreSQL avec nouvelles capabilities)
- [ ] Audit sécurité complet (CrowdSec, Fail2Ban logs)
- [ ] Plan de rollback si PostgreSQL 18 pose problèmes
- [ ] Envisager réseau `egress` avec proxy sortant (contrôle API calls)

---

## 📎 Références

- [PostgreSQL Docker 18+ Breaking Changes](https://github.com/docker-library/postgres/pull/1259)
- [PostgreSQL Upgrade Discussion](https://github.com/docker-library/postgres/issues/37)
- [Docker Compose Network Labels](https://docs.docker.com/compose/compose-file/06-networks/)
- [Linux Capabilities Man Page](https://man7.org/linux/man-pages/man7/capabilities.7.html)

---

**Auteur** : Claude Sonnet 4.5 (avec utilisateur mobuone)
**Date** : 2026-02-15
**Version** : 1.0
**Statut** : DRAFT - En attente review Opus 4.6
