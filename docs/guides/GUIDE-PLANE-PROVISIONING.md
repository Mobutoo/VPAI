# GUIDE-PLANE-PROVISIONING.md

## Overview

Plane provisioning is semi-automated due to a critical limitation in Plane v1.2.2: the instance admin API token cannot be created programmatically. This guide walks through the manual UI steps required before the automated provisioning script can run.

**Workflow:**
1. Manual: First login and God Mode setup (creates instance admin account)
2. Manual: Admin API token creation via UI
3. Manual: Update Ansible Vault with real admin token
4. Automated: Run provisioning playbook (creates workspace, agents, tokens, custom fields)

## Prerequisites

- Plane deployment completed (01-01b plan)
- VPN connection active to access `https://work.{{ domain_name }}`
- Ansible vault password available

## Section 1: First Login (Manual UI Setup)

Plane requires a one-time setup wizard called "God Mode" that creates the instance administrator account.

### Steps:

1. **Connect to VPN**:
   ```bash
   # Verify Tailscale is connected
   tailscale status | grep sese-ai
   ```

2. **Access Plane UI**:
   - URL: `https://work.{{ domain_name }}` (VPN-only access)
   - Expected: God Mode setup wizard appears

3. **Complete God Mode Setup**:
   - Enter admin email: Use value from `{{ admin_email }}` variable (check `inventory/group_vars/all/main.yml`)
   - Enter admin password: Choose a strong password (store securely)
   - Click "Setup Instance"

4. **Login**:
   - Use the email and password you just created
   - Expected: Plane dashboard appears

**Verification:**
- You are logged into Plane dashboard
- Top-right corner shows your profile picture/initials

## Section 2: Admin API Token Creation

The admin API token is required for all provisioning operations.

### Steps:

1. **Navigate to Profile Settings**:
   - Click your profile icon (top-right)
   - Select "Profile Settings"

2. **Go to Personal Access Tokens**:
   - In left sidebar, click "Personal Access Tokens"

3. **Create New Token**:
   - Click "Create New Token" button
   - **Name:** `ansible-provisioning`
   - **Scope:** Full access (instance admin)
   - **Expiration:** Never
     - Justification: Internal VPN-only service with controlled access
     - Alternative: Set expiration and rotate token in vault before expiry
   - Click "Create Token"

4. **Copy Token Value**:
   - **CRITICAL:** Copy the token immediately - it's shown only once
   - Expected format: Long alphanumeric string (e.g., `plane_xxxxxxxxxxxxxxxxxxxxxxxxxx`)

**Verification:**
- Token is copied to clipboard
- Token list shows "ansible-provisioning" token as active

### Update Ansible Vault:

```bash
# Edit vault file
ansible-vault edit inventory/group_vars/all/secrets.yml

# Find this line:
# vault_plane_admin_api_token: "REPLACE_AFTER_FIRST_LOGIN"

# Replace with actual token:
# vault_plane_admin_api_token: "plane_xxxxxxxxxxxxxxxxxxxxxxxxxx"

# Save and exit (:wq in vim)
```

**Verification Command:**
```bash
# Check admin token is not placeholder (should return empty - grep -v inverts match)
ansible-vault view inventory/group_vars/all/secrets.yml | grep vault_plane_admin_api_token | grep -v REPLACE

# Expected output:
# vault_plane_admin_api_token: "plane_xxxxxxxxxxxxxxxxxxxxxxxxxx"
```

## Section 3: Run Provisioning Playbook

With the admin token in place, the automated provisioning can now run.

### Command:

```bash
# Activate Ansible venv (required)
source /home/mobuone/seko/VPAI/.venv/bin/activate

# Run provisioning role
make deploy-role ROLE=plane-provision ENV=prod

# Alternative: Run playbook directly
ansible-playbook playbooks/site.yml --tags plane-provision -e "ansible_port_override=804"
```

### Expected Output:

The provisioning script performs these operations idempotently:

