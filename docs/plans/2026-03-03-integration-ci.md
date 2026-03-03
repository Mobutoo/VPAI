# Integration CI Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a GitHub Actions workflow that provisions an ephemeral Hetzner CX22 (Debian 13), deploys the full stack, checks idempotence, runs 17 smoke tests (9 HTTPS + 8 internal), then destroys the server.

**Architecture:** 4 sequential jobs — `provision` (hcloud + OVH DNS), `deploy` (Ansible ×2 with idempotence check), `smoke-tests` (SSH on-server + external curl from CI runner), `destroy` (always, hcloud delete + DNS cleanup). Triggered by cron (Sunday 05:00 UTC) + `workflow_dispatch`. `make integration` on Waza triggers it via `gh workflow run`.

**Tech Stack:** GitHub Actions, hcloud CLI, Python `ovh` SDK (DNS), Ansible (site.yml), Bash (smoke tests)

---

## Context

**Reference files to read before implementing:**
- `.github/workflows/deploy-preprod.yml` — existing workflow structure to reuse/replace
- `.github/workflows/ci.yml` — pattern for step structure
- `roles/smoke-tests/templates/smoke-test.sh.j2` — already comprehensive on-server script
- `roles/smoke-tests/defaults/main.yml` — `smoke_test_script_path`, `smoke_test_base_url`
- `Makefile` — end of file for `make integration` placement
- `docs/plans/2026-03-03-integration-ci-design.md` — approved design

**Key constraints from CLAUDE.md:**
- SSH moves to port 804 after hardening → always pass `-e "ansible_port_override=22"` in CI so hardening keeps port 22 + public IP accessible
- `ansible_facts['xxx']` not `ansible_xxx` (inject_facts_as_vars = False)
- FQCN mandatory: `ansible.builtin.`, `community.general.`
- Domain: `ewutelo.cloud` (not javisi.io — confirmed by user)

**GitHub Secrets required (environment `integration`):**
`HETZNER_CLOUD_TOKEN`, `ANSIBLE_VAULT_PASSWORD`, `SSH_PRIVATE_KEY`, `OVH_APPLICATION_KEY`, `OVH_APPLICATION_SECRET`, `OVH_CONSUMER_KEY`, `PREPROD_DOMAIN` (=`preprod.ewutelo.cloud`), `LITELLM_MASTER_KEY`

---

## Task 1: Create `integration.yml` — Skeleton + `provision` Job

**Files:**
- Create: `.github/workflows/integration.yml`

**Step 1: Create the workflow skeleton**

