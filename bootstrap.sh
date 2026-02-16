#!/bin/bash
# ====================================================================
# bootstrap.sh — Initialisation du projet Ansible AI Stack
# Usage : ./bootstrap.sh
# ====================================================================

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} AI Stack — Project Bootstrap${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# --- Check prerequisites ---
echo -e "${YELLOW}>>> Checking prerequisites...${NC}"

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo -e "${RED}>>> MISSING: $1 — $2${NC}"
    MISSING=true
  else
    echo -e "${GREEN}  ✓ $1 $(command -v "$1")${NC}"
  fi
}

MISSING=false
check_cmd "python3" "Install: apt install python3"
check_cmd "pip3" "Install: apt install python3-pip"
check_cmd "git" "Install: apt install git"
check_cmd "ssh-keygen" "Install: apt install openssh-client"
check_cmd "make" "Install: apt install make"

if [ "$MISSING" = true ]; then
  echo -e "${RED}>>> Install missing prerequisites and re-run.${NC}"
  exit 1
fi

echo ""

# --- Create directory structure ---
echo -e "${YELLOW}>>> Creating directory structure...${NC}"

DIRS=(
  "inventory/group_vars/all"
  "inventory/group_vars/prod"
  "inventory/group_vars/preprod"
  "roles"
  "playbooks"
  "scripts"
  "templates"
  "docs"
  "molecule/default"
)

for dir in "${DIRS[@]}"; do
  mkdir -p "$dir"
  echo -e "${GREEN}  ✓ $dir/${NC}"
done

# --- Create role skeletons ---
echo ""
echo -e "${YELLOW}>>> Creating role skeletons...${NC}"

ROLES=(
  "common"
  "hardening"
  "docker"
  "headscale-node"
  "caddy"
  "postgresql"
  "redis"
  "qdrant"
  "n8n"
  "openclaw"
  "litellm"
  "monitoring"
  "diun"
  "backup-config"
  "uptime-config"
  "smoke-tests"
)

for role in "${ROLES[@]}"; do
  ROLE_DIRS=(
    "roles/$role/tasks"
    "roles/$role/handlers"
    "roles/$role/defaults"
    "roles/$role/vars"
    "roles/$role/templates"
    "roles/$role/files"
    "roles/$role/meta"
    "roles/$role/molecule/default"
  )

  for rd in "${ROLE_DIRS[@]}"; do
    mkdir -p "$rd"
  done

  # Create empty main.yml files if they don't exist
  for f in tasks handlers defaults vars meta; do
    FILE="roles/$role/$f/main.yml"
    if [ ! -f "$FILE" ]; then
      echo "---" > "$FILE"
      echo "# $role — $f" >> "$FILE"
    fi
  done

  # Create empty README
  if [ ! -f "roles/$role/README.md" ]; then
    echo "# Role: $role" > "roles/$role/README.md"
    echo "" >> "roles/$role/README.md"
    echo "## Description" >> "roles/$role/README.md"
    echo "" >> "roles/$role/README.md"
    echo "TODO" >> "roles/$role/README.md"
    echo "" >> "roles/$role/README.md"
    echo "## Variables" >> "roles/$role/README.md"
    echo "" >> "roles/$role/README.md"
    echo "| Variable | Default | Description |" >> "roles/$role/README.md"
    echo "|----------|---------|-------------|" >> "roles/$role/README.md"
    echo "" >> "roles/$role/README.md"
    echo "## Dependencies" >> "roles/$role/README.md"
    echo "" >> "roles/$role/README.md"
    echo "None." >> "roles/$role/README.md"
  fi

  # Create Molecule config
  if [ ! -f "roles/$role/molecule/default/molecule.yml" ]; then
    cat > "roles/$role/molecule/default/molecule.yml" << 'MOLECULE_EOF'
---
dependency:
  name: galaxy
driver:
  name: docker
platforms:
  - name: instance
    image: debian:bookworm
    pre_build_image: true
    privileged: true
    command: /sbin/init
    tmpfs:
      - /run
      - /tmp
provisioner:
  name: ansible
  playbooks:
    converge: converge.yml
    verify: verify.yml
verifier:
  name: ansible
MOLECULE_EOF
  fi

  if [ ! -f "roles/$role/molecule/default/converge.yml" ]; then
    cat > "roles/$role/molecule/default/converge.yml" << EOF
---
- name: Converge
  hosts: all
  roles:
    - role: $role
EOF
  fi

  if [ ! -f "roles/$role/molecule/default/verify.yml" ]; then
    cat > "roles/$role/molecule/default/verify.yml" << 'VERIFY_EOF'
---
- name: Verify
  hosts: all
  gather_facts: false
  tasks:
    - name: Placeholder verification
      ansible.builtin.assert:
        that: true
VERIFY_EOF
  fi

  echo -e "${GREEN}  ✓ roles/$role/${NC}"
done

# --- Install Python dependencies ---
echo ""
echo -e "${YELLOW}>>> Installing Python dependencies...${NC}"
pip3 install --user --quiet \
  ansible \
  ansible-lint \
  yamllint \
  molecule \
  molecule-docker \
  jmespath \
  ovh 2>/dev/null || {
    echo -e "${YELLOW}>>> pip install with --break-system-packages...${NC}"
    pip3 install --user --break-system-packages --quiet \
      ansible ansible-lint yamllint molecule molecule-docker jmespath ovh
  }
echo -e "${GREEN}  ✓ Python packages installed${NC}"

# --- Install Ansible collections ---
echo ""
echo -e "${YELLOW}>>> Installing Ansible collections...${NC}"
if [ -f "requirements.yml" ]; then
  ansible-galaxy install -r requirements.yml --force 2>/dev/null
  echo -e "${GREEN}  ✓ Collections installed${NC}"
else
  echo -e "${YELLOW}  ⚠ requirements.yml not found, skipping${NC}"
fi

# --- Git init ---
echo ""
echo -e "${YELLOW}>>> Initializing Git...${NC}"
if [ ! -d ".git" ]; then
  git init
  git add -A
  git commit -m "feat: initial project scaffold

- 16 role skeletons with Molecule tests
- Ansible config (pipelining, ControlMaster, forks=10)
- Makefile with lint/test/deploy shortcuts
- CI/CD workflow stubs
- Documentation structure (PRD, TECHNICAL-SPEC, GOLDEN-PROMPT)"
  echo -e "${GREEN}  ✓ Git initialized with initial commit${NC}"
else
  echo -e "${YELLOW}  ⚠ Git already initialized${NC}"
fi

# --- Vault setup reminder ---
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} Bootstrap complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo -e "  1. ${GREEN}Fill the wizard${NC} in PRD.md section 2 with your values"
echo ""
echo -e "  2. ${GREEN}Create the Vault${NC} password file:"
echo -e "     echo 'your-vault-password' > .vault_password"
echo -e "     chmod 600 .vault_password"
echo ""
echo -e "  3. ${GREEN}Create secrets${NC}:"
echo -e "     make vault-init"
echo ""
echo -e "  4. ${GREEN}Start development${NC} with Claude Code:"
echo -e "     Open this directory in Claude Code"
echo -e "     It will read CLAUDE.md automatically"
echo -e "     Give it GOLDEN-PROMPT.md Phase 1 to start"
echo ""
echo -e "  5. ${GREEN}Verify${NC}:"
echo -e "     make lint"
echo -e "     make test"
echo ""