1. **Workspace Creation:**
   ```
   TASK [plane-provision : Create javisi workspace]
   changed: [sese-ai] => Workspace 'javisi' created
   ```

2. **Agent Token Generation (10 tokens):**
   ```
   TASK [plane-provision : Generate agent API tokens]
   changed: [sese-ai] => (item=concierge) Token created
   changed: [sese-ai] => (item=imhotep) Token created
   changed: [sese-ai] => (item=thot) Token created
   ...
   ```

3. **Custom Fields Creation (4 fields):**
   ```
   TASK [plane-provision : Create custom fields]
   changed: [sese-ai] => (item=agent_id) Field created
   changed: [sese-ai] => (item=cost_estimate) Field created
   changed: [sese-ai] => (item=confidence_score) Field created
   changed: [sese-ai] => (item=session_id) Field created
   ```

4. **Onboarding Project Creation:**
   ```
   TASK [plane-provision : Create Onboarding project]
   changed: [sese-ai] => Project created with 3 demo issues
   ```

5. **Vault Update:**
   ```
   TASK [plane-provision : Update vault with agent tokens]
   changed: [localhost] => vault_plane_agent_tokens populated
   ```

**Duration:** ~30-45 seconds (depends on API latency)

**Idempotency:** Safe to re-run - existing resources are skipped, missing ones created.

## Section 4: Verification

After provisioning completes, verify all resources were created correctly.

### UI Verification:

1. **Workspace Exists:**
   - Plane dashboard → Workspace dropdown (top-left)
   - Expected: "javisi" workspace is listed and active

2. **Onboarding Project:**
   - Projects list shows "Onboarding" project
   - Click project → Expected: 3 demo issues present
     - "Welcome to Plane"
     - "Create your first project"
     - "Invite team members"

3. **Custom Fields:**
   - Settings (left sidebar) → Custom Fields
   - Expected: 4 custom fields present:
     - `agent_id` (Text)
     - `cost_estimate` (Number)
     - `confidence_score` (Number)
     - `session_id` (Text)

4. **API Tokens:**
   - Profile Settings → Personal Access Tokens
   - Expected: 11 tokens total (1 admin + 10 agents)

### Vault Verification:

```bash
# Check admin token is not placeholder
ansible-vault view inventory/group_vars/all/secrets.yml | grep vault_plane_admin_api_token | grep -v REPLACE
# Expected: Returns line with real token

# Check all 10 agent tokens are populated (should return 10)
ansible-vault view inventory/group_vars/all/secrets.yml | awk '/vault_plane_agent_tokens:/,/^[^ ]/ {if ($2 != "\"\"" && $2 != "" && $1 != "vault_plane_agent_tokens:") print}' | grep -c ':'
# Expected output: 10

# Verify no empty tokens remain (should return 0)
ansible-vault view inventory/group_vars/all/secrets.yml | awk '/vault_plane_agent_tokens:/,/^[^ ]/ {print}' | grep -c '""'
# Expected output: 0
```

### API Verification (Manual Testing):

```bash
# Test admin token authentication
curl -H "Authorization: Bearer $(ansible-vault view inventory/group_vars/all/secrets.yml | grep vault_plane_admin_api_token | awk '{print $2}' | tr -d '"')" \
  https://work.ewutelo.cloud/api/v1/workspaces/

# Expected output: JSON array with javisi workspace object

# Test agent token (example: concierge)
CONCIERGE_TOKEN=$(ansible-vault view inventory/group_vars/all/secrets.yml | awk '/vault_plane_agent_tokens:/,/concierge:/ {if (/concierge:/) print $2}' | tr -d '"')

curl -H "Authorization: Bearer ${CONCIERGE_TOKEN}" \
  https://work.ewutelo.cloud/api/v1/workspaces/javisi/projects/

# Expected output: JSON array with Onboarding project
```

## Section 5: Troubleshooting

### Issue: API Returns 401 Unauthorized

**Cause:** Admin token is invalid, expired, or incorrectly copied.