```yaml
---
# .github/workflows/integration.yml — Integration tests on ephemeral Hetzner CX22
# Design: docs/plans/2026-03-03-integration-ci-design.md
#
# Triggers:
#   - schedule: Sunday 05:00 UTC (after backups at 03:00)
#   - workflow_dispatch: manual via GitHub UI or `make integration` (Waza)
#
# Required secrets (environment: integration):
#   HETZNER_CLOUD_TOKEN, ANSIBLE_VAULT_PASSWORD, SSH_PRIVATE_KEY,
#   OVH_APPLICATION_KEY, OVH_APPLICATION_SECRET, OVH_CONSUMER_KEY,
#   PREPROD_DOMAIN (e.g. preprod.ewutelo.cloud), LITELLM_MASTER_KEY

name: Integration

on:
  schedule:
    - cron: '0 5 * * 0'   # Dimanche 05:00 UTC — backups 03:00 terminés
  workflow_dispatch:

env:
  ANSIBLE_FORCE_COLOR: "1"
  ANSIBLE_ALLOW_BROKEN_CONDITIONALS: "True"

jobs:
  provision:
    name: Provision CX22 + DNS
    runs-on: ubuntu-latest
    environment: integration
    outputs:
      server_id: ${{ steps.server.outputs.server_id }}
      server_ip: ${{ steps.server.outputs.server_ip }}
      ssh_key_name: ${{ steps.server.outputs.ssh_key_name }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: pip install ovh requests

      - name: Install hcloud CLI
        run: |
          HCLOUD_VERSION="v1.47.0"
          curl -sL "https://github.com/hetznercloud/cli/releases/download/${HCLOUD_VERSION}/hcloud-linux-amd64.tar.gz" \
            | tar xz hcloud
          sudo mv hcloud /usr/local/bin/hcloud
          hcloud version

      - name: Prepare SSH key
        run: |
          mkdir -p ~/.ssh
          printf '%s\n' "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/ci_key
          chmod 600 ~/.ssh/ci_key
          ssh-keygen -y -f ~/.ssh/ci_key > ~/.ssh/ci_key.pub

      - name: Create CX22 server (Debian 13)
        id: server
        env:
          HCLOUD_TOKEN: ${{ secrets.HETZNER_CLOUD_TOKEN }}
        run: |
          KEY_NAME="ci-integration-${{ github.run_id }}"
          PUBKEY=$(cat ~/.ssh/ci_key.pub)

          # Register SSH public key
          hcloud ssh-key create --name "${KEY_NAME}" --public-key "${PUBKEY}"

          # Create CX22 with Debian 13 (trixie)
          SERVER_JSON=$(hcloud server create \
            --name "ci-integration-${{ github.run_id }}" \
            --type cx22 \
            --image debian-13 \
            --ssh-key "${KEY_NAME}" \
            --location nbg1 \
            --label "ci=integration" \
            --label "run_id=${{ github.run_id }}" \
            --output json)

          SERVER_ID=$(echo "${SERVER_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['server']['id'])")
          SERVER_IP=$(hcloud server describe "${SERVER_ID}" --output json \
            | python3 -c "import sys,json; print(json.load(sys.stdin)['public_net']['ipv4']['ip'])")

          echo "server_id=${SERVER_ID}" >> "${GITHUB_OUTPUT}"
          echo "server_ip=${SERVER_IP}" >> "${GITHUB_OUTPUT}"
          echo "ssh_key_name=${KEY_NAME}" >> "${GITHUB_OUTPUT}"
          echo "CX22 created: ID=${SERVER_ID} IP=${SERVER_IP}"

      - name: Wait for SSH availability
        run: |
          SERVER_IP="${{ steps.server.outputs.server_ip }}"
          for i in $(seq 1 24); do
            if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
              -i ~/.ssh/ci_key "root@${SERVER_IP}" echo "SSH ready"; then
              exit 0
            fi
            echo "Waiting for SSH... (attempt ${i}/24)"
            sleep 5
          done
          echo "ERROR: SSH not available after 120s" && exit 1

      - name: Add known host
        run: |
          SERVER_IP="${{ steps.server.outputs.server_ip }}"
          ssh-keyscan -H "${SERVER_IP}" >> ~/.ssh/known_hosts

      - name: Set OVH DNS record (*.preprod → CX22 IP)
        env:
          OVH_APP_KEY: ${{ secrets.OVH_APPLICATION_KEY }}
          OVH_APP_SECRET: ${{ secrets.OVH_APPLICATION_SECRET }}
          OVH_CONSUMER_KEY: ${{ secrets.OVH_CONSUMER_KEY }}
          SERVER_IP: ${{ steps.server.outputs.server_ip }}
          PREPROD_DOMAIN: ${{ secrets.PREPROD_DOMAIN }}
        run: |
          # PREPROD_DOMAIN = preprod.ewutelo.cloud
          # We create: *.preprod.ewutelo.cloud A → SERVER_IP
          # Extract base domain (ewutelo.cloud) and subdomain (preprod)
          BASE_DOMAIN=$(echo "${PREPROD_DOMAIN}" | cut -d. -f2-)
          SUB=$(echo "${PREPROD_DOMAIN}" | cut -d. -f1)
          WILDCARD_SUB="*.${SUB}"

          python3 << 'PYEOF'
          import os, ovh

          base_domain = os.environ['BASE_DOMAIN']
          wildcard_sub = os.environ['WILDCARD_SUB']
          server_ip = os.environ['SERVER_IP']

          client = ovh.Client(
              endpoint='ovh-eu',
              application_key=os.environ['OVH_APP_KEY'],
              application_secret=os.environ['OVH_APP_SECRET'],
              consumer_key=os.environ['OVH_CONSUMER_KEY'],
          )

          # Create wildcard A record
          client.post(f'/domain/zone/{base_domain}/record',
              fieldType='A',
              subDomain=wildcard_sub,
              target=server_ip,
              ttl=60)

          # Refresh zone
          client.post(f'/domain/zone/{base_domain}/refresh')
          print(f"DNS: {wildcard_sub}.{base_domain} → {server_ip} (TTL 60)")
          PYEOF
        shell: bash

      - name: Wait for DNS propagation (60s)
        run: |
          echo "Waiting 60s for DNS propagation..."
          sleep 60
          # Verify DNS resolves
          SERVER_IP="${{ steps.server.outputs.server_ip }}"
          PREPROD_DOMAIN="${{ secrets.PREPROD_DOMAIN }}"
          RESOLVED=$(dig +short "test.${PREPROD_DOMAIN}" @1.1.1.1 | head -1) || RESOLVED=""
          if [ "${RESOLVED}" = "${SERVER_IP}" ]; then
            echo "DNS OK: test.${PREPROD_DOMAIN} → ${RESOLVED}"
          else
            echo "WARN: DNS not yet resolved (got: '${RESOLVED}', expected: '${SERVER_IP}')"
            echo "Waiting 30s more..."
            sleep 30
          fi
```

