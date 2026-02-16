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
	find . \( -name '*.yml' -o -name '*.yaml' \) ! -path './.git/*' ! -path './.venv/*' ! -path '*/molecule/*' ! -path '*/collections/*' ! -name 'secrets.yml' -print0 | xargs -0 $(YAMLLINT) -c .yamllint.yml
	@echo "$(GREEN)>>> Running ansible-lint...$(NC)"
	$(ANSIBLE_LINT) playbooks/site.yml
	@echo "$(GREEN)>>> All linting passed$(NC)"

.PHONY: lint-yaml
lint-yaml: ## Lancer yamllint uniquement
	find . \( -name '*.yml' -o -name '*.yaml' \) ! -path './.git/*' ! -path './.venv/*' ! -path '*/molecule/*' ! -path '*/collections/*' ! -name 'secrets.yml' -print0 | xargs -0 $(YAMLLINT) -c .yamllint.yml

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

.PHONY: smoke-test
smoke-test: ## Lancer les smoke tests
	@if [ -z "$(URL)" ]; then \
		echo "$(RED)>>> Usage: make smoke-test URL=https://example.com$(NC)"; exit 1; \
	fi
	bash scripts/smoke-test.sh "$(URL)"

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
# CLEANUP
# ====================================================================

.PHONY: clean
clean: ## Nettoyer les fichiers temporaires
	find . -name "*.retry" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf /tmp/ansible_facts_cache
	@echo "$(GREEN)>>> Cleaned$(NC)"