**Solution:**
1. Regenerate token via Plane UI (Profile Settings → Personal Access Tokens)
2. Revoke old "ansible-provisioning" token
3. Create new token with same name
4. Update vault: `ansible-vault edit inventory/group_vars/all/secrets.yml`
5. Re-run provisioning playbook

### Issue: Workspace Already Exists Error

**Cause:** Provisioning was partially completed previously.

**Solution:**
- Provisioning script is idempotent - safe to re-run
- Script will skip existing workspace and proceed to missing resources
- No manual cleanup needed

### Issue: Custom Fields Fail to Create

**Cause:** Work item type ID mismatch (Plane changed default IDs).

**Diagnosis:**
```bash
# Check available work item types
curl -H "Authorization: Bearer <admin_token>" \
  https://work.ewutelo.cloud/api/v1/workspaces/javisi/work-item-types/ | jq '.[] | {id, name}'
```

**Solution:**
- Update `plane-provision` role with correct work item type ID
- Default is usually the first type ID returned
- Edit `roles/plane-provision/tasks/custom-fields.yml`

### Issue: Agent Tokens Empty After Provisioning

**Cause:** Provision script failed to write tokens to vault, or vault file permission denied.

**Diagnosis:**
```bash
# Check provision script logs
ansible-playbook playbooks/site.yml --tags plane-provision -vv

# Check vault file permissions
ls -la inventory/group_vars/all/secrets.yml
# Expected: -rw------- (owner read/write only)
```

**Solution:**
1. Verify script has write access to vault file
2. Check for Ansible connection errors in logs
3. Manually verify tokens were created in Plane UI
4. If needed, manually copy token values from UI to vault

### Issue: VPN Connection Lost During Provisioning

**Cause:** Tailscale connection dropped, DNS resolution failed.

**Solution:**
```bash
# Verify VPN is connected
tailscale status | grep sese-ai
# Expected: Shows connection to sese-ai node

# Test DNS resolution
nslookup work.ewutelo.cloud
# Expected: Resolves to VPN IP (100.64.x.x)

# Reconnect if needed
sudo tailscale up

# Re-run provisioning (idempotent)
make deploy-role ROLE=plane-provision ENV=prod
```

### Issue: Permission Denied When Editing Vault

**Cause:** Vault file is encrypted, Ansible vault password not provided.

**Solution:**
```bash
# Set vault password file or use --ask-vault-pass
export ANSIBLE_VAULT_PASSWORD_FILE=~/.ansible/vault_pass.txt

# Or pass inline:
ansible-vault edit inventory/group_vars/all/secrets.yml --ask-vault-pass
```

## Reference: Agent Token Mapping

The provision script creates 10 agent tokens corresponding to the OpenClaw agent personas:

| Agent Name | Role | Token Variable |
|------------|------|----------------|
| Concierge | Project orchestration, Telegram interface | `vault_plane_agent_tokens.concierge` |
| Imhotep | Technical architecture, system design | `vault_plane_agent_tokens.imhotep` |
| Thot | Knowledge management, documentation | `vault_plane_agent_tokens.thot` |
| Basquiat | Creative design, UI/UX | `vault_plane_agent_tokens.basquiat` |
| R2D2 | DevOps, infrastructure automation | `vault_plane_agent_tokens.r2d2` |
| Shuri | Research, innovation, prototyping | `vault_plane_agent_tokens.shuri` |
| Piccolo | Code generation, implementation | `vault_plane_agent_tokens.piccolo` |
| CFO | Resource optimization, cost analysis | `vault_plane_agent_tokens.cfo` |
| Maintainer | Maintenance, refactoring, debt reduction | `vault_plane_agent_tokens.maintainer` |
| Hermes | Communication, reporting, stakeholder sync | `vault_plane_agent_tokens.hermes` |

## Next Steps

After successful provisioning:
1. Verify all tokens are populated using vault verification commands
2. Proceed to Plan 01-03: Smoke tests and integration validation
3. Smoke tests will validate agent authentication using populated tokens
4. If smoke tests fail due to auth errors, return to Section 4 verification steps
