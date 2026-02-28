# Testing Patterns

**Analysis Date:** 2026-02-28

## Test Framework

**Test Runner:**
- Molecule v5+ (with Docker driver)
- Config: `roles/<role>/molecule/default/molecule.yml` (per-role)

**Assertion Library:**
- Ansible assertions via `ansible.builtin.assert` (pre-flight checks)
- Molecule verifier: Ansible playbooks (`verify.yml`)
- Shell script assertions: bash conditionals with explicit exit codes

**Run Commands:**

```bash
# Run all role tests
make test

# Test specific role
make test-role ROLE=caddy

# Manual Molecule test (from role directory)
cd roles/caddy && molecule test

# Dry-run with lint
make lint

# Check for code issues (no :latest tags, no hardcoded values)
make check-no-latest
make check-hardcoded
```

## Test File Organization

**Location:**
- Co-located with roles: each role has `molecule/default/` subdirectory
- Not in separate test directory
- Smoke tests: `scripts/smoke-test.sh` (integration tests, shell-based)

**Naming:**
- `molecule.yml` — test configuration (platforms, driver, provisioner)
- `converge.yml` — playbook to apply the role under test
- `verify.yml` — playbook to verify role effects

**Structure:**

```
roles/
├── caddy/
│   ├── tasks/
│   ├── handlers/
│   ├── defaults/
│   ├── templates/
│   └── molecule/
│       └── default/
│           ├── molecule.yml      # Test config
│           ├── converge.yml      # Apply role
│           └── verify.yml        # Verify results
├── n8n/
│   └── molecule/
│       └── default/
│           ├── molecule.yml
│           ├── converge.yml
│           └── verify.yml
```

## Test Structure

**Molecule Configuration (converge.yml):**

```yaml
---
- name: Converge
  hosts: all
  roles:
    - role: caddy
```

Simple: just applies the role being tested. No additional setup per role.

**Molecule Platform Config (molecule.yml):**

```yaml
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
```

**Key points:**
- Docker driver with Debian bookworm base image
- Privileged container (needed for systemd)
- tmpfs for /run and /tmp (systemd requirement)
- Verifier: Ansible (custom playbook)

## Test Structure — Verify Playbooks

**Pattern — Verify File Existence:**

```yaml
---
- name: Verify caddy role
  hosts: all
  gather_facts: false
  tasks:
    - name: Check Caddyfile exists
      ansible.builtin.stat:
        path: "/opt/{{ project_name | default('vpai') }}/configs/caddy/Caddyfile"
      register: caddyfile
      failed_when: not caddyfile.stat.exists
```

Tests assert that expected files/directories were created.

**Pattern — Verify with Dynamic Variable:**

Most verify playbooks use `{{ project_name | default('vpai') }}` to handle both:
- Molecule tests (no variable defined, uses default 'vpai')
- Production deploys (variable defined in inventory)

**Example from `roles/caddy/molecule/default/verify.yml`:**

```yaml
---
- name: Verify caddy role
  hosts: all
  gather_facts: false
  tasks:
    - name: Check Caddyfile exists
      ansible.builtin.stat:
        path: "/opt/{{ project_name | default('vpai') }}/configs/caddy/Caddyfile"
      register: caddyfile
      failed_when: not caddyfile.stat.exists
```

Fails the test if file does not exist.

## Mocking

**No explicit mocking framework used:**

Molecule tests run in Docker containers with minimal Debian bookworm base — tests are mostly integration-level, verifying:
- Files are created at expected paths
- Directories have correct permissions
- Docker images build successfully
- Handlers can be called

**What to Mock (patterns):**

For tasks that interact with external services, use environment variable defaults:

```yaml
# In defaults/main.yml
n8n_api_url: "{{ n8n_api_url | default('http://n8n:5678') }}"

# In Molecule converge.yml, override if needed
- role: n8n
  vars:
    n8n_api_url: "http://test-n8n:5678"
```

**What NOT to Mock:**

- File operations (test them in Docker)
- Template rendering (test actual outputs)
- Docker image builds (run them if possible)

## Fixtures and Factories

**Test Data:**

No formal fixture framework. Test data embedded in:
- `defaults/main.yml` (example configs, default paths)
- Molecule variables (passed in converge.yml)
- Docker container setup (pre-built images)

**Example — Caddy test defaults:**

In `roles/caddy/defaults/main.yml`, all variables are defaulted for testing:
```yaml
caddy_config_dir: "/opt/{{ project_name }}/configs/caddy"
caddy_image_tag: "{{ caddy_image }}"
```

When Molecule runs, `project_name` defaults to 'vpai', so paths are:
```
/opt/vpai/configs/caddy/
```

**Location:**
- Test data lives in role `defaults/main.yml` (shared with production)
- Molecule overrides: `molecule.yml` or `converge.yml` `vars:`

## Coverage

