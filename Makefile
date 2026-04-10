# ====================================================================
# Makefile — Raccourcis pour le projet Ansible AI Stack
# ====================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Variables
ANSIBLE_PLAYBOOK := ansible-playbook
ANSIBLE_LINT := ansible-lint
YAMLLINT := yamllint
MOLECULE := molecule
VAULT_FILE := inventory/group_vars/all/secrets.yml

# Colors
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
NC     := \033[0m

.PHONY: help
help: ## Afficher cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# ====================================================================
# SETUP
# ====================================================================

.PHONY: setup
setup: ## Installation complète des dépendances
	@echo "$(GREEN)>>> Installing Python dependencies...$(NC)"
	pip3 install --user ansible ansible-lint yamllint molecule molecule-docker jmespath
	@echo "$(GREEN)>>> Installing Ansible collections...$(NC)"
	ansible-galaxy install -r requirements.yml --force
	@echo "$(GREEN)>>> Setup complete$(NC)"

.PHONY: vault-init
vault-init: ## Créer le fichier Ansible Vault (interactif)
	@if [ -f $(VAULT_FILE) ]; then \
		echo "$(YELLOW)>>> Vault file already exists. Use 'make vault-edit' to modify.$(NC)"; \
	else \
		ansible-vault create $(VAULT_FILE); \
		echo "$(GREEN)>>> Vault file created$(NC)"; \
	fi

.PHONY: vault-edit
vault-edit: ## Éditer le fichier Ansible Vault
	ansible-vault edit $(VAULT_FILE)

# ====================================================================
# QUALITY
# ====================================================================

.PHONY: lint
lint: ## Lancer yamllint + ansible-lint
	@echo "$(GREEN)>>> Running yamllint...$(NC)"
	find . \( -name '*.yml' -o -name '*.yaml' \) ! -path './.git/*' ! -path './.venv/*' ! -path '*/molecule/*' ! -path '*/collections/*' ! -path '*/node_modules/*' ! -name 'secrets.yml' -print0 | xargs -0 $(YAMLLINT) -c .yamllint.yml
	@echo "$(GREEN)>>> Running ansible-lint...$(NC)"
	$(ANSIBLE_LINT) playbooks/site.yml
	@echo "$(GREEN)>>> All linting passed$(NC)"

.PHONY: lint-yaml
lint-yaml: ## Lancer yamllint uniquement
	find . \( -name '*.yml' -o -name '*.yaml' \) ! -path './.git/*' ! -path './.venv/*' ! -path '*/molecule/*' ! -path '*/collections/*' ! -path '*/node_modules/*' ! -name 'secrets.yml' -print0 | xargs -0 $(YAMLLINT) -c .yamllint.yml

.PHONY: lint-ansible
lint-ansible: ## Lancer ansible-lint uniquement
	$(ANSIBLE_LINT) playbooks/site.yml

.PHONY: check-no-latest
check-no-latest: ## Vérifier qu'aucune image Docker n'utilise :latest
	@echo "$(GREEN)>>> Checking for :latest tags...$(NC)"
	@if grep -r ':latest\|:stable\|:main' inventory/group_vars/all/versions.yml; then \
		echo "$(RED)>>> FAIL: Found :latest or :stable tags!$(NC)"; exit 1; \
	else \
		echo "$(GREEN)>>> OK: No :latest tags found$(NC)"; \
	fi

.PHONY: check-hardcoded
check-hardcoded: ## Vérifier qu'aucune valeur n'est hardcodée (recherche le nom du projet)
	@echo "$(GREEN)>>> Checking for hardcoded values...$(NC)"
	@echo "$(YELLOW)>>> Enter project name to check (e.g., seko-ai):$(NC)"
	@read PROJECT_NAME && \
	FOUND=$$(grep -rl "$$PROJECT_NAME" --include="*.yml" --include="*.j2" --include="*.cfg" \
		--exclude-dir=.git --exclude="PRD.md" --exclude="TECHNICAL-SPEC.md" \
		--exclude="GOLDEN-PROMPT.md" --exclude="CLAUDE.md" . 2>/dev/null | head -20); \
	if [ -n "$$FOUND" ]; then \
		echo "$(RED)>>> FAIL: Hardcoded values found in:$(NC)"; \
		echo "$$FOUND"; exit 1; \
	else \
		echo "$(GREEN)>>> OK: No hardcoded values$(NC)"; \
	fi

# ====================================================================
# TESTS
# ====================================================================

.PHONY: test
test: ## Lancer les tests Molecule pour tous les rôles
	@echo "$(GREEN)>>> Running Molecule tests for all roles...$(NC)"
	@for role in roles/*/; do \
		if [ -d "$$role/molecule" ]; then \
			echo "$(GREEN)>>> Testing $$(basename $$role)...$(NC)"; \
			cd "$$role" && $(MOLECULE) test && cd ../..; \
		fi \
	done
	@echo "$(GREEN)>>> All tests passed$(NC)"

.PHONY: test-role
test-role: ## Tester un rôle spécifique (usage: make test-role ROLE=common)
	@if [ -z "$(ROLE)" ]; then \
		echo "$(RED)>>> Usage: make test-role ROLE=<role_name>$(NC)"; exit 1; \
	fi
	@echo "$(GREEN)>>> Testing role $(ROLE)...$(NC)"
	cd roles/$(ROLE) && $(MOLECULE) test

# ====================================================================
# DEPLOY
# ====================================================================

.PHONY: check
check: ## Dry-run du playbook principal (--check --diff)
	$(ANSIBLE_PLAYBOOK) playbooks/site.yml --check --diff

.PHONY: deploy-preprod
deploy-preprod: lint ## Déployer en pré-production (Hetzner permanent)
	@echo "$(YELLOW)>>> Deploying to PRE-PRODUCTION...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/site.yml \
		-e "target_env=preprod" \
		--diff

.PHONY: deploy-prod
deploy-prod: lint ## Déployer en production (usage: make deploy-prod EXTRA_VARS="ansible_port_override=804")
	@echo "$(RED)>>> PRODUCTION DEPLOYMENT$(NC)"
	@echo "$(YELLOW)>>> Are you sure? Type 'yes' to continue:$(NC)"
	@read CONFIRM && \
	if [ "$$CONFIRM" = "yes" ]; then \
		$(ANSIBLE_PLAYBOOK) playbooks/site.yml \
			-e "target_env=prod" \
			$(if $(EXTRA_VARS),-e "$(EXTRA_VARS)") \
			--diff; \
	else \
		echo "$(YELLOW)>>> Aborted$(NC)"; exit 1; \
	fi

.PHONY: deploy-role
deploy-role: ## Déployer un rôle spécifique (usage: make deploy-role ROLE=n8n ENV=prod)
	@if [ -z "$(ROLE)" ] || [ -z "$(ENV)" ]; then \
		echo "$(RED)>>> Usage: make deploy-role ROLE=<role> ENV=<prod|preprod>$(NC)"; exit 1; \
	fi
	$(ANSIBLE_PLAYBOOK) playbooks/site.yml \
		-e "target_env=$(ENV)" \
		--tags "$(ROLE)" \
		--diff

.PHONY: openclaw-profile
openclaw-profile: ## Basculer le profil modèle OpenClaw (usage: make openclaw-profile PROFILE=premium)
	@if [ -z "$(PROFILE)" ]; then \
		echo "$(RED)>>> Usage: make openclaw-profile PROFILE=<eco|balanced|premium|openai>$(NC)"; \
		echo "$(YELLOW)>>>   eco      = modèles gratuits (DeepSeek, Qwen) — $$0/jour$(NC)"; \
		echo "$(YELLOW)>>>   balanced = mid-tier (GLM-5, DeepSeek R1) — ~$$1-2/jour$(NC)"; \
		echo "$(YELLOW)>>>   premium  = qualité max (Claude, GPT-4o) — ~$$3-5/jour$(NC)"; \
		echo "$(YELLOW)>>>   openai   = OpenAI OAuth only (GPT-5.4, 5.3-Codex, o4-mini) — abo Plus$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)>>> Switching OpenClaw to profile: $(PROFILE)$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/site.yml \
		-e "target_env=prod" \
		-e "openclaw_model_profile=$(PROFILE)" \
		--tags "openclaw" \
		--diff
	@if [ "$(PROFILE)" = "openai" ]; then \
		echo "$(YELLOW)>>> IMPORTANT: Run 'make openclaw-oauth-login' to authenticate with OpenAI$(NC)"; \
	fi

.PHONY: openclaw-oauth-start
openclaw-oauth-start: ## Étape 1 OAuth : générer l'URL d'autorisation OpenAI
	@echo "$(YELLOW)>>> Generating OpenAI OAuth URL...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/openclaw-oauth.yml \
		-e "target_env=prod" \
		-e "oauth_step=start"

.PHONY: openclaw-oauth-complete
openclaw-oauth-complete: ## Étape 2 OAuth : échanger le code (usage: make openclaw-oauth-complete URL=<redirect-url>)
	@if [ -z "$(URL)" ]; then \
		echo "$(RED)>>> Usage: make openclaw-oauth-complete URL=<redirect-url-from-browser>$(NC)"; exit 1; \
	fi
	@echo "$(YELLOW)>>> Exchanging auth code for token...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/openclaw-oauth.yml \
		-e "target_env=prod" \
		-e "oauth_step=complete" \
		-e "oauth_callback_url=$(URL)"

.PHONY: openclaw-oauth-status
openclaw-oauth-status: ## Vérifier le statut OAuth OpenAI sur OpenClaw
	ansible prod-server -m raw \
		-a 'docker exec {{ project_name }}_openclaw openclaw models status' \
		-e "target_env=prod"

.PHONY: smoke-test
smoke-test: ## Lancer les smoke tests
	@if [ -z "$(URL)" ]; then \
		echo "$(RED)>>> Usage: make smoke-test URL=https://example.com$(NC)"; exit 1; \
	fi
	bash scripts/smoke-test.sh "$(URL)"

# ====================================================================
# VPN TOGGLE
# ====================================================================

.PHONY: vpn-on
vpn-on: ## Basculer en mode VPN-only (ports fermés, webhooks via relay)
	@echo "$(RED)>>> VPN-ONLY MODE ACTIVATION$(NC)"
	@echo "$(YELLOW)>>> This will restrict port 443 to VPN CIDR and close port 80.$(NC)"
	@echo "$(YELLOW)>>> A dead man switch will auto-revert UFW in 15 min if toggle fails.$(NC)"
	@echo "$(YELLOW)>>> Are you sure? Type 'yes' to continue:$(NC)"
	@read CONFIRM && \
	if [ "$$CONFIRM" = "yes" ]; then \
		$(ANSIBLE_PLAYBOOK) playbooks/vpn-toggle.yml \
			-e "vpn_mode=on" \
			--diff; \
	else \
		echo "$(YELLOW)>>> Aborted$(NC)"; exit 1; \
	fi

.PHONY: vpn-off
vpn-off: ## Retour en mode public (ports 80+443 ouverts)
	@echo "$(YELLOW)>>> Switching to PUBLIC mode...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/vpn-toggle.yml \
		-e "vpn_mode=off" \
		--diff

.PHONY: vpn-status
vpn-status: ## Afficher l'état VPN actuel (UFW, Caddy, relay)
	@echo "$(GREEN)>>> Checking VPN status...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/safety-check.yml -e "target_env=prod"

# ====================================================================
# OPERATIONS
# ====================================================================

.PHONY: backup-restore
backup-restore: ## Restaurer depuis un backup S3
	$(ANSIBLE_PLAYBOOK) playbooks/backup-restore.yml --diff

.PHONY: rollback
rollback: ## Rollback à la version précédente
	@echo "$(RED)>>> ROLLBACK$(NC)"
	@echo "$(YELLOW)>>> Are you sure? Type 'yes' to continue:$(NC)"
	@read CONFIRM && \
	if [ "$$CONFIRM" = "yes" ]; then \
		$(ANSIBLE_PLAYBOOK) playbooks/rollback.yml --diff; \
	else \
		echo "$(YELLOW)>>> Aborted$(NC)"; exit 1; \
	fi

.PHONY: rotate-secrets
rotate-secrets: ## Rotation de tous les secrets
	$(ANSIBLE_PLAYBOOK) playbooks/rotate-secrets.yml --diff

.PHONY: inventory
inventory: ## Afficher l'inventaire
	ansible-inventory --list --yaml

# ====================================================================
# WORKSTATION
# ====================================================================

.PHONY: deploy-workstation
deploy-workstation: ## Deployer la workstation Pi
	@echo "$(GREEN)>>> Deploying Workstation Pi...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --diff

.PHONY: deploy-memory-worker
deploy-memory-worker: ## Deployer uniquement le worker memoire sur la workstation Pi
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "llamaindex-memory-worker" --diff

.PHONY: memory-benchmark
memory-benchmark: ## Lancer le benchmark retrieval sur Waza (usage: make memory-benchmark REPO=VPAI)
	@if [ -z "$(REPO)" ]; then \
		echo "$(RED)>>> Usage: make memory-benchmark REPO=<VPAI|flash-studio|story-engine>$(NC)"; exit 1; \
	fi
	ansible workstation -i inventory/hosts.yml -m shell -a 'bash -lc "set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a; /opt/workstation/ai-memory-worker/.venv/bin/python /opt/workstation/ai-memory-worker/benchmark_memory.py --config /opt/workstation/configs/ai-memory-worker/config.yml --repo $(REPO)"'

.PHONY: memory-benchmark-all
memory-benchmark-all: ## Lancer le benchmark retrieval sur les 3 repos prioritaires
	@for repo in VPAI flash-studio story-engine; do \
		echo "$(GREEN)>>> Benchmark $$repo...$(NC)"; \
		$(MAKE) memory-benchmark REPO=$$repo || exit $$?; \
	done

.PHONY: memory-backfill
memory-backfill: ## Lancer un backfill manuel sur Waza (usage: make memory-backfill REPO=VPAI EXTRA=\"--dry-run --max-files 50\")
	@if [ -z "$(REPO)" ]; then \
		echo "$(RED)>>> Usage: make memory-backfill REPO=<VPAI|flash-studio|story-engine> [EXTRA=\"...\"]$(NC)"; exit 1; \
	fi
	ansible workstation -i inventory/hosts.yml -m shell -a 'bash -lc "/home/mobuone/VPAI/scripts/memory-backfill.sh --repo $(REPO) $(EXTRA)"'

.PHONY: memory-backfill-seed
memory-backfill-seed: ## Lancer le seed v0.3 d'un repo prioritaire (usage: make memory-backfill-seed REPO=VPAI)
	@if [ -z "$(REPO)" ]; then \
		echo "$(RED)>>> Usage: make memory-backfill-seed REPO=<VPAI|flash-studio|story-engine>$(NC)"; exit 1; \
	fi
	@case "$(REPO)" in \
		VPAI) EXTRA_ARGS='--path /home/mobuone/VPAI/playbooks/site.yml --path /home/mobuone/VPAI/playbooks/workstation.yml --path /home/mobuone/VPAI/inventory/hosts.yml --path /home/mobuone/VPAI/roles/llamaindex-memory-worker/defaults/main.yml --path /home/mobuone/VPAI/roles/llamaindex-memory-worker/tasks/main.yml --path /home/mobuone/VPAI/scripts/n8n-workflows/memory-run-report-ingest.json --path /home/mobuone/VPAI/scripts/n8n-workflows/memory-healthcheck.json --path /home/mobuone/VPAI/docs/runbooks/AI-MEMORY-OPERATIONS.md --path /home/mobuone/VPAI/Makefile' ;; \
		flash-studio) EXTRA_ARGS='--path /home/mobuone/flash-studio/docs/QUICK_REFERENCE.md --path /home/mobuone/flash-studio/docs/GUIDE_INITIALISATION.md --path /home/mobuone/flash-studio/flash-infra/README.md --path /home/mobuone/flash-studio/flash-infra/ARCHITECTURE.md --path /home/mobuone/flash-studio/flash-infra/ansible/playbooks/site.yml --path /home/mobuone/flash-studio/flash-infra/ansible/playbooks/rebuild-work.yml --path /home/mobuone/flash-studio/flash-infra/scripts/flash-daemon.sh --path /home/mobuone/flash-studio/flash-infra/scripts/flash-ctl.sh' ;; \
		story-engine) EXTRA_ARGS='--path /home/mobuone/projects/saas/story-engine/CLAUDE.md --path /home/mobuone/projects/saas/story-engine/apps/api/src/story_engine/main.py --path /home/mobuone/projects/saas/story-engine/apps/collab/src/server.ts --path /home/mobuone/projects/saas/story-engine/apps/collab/src/health.ts --path /home/mobuone/projects/saas/story-engine/apps/collab/src/extensions/database.ts --path /home/mobuone/projects/saas/story-engine/packages/editor/src/extensions.ts --path /home/mobuone/projects/saas/story-engine/infra/docker-compose.yml --path /home/mobuone/projects/saas/story-engine/docs/specs/2026-04-01-gaps-resolution.md' ;; \
		*) echo "$(RED)>>> Repo inconnu: $(REPO)$(NC)"; exit 1 ;; \
	esac; \
	ansible workstation -i inventory/hosts.yml -m shell -a "bash -lc '/home/mobuone/VPAI/scripts/memory-backfill.sh --repo $(REPO) $$EXTRA_ARGS'"

.PHONY: deploy-opencode
deploy-opencode: ## Deployer OpenCode uniquement
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "opencode" --diff

.PHONY: deploy-claude-code
deploy-claude-code: ## Deployer Claude Code CLI + MCP servers sur RPi
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "claude-code" --diff

.PHONY: deploy-codex-cli
deploy-codex-cli: ## Deployer Codex CLI (OpenAI) sur RPi
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "codex-cli" --diff

.PHONY: deploy-gemini-cli
deploy-gemini-cli: ## Deployer Gemini CLI (Google) sur RPi
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "gemini-cli" --diff

.PHONY: deploy-n8n-mcp
deploy-n8n-mcp: ## Deployer n8n-MCP doc server sur RPi (port 3001) + client mcp.json Windows
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "n8n-mcp,windows-client" --diff
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "claude-code" --diff

.PHONY: deploy-comfyui
deploy-comfyui: ## Deployer ComfyUI (image gen) sur RPi
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "comfyui" --diff

.PHONY: deploy-remotion
deploy-remotion: ## Deployer Remotion (video render) sur RPi
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "remotion" --diff

.PHONY: deploy-opencut
deploy-opencut: ## Deployer OpenCut (video editor on-demand) sur RPi
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "opencut" --diff

.PHONY: deploy-openpencil
deploy-openpencil: ## Deployer OpenPencil (design editor AI) sur RPi
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "openpencil" --diff

.PHONY: penpot-up
penpot-up: ## Provisionner VPS ephemere + deployer Penpot (CX23 Hetzner)
	@echo "$(GREEN)>>> Provisioning Penpot ephemeral VPS...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/penpot-up.yml --diff

.PHONY: penpot-down
penpot-down: ## Backup S3 + detruire VPS Penpot (cout = 0 apres)
	@echo "$(YELLOW)>>> Backing up Penpot to S3 and destroying VPS...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/penpot-down.yml --diff

.PHONY: deploy-workstation-monitoring
deploy-workstation-monitoring: ## Deployer node_exporter + metriques custom sur RPi
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "workstation-monitoring" --diff

.PHONY: deploy-vpn-dns
deploy-vpn-dns: ## Mettre a jour Split DNS Headscale (VPS + workstation Pi)
	$(ANSIBLE_PLAYBOOK) playbooks/vpn-dns.yml --diff

.PHONY: deploy-obsidian
deploy-obsidian: ## Deployer CouchDB Obsidian LiveSync sur Seko-VPN
	@echo "$(GREEN)>>> Deploying Obsidian CouchDB on Seko-VPN...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/obsidian.yml --diff

.PHONY: deploy-obsidian-collectors
deploy-obsidian-collectors: ## Deployer les collectors Obsidian (Sese-AI + Pi)
	@echo "$(GREEN)>>> Deploying Obsidian collectors on Sese-AI + Pi...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/site.yml --tags obsidian-collector -e "target_env=prod" --diff
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags obsidian-collector-pi --diff

# ====================================================================
# PROD APPS (Hetzner)
# ====================================================================

.PHONY: provision-hetzner
provision-hetzner: ## Provisionner un serveur Hetzner CX22
	@echo "$(YELLOW)>>> Provisioning Hetzner CX22...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/provision-hetzner.yml --diff

.PHONY: deploy-app-prod
deploy-app-prod: lint ## Deployer sur le serveur Prod Apps
	@echo "$(RED)>>> PROD APPS DEPLOYMENT$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/app-prod.yml \
		-e "target_env=app_prod" \
		--diff

# ====================================================================
# INTEGRATION CI
# ====================================================================

.PHONY: integration
integration: ## Déclencher le pipeline d'intégration manuellement (Waza → GitHub Actions)
	@echo "$(YELLOW)>>> Triggering integration pipeline on GitHub Actions...$(NC)"
	gh workflow run integration.yml --ref main
	@echo "$(GREEN)>>> Triggered. Monitor: make integration-status$(NC)"

.PHONY: integration-status
integration-status: ## Voir le statut des derniers runs d'intégration
	@gh run list --workflow=integration.yml --limit 5

# ====================================================================
# CLEANUP
# ====================================================================

.PHONY: clean
clean: ## Nettoyer les fichiers temporaires
	find . -name "*.retry" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf /tmp/ansible_facts_cache
	@echo "$(GREEN)>>> Cleaned$(NC)"