**Step 2: Validate YAML syntax**

```bash
cd /home/asus/seko/VPAI
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/integration.yml'))"
# Expected: no output (success)
```

**Step 3: Commit**

```bash
git add .github/workflows/integration.yml
git commit -m "feat(ci): add integration workflow — provision job (CX22 + OVH DNS)"
```

---

## Task 2: Add `deploy` Job to `integration.yml`

**Files:**
- Modify: `.github/workflows/integration.yml` (append `deploy` job)

**Step 1: Add the `deploy` job after the `provision` job**

Append this job block to the `jobs:` section in `integration.yml`:

```yaml
  deploy:
    name: Deploy + Idempotence Check
    runs-on: ubuntu-latest
    environment: integration
    needs: provision
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install Ansible dependencies
        run: |
          pip install -r requirements.txt

      - name: Install Ansible collections
        run: |
          ansible-galaxy install -r requirements.yml

      - name: Configure SSH key
        run: |
          mkdir -p ~/.ssh
          printf '%s\n' "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/ci_key
          chmod 600 ~/.ssh/ci_key
          SERVER_IP="${{ needs.provision.outputs.server_ip }}"
          ssh-keyscan -H "${SERVER_IP}" >> ~/.ssh/known_hosts

      - name: Create vault password file
        run: |
          printf '%s' "${{ secrets.ANSIBLE_VAULT_PASSWORD }}" > .vault_password
          chmod 600 .vault_password

      - name: Deploy — First run (fresh server, port 22)
        env:
          SERVER_IP: ${{ needs.provision.outputs.server_ip }}
          PREPROD_DOMAIN: ${{ secrets.PREPROD_DOMAIN }}
        run: |
          ansible-playbook playbooks/site.yml \
            -i "${SERVER_IP}," \
            -e "ansible_user=root" \
            -e "ansible_port=22" \
            -e "ansible_port_override=22" \
            -e "ansible_ssh_private_key_file=~/.ssh/ci_key" \
            -e "ansible_ssh_common_args='-o StrictHostKeyChecking=no'" \
            -e "target_env=preprod" \
            -e "domain_name=${PREPROD_DOMAIN}" \
            --diff

      - name: Deploy — Second run (idempotence check)
        env:
          SERVER_IP: ${{ needs.provision.outputs.server_ip }}
          PREPROD_DOMAIN: ${{ secrets.PREPROD_DOMAIN }}
        run: |
          RESULT=$(ansible-playbook playbooks/site.yml \
            -i "${SERVER_IP}," \
            -e "ansible_user=root" \
            -e "ansible_port=22" \
            -e "ansible_port_override=22" \
            -e "ansible_ssh_private_key_file=~/.ssh/ci_key" \
            -e "ansible_ssh_common_args='-o StrictHostKeyChecking=no'" \
            -e "target_env=preprod" \
            -e "domain_name=${PREPROD_DOMAIN}" \
            2>&1 | tee /tmp/ansible_idempotence.log)

          # Parse PLAY RECAP for changed count
          CHANGED=$(grep -oP '(?<=changed=)\d+' /tmp/ansible_idempotence.log \
            | paste -sd+ - | bc 2>/dev/null || echo "0")

          echo "Idempotence result: changed=${CHANGED}"

          if [ "${CHANGED:-0}" -gt 0 ]; then
            echo "IDEMPOTENCE FAILED — ${CHANGED} task(s) changed on 2nd run"
            echo "=== Tasks that changed ==="
            grep "changed:" /tmp/ansible_idempotence.log | head -20 || true
            exit 1
          fi

          echo "IDEMPOTENCE PASSED — 0 tasks changed"
```