**Requirements:** No explicit coverage reporting.

**View Coverage (implicit):**

Molecule test results indicate which tasks executed:
```bash
cd roles/caddy && molecule test
# Output shows which tasks converged and which were skipped
```

Each role has at least one `verify.yml` playbook checking critical outputs.

## Test Types

**Unit Tests (Ansible Module-level):**

Not used. Roles are functional and tested via Molecule.

**Integration Tests (Molecule):**

Each role tests against Debian bookworm Docker image:
- Tasks run in isolated container
- Verifies files/permissions created correctly
- No external service dependencies (mock via defaults)

**Smoke Tests (CI/CD):**

Shell script: `scripts/smoke-test.sh`

**Usage:**
```bash
# Test public endpoints
./scripts/smoke-test.sh https://example.com

# Test with admin endpoints (VPN)
./scripts/smoke-test.sh https://example.com https://admin.example.com

# CI mode (public only, skip VPN-only endpoints)
./scripts/smoke-test.sh --ci https://example.com
```

**Test Coverage (from `scripts/smoke-test.sh`):**

```bash
# HTTPS & TLS
✓ Caddy HTTPS health
✓ TLS certificate validity
✓ DNS resolution

# Public Endpoints
✓ LiteLLM health check
✓ LiteLLM models list

# Admin Endpoints (VPN-only, skipped in CI)
✓ n8n healthz
✓ Grafana health

# Exit code: 0 = pass, 1 = failure
```

**Assertion Pattern:**

```bash
check() {
  local name="$1" url="$2" expected="${3:-200}"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null) || status="000"
  if [ "$status" = "$expected" ]; then
    echo "PASS  $name (HTTP $status)"
  else
    echo "FAIL  $name (HTTP $status, expected $expected)"
    FAILURES=$((FAILURES + 1))
  fi
}

check "Caddy HTTPS health" "${BASE_URL}/health"
```

Exit code on expected HTTP status (e.g., 200 for healthz, 403 for VPN-blocked endpoint).

## Common Patterns

**Async Testing (not applicable):**

Ansible has `async` keyword for long-running tasks, not used in this project.

**Error Testing:**

Pre-flight assertions in playbooks prevent errors before they propagate:

```yaml
- name: Verify Ansible version
  ansible.builtin.assert:
    that:
      - ansible_version.full is version('2.16', '>=')
    fail_msg: "Ansible 2.16+ required. Current: {{ ansible_version.full }}"
  tags: [always]
```

Fails the entire playbook if condition not met.

**Handler Testing (implicit in Molecule):**

Handlers defined in `handlers/main.yml` are verified by observing their effects:
- Files changed → handler notified → service restarted
- Molecule verify playbook checks output state

Example: `roles/caddy/handlers/main.yml` restarts caddy stack:
```yaml
- name: Restart caddy stack
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose-infra.yml
    services:
      - caddy
    state: restarted
```

Verify that Caddyfile exists after deploy (implies handler was triggered).

## CI/CD Pipeline

**GitHub Actions (linting only):**

Makefile targets for linting:
```bash
make lint              # Run all linting (yamllint + ansible-lint)
make check-no-latest  # Fail if :latest tags found
make check-hardcoded  # Fail if hardcoded project names found
```

Pre-deploy checks:
```bash
ansible-playbook playbooks/site.yml --check --diff
```

**Smoke Test Integration:**

After deployment:
```bash
./scripts/smoke-test.sh --ci https://prod.example.com
# In CI mode: skips VPN-only endpoints, tests public endpoints only
```

Exit code determines if deployment successful.

## Best Practices

**When Writing Tests:**

1. **Name verify.yml tasks clearly:** "Check X exists", "Verify Y permission"
2. **Use `failed_when: not <condition>`** for assertion syntax
3. **Default variables in tests:** `{{ variable | default('fallback') }}` for Molecule compatibility
4. **Test file paths not contents:** Don't read entire files in verify, just check existence
5. **Test permissions carefully:** Use `stat` module to verify ownership/mode
6. **Don't test Docker internals:** Test inputs/outputs, not container internals

**When Debugging Tests:**

```bash
# Verbose Molecule output
cd roles/caddy && molecule test -v

# Keep containers for inspection
molecule create      # Create test container
molecule converge    # Apply role
# ... inspect manually ...
molecule destroy     # Clean up

# SSH into container
docker exec -it instance /bin/bash
```

## Integration with Deployment

**Full Deploy Flow:**

1. `make lint` — Verify YAML/Ansible syntax
2. `make deploy-prod` — Deploy via ansible-playbook
3. Post-deploy: `./scripts/smoke-test.sh https://domain.com` — Verify endpoints

**Dry-run Before Prod:**

```bash
ansible-playbook playbooks/site.yml --check --diff
```

Shows exactly what would change without making changes.

---

*Testing analysis: 2026-02-28*
