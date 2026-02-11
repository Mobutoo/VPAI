#!/bin/bash
# ====================================================================
# wizard.sh — Assistant interactif de configuration VPAI
# Usage : bash scripts/wizard.sh
# ====================================================================

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Output files
VAULT_FILE="inventory/group_vars/all/secrets.yml"
MAIN_FILE="inventory/group_vars/all/main.yml"
VAULT_PASS_FILE=".vault_password"
GENERATED_SECRETS_FILE="/tmp/vpai-secrets-$(date +%s).txt"

# ====================================================================
# Helper functions
# ====================================================================

banner() {
  echo ""
  echo -e "${CYAN}${BOLD}========================================${NC}"
  echo -e "${CYAN}${BOLD} $1${NC}"
  echo -e "${CYAN}${BOLD}========================================${NC}"
  echo ""
}

step() {
  echo -e "${GREEN}${BOLD}>>> $1${NC}"
}

warn() {
  echo -e "${YELLOW}  ⚠ $1${NC}"
}

error() {
  echo -e "${RED}  ✗ $1${NC}"
}

success() {
  echo -e "${GREEN}  ✓ $1${NC}"
}

ask() {
  local prompt="$1"
  local default="${2:-}"
  local var_name="$3"

  if [ -n "$default" ]; then
    echo -ne "  ${prompt} ${YELLOW}[${default}]${NC}: "
    read -r input
    eval "$var_name='${input:-$default}'"
  else
    echo -ne "  ${prompt}: "
    read -r input
    while [ -z "$input" ]; do
      echo -ne "  ${RED}Requis.${NC} ${prompt}: "
      read -r input
    done
    eval "$var_name='$input'"
  fi
}

ask_secret() {
  local prompt="$1"
  local var_name="$2"

  echo -ne "  ${prompt}: "
  read -rs input
  echo ""
  while [ -z "$input" ]; do
    echo -ne "  ${RED}Requis.${NC} ${prompt}: "
    read -rs input
    echo ""
  done
  eval "$var_name='$input'"
}

ask_yesno() {
  local prompt="$1"
  local default="${2:-y}"
  local var_name="$3"

  if [ "$default" = "y" ]; then
    echo -ne "  ${prompt} ${YELLOW}[Y/n]${NC}: "
  else
    echo -ne "  ${prompt} ${YELLOW}[y/N]${NC}: "
  fi
  read -r input
  input="${input:-$default}"
  case "$input" in
    [yY]*) eval "$var_name=true" ;;
    *) eval "$var_name=false" ;;
  esac
}

generate_secret() {
  openssl rand -base64 32 | tr -d '=/+' | head -c 32
}

generate_hex() {
  openssl rand -hex 32
}

# ====================================================================
# Pre-checks
# ====================================================================

banner "VPAI — Assistant de Configuration"

echo -e "  Ce wizard va te guider pour configurer ton deploiement VPAI."
echo -e "  Il va :"
echo -e "    1. Te poser des questions sur ton infrastructure"
echo -e "    2. Generer les secrets internes automatiquement"
echo -e "    3. Te demander les cles API externes"
echo -e "    4. Creer le fichier Vault chiffre"
echo ""
echo -e "  ${YELLOW}Duree estimee : 10-15 minutes${NC}"
echo ""

# Check prerequisites
step "Verification des prerequis..."

MISSING=false
for cmd in ansible-vault openssl jq; do
  if command -v "$cmd" &>/dev/null; then
    success "$cmd installe"
  else
    error "$cmd manquant"
    MISSING=true
  fi
done

if [ "$MISSING" = true ]; then
  error "Installe les outils manquants et relance le wizard."
  exit 1
fi

echo ""
echo -ne "  ${BOLD}Pret a commencer ? [Entree pour continuer]${NC}"
read -r

# ====================================================================
# ETAPE 1 : Identite du projet
# ====================================================================