**Step 2: Validate**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/integration.yml'))"
```

**Step 3: Commit**

```bash
git add .github/workflows/integration.yml
git commit -m "feat(ci): integration — add deploy job with idempotence check"
```

---

## Task 3: Add `smoke-tests` Job to `integration.yml`

**Files:**
- Modify: `.github/workflows/integration.yml` (append `smoke-tests` job)

**Step 1: Add the `smoke-tests` job**

```yaml
  smoke-tests:
    name: Smoke Tests (HTTPS + Internal)
    runs-on: ubuntu-latest
    environment: integration
    needs: [provision, deploy]
    steps:
      - name: Configure SSH
        run: |
          mkdir -p ~/.ssh
          printf '%s\n' "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/ci_key
          chmod 600 ~/.ssh/ci_key
          ssh-keyscan -H "${{ needs.provision.outputs.server_ip }}" >> ~/.ssh/known_hosts

      - name: Wait for TLS certificate issuance (Caddy ACME)
        run: |
          echo "Waiting 90s for Caddy to obtain TLS certificates via ACME..."
          sleep 90

      - name: External HTTPS smoke tests (from CI runner)
        env:
          PREPROD_DOMAIN: ${{ secrets.PREPROD_DOMAIN }}
          LITELLM_KEY: ${{ secrets.LITELLM_MASTER_KEY }}
        run: |
          FAILURES=0
          TIMEOUT=20

          check_https() {
            local name="$1" url="$2" expected="${3:-200}"
            local status
            status=$(curl -sL -o /dev/null -w "%{http_code}" \
              --max-time "${TIMEOUT}" "${url}" 2>/dev/null) || status="000"
            if [ "${status}" = "${expected}" ]; then
              echo "PASS  ${name} (HTTP ${status})"
            else
              echo "FAIL  ${name} (HTTP ${status}, expected ${expected})"
              FAILURES=$((FAILURES + 1))
            fi
          }

          D="${PREPROD_DOMAIN}"

          echo "=== External HTTPS Checks (runner → preprod) ==="
          check_https "Caddy /health"           "https://${D}/health"
          check_https "n8n /healthz"             "https://n8n.${D}/healthz"
          check_https "LiteLLM /health" \
            "$(curl -sL -o /dev/null -w '%{http_code}' --max-time ${TIMEOUT} \
               -H "Authorization: Bearer ${LITELLM_KEY}" \
               "https://llm.${D}/health" 2>/dev/null || echo '000')" "200" || true
          # LiteLLM needs special handling for auth header:
          LITELLM_STATUS=$(curl -sL -o /dev/null -w "%{http_code}" \
            --max-time "${TIMEOUT}" \
            -H "Authorization: Bearer ${LITELLM_KEY}" \
            "https://llm.${D}/health" 2>/dev/null) || LITELLM_STATUS="000"
          [ "${LITELLM_STATUS}" = "200" ] && \
            echo "PASS  LiteLLM /health (HTTP ${LITELLM_STATUS})" || \
            { echo "FAIL  LiteLLM /health (HTTP ${LITELLM_STATUS})"; FAILURES=$((FAILURES+1)); }

          check_https "Grafana /api/health"      "https://tala.${D}/api/health"
          check_https "Qdrant /healthz"           "https://qdrant.${D}/healthz"
          check_https "NocoDB /api/v1/db/meta"   "https://nocodb.${D}/api/v1/db/meta/projects" "401"
          check_https "OpenClaw /health"          "https://oc.${D}/health"
          check_https "Palais /health"            "https://palais.${D}/health"
          check_https "Plane /api/"               "https://plane.${D}/api/"

          echo ""
          echo "External checks: $((9 - FAILURES)) passed, ${FAILURES} failed"
          [ "${FAILURES}" -eq 0 ] || exit 1

      - name: Internal smoke tests (SSH on CX22)
        env:
          SERVER_IP: ${{ needs.provision.outputs.server_ip }}
        run: |
          # Run the on-server smoke-test.sh deployed by the smoke-tests role
          ssh -i ~/.ssh/ci_key \
            -o StrictHostKeyChecking=no \
            -o ConnectTimeout=30 \
            "root@${SERVER_IP}" \
            "bash /opt/*/scripts/smoke-test.sh 2>&1"
