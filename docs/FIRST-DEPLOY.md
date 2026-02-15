# Premier Deploiement - Guide Pas-a-Pas

> **Public** : Technicien junior ayant acces au VPS et au VPN
> **Duree estimee** : 2-3 heures (1ere fois), 30 min (redeploiement)
> **Prerequis** : Un terminal Linux (ou WSL), un acces internet

---

## Table des Matieres

0. [Vue d'ensemble](#0-vue-densemble)
1. [Prerequis materiel et comptes](#1-prerequis-materiel-et-comptes)
2. [Installer les outils sur ta machine](#2-installer-les-outils-sur-ta-machine)
3. [Cloner le projet](#3-cloner-le-projet)
4. [Obtenir les cles API externes](#4-obtenir-les-cles-api-externes)
5. [Generer les secrets internes](#5-generer-les-secrets-internes)
6. [Configurer le projet (wizard)](#6-configurer-le-projet-wizard)
7. [Creer et remplir le Vault](#7-creer-et-remplir-le-vault)
8. [Preparer le VPS cible](#8-preparer-le-vps-cible)
9. [Deployer en pre-production](#9-deployer-en-pre-production)
10. [Valider le deploiement](#10-valider-le-deploiement)
11. [Deployer en production](#11-deployer-en-production)
12. [Configurer les services externes](#12-configurer-les-services-externes)
13. [Checklist finale](#13-checklist-finale)
14. [Depannage](#14-depannage)

---

## 0. Vue d'ensemble

```
Ce que tu vas faire :

  [Ta machine] ----Ansible SSH----> [VPS Prod]
       |                               |
       |-- Ansible installe tout -->   |-- Docker Compose demarre 12+ services
       |                               |-- Caddy gere les certificats TLS
       |                               |-- Tout est accessible via VPN
       |
       +-- [GitHub Actions] -- CI/CD automatique sur chaque push
```

**En resume** : Tu remplis un formulaire de config, tu lances une commande, Ansible fait le reste.

---

## 1. Prerequis materiel et comptes

### Ce qu'il te faut AVANT de commencer

| Element | Details | Ou l'obtenir |
|---------|---------|--------------|
| **VPS Linux** | Debian 12+ ou 13, minimum 4 Go RAM, 40 Go disque | OVH, Hetzner, Ionos... |
| **Domaine** | Un nom de domaine pointe vers l'IP du VPS | OVH, Cloudflare... |
| **VPN Headscale** | Serveur Headscale fonctionnel | Deja deploye sur Seko-VPN |
| **Compte GitHub** | Pour le CI/CD | github.com |
| **Compte Anthropic** | API Claude (LLM) | console.anthropic.com |
| **Compte OpenAI** | API GPT (LLM) | platform.openai.com |
| **Compte Hetzner** | Pour le stockage S3 et la preprod | console.hetzner.cloud |
| **Machine locale** | Linux, macOS, ou Windows+WSL | Ton PC |

> **Note** : Les comptes Anthropic et OpenAI sont payants (paiement a l'usage).
> Budget typique : 5-50 EUR/mois selon l'utilisation des LLM.

---

## 2. Installer les outils sur ta machine

### Sur Ubuntu/Debian (ou WSL)

```bash
# Mettre a jour les paquets
sudo apt update && sudo apt upgrade -y

# Installer les outils de base
sudo apt install -y python3 python3-pip python3-venv git make openssh-client curl jq

# Creer un environnement virtuel Python
python3 -m venv ~/.venv-vpai
source ~/.venv-vpai/bin/activate

# Installer Ansible et les outils de qualite
pip install ansible ansible-lint yamllint molecule molecule-docker jmespath
```

### Verifier que tout est installe

```bash
ansible --version    # Doit afficher 2.16+
ansible-lint --version
yamllint --version
molecule --version
ssh -V
git --version
```

> **Si tu es sous WSL** : Active toujours le venv avant de travailler :
> `source ~/.venv-vpai/bin/activate`

---

## 3. Cloner le projet

```bash
# Cloner le repository
git clone https://github.com/Mobutoo/VPAI.git
cd VPAI

# Verifier la structure
ls -la
# Tu dois voir : roles/  playbooks/  inventory/  templates/  docs/  Makefile  etc.
```

---

## 4. Obtenir les cles API externes

### 4.1 Cle API Anthropic (Claude)

1. Va sur **https://console.anthropic.com/**
2. Connecte-toi ou cree un compte
3. Va dans **Settings** > **API Keys**
4. Clique **Create Key**
5. Donne un nom (ex: `vpai-prod`)
6. **Copie la cle** (format `sk-ant-api03-...`) — elle ne sera plus affichee !
7. Ajoute du credit : **Settings** > **Billing** > ajoute une carte et charge 10 EUR minimum

> **Note la cle** dans un fichier temporaire securise. Tu la mettras dans le Vault a l'etape 7.

### 4.2 Cle API OpenAI (GPT)

1. Va sur **https://platform.openai.com/**
2. Connecte-toi ou cree un compte
3. Va dans **API Keys** (menu de gauche ou https://platform.openai.com/api-keys)
4. Clique **Create new secret key**
5. Donne un nom (ex: `vpai-prod`)
6. **Copie la cle** (format `sk-proj-...`)
7. Ajoute du credit : **Settings** > **Billing** > ajoute 10 EUR minimum

### 4.3 Token Hetzner Cloud (pour la CI/CD preprod)

1. Va sur **https://console.hetzner.cloud/**
2. Cree un projet (ex: `VPAI`)
3. Va dans **Security** > **API Tokens**
4. Clique **Generate API Token**
5. Nom : `vpai-ci` | Permissions : **Read & Write**
6. **Copie le token**

### 4.4 Cles S3 Hetzner (pour les backups et le partage)

Le projet utilise **2 buckets S3** (meme plan a 4.99 EUR/mois, 1 TB partage) :

| Bucket | Role | Format |
|--------|------|--------|
| `vpai-backups` | Backups techniques (Restic chiffre) | Non navigable |
| `vpai-shared` | Seed preprod, exports, documents | Navigable, montable Nextcloud |

1. Toujours dans la Hetzner Console
2. Va dans **Object Storage** (menu de gauche)
3. Cree **2 buckets** :
   - Bucket 1 : `vpai-backups` — Region : `fsn1` (Falkenstein)
   - Bucket 2 : `vpai-shared` — Region : `fsn1`
4. Va dans **Manage credentials** (en haut de la page Object Storage)
5. Clique **Generate credentials** (les memes credentials fonctionnent pour les 2 buckets)
6. **Note** l'Access Key et le Secret Key

> **Attention** : Les credentials S3 ne sont affichees qu'une seule fois. Si tu les perds, il faut en regenerer.
>
> **Strategie complete** : Voir `docs/BACKUP-STRATEGY.md` pour le tiering HOT/WARM/COLD et la retention GFS.

### 4.5 Cles API OVH (pour la gestion DNS automatique)

> **Necessaire uniquement si ton domaine est chez OVH.**
> Caddy utilise le DNS challenge Let's Encrypt pour generer les certificats TLS.
> L'API OVH permet de creer automatiquement les enregistrements DNS necessaires.

#### Etape 1 : Creer le token sur le portail OVH

1. Ouvre ce lien (droits pre-remplis pour la zone DNS) :

   **https://api.ovh.com/createToken/?GET=/domain/zone/*&POST=/domain/zone/*&PUT=/domain/zone/*&DELETE=/domain/zone/*/record/***

   > Ce lien pre-configure les droits minimaux : lecture/ecriture/suppression uniquement
   > sur les zones DNS. Aucun acces a tes serveurs, emails, ou facturation.

2. Connecte-toi avec ton **compte OVH** (identifiant NIC-handle ou email + mot de passe)

3. Remplis le formulaire :

   | Champ | Valeur |
   |-------|--------|
   | **Script name** | `vpai-dns` |
   | **Script description** | `VPAI - Gestion DNS automatique pour TLS` |
   | **Validity** | **Unlimited** (recommande) |

   Les droits sont deja pre-remplis par le lien. Verifie qu'ils contiennent :

   | Methode | Chemin |
   |---------|--------|
   | GET | `/domain/zone/*` |
   | POST | `/domain/zone/*` |
   | PUT | `/domain/zone/*` |
   | DELETE | `/domain/zone/*/record/*` |

4. Clique **Create keys**

5. **La page affiche 3 valeurs** — note-les IMMEDIATEMENT :

   ```
   Application Key:    xxxxxxxxxxxxxxxx
   Application Secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   Consumer Key:       xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

> **IMPORTANT** : Ces 3 valeurs ne sont affichees qu'une seule fois !
> Si tu fermes la page sans les copier, tu devras en recreer.

#### Etape 2 : Verifier que le token fonctionne

```bash
# Teste avec curl (remplace les valeurs)
curl -s \
  -H "X-Ovh-Application: TA_APPLICATION_KEY" \
  -H "X-Ovh-Consumer: TA_CONSUMER_KEY" \
  https://eu.api.ovh.com/1.0/domain/zone/ | jq '.'

# Doit afficher la liste de tes domaines, ex: ["mondomaine.com"]
```

> **Signature OVH** : Pour les requetes POST/PUT/DELETE, l'API OVH requiert une signature
> calculee avec le secret. Ansible et Caddy gerent cela automatiquement via les librairies OVH.
> Le test curl ci-dessus ne fonctionne que pour les GET simples.

#### Pour restreindre a un seul domaine (optionnel, plus securise)

Si tu veux limiter les droits a un seul domaine (ex: `ai.mondomaine.com`), utilise ce lien en remplacant `mondomaine.com` :

```
https://api.ovh.com/createToken/?GET=/domain/zone/mondomaine.com/*&POST=/domain/zone/mondomaine.com/*&PUT=/domain/zone/mondomaine.com/*&DELETE=/domain/zone/mondomaine.com/record/*&GET=/domain/zone/mondomaine.com
```

#### Delais et limites

- **Creation du token** : instantanee
- **Propagation DNS** : les modifications DNS prennent generalement **1 a 5 minutes** pour propager via l'API OVH
- **Rate limiting** : l'API OVH autorise environ **60 requetes par minute** par token — largement suffisant
- **Validite** : si tu as choisi "Unlimited", le token n'expire jamais. Sinon, il faudra le recreer a l'expiration
- **Revocation** : tu peux revoquer le token a tout moment sur https://eu.api.ovh.com/console/ > **Manage credentials**

### 4.6 Cle pre-authentification Headscale

Sur ton serveur VPN (Seko-VPN), via SSH :

```bash
# Lister les namespaces existants
headscale namespaces list

# Creer une cle pour le namespace voulu (ex: "prod")
headscale preauthkeys create --namespace prod --reusable --expiration 24h
```

> **Copie la cle** affichee. Elle expire dans 24h, donc fais cette etape juste avant le deploiement.

### 4.7 Webhook de notification (optionnel mais recommande)

#### Option Telegram (recommande)

Le projet utilise **2 bots Telegram distincts** :

| Bot | Role | Variables |
|-----|------|-----------|
| **Bot Monitoring** | Alertes Grafana, DIUN, backup heartbeat | `vault_telegram_monitoring_bot_token`, `vault_telegram_monitoring_chat_id` |
| **Bot OpenClaw** | Notifications agents IA | `vault_telegram_openclaw_bot_token`, `vault_telegram_openclaw_chat_id` |

> **Note** : Le bot monitoring peut etre partage avec d'autres projets (ex: Seko-VPN).
> Le bot OpenClaw doit etre dedie pour eviter le bruit dans les alertes infra.

Pour chaque bot :

1. Ouvre Telegram et cherche **@BotFather**
2. Envoie `/newbot` et suis les instructions
3. Note le **token du bot** (format `123456:ABC-DEF...`)
4. Cree un groupe ou canal, ajoute le bot
5. Recupere le **chat ID** :
   ```bash
   # Envoie un message dans le groupe, puis :
   curl https://api.telegram.org/bot<TON_TOKEN>/getUpdates | jq '.result[0].message.chat.id'
   ```

#### Option Discord

1. Dans ton serveur Discord : **Parametres du canal** > **Integrations** > **Webhooks**
2. Clique **Nouveau webhook**
3. **Copie l'URL du webhook**

#### Option Slack

1. Va sur **https://api.slack.com/apps** > **Create New App**
2. **Incoming Webhooks** > Active > **Add New Webhook to Workspace**
3. Choisis le canal > **Copie l'URL**

---

## 5. Generer les secrets internes

Ces secrets sont des mots de passe et tokens que tu generes toi-meme. Lance cette commande :

```bash
# Ou utilise le wizard interactif (recommande) :
bash scripts/wizard.sh
```

Si tu preferes les generer manuellement :

```bash
echo "=== SECRETS A COPIER DANS LE VAULT ==="
echo ""
echo "postgresql_password: $(openssl rand -base64 32)"
echo "redis_password: $(openssl rand -base64 32)"
echo "qdrant_api_key: $(openssl rand -hex 32)"
echo "litellm_master_key: sk-$(openssl rand -hex 24)"
echo "n8n_encryption_key: $(openssl rand -hex 32)"
echo "n8n_owner_password: $(openssl rand -base64 24)"
echo "litellm_ui_password: $(openssl rand -base64 24)"
echo "litellm_salt_key: $(openssl rand -hex 32)"
echo "grafana_admin_password: $(openssl rand -base64 24)"
echo "openclaw_api_key: $(openssl rand -hex 32)"
echo ""
echo ">>> COPIE CES VALEURS ! Tu en auras besoin a l'etape 7."
```

> **IMPORTANT** : `n8n_encryption_key` ne doit **JAMAIS** etre change apres le premier deploiement.
> n8n l'utilise pour chiffrer les credentials stockes en base.
> Si tu la perds, tu perds l'acces a tous les credentials n8n.

---

## 6. Configurer le projet (wizard)

### Option A : Wizard interactif (recommande)

```bash
bash scripts/wizard.sh
```

Le wizard te pose chaque question et genere les fichiers automatiquement.

### Option B : Configuration manuelle

```bash
# Copier le template
cp PRD.md.example PRD.md

# Editer avec ton editeur favori
nano PRD.md
# OU
code PRD.md
```

Remplis chaque champ `<A_REMPLIR>` avec tes valeurs :

| Champ | Exemple | Explication |
|-------|---------|-------------|
| `project_name` | `vpai` | Nom court, pas d'espaces, minuscules |
| `project_display_name` | `VPAI` | Nom affiche dans les dashboards |
| `domain_name` | `ai.mondomaine.com` | Domaine pointe vers le VPS |
| `prod_hostname` | `vps-prod-01` | Hostname du VPS |
| `prod_ip` | `203.0.113.42` | IP publique du VPS |
| `prod_ssh_port` | `2222` | Port SSH (pas 22 pour la securite) |
| `prod_user` | `deploy` | Utilisateur SSH |
| `vpn_headscale_url` | `https://vpn.example.com` | URL de ton serveur Headscale |
| `vpn_headscale_ip` | `100.64.0.1` | IP Headscale du serveur VPN |
| `s3_bucket_name` | `vpai-backups` | Nom du bucket S3 |
| `notification_method` | `telegram` | `telegram`, `discord`, `slack` |

---

## 7. Creer et remplir le Vault

Le Vault est un fichier chiffre qui contient tous les secrets. Personne ne peut le lire sans le mot de passe.

### 7.1 Choisir un mot de passe Vault

Choisis un mot de passe **fort** (20+ caracteres). Tu en auras besoin a chaque deploiement.

```bash
# Stocker le mot de passe pour ne pas le retaper a chaque fois
echo 'ton-mot-de-passe-vault-ici' > .vault_password
chmod 600 .vault_password
```

> **`.vault_password`** est dans `.gitignore` — il ne sera jamais commite.

### 7.2 Creer le fichier Vault

```bash
# Creer et editer le vault
ansible-vault create inventory/group_vars/all/secrets.yml --vault-password-file .vault_password
```

Cela ouvre ton editeur. Colle le contenu suivant en remplacant chaque valeur :

```yaml
---
# ====================================================================
# SECRETS — Ne JAMAIS commiter ce fichier en clair
# Editer avec : ansible-vault edit inventory/group_vars/all/secrets.yml
# ====================================================================

# --- Domaine et infra (valeurs sensibles du wizard) ---
vault_domain_name: "ai.mondomaine.com"
vault_prod_hostname: "vps-prod-01"
vault_prod_ip: "203.0.113.42"
vault_vpn_hostname: "seko-vpn"
vault_vpn_headscale_url: "https://vpn.example.com"
vault_vpn_headscale_ip: "100.64.0.1"
vault_s3_bucket_name: "vpai-backups"
vault_notification_email: "alerts@example.com"
vault_notification_webhook_url: ""

# --- Telegram Monitoring (shared with Seko-VPN) ---
vault_telegram_monitoring_bot_token: "123456:ABC-DEF..."
vault_telegram_monitoring_chat_id: "-100123456789"

# --- Telegram OpenClaw (dedicated) ---
vault_telegram_openclaw_bot_token: "789012:GHI-JKL..."
vault_telegram_openclaw_chat_id: "-100987654321"

# --- DNS API (OVH) ---
ovh_application_key: "ton-app-key-ovh"
ovh_application_secret: "ton-app-secret-ovh"
ovh_consumer_key: "ton-consumer-key-ovh"

# --- Hetzner Cloud ---
hetzner_cloud_token: "ton-token-hetzner-cloud"
hetzner_s3_access_key: "ton-access-key-s3"
hetzner_s3_secret_key: "ton-secret-key-s3"

# --- Base de donnees ---
postgresql_password: "COLLE-TA-VALEUR-GENEREE"
redis_password: "COLLE-TA-VALEUR-GENEREE"

# --- Applications ---
n8n_encryption_key: "COLLE-TA-VALEUR-GENEREE"
n8n_owner_password: "COLLE-TA-VALEUR-GENEREE"
litellm_master_key: "sk-COLLE-TA-VALEUR-GENEREE"
litellm_ui_password: "COLLE-TA-VALEUR-GENEREE"
litellm_salt_key: "COLLE-TA-VALEUR-GENEREE"
openclaw_api_key: "COLLE-TA-VALEUR-GENEREE"
grafana_admin_password: "COLLE-TA-VALEUR-GENEREE"
qdrant_api_key: "COLLE-TA-VALEUR-GENEREE"

# --- API LLM ---
anthropic_api_key: "sk-ant-api03-..."
openai_api_key: "sk-proj-..."

# --- Headscale/Tailscale ---
headscale_auth_key: "ta-cle-preauthkey-headscale"

# --- Backup heartbeat ---
vault_backup_heartbeat_url: ""

# --- SSH ---
ssh_authorized_keys:
  - "ssh-ed25519 AAAAC3... ton-email@example.com"
```

Sauvegarde et ferme l'editeur.

### 7.3 Verifier le Vault

```bash
# Le fichier doit etre chiffre
head -1 inventory/group_vars/all/secrets.yml
# Doit afficher : $ANSIBLE_VAULT;1.1;AES256

# Verifier qu'on peut le dechiffrer
ansible-vault view inventory/group_vars/all/secrets.yml --vault-password-file .vault_password
```

---

## 8. Preparer le VPS cible

### 8.1 Acces SSH initial

Connecte-toi au VPS avec les credentials de ton hebergeur :

```bash
ssh root@<IP_DU_VPS>
```

### 8.2 Creer l'utilisateur de deploiement

> **Note** : Le role `common` cree automatiquement l'utilisateur `{{ prod_user }}` avec sudo
> et configure sa cle SSH. Cette etape manuelle n'est necessaire que si le premier
> deploiement Ansible echoue (ex: connexion initiale en root uniquement).

```bash
# Sur le VPS, en tant que root (uniquement si deploiement Ansible echoue) :
adduser deploy
usermod -aG sudo deploy

# Configurer l'acces SSH par cle
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh

# Colle ta cle publique SSH
echo "ssh-ed25519 AAAAC3... ton-email@example.com" > /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
```

### 8.3 Tester la connexion

Depuis ta machine locale :

```bash
ssh deploy@<IP_DU_VPS>
# Doit se connecter sans mot de passe (via cle SSH)

# Tester sudo
sudo whoami
# Doit afficher : root
```

### 8.4 Tester Ansible

```bash
# Depuis le dossier du projet
cd VPAI

# Ping le serveur
ansible prod -m ping --vault-password-file .vault_password
# Doit afficher : prod-server | SUCCESS
```

> **Si ca echoue** : Verifie que `prod_ip`, `prod_ssh_port`, et `prod_user` correspondent
> dans `inventory/group_vars/all/secrets.yml` (ou `main.yml`).

---

## 9. Deployer en pre-production

> **Recommande** : Deployer d'abord sur un serveur de test avant la production.
> Si tu n'as pas de serveur de test, passe directement a l'etape 11.

### Avec un serveur Hetzner ephemere (CI/CD)

```bash
# Lancer le lint d'abord
source ~/.venv-vpai/bin/activate
make lint

# Si le lint passe, deployer en preprod
make deploy-preprod
```

### Avec un VPS de test deja provisionne

Modifie temporairement l'IP de preprod dans l'inventaire puis :

```bash
ansible-playbook playbooks/site.yml \
  -e "target_env=preprod" \
  --vault-password-file .vault_password \
  --diff
```

---

## 10. Valider le deploiement

### 10.1 Smoke tests automatiques

```bash
make smoke-test URL=https://ton-domaine.com
```

### 10.2 Verification manuelle

```bash
# Depuis le VPS (via SSH ou VPN)
ssh deploy@<IP_DU_VPS>

# Verifier que tous les containers tournent
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | sort

# Verifier les healthchecks
docker ps --format "{{.Names}}: {{.Status}}" | grep -i health

# Verifier les logs (pas d'erreurs critiques)
cd /opt/vpai
docker compose logs --tail 20 2>&1 | grep -i error
```

### 10.3 Tester chaque service

| Service | URL de test | Attendu |
|---------|-------------|---------|
| Caddy (HTTPS) | `curl -I https://ton-domaine.com/health` | 200 OK |
| n8n | `curl https://admin.ton-domaine.com/n8n/healthz` (VPN) | 200 OK |
| Grafana | `curl https://admin.ton-domaine.com/grafana/api/health` (VPN) | 200 OK |
| LiteLLM | `curl -H "Authorization: Bearer sk-..." https://ton-domaine.com/litellm/health` | 200 OK |
| PostgreSQL | `docker exec vpai_postgresql pg_isready` | accepting connections |
| Redis | `docker exec vpai_redis redis-cli -a <password> ping` | PONG |
| Qdrant | `curl http://localhost:6333/healthz` (depuis le VPS) | 200 OK |

### 10.4 Tester l'API LiteLLM

```bash
# Lister les modeles disponibles
curl -s https://ton-domaine.com/litellm/v1/models \
  -H "Authorization: Bearer sk-ta-litellm-master-key" | jq '.data[].id'

# Tester un appel Claude
curl -s https://ton-domaine.com/litellm/v1/chat/completions \
  -H "Authorization: Bearer sk-ta-litellm-master-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet", "messages": [{"role": "user", "content": "Hello!"}]}' | jq '.choices[0].message.content'
```

---

## 11. Deployer en production

> **ATTENTION** : Assure-toi que les etapes 4 a 10 sont validees avant de deployer en prod !

```bash
# Dernier lint de verification
make lint

# Deploiement production (avec confirmation)
make deploy-prod
# Tape "yes" quand demande
```

Le deploiement :
1. Execute les 16 roles Ansible dans l'ordre
2. Cree les repertoires, deploie les configs
3. Pull et demarre les containers Docker
4. Configure le reverse proxy Caddy
5. Lance les smoke tests automatiques

**Duree estimee** : 10-20 minutes (premier deploiement), 2-5 minutes (mise a jour).

---

## 12. Configurer les services externes

### 12.1 Uptime Kuma (sur Seko-VPN)

Suivre la procedure dans `docs/RUNBOOK.md` section 4. En resume :

1. Ouvrir Uptime Kuma sur le serveur VPN
2. Creer 6 monitors (HTTPS, n8n, Grafana, PostgreSQL, TLS, Backup Heartbeat)
3. Configurer les notifications
4. Copier l'URL du monitor Push (Backup Heartbeat) dans le Vault

### 12.2 Zerobyte (sur Seko-VPN)

Suivre la procedure dans `docs/RUNBOOK.md` section 3. En resume :

1. Ouvrir Zerobyte sur le serveur VPN
2. Creer le repository S3 (Hetzner Object Storage)
3. Creer les volumes (pg_dump, redis, qdrant, n8n, configs, grafana)
4. Creer les 6 jobs de backup avec schedules
5. Tester un backup manuel

### 12.3 GitHub Actions Secrets

Dans **GitHub** > **Settings** > **Secrets and variables** > **Actions**, ajouter :

| Secret | Valeur |
|--------|--------|
| `ANSIBLE_VAULT_PASSWORD` | Le mot de passe choisi a l'etape 7.1 |
| `SSH_PRIVATE_KEY` | Le contenu de ta cle privee SSH (cat ~/.ssh/id_ed25519) |
| `HETZNER_CLOUD_TOKEN` | Token Hetzner de l'etape 4.3 |
| `PROD_SERVER_IP` | IP publique du VPS prod |
| `PROD_DOMAIN` | Ton domaine (ex: ai.mondomaine.com) |
| `LITELLM_MASTER_KEY` | Meme valeur que dans le Vault |

---

## 13. Checklist finale

### Premier deploiement

- [ ] Outils installes (Ansible, ansible-lint, yamllint)
- [ ] Cles API obtenues (Anthropic, OpenAI)
- [ ] Secrets generes (8 secrets internes)
- [ ] PRD.md rempli avec mes valeurs
- [ ] Vault cree et rempli
- [ ] VPS prepare (utilisateur deploy, cle SSH)
- [ ] `make lint` passe sans erreur
- [ ] Connexion SSH depuis ma machine fonctionne
- [ ] `ansible prod -m ping` repond SUCCESS
- [ ] Deploiement execute sans erreur
- [ ] Smoke tests passent
- [ ] HTTPS fonctionne (certificat TLS valide)
- [ ] n8n accessible via VPN
- [ ] Grafana accessible via VPN
- [ ] LiteLLM repond aux appels API
- [ ] Uptime Kuma configure (6 monitors)
- [ ] Zerobyte configure (6 jobs de backup)
- [ ] GitHub Actions secrets configures
- [ ] Premier backup execute et verifie

### Mise a jour (redeploiement)

- [ ] Modifier la version dans `inventory/group_vars/all/versions.yml`
- [ ] `make lint` passe
- [ ] Deployer avec tags : `ansible-playbook playbooks/site.yml --tags <service> -e "target_env=prod"`
- [ ] Smoke tests passent
- [ ] Verifier les logs du service mis a jour

---

## 14. Depannage

### "Connection refused" sur SSH

```bash
# Verifie le port SSH
ssh -p 2222 deploy@<IP>

# Si le port n'est pas encore change (premier acces)
ssh root@<IP>  # port 22 par defaut
```

### "Permission denied" sur Ansible

```bash
# Verifie que ta cle publique est sur le VPS
ssh-copy-id -p 2222 deploy@<IP>

# Teste manuellement
ssh -p 2222 deploy@<IP> "sudo whoami"
```

### Vault : "Decryption failed"

```bash
# Verifie le mot de passe
ansible-vault view inventory/group_vars/all/secrets.yml --ask-vault-pass

# Regenerer le vault si le mot de passe est perdu
# (tu perds les secrets, il faudra les regenerer)
rm inventory/group_vars/all/secrets.yml
make vault-init
```

### Container qui redémarre en boucle

```bash
# Sur le VPS
docker logs --tail 50 vpai_<service>
# Cherche l'erreur dans les dernieres lignes

# Causes frequentes :
# - Variable mal remplie dans le vault
# - Base de donnees pas encore prete (depends_on pas respecte)
# - Port deja utilise
```

### "No space left on device"

```bash
# Nettoyer Docker
docker system prune --volumes -f

# Verifier l'espace
df -h /
```

### make lint echoue

```bash
# Verifier que le venv est active
source ~/.venv-vpai/bin/activate

# Erreur UTF-8 / CRLF :
find roles/ -name '*.yml' -exec file {} \; | grep -v UTF-8
# Si des fichiers non-UTF-8 apparaissent :
find roles/ -name '*.yml' -exec sed -i 's/\r$//' {} \;
```

---

---

## 15. Premier acces aux services

> **Note** : Les comptes administrateurs sont provisionnes automatiquement par Ansible
> a partir des variables `users.yml` et `secrets.yml`. Si le provisioning automatique
> echoue, suivez les procedures de fallback ci-dessous.

### 15.1 n8n (provisionne automatiquement)

Le compte owner est cree automatiquement par Ansible via l'API `/rest/owner/setup`.

- **URL** : `https://admin.<votre-domaine>/n8n/`
- **Email** : la valeur de `n8n_owner_email` dans `users.yml`
- **Mot de passe** : la valeur de `n8n_owner_password` dans `secrets.yml`

**Fallback manuel** : Si le provisioning automatique a echoue, ouvrez l'URL ci-dessus.
n8n affichera le formulaire de setup initial. Remplissez-le avec les memes credentials.

### 15.2 Grafana

- **URL** : `https://admin.<votre-domaine>/grafana/`
- **Utilisateur** : la valeur de `grafana_admin_user` dans `users.yml` (defaut: `admin`)
- **Mot de passe** : la valeur de `grafana_admin_password` dans `secrets.yml`

> Il est recommande de changer le mot de passe admin au premier login via l'interface Grafana.

### 15.3 LiteLLM

- **URL** : `https://admin.<votre-domaine>/litellm/`
- **Utilisateur** : la valeur de `litellm_ui_username` dans `users.yml`
- **Mot de passe** : la valeur de `litellm_ui_password` dans `secrets.yml`

### 15.4 OpenClaw

- **URL** : `https://admin.<votre-domaine>/openclaw/`
- **Acces API** : cle `openclaw_api_key` dans `secrets.yml`
- **Notifications** : Bot Telegram dedie si configure (voir `main.yml`)

---

> **Tu es bloque ?** Ouvre une issue sur le repository GitHub ou consulte le `docs/RUNBOOK.md` pour les procedures operationnelles.