banner "Etape 1/8 — Identite du Projet"

ask "Nom court du projet (minuscules, sans espaces)" "vpai" PROJECT_NAME
ask "Nom affiche (pour les dashboards)" "VPAI" PROJECT_DISPLAY
ask "Description du projet" "Stack AI/automatisation auto-hebergee" PROJECT_DESC

# ====================================================================
# ETAPE 2 : Domaine et DNS
# ====================================================================

banner "Etape 2/8 — Domaine et DNS"

ask "Nom de domaine principal" "" DOMAIN_NAME
echo ""
echo -e "  Quel est ton registrar DNS ?"
echo -e "    1) OVH"
echo -e "    2) Cloudflare"
echo -e "    3) Hetzner"
echo -ne "  Choix [1]: "
read -r dns_choice
dns_choice="${dns_choice:-1}"
case "$dns_choice" in
  1) DOMAIN_REGISTRAR="ovh" ; DNS_ENDPOINT="ovh-eu" ;;
  2) DOMAIN_REGISTRAR="cloudflare" ; DNS_ENDPOINT="cloudflare" ;;
  3) DOMAIN_REGISTRAR="hetzner" ; DNS_ENDPOINT="hetzner" ;;
  *) DOMAIN_REGISTRAR="ovh" ; DNS_ENDPOINT="ovh-eu" ;;
esac
success "Registrar : $DOMAIN_REGISTRAR"

# ====================================================================
# ETAPE 3 : VPS Production
# ====================================================================

banner "Etape 3/8 — VPS Production"

ask "IP publique du VPS" "" PROD_IP
ask "Hostname du VPS" "vps-prod-01" PROD_HOSTNAME
ask "Port SSH" "2222" PROD_SSH_PORT
ask "Utilisateur de deploiement" "deploy" PROD_USER
ask "RAM du VPS en Go" "8" PROD_RAM
ask "Nombre de CPU cores" "4" PROD_CPU

echo ""
echo -e "  Quel est ton fournisseur VPS ?"
echo -e "    1) OVH"
echo -e "    2) Hetzner"
echo -e "    3) Ionos"
echo -e "    4) Autre"
echo -ne "  Choix [1]: "
read -r vps_choice
case "${vps_choice:-1}" in
  1) PROD_PROVIDER="ovh" ;;
  2) PROD_PROVIDER="hetzner" ;;
  3) PROD_PROVIDER="ionos" ;;
  *) ask "Nom du fournisseur" "" PROD_PROVIDER ;;
esac

# ====================================================================
# ETAPE 4 : VPN Headscale
# ====================================================================

banner "Etape 4/8 — VPN Headscale"

echo -e "  ${YELLOW}Tu dois avoir un serveur Headscale fonctionnel.${NC}"
echo ""

ask "URL du serveur Headscale" "https://vpn.example.com" VPN_HEADSCALE_URL
ask "IP Headscale du serveur VPN" "" VPN_HEADSCALE_IP
ask "Hostname du serveur VPN" "seko-vpn" VPN_HOSTNAME
ask "CIDR du reseau VPN" "100.64.0.0/10" VPN_CIDR

echo ""
echo -e "  Quel est le fournisseur du serveur VPN ?"
echo -e "    1) Ionos"
echo -e "    2) Hetzner"
echo -e "    3) OVH"
echo -ne "  Choix [1]: "
read -r vpn_provider_choice
case "${vpn_provider_choice:-1}" in
  1) VPN_PROVIDER="ionos" ;;
  2) VPN_PROVIDER="hetzner" ;;
  3) VPN_PROVIDER="ovh" ;;
  *) VPN_PROVIDER="ionos" ;;
esac

# ====================================================================
# ETAPE 5 : Notifications
# ====================================================================

banner "Etape 5/8 — Notifications"