```

**Step 2: Fix the LiteLLM check (the inline above is messy — simplify it)**

The `check_https` function doesn't support custom headers. Replace the LiteLLM section with a direct curl call. The clean version is already in the template above — verify it reads clearly and remove the duplicate `check_https` call for LiteLLM.

**Step 3: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/integration.yml'))"
```

**Step 4: Commit**

```bash
git add .github/workflows/integration.yml
git commit -m "feat(ci): integration — add smoke-tests job (9 HTTPS + SSH internal)"
```

---

## Task 4: Add `destroy` Job to `integration.yml`

**Files:**
- Modify: `.github/workflows/integration.yml` (append `destroy` job)

**Step 1: Add the `destroy` job — runs `if: always()`**

```yaml
  destroy:
    name: Destroy CX22 + DNS Cleanup
    runs-on: ubuntu-latest
    environment: integration
    needs: [provision, smoke-tests]
    if: always()
    steps:
      - name: Install hcloud CLI
        run: |
          HCLOUD_VERSION="v1.47.0"
          curl -sL "https://github.com/hetznercloud/cli/releases/download/${HCLOUD_VERSION}/hcloud-linux-amd64.tar.gz" \
            | tar xz hcloud
          sudo mv hcloud /usr/local/bin/hcloud

      - name: Install Python OVH SDK
        run: pip install ovh

      - name: Delete CX22 server
        env:
          HCLOUD_TOKEN: ${{ secrets.HETZNER_CLOUD_TOKEN }}
          SERVER_ID: ${{ needs.provision.outputs.server_id }}
          SSH_KEY_NAME: ${{ needs.provision.outputs.ssh_key_name }}
        run: |
          if [ -n "${SERVER_ID}" ]; then
            hcloud server delete "${SERVER_ID}" && \
              echo "Server ${SERVER_ID} deleted" || \
              echo "WARN: Could not delete server ${SERVER_ID}"
          else
            echo "WARN: No server_id to delete"
          fi

          # Also delete the CI SSH key
          if [ -n "${SSH_KEY_NAME}" ]; then
            hcloud ssh-key delete "${SSH_KEY_NAME}" 2>/dev/null && \
              echo "SSH key ${SSH_KEY_NAME} deleted" || \
              echo "WARN: Could not delete SSH key ${SSH_KEY_NAME}"
          fi

      - name: Remove OVH DNS record
        env:
          OVH_APP_KEY: ${{ secrets.OVH_APPLICATION_KEY }}
          OVH_APP_SECRET: ${{ secrets.OVH_APPLICATION_SECRET }}
          OVH_CONSUMER_KEY: ${{ secrets.OVH_CONSUMER_KEY }}
          PREPROD_DOMAIN: ${{ secrets.PREPROD_DOMAIN }}
        run: |
          BASE_DOMAIN=$(echo "${PREPROD_DOMAIN}" | cut -d. -f2-)
          SUB=$(echo "${PREPROD_DOMAIN}" | cut -d. -f1)
          WILDCARD_SUB="*.${SUB}"

          python3 << 'PYEOF'
          import os, ovh

          base_domain = os.environ['BASE_DOMAIN']
          wildcard_sub = os.environ['WILDCARD_SUB']

          client = ovh.Client(
              endpoint='ovh-eu',
              application_key=os.environ['OVH_APP_KEY'],
              application_secret=os.environ['OVH_APP_SECRET'],
              consumer_key=os.environ['OVH_CONSUMER_KEY'],
          )

          # Find and delete the record
          records = client.get(f'/domain/zone/{base_domain}/record',
              fieldType='A', subDomain=wildcard_sub)

          for record_id in records:
              client.delete(f'/domain/zone/{base_domain}/record/{record_id}')
              print(f"Deleted DNS record {record_id} ({wildcard_sub}.{base_domain})")

          client.post(f'/domain/zone/{base_domain}/refresh')
          print("DNS zone refreshed")
          PYEOF
        shell: bash
```

