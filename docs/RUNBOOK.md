# RUNBOOK — Procedures Operationnelles

> **Projet** : VPAI — Stack AI Auto-Hebergee
> **Version** : 1.1.0
> **Noms reels** : projet = `javisi`, containers = `javisi_<service>`, data = `/opt/javisi/`

---

## Table des Matieres

1. [Stack Start / Stop](#1-stack-start--stop)
2. [Service Update](#2-service-update)
3. [Redeploy Cible (sans downtime)](#3-redeploy-cible-sans-downtime)
4. [Zerobyte Backup Configuration (Seko-VPN)](#4-zerobyte-backup-configuration-seko-vpn)
5. [Uptime Kuma Configuration (Seko-VPN)](#5-uptime-kuma-configuration-seko-vpn)
6. [OpenClaw — Gestion des Modeles et Agents](#6-openclaw--gestion-des-modeles-et-agents)
7. [Ajout d'un Nouveau Modele LiteLLM](#7-ajout-dun-nouveau-modele-litellm)
8. [Secret Rotation](#8-secret-rotation)
9. [Restore from Backup](#9-restore-from-backup)
10. [Incident Response](#10-incident-response)
11. [VPN Mode Toggle](#11-vpn-mode-toggle)
12. [LiteLLM — Surveillance des Coûts](#12-litellm--surveillance-des-co%C3%BBts)
13. [Workstation Pi — AI Creative Studio](#13-workstation-pi--ai-creative-studio)

---

## 1. Stack Start / Stop

### Demarrer la stack complete

```bash
# Phase A — Infra (PostgreSQL, Redis, Qdrant, Caddy)
cd /opt/javisi
docker compose -f docker-compose-infra.yml up -d

# Phase B — Applications (n8n, LiteLLM, OpenClaw, Monitoring)
docker compose up -d
```

### Arreter la stack

```bash
cd /opt/javisi
# Arreter seulement les apps (infra reste active)
docker compose down

# Arreter tout (apps + infra)
docker compose down
docker compose -f docker-compose-infra.yml down
```

### Restart d'un service unique

```bash
cd /opt/javisi
docker compose restart <service_name>
# Exemples : grafana, n8n, litellm, openclaw, alloy, victoriametrics
```

### Voir les logs

```bash
# Tous les services (Phase B)
docker compose logs -f --tail 100

# Service specifique (Phase B)
docker compose logs -f --tail 100 litellm
docker compose logs -f --tail 100 openclaw

# Service Phase A (infra)
docker compose -f docker-compose-infra.yml logs -f --tail 100 postgresql
docker compose -f docker-compose-infra.yml logs -f --tail 100 redis
```

### Verifier la sante de la stack

```bash
# Status de tous les containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Services unhealthy uniquement
docker ps --filter "health=unhealthy" --format "table {{.Names}}\t{{.Status}}"
```

---

## 2. Service Update

### Via Ansible (recommande)

1. Mettre a jour la version dans `inventory/group_vars/all/versions.yml`
2. Deployer depuis la machine de deploiement (WSL Ubuntu) :

```bash
cd ~/seko/VPAI
source .venv/bin/activate

# Service specifique avec tag
ansible-playbook playbooks/site.yml --tags <service_name> -e "target_env=prod" --diff

# Exemples
ansible-playbook playbooks/site.yml --tags litellm -e "target_env=prod"
ansible-playbook playbooks/site.yml --tags monitoring -e "target_env=prod"
ansible-playbook playbooks/site.yml --tags openclaw -e "target_env=prod"
```

### Mise a jour manuelle Docker

```bash
cd /opt/javisi
docker compose pull <service_name>
docker compose up -d <service_name>
```

---

## 3. Redeploy Cible (sans downtime)

### Grafana datasources + dashboards uniquement

```bash
ansible-playbook playbooks/site.yml --tags monitoring -e "target_env=prod"
# Regenere datasources.yaml + 9 fichiers JSON dashboards
# Grafana recharge automatiquement sans restart
```

### OpenClaw config uniquement (modeles, agents, skills)

```bash
ansible-playbook playbooks/site.yml --tags openclaw -e "target_env=prod"
# Regenere openclaw.json et openclaw.env, restart le container
```

### Workflows n8n uniquement

```bash
ansible-playbook playbooks/site.yml --tags n8n-provision -e "target_env=prod"
# Reimporte les workflows modifies (checksum-based)
```

### Dry run avant redeploy

```bash
cd ~/seko/VPAI && source .venv/bin/activate
ansible-playbook playbooks/site.yml --tags <role> --check --diff -e "target_env=prod"
```

---

## 4. Zerobyte Backup Configuration (Seko-VPN)

> **Localisation** : Serveur Seko-VPN, Zerobyte UI sur port 4096
> **Prerequis** : Connectivite VPN entre Seko-AI et Seko-VPN

### 4.1 Creer les Repositories S3

**Repository 1 — vpai-backups (Restic chiffre)**

1. Aller dans **Repositories** > **Add Repository**
2. Configurer :
   - **Name** : `vpai-backups` | **Type** : Restic + S3
   - **Endpoint** : `fsn1.your-objectstorage.com`
   - **Bucket** : (valeur de vault `s3_bucket_backups`)
   - **Access Key / Secret Key** : (depuis Hetzner Object Storage)
   - **Region** : `fsn1` | **Encryption** : Activer (stocker le password dans vault)

**Repository 2 — vpai-shared (fichiers bruts)**

- Meme procedure, **Type** : rclone + S3 | **Encryption** : Aucune

### 4.2 Creer les Volumes

| Volume Name | Type | Source Path (via VPN) |
|---|---|---|
| `vpai-postgres` | Directory | `/opt/javisi/backups/pg_dump/` |
| `vpai-redis` | Directory | `/opt/javisi/data/redis/` |
| `vpai-qdrant` | Directory | `/opt/javisi/backups/qdrant/` |
| `vpai-n8n` | Directory | `/opt/javisi/backups/n8n/` |
| `vpai-configs` | Directory | `/opt/javisi/configs/` |
| `vpai-grafana` | Directory | `/opt/javisi/backups/grafana/` |

### 4.3 Creer les Jobs (Retention GFS)

| Job | Volume | Repository | Schedule | Retention GFS |
|---|---|---|---|---|
| DB Full | `vpai-postgres` | vpai-backups | Daily 03:00 | 7d / 4w / 6m / 2y |
| Redis | `vpai-redis` | vpai-backups | Daily 03:05 | 7d / 4w |
| Qdrant | `vpai-qdrant` | vpai-backups | Daily 03:10 | 7d / 4w / 6m |
| n8n | `vpai-n8n` | vpai-backups | Daily 03:15 | 7d / 4w / 6m / 2y |
| Configs | `vpai-configs` | vpai-backups | Daily 03:20 | 7d / 4w |
| Grafana | `vpai-grafana` | vpai-backups | Weekly Sun 03:00 | 4w / 6m |
| Seed | `vpai-postgres` | vpai-shared | Daily 03:30 | Latest only |

Pour chaque job Restic : Keep Daily=7, Weekly=4, Monthly=6, Yearly=2, Auto-prune=Yes.

> Strategie complete avec tiering NAS : `docs/BACKUP-STRATEGY.md`

### 4.4 Verifier le Backup

```bash
# Sur Seko-AI : declencher un pre-backup manuel
/opt/javisi/scripts/pre-backup.sh

# Sur Seko-VPN : declencher via Zerobyte UI > Jobs > Run Now
# Verifier via Zerobyte UI > Repository > Browse
```

---

## 5. Uptime Kuma Configuration (Seko-VPN)

> **Prerequis** : Connectivite VPN vers Seko-AI

### 5.1 Creer le Groupe de Notification

1. **Settings** > **Notifications** > **Setup Notification**
2. Creer un webhook correspondant a la methode configuree + tester

### 5.2 Creer les Moniteurs

| # | Name | Type | URL/Host | Intervalle |
|---|---|---|---|---|
| 1 | VPAI — HTTPS | HTTP(s) | `https://<domain>/health` | 60s |
| 2 | VPAI — n8n | HTTP(s) | `https://mayi.<domain>/healthz` | 60s |
| 3 | VPAI — Grafana | HTTP(s) | `https://tala.<domain>/api/health` | 120s |
| 4 | VPAI — PostgreSQL | TCP Port | `<headscale_ip>:5432` | 120s |
| 5 | VPAI — TLS Certificate | HTTP(s) | `https://<domain>` | 86400s |
| 6 | VPAI — Backup Heartbeat | Push | — | 86400s |

**Notes** :
- Moniteurs 2-4 : requierent l'acces VPN (headscale)
- Moniteur 5 : activer "Certificate Expiry Notification"
- Moniteur 6 : copier l'URL push → stocker dans vault comme `vault_backup_heartbeat_url`

---

## 6. OpenClaw — Gestion des Modeles et Agents

### 6.1 Assignation Actuelle des Modeles

| Agent | Persona | Modele | Note |
|---|---|---|---|
| Concierge | Mobutoo | minimax-m25 | kimi-k2 ecarte (token leakage bug) |
| Builder | Imhotep | qwen3-coder | Code gen FREE |
| Writer | Thot | glm-5 | Low hallucination, agent-oriented |
| Artist | Basquiat | minimax-m25 | 1M context, multimodal |
| Tutor | Piccolo | minimax-m25 | kimi-k2 ecarte |
| Explorer | R2D2 | grok-search | Web + X search #1 |

### 6.2 Changer le Modele d'un Agent

1. Editer `roles/openclaw/defaults/main.yml` — variable `openclaw_<agent>_model`
2. Deployer : `ansible-playbook playbooks/site.yml --tags openclaw -e "target_env=prod"`
3. Verifier : `docker exec javisi_openclaw cat /home/node/.openclaw/openclaw.json | jq '.agents'`

### 6.3 Verifier les Skills Charges

```bash
docker exec javisi_openclaw node --input-type=module -e \
  "import{loadSkillsFromDir}from'@mariozechner/pi-coding-agent'; \
  const r=loadSkillsFromDir({dir:'/home/node/.openclaw/skills',source:'t'}); \
  console.log(r.skills.length,r.diagnostics)"
```

### 6.4 Approuver le Pairing Telegram (si necessaire)

```bash
# Si dmPolicy=pairing, approuver le code envoye par le bot
docker exec javisi_openclaw node openclaw.mjs pairing approve telegram <CODE>
```

### 6.5 Bootstrap Token (premier acces UI)

```
https://<admin_subdomain>.<domain>/__bootstrap__
# Injecte le gateway token dans localStorage et redirige vers l'UI
```

---

## 7. Ajout d'un Nouveau Modele LiteLLM

1. Editer `roles/litellm/templates/litellm_config.yaml.j2` — ajouter dans `model_list`
2. Si nouveau provider : ajouter la cle API dans vault
   `ansible-vault edit inventory/group_vars/all/secrets.yml`
3. Ajouter le modele dans `roles/openclaw/templates/openclaw.json.j2` (section providers)
4. Deployer les deux :
   `ansible-playbook playbooks/site.yml --tags litellm,openclaw -e "target_env=prod"`
5. Verifier les modeles :
   ```bash
   docker exec javisi_litellm curl -sH \
     "Authorization: Bearer <litellm_master_key>" \
     http://localhost:4000/v1/models | jq '.data[].id'
   ```

---

## 8. Secret Rotation

### Secrets et Services Affectes

| Secret | Services Affectes | Frequence |
|---|---|---|
| `postgresql_password` | postgresql, n8n, litellm, openclaw, grafana-datasource | Trimestriel |
| `redis_password` | redis, litellm, openclaw | Trimestriel |
| `grafana_admin_password` | grafana | Trimestriel |
| `litellm_master_key` | litellm, openclaw, caddy | Trimestriel |
| `n8n_encryption_key` | n8n | **JAMAIS** (casse les donnees chiffrees) |
| `qdrant_api_key` | qdrant, openclaw | Trimestriel |
| `openclaw_gateway_token` | openclaw, caddy (route bootstrap) | Trimestriel |
| `sure_secret_key_base` | sure-web, sure-worker | **JAMAIS** (casse les sessions Rails) |
| `sure_db_password` | sure-web, sure-worker, postgresql | Trimestriel |
| `sure_api_key` | sure-web, claude-code MCP | Trimestriel |
| `github_webhook_secret` | n8n (github-autofix workflow) | Annuel |

### Generer les nouveaux secrets (Sure + autofix pipeline)

```bash
# Secret key base Rails (64 octets hex) — NE PAS CHANGER apres premier deploy
openssl rand -hex 64

# Mot de passe DB Sure
openssl rand -hex 32

# GitHub webhook secret
openssl rand -hex 32

# Ajouter dans le vault :
ansible-vault edit inventory/group_vars/all/secrets.yml
# Ajouter les cles suivantes :
# vault_sure_secret_key_base: "<resultat openssl rand -hex 64>"
# vault_sure_db_password: "<resultat openssl rand -hex 32>"
# vault_sure_api_key: ""  # Remplir apres premier boot Sure (Settings > API)
# vault_github_webhook_secret: "<resultat openssl rand -hex 32>"
```

### Procedure

```bash
# 1. Editer le vault
ansible-vault edit inventory/group_vars/all/secrets.yml

# 2. Changer la valeur du secret

# 3. Redeployer les services affectes (adapter les tags)
ansible-playbook playbooks/site.yml --tags postgresql,n8n,litellm,openclaw -e "target_env=prod"
```

---

## 9. Restore from Backup

### 9.1 PostgreSQL

```bash
# Copier le dump dans le container
cp /opt/javisi/backups/pg_dump/<db>-<timestamp>.dump /tmp/restore.dump
docker cp /tmp/restore.dump javisi_postgresql:/tmp/restore.dump

# Restaurer
docker exec javisi_postgresql pg_restore -U postgres -d <db> --clean --if-exists /tmp/restore.dump

# Nettoyer
docker exec javisi_postgresql rm /tmp/restore.dump && rm /tmp/restore.dump
```

Bases disponibles : `n8n`, `litellm`, `openclaw`

### 9.2 Redis

```bash
cd /opt/javisi
docker compose -f docker-compose-infra.yml stop redis
cp /opt/javisi/backups/redis/dump-<timestamp>.rdb /opt/javisi/data/redis/dump.rdb
docker compose -f docker-compose-infra.yml start redis
```

### 9.3 Restauration Complete depuis S3

1. Sur Seko-VPN : Restaurer via Zerobyte UI (choisir snapshot, cible = volumes)
2. Sur Seko-AI :
   ```bash
   cd /opt/javisi
   docker compose down
   docker compose -f docker-compose-infra.yml down
   # (Restaurer les donnees depuis les volumes montes par Zerobyte)
   docker compose -f docker-compose-infra.yml up -d
   sleep 30  # Attendre que l'infra soit healthy
   docker compose up -d
   /opt/javisi/scripts/smoke-test.sh
   ```

---

## 10. Incident Response

### Container en Crash Loop

```bash
# Logs du service
docker logs --tail 50 javisi_<service>
docker logs --tail 50 --since 5m javisi_<service>

# Verifier OOMKilled
docker inspect javisi_<service> | jq '.[0].State'
docker stats --no-stream
```

**Causes frequentes** :
- **OOMKilled** → augmenter `mem_limit` dans `inventory/group_vars/all/docker.yml`
- **Config invalide** → corriger le template Jinja2 + redeploy cible
- **PostgreSQL pas encore pret** → `docker compose restart <service>` apres 30s

### VPS Down

1. Creer un nouveau VPS depuis le dernier snapshot
2. Mettre a jour le DNS (nouvelle IP publique)
3. Restaurer depuis Zerobyte S3 (section 9.3)
4. Re-executer Ansible : `make deploy-prod EXTRA_VARS="ansible_port_override=22"`
5. Smoke tests : `/opt/javisi/scripts/smoke-test.sh`

### Corruption de Base de Donnees

1. Arreter le service : `docker compose stop <service>`
2. Restaurer depuis backup (section 9.1)
3. Redemarrer et verifier : `docker compose start <service>`

### Compromission Securite

1. **Isoler** — couper l'internet public (garder VPN)
2. **Evaluer** — analyser Loki + logs systeme, identifier le vecteur
3. **Rotater** — tous les secrets (section 8)
4. **Redeployer** — full Ansible depuis un etat propre
5. **Surveiller** — 48h vigilance accrue (Grafana + alertes Loki)

### Erreur Datasource Grafana

```bash
# Tester la connexion PostgreSQL depuis Grafana
docker inspect javisi_grafana | grep '"IPAddress"'
docker exec javisi_grafana wget -qO- --post-data="{}" \
  "http://admin:<grafana_admin_password>@<IP_CONTAINER>:3000/api/datasources/uid/PostgreSQL-n8n/health"
# OK : {"message":"Database Connection OK","status":"OK"}

# Redeploy monitoring si KO
ansible-playbook ~/seko/VPAI/playbooks/site.yml --tags monitoring -e "target_env=prod"
```

### Consulter le Tableau de Scoring IA

```bash
# Scores des modeles
docker exec javisi_postgresql psql -U n8n -d n8n -c \
  "SELECT model, total_calls, likes, dislikes, score, \
   ROUND(avg_cost_per_call::numeric * 1000, 4) AS cost_per_1k \
   FROM model_scores ORDER BY score DESC;"
```

---

## 11. VPN Mode Toggle

### Activer le mode VPN-only

```bash
make vpn-on   # Applique UFW + Caddy VPN enforce avec dead man switch 15min
```

Prérequis : Tailscale doit être connecté sur le client, Split DNS opérationnel.

### Désactiver (retour mode public)

```bash
make vpn-off
```

### Vérifier l'état

```bash
# Vérifier que le Split DNS fonctionne (Windows PowerShell)
Resolve-DnsName mayi.ewutelo.cloud   # Doit retourner 100.64.0.14

# Vérifier les extra_records Headscale sur le serveur
ansible vpn-server -m shell -a 'cat /opt/services/headscale/config/config.yaml' -b | grep -A 20 extra_records

# Vérifier que Caddy applique l'ACL VPN
ansible prod-server -m shell -a 'grep -A3 "vpn_only" /opt/javisi/configs/caddy/Caddyfile' -b
```

### Dead Man Switch

Le playbook `vpn-toggle.yml` programme un revert UFW automatique dans **15 minutes** via `at`. Si le déploiement échoue ou si tu es locké dehors, UFW revient en mode ouvert après 15 min.

## 12. LiteLLM — Surveillance des Coûts

### Vérifier les dépenses par modèle

```bash
# Top 10 modèles les plus coûteux
ansible prod-server -m shell -a "docker exec javisi_postgresql psql -U litellm -d litellm -t -A -c \"SELECT model, SUM(spend) as total, COUNT(*) as calls FROM \\\"LiteLLM_SpendLogs\\\" GROUP BY model ORDER BY total DESC LIMIT 10;\"" -b
```

### Détecter les health checks parasites

```bash
# Health checks par modèle (tag litellm-internal-health-check)
ansible prod-server -m shell -a "docker exec javisi_postgresql psql -U litellm -d litellm -t -A -c \"SELECT model, COUNT(*), SUM(spend) FROM \\\"LiteLLM_SpendLogs\\\" WHERE request_tags::text LIKE '%health%' GROUP BY model ORDER BY SUM(spend) DESC;\"" -b
```

Si des modèles apparaissent → vérifier `health_check_interval: 0` dans `litellm_config.yaml.j2`.

### Budget par provider (limite quotidienne)

Configuré dans `inventory/group_vars/all/main.yml` :
- `litellm_anthropic_budget_daily` (défaut: 20$)
- `litellm_openrouter_budget_daily` (défaut: 5$)
- `litellm_openai_budget_daily`

---

## 13. Workstation Pi — AI Creative Studio

> **SSH** : `ssh -i ~/.ssh/seko-vpn-deploy mobuone@192.168.1.8`
> **Docker Compose** : `/opt/workstation/comfyui/docker-compose-creative.yml`

### 13.1 Start / Stop Creative Studio

```bash
# SSH sur le Pi
ssh -i ~/.ssh/seko-vpn-deploy mobuone@192.168.1.8

# Démarrer
cd /opt/workstation/comfyui
sudo docker compose -f docker-compose-creative.yml up -d

# Arrêter
sudo docker compose -f docker-compose-creative.yml down

# Restart d'un service
sudo docker compose -f docker-compose-creative.yml restart comfyui
sudo docker compose -f docker-compose-creative.yml restart remotion
```

### 13.2 Vérifier l'état

```bash
# Status containers
docker ps --filter name=workstation_

# Santé ComfyUI (attendre ~2 min au démarrage)
curl -s http://127.0.0.1:8188/system_stats | python3 -m json.tool

# Santé Remotion
curl -s http://127.0.0.1:3200/health

# Logs
docker logs workstation_comfyui --tail 50
docker logs workstation_remotion --tail 50

# Services systemd
systemctl status caddy-workstation tailscaled --no-pager
```

### 13.3 Tester le Creative Pipeline depuis n8n

Depuis un navigateur VPN, ouvrir n8n (`https://tala.ewutelo.cloud`) et déclencher le workflow `Creative Pipeline` manuellement avec un payload test :

```json
{
  "type": "image",
  "prompt": "a beautiful sunset over mountains, photorealistic",
  "model": "comfyui",
  "output_name": "test-sunset"
}
```

Pour un test vidéo :
```json
{
  "type": "video",
  "prompt": "a time-lapse of clouds moving over a city",
  "model": "remotion",
  "composition": "ProductDemo",
  "duration": 5,
  "output_name": "test-video"
}
```

### 13.4 Ajouter un modèle ComfyUI

```bash
# SSH sur le Pi
ssh -i ~/.ssh/seko-vpn-deploy mobuone@192.168.1.8

# Télécharger dans le répertoire models (ex: checkpoints)
wget -O /opt/workstation/data/comfyui/models/checkpoints/mon_modele.safetensors \
  "https://url_du_modele"

# Le modèle est disponible immédiatement (volume monté)
# Vérifier dans l'UI : https://studio.ewutelo.cloud
```

Ou via Ansible (recommandé pour les modèles récurrents) : ajouter dans `comfyui_models` dans `inventory/group_vars/all/main.yml`.

### 13.5 Mettre à jour ComfyUI ou Remotion

```bash
# 1. Mettre à jour la version dans versions.yml (ou defaults/main.yml)
# comfyui_version: "v0.3.28"
# remotion_version: "4.0.260"

# 2. Redéployer le rôle (rebuild l'image Docker ARM64)
source .venv/bin/activate
ansible-playbook playbooks/workstation.yml --vault-password-file .vault_pass --tags comfyui
ansible-playbook playbooks/workstation.yml --vault-password-file .vault_pass --tags remotion
```

> **Durée** : ~10-15 min par service (build ARM64 depuis source).

### 13.6 Dépannage Creative Studio

| Symptôme | Cause probable | Fix |
|---|---|---|
| `workstation_comfyui` unhealthy | Modèles pas chargés | Attendre 2 min, vérifier `docker logs` |
| `studio.ewutelo.cloud` → 502 | ComfyUI pas démarré | `docker compose up -d comfyui` |
| n8n → ComfyUI timeout | CPU trop lent / modèle lourd | Normal — timeout 300s, attendre |
| `cut.ewutelo.cloud` → 502 | Remotion pas démarré | `docker compose up -d remotion` |
| Remotion OOM (exit code 137) | 512M insuffisant | Augmenter `remotion_memory_limit` dans defaults |
| Images générées vides | Modèle absent dans `/models/checkpoints/` | Télécharger le modèle (section 13.4) |
| Tailscale déconnecté | Reboot Pi sans reconnexion | `sudo tailscale up` (normalement auto) |

### 13.7 Asset Provenance (PostgreSQL VPS)

Les assets générés sont tracés dans la table `asset_provenance` sur le VPS :

```bash
# Depuis WSL (via ansible)
ansible prod-server -m shell -a "docker exec javisi_postgresql psql -U n8n -d n8n -t -A -c \
  \"SELECT asset_id, type, provider, output_name, generated_at FROM asset_provenance ORDER BY generated_at DESC LIMIT 10;\"" -b
```

### 13.8 Caddy Workstation — Redémarrage

```bash
ssh -i ~/.ssh/seko-vpn-deploy mobuone@192.168.1.8
sudo systemctl restart caddy-workstation
sudo systemctl status caddy-workstation --no-pager

# Vérifier les certificats TLS
sudo caddy list-modules 2>&1 | grep -i ovh   # dns.providers.ovh doit être présent
```