echo -e "  Quel canal pour les alertes ?"
echo -e "    1) Telegram"
echo -e "    2) Discord"
echo -e "    3) Slack"
echo -e "    4) Aucun (je configurerai plus tard)"
echo -ne "  Choix [1]: "
read -r notif_choice

case "${notif_choice:-1}" in
  1)
    NOTIF_METHOD="telegram"
    echo ""
    echo -e "  ${CYAN}Comment obtenir le webhook Telegram :${NC}"
    echo -e "    1. Ouvre Telegram, cherche @BotFather"
    echo -e "    2. Envoie /newbot, suis les instructions"
    echo -e "    3. Note le token du bot"
    echo -e "    4. Cree un groupe, ajoute le bot"
    echo -e "    5. Recupere le chat ID (voir docs/FIRST-DEPLOY.md)"
    echo ""
    ask "URL webhook Telegram (ou vide pour plus tard)" "" NOTIF_WEBHOOK
    ;;
  2)
    NOTIF_METHOD="discord"
    echo ""
    echo -e "  ${CYAN}Parametres du canal Discord > Integrations > Webhooks > Nouveau webhook${NC}"
    echo ""
    ask "URL webhook Discord (ou vide pour plus tard)" "" NOTIF_WEBHOOK
    ;;
  3)
    NOTIF_METHOD="slack"
    ask "URL webhook Slack (ou vide pour plus tard)" "" NOTIF_WEBHOOK
    ;;
  *)
    NOTIF_METHOD="none"
    NOTIF_WEBHOOK=""
    ;;
esac

ask "Email de notification" "" NOTIF_EMAIL

# ====================================================================
# ETAPE 6 : Cles API externes
# ====================================================================

banner "Etape 6/8 — Cles API Externes"

echo -e "  ${YELLOW}Tu vas avoir besoin des cles API de tes fournisseurs LLM.${NC}"
echo -e "  ${YELLOW}Si tu ne les as pas encore, tu peux les ajouter plus tard via :${NC}"
echo -e "  ${YELLOW}  ansible-vault edit inventory/group_vars/all/secrets.yml${NC}"
echo ""

# Anthropic
echo -e "  ${CYAN}--- Anthropic (Claude) ---${NC}"
echo -e "  Obtenir sur : https://console.anthropic.com/settings/keys"
ask "Cle API Anthropic (sk-ant-... ou vide)" "" ANTHROPIC_KEY

# OpenAI
echo ""
echo -e "  ${CYAN}--- OpenAI (GPT) ---${NC}"
echo -e "  Obtenir sur : https://platform.openai.com/api-keys"
ask "Cle API OpenAI (sk-proj-... ou vide)" "" OPENAI_KEY

# Hetzner
echo ""
echo -e "  ${CYAN}--- Hetzner Cloud (CI/CD preprod) ---${NC}"
echo -e "  Obtenir sur : https://console.hetzner.cloud > Security > API Tokens"
ask "Token Hetzner Cloud (ou vide)" "" HETZNER_TOKEN

# Hetzner S3
echo ""
echo -e "  ${CYAN}--- Hetzner S3 (backups) ---${NC}"
echo -e "  Obtenir sur : https://console.hetzner.cloud > Object Storage > Manage credentials"
ask "S3 Access Key (ou vide)" "" S3_ACCESS_KEY
ask "S3 Secret Key (ou vide)" "" S3_SECRET_KEY
ask "Nom du bucket S3" "vpai-backups" S3_BUCKET

# OVH DNS (si registrar OVH)
OVH_APP_KEY=""
OVH_APP_SECRET=""
OVH_CONSUMER_KEY=""
if [ "$DOMAIN_REGISTRAR" = "ovh" ]; then
  echo ""
  echo -e "  ${CYAN}--- OVH API (gestion DNS automatique) ---${NC}"
  echo -e "  Obtenir sur : https://api.ovh.com/createToken/"
  echo -e "  Droits requis : GET/PUT/POST/DELETE sur /domain/zone/*"
  echo ""
  ask "OVH Application Key (ou vide)" "" OVH_APP_KEY
  ask "OVH Application Secret (ou vide)" "" OVH_APP_SECRET
  ask "OVH Consumer Key (ou vide)" "" OVH_CONSUMER_KEY