**Step 2: Validate full workflow YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/integration.yml'))"
# Expected: no output
```

**Step 3: Commit**

```bash
git add .github/workflows/integration.yml
git commit -m "feat(ci): integration — add destroy job (always runs, hcloud + OVH cleanup)"
```

---

## Task 5: Add `make integration` to Makefile

**Files:**
- Modify: `Makefile` (add target in a new `INTEGRATION` section before `CLEANUP`)

**Step 1: Add the section before the `# CLEANUP` section**

Find the `# CLEANUP` section in the Makefile and insert before it:

```makefile
# ====================================================================
# INTEGRATION CI
# ====================================================================

.PHONY: integration
integration: ## Déclencher le pipeline d'intégration manuellement (Waza → GitHub Actions)
	@echo "$(YELLOW)>>> Triggering integration pipeline on GitHub Actions...$(NC)"
	gh workflow run integration.yml --ref main
	@echo "$(GREEN)>>> Triggered. Monitor: gh run list --workflow=integration.yml$(NC)"

.PHONY: integration-status
integration-status: ## Voir le statut du dernier run d'intégration
	@gh run list --workflow=integration.yml --limit 5
```

**Step 2: Verify `gh` CLI is available on Waza**

```bash
# On Waza (Pi):
gh --version
# Expected: gh version 2.x.x
```

**Step 3: Validate Makefile syntax**

```bash
cd /home/asus/seko/VPAI && make help | grep integration
# Expected: integration and integration-status listed
```

**Step 4: Commit**

```bash
git add Makefile
git commit -m "feat: add make integration + integration-status targets (Waza CLI)"
```

---

## Task 6: Lint Validation

**Step 1: Run YAML lint on the new workflow**

```bash
cd /home/asus/seko/VPAI
source .venv/bin/activate
yamllint -c .yamllint.yml .github/workflows/integration.yml
# Expected: no output (all OK)
```

**Note:** The `.yamllint.yml` config might exclude `*/molecule/*` but not `*.github/workflows/*`. If there are line-length warnings, check the rule config. The workflow uses long `run:` blocks — these are typically excluded from line-length rules or use `|` multiline strings.

**Step 2: Check for hardcoded values**

```bash
grep -r 'javisi\|ewutelo.cloud' .github/workflows/integration.yml
# Expected: no occurrences (domain comes from secrets.PREPROD_DOMAIN)
```

**Step 3: Verify Python script syntax in the workflow**

The Python `<< 'PYEOF'` heredocs are not directly testable from YAML. Verify the indentation is consistent (the heredoc content must not have shell expansion issues).

**Step 4: Final commit and push**

```bash
cd /home/asus/seko/VPAI
git push origin main
# Then monitor:
# gh run list --limit 3
```

---

## Task 7: Configure GitHub Secrets (Manual Step)

**This task requires manual action in the GitHub UI.**

Go to: `https://github.com/Mobutoo/VPAI/settings/environments` → Create environment `integration` → Add secrets:

| Secret name | Value source |
|-------------|-------------|
| `HETZNER_CLOUD_TOKEN` | Hetzner Cloud Console → API Tokens |
| `ANSIBLE_VAULT_PASSWORD` | Local `.vault_password` file content |
| `SSH_PRIVATE_KEY` | Content of `~/.ssh/seko-vpn-deploy` |
| `OVH_APPLICATION_KEY` | OVH API credentials (already in inventory vars) |
| `OVH_APPLICATION_SECRET` | Same |
| `OVH_CONSUMER_KEY` | Same |
| `PREPROD_DOMAIN` | `preprod.ewutelo.cloud` |
| `LITELLM_MASTER_KEY` | From `secrets.yml` (ansible-vault view) |

**Verification:**

After adding secrets, run:
```bash
gh workflow run integration.yml --ref main
gh run list --workflow=integration.yml --limit 1
```
Expected: run appears as `queued` → `in_progress` → `success`

---

## Execution Order

1. Task 1 → Task 2 → Task 3 → Task 4 (sequential — all modify same file)
2. Task 5 (Makefile — independent, can be done in parallel with Tasks 1-4)
3. Task 6 (lint — after all code tasks)
4. Task 7 (secrets — manual, last step before first real run)