fi

# Headscale
echo ""
echo -e "  ${CYAN}--- Headscale (pre-auth key) ---${NC}"
echo -e "  Generer sur ton serveur VPN :"
echo -e "    headscale preauthkeys create --namespace prod --reusable --expiration 24h"
echo ""
ask "Cle pre-authentification Headscale (ou vide)" "" HEADSCALE_KEY

# ====================================================================
# ETAPE 7 : Generation des secrets internes
# ====================================================================

banner "Etape 7/8 — Generation des Secrets Internes"

step "Generation automatique de 8 secrets..."

PG_PASSWORD=$(generate_secret)
REDIS_PASSWORD=$(generate_secret)
QDRANT_KEY=$(generate_hex)
LITELLM_KEY="sk-$(openssl rand -hex 24)"
N8N_ENCRYPTION=$(generate_hex)
N8N_AUTH_PASSWORD=$(generate_secret)
GRAFANA_PASSWORD=$(generate_secret)
OPENCLAW_KEY=$(generate_hex)

success "postgresql_password : ${PG_PASSWORD:0:8}..."
success "redis_password      : ${REDIS_PASSWORD:0:8}..."
success "qdrant_api_key      : ${QDRANT_KEY:0:8}..."
success "litellm_master_key  : ${LITELLM_KEY:0:12}..."
success "n8n_encryption_key  : ${N8N_ENCRYPTION:0:8}..."
success "n8n_basic_auth_pass : ${N8N_AUTH_PASSWORD:0:8}..."
success "grafana_admin_pass  : ${GRAFANA_PASSWORD:0:8}..."
success "openclaw_api_key    : ${OPENCLAW_KEY:0:8}..."

echo ""
warn "IMPORTANT : n8n_encryption_key ne doit JAMAIS etre change apres le 1er deploiement !"

# Sauvegarder en clair temporairement
cat > "$GENERATED_SECRETS_FILE" << SECRETS_EOF
# SECRETS GENERES — $(date)
# SUPPRIMER CE FICHIER APRES AVOIR VERIFIE LE VAULT !

postgresql_password: $PG_PASSWORD
redis_password: $REDIS_PASSWORD
qdrant_api_key: $QDRANT_KEY
litellm_master_key: $LITELLM_KEY
n8n_encryption_key: $N8N_ENCRYPTION
n8n_basic_auth_password: $N8N_AUTH_PASSWORD
grafana_admin_password: $GRAFANA_PASSWORD
openclaw_api_key: $OPENCLAW_KEY
SECRETS_EOF
chmod 600 "$GENERATED_SECRETS_FILE"
warn "Secrets sauvegardes temporairement dans : $GENERATED_SECRETS_FILE"
warn "SUPPRIME ce fichier apres verification !"

# ====================================================================
# ETAPE 8 : Ecriture des fichiers
# ====================================================================

banner "Etape 8/8 — Ecriture de la Configuration"

# --- SSH Key ---
SSH_PUB_KEY=""
if [ -f "$HOME/.ssh/id_ed25519.pub" ]; then
  SSH_PUB_KEY=$(cat "$HOME/.ssh/id_ed25519.pub")
  success "Cle SSH publique detectee : ${SSH_PUB_KEY:0:30}..."
elif [ -f "$HOME/.ssh/id_rsa.pub" ]; then
  SSH_PUB_KEY=$(cat "$HOME/.ssh/id_rsa.pub")
  success "Cle SSH publique detectee : ${SSH_PUB_KEY:0:30}..."
else
  warn "Pas de cle SSH publique trouvee."
  ask "Colle ta cle publique SSH (ou vide)" "" SSH_PUB_KEY
fi

# --- Vault password ---
step "Configuration du mot de passe Vault..."
if [ -f "$VAULT_PASS_FILE" ]; then
  warn "Fichier $VAULT_PASS_FILE existe deja, on le reutilise."
else
  echo ""
  echo -e "  Choisis un mot de passe pour chiffrer le Vault (20+ caracteres)."
  echo -e "  ${YELLOW}Tu en auras besoin a chaque deploiement.${NC}"
  echo ""
  ask_secret "Mot de passe Vault" VAULT_PASSWORD

  echo "$VAULT_PASSWORD" > "$VAULT_PASS_FILE"
  chmod 600 "$VAULT_PASS_FILE"
  success "Mot de passe sauvegarde dans $VAULT_PASS_FILE"
fi

# --- Write main.yml ---
step "Ecriture de inventory/group_vars/all/main.yml..."

cat > "$MAIN_FILE" << MAIN_EOF
---
# inventory/group_vars/all/main.yml — Variables generales (wizard)
# Genere par scripts/wizard.sh le $(date '+%Y-%m-%d %H:%M')
# Source unique de verite — Remplir avant tout deploiement

# --- Identite projet ---
project_name: "$PROJECT_NAME"
project_display_name: "$PROJECT_DISPLAY"
project_description: "$PROJECT_DESC"
project_repo_url: "git@github.com:Mobutoo/VPAI.git"
project_repo_branch: "main"

# --- Domaine & DNS ---
domain_name: "{{ vault_domain_name | default('example.com') }}"
domain_registrar: "$DOMAIN_REGISTRAR"
dns_api_endpoint: "$DNS_ENDPOINT"
subdomain_preprod: "preprod"

# --- VPS Production ---
prod_provider: "$PROD_PROVIDER"
prod_hostname: "{{ vault_prod_hostname | default('vps-prod-01') }}"
prod_ip: "{{ vault_prod_ip | default('127.0.0.1') }}"
prod_os: "debian-13"
prod_ram_gb: $PROD_RAM
prod_cpu_cores: $PROD_CPU
prod_disk_gb: 75
prod_ssh_port: $PROD_SSH_PORT
prod_user: "$PROD_USER"

# --- VPS VPN (existant) ---
vpn_provider: "$VPN_PROVIDER"
vpn_hostname: "{{ vault_vpn_hostname | default('seko-vpn') }}"
vpn_headscale_url: "{{ vault_vpn_headscale_url | default('https://vpn.example.com') }}"
vpn_headscale_ip: "{{ vault_vpn_headscale_ip | default('127.0.0.1') }}"
vpn_network_cidr: "$VPN_CIDR"

# --- Pre-production (Hetzner Cloud) ---
preprod_provider: "hetzner"
preprod_server_type: "cx23"
preprod_location: "fsn1"
preprod_os_image: "debian-13"

# --- Stockage S3 (Hetzner Object Storage) ---
s3_provider: "hetzner"
s3_region: "fsn1"
s3_bucket_name: "{{ vault_s3_bucket_name | default('vpai-backups') }}"
s3_endpoint: "fsn1.your-objectstorage.com"

# --- Notifications ---
notification_method: "$NOTIF_METHOD"
notification_webhook_url: "{{ vault_notification_webhook_url | default('') }}"
notification_email: "{{ vault_notification_email | default('') }}"

# --- Timezone ---
timezone: "Europe/Paris"
locale: "fr_FR.UTF-8"

# --- Environment ---
target_env: "prod"
MAIN_EOF

success "main.yml ecrit"

# --- Write Vault ---
step "Creation du Vault chiffre..."

# Create temporary cleartext vault
VAULT_TEMP=$(mktemp)
cat > "$VAULT_TEMP" << VAULT_EOF
---
# ====================================================================
# SECRETS — Genere par wizard.sh le $(date '+%Y-%m-%d %H:%M')
# Editer avec : ansible-vault edit inventory/group_vars/all/secrets.yml
# ====================================================================

# --- Domaine et infra ---
vault_domain_name: "$DOMAIN_NAME"
vault_prod_hostname: "$PROD_HOSTNAME"
vault_prod_ip: "$PROD_IP"
vault_vpn_hostname: "$VPN_HOSTNAME"
vault_vpn_headscale_url: "$VPN_HEADSCALE_URL"
vault_vpn_headscale_ip: "$VPN_HEADSCALE_IP"
vault_s3_bucket_name: "$S3_BUCKET"
vault_notification_webhook_url: "$NOTIF_WEBHOOK"
vault_notification_email: "$NOTIF_EMAIL"

# --- DNS API (OVH) ---
ovh_application_key: "$OVH_APP_KEY"
ovh_application_secret: "$OVH_APP_SECRET"
ovh_consumer_key: "$OVH_CONSUMER_KEY"

# --- Hetzner Cloud ---
hetzner_cloud_token: "$HETZNER_TOKEN"
hetzner_s3_access_key: "$S3_ACCESS_KEY"
hetzner_s3_secret_key: "$S3_SECRET_KEY"

# --- Base de donnees ---
postgresql_password: "$PG_PASSWORD"
redis_password: "$REDIS_PASSWORD"

# --- Applications ---
n8n_encryption_key: "$N8N_ENCRYPTION"
n8n_basic_auth_user: "admin"
n8n_basic_auth_password: "$N8N_AUTH_PASSWORD"
litellm_master_key: "$LITELLM_KEY"
openclaw_api_key: "$OPENCLAW_KEY"
grafana_admin_password: "$GRAFANA_PASSWORD"
qdrant_api_key: "$QDRANT_KEY"

# --- API LLM ---
anthropic_api_key: "$ANTHROPIC_KEY"
openai_api_key: "$OPENAI_KEY"

# --- Headscale/Tailscale ---
headscale_auth_key: "$HEADSCALE_KEY"

# --- Backup heartbeat ---
vault_backup_heartbeat_url: ""

# --- SSH ---
ssh_authorized_keys:
  - "$SSH_PUB_KEY"
VAULT_EOF

# Encrypt the vault
ansible-vault encrypt "$VAULT_TEMP" --vault-password-file "$VAULT_PASS_FILE" --output "$VAULT_FILE" 2>/dev/null
rm -f "$VAULT_TEMP"
success "Vault cree et chiffre : $VAULT_FILE"

# ====================================================================
# Recap
# ====================================================================

banner "Configuration Terminee !"

echo -e "  ${GREEN}Fichiers generes :${NC}"
echo -e "    ✓ $MAIN_FILE"
echo -e "    ✓ $VAULT_FILE (chiffre)"
echo -e "    ✓ $VAULT_PASS_FILE"
echo ""
echo -e "  ${YELLOW}Prochaines etapes :${NC}"
echo ""
echo -e "    1. ${BOLD}Verifier la config :${NC}"
echo -e "       ansible-vault view $VAULT_FILE --vault-password-file $VAULT_PASS_FILE"
echo ""
echo -e "    2. ${BOLD}Lancer le lint :${NC}"
echo -e "       make lint"
echo ""
echo -e "    3. ${BOLD}Tester la connexion SSH :${NC}"
echo -e "       ssh -p $PROD_SSH_PORT $PROD_USER@$PROD_IP"
echo ""
echo -e "    4. ${BOLD}Deployer :${NC}"
echo -e "       make deploy-prod"
echo ""
echo -e "  ${RED}N'oublie pas de supprimer le fichier temporaire des secrets :${NC}"
echo -e "    rm $GENERATED_SECRETS_FILE"
echo ""
echo -e "  ${CYAN}Documentation complete : docs/FIRST-DEPLOY.md${NC}"
echo ""
