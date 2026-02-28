# Coding Conventions

**Analysis Date:** 2026-02-28

## Naming Patterns

**Files:**
- Role directories: lowercase with hyphens (e.g., `roles/common/`, `roles/caddy/`, `roles/n8n-mcp/`)
- Task files: `roles/<role>/tasks/main.yml`
- Handler files: `roles/<role>/handlers/main.yml`
- Default variables: `roles/<role>/defaults/main.yml`
- Fixed variables: `roles/<role>/vars/main.yml` (less common)
- Meta: `roles/<role>/meta/main.yml`
- Templates: `roles/<role>/templates/<name>.j2` (always `.j2` extension)
- Molecule tests: `roles/<role>/molecule/default/` (converge.yml, verify.yml, molecule.yml)
- Playbooks: `playbooks/<name>.yml` (e.g., `playbooks/site.yml`, `playbooks/workstation.yml`)
- Shell scripts: `scripts/<name>.sh` (e.g., `scripts/smoke-test.sh`, `scripts/wizard.sh`)

**Variables:**
- Role-scoped defaults: prefix with role name (e.g., `caddy_config_dir`, `n8n_data_dir`, `postgresql_password`)
- Global variables: no prefix (e.g., `project_name`, `domain_name`, `prod_user`, `target_env`)
- Internal/computed variables: register in tasks (e.g., `caddy_build_result`, `sshd_preflight`, `common_repo_check`)
- Boolean defaults: use `| default(false) | bool` pattern for safety
- Snake_case only: never camelCase (e.g., `caddy_vpn_enforce`, not `caddyVpnEnforce`)

**Functions (shell/Python):**
- Lowercase with underscores (e.g., `livesync_id()`, `couch_request()`, `push_note()`)
- Python functions: document with docstrings explaining purpose
- Shell functions in templates: minimal, use native bash/utilities

**Task Names:**
- Descriptive and actionable (e.g., "Create Caddy config directory", "Deploy Caddyfile", "Restart caddy stack")
- Include condition context if not obvious (e.g., "VPN-only: Build Caddy image with OVH DNS plugin")
- Use "Check" prefix for informational commands (e.g., "Check Debian repos completeness")
- Use "Verify" prefix for assertions (e.g., "Verify Ansible version")

## Code Style

**Formatting:**

YAML formatting (enforced by `yamllint`):
- Indentation: 2 spaces (no tabs)
- Line length: 160 chars max (warning level)
- Brace/bracket spacing: max 1 space inside (e.g., `{ key: value }`)
- Quotes: use single quotes for strings unless $ interpolation needed
- Boolean values: must be `true`/`false` or `yes`/`no` (no unquoted `True`/`False`)
- Comment spacing: 1 space minimum after `#` (enforced)

Config file: `.yamllint.yml` in repository root.

**Linting:**

Ansible linting (enforced by `ansible-lint` in production profile):
- FQCN mandatory: `ansible.builtin.file`, not `file`
- `changed_when` and `failed_when` required on all `command` and `shell` tasks
- No bare `command`/`shell` if a module exists (e.g., use `ansible.builtin.apt` not `shell apt-get`)
- Idempotence: tasks must be safe to run multiple times (exit status 0 on second run)

Config file: `.ansible-lint` in repository root (strict profile, FQCN enforced).

**Shell Blocks:**

All `shell` tasks must include shebang and error handling:
```yaml
- name: Example shell task
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: |
      set -euo pipefail
      # Commands here
  changed_when: '<condition>'
  failed_when: '<condition>'
```

Lines in templates: required: `#!/usr/bin/env bash` or `#!/usr/bin/env python3`

## Import Organization

**Ansible Task Order (within role):**

1. Pre-flight checks (info gathering, validation)
2. Directory/file creation
3. File deployments (templates, copies)
4. Service/container operations
5. Handlers triggered last (via `notify`)

**Task Dependencies (cross-role):**

Explicit in `meta/main.yml` `dependencies` section:
```yaml
dependencies:
  - role: docker        # Docker must be deployed before this role
  - role: postgresql    # PostgreSQL client must be available
```

Example from `roles/n8n/meta/main.yml`:
```yaml
dependencies:
  - role: docker
  - role: postgresql
```

**Python Imports (templates):**

Order in Python scripts:
1. Standard library (`import os`, `import sys`, `json`, `urllib`)
2. Third-party (none in current codebase, but would come here)
3. Application config (variables injected by Jinja2)
4. Function/class definitions

Example from `roles/obsidian-collector/templates/collector.py.j2`:
```python
import base64
import glob
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# === Configuration (générée par Ansible) ===
COUCHDB_URL = "{{ obsidian_collector_couchdb_url }}"
```

## Error Handling

**Pattern 1 - Command/Shell Output Parsing:**

```yaml
- name: Check something
  ansible.builtin.command:
    cmd: some-command
  register: result
  changed_when: false
  failed_when: false

- name: Act on result
  ansible.builtin.debug:
    msg: "{{ result.stdout }}"
  when: result.rc == 0
```

Use `changed_when: false` for read-only commands. Use `failed_when: false` to allow non-zero exits.

**Pattern 2 - Conditional Based on Stdout:**

```yaml
- name: Build image if needed
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: |
      set -euo pipefail
      docker build --tag myimage:tag .
      echo "BUILT:myimage:tag"
  register: build_result
  changed_when: "'BUILT:' in build_result.stdout"
  failed_when: build_result.rc != 0
```

Echo a marker token for `changed_when` to detect if work was done.

**Pattern 3 - Assertion Pre-flight:**

```yaml
- name: Verify Ansible version
  ansible.builtin.assert:
    that:
      - ansible_version.full is version('2.16', '>=')
    fail_msg: "Ansible 2.16+ required. Current: {{ ansible_version.full }}"
```

Anti-lockout pattern (always in `pre_tasks`):
```yaml
- name: "ANTI-LOCKOUT: Validate sshd config before proceeding"
  ansible.builtin.command:
    cmd: sshd -t
  become: true
  changed_when: false
  failed_when: false
  register: sshd_preflight
  tags: [always]

- name: "ANTI-LOCKOUT: Warn if sshd config is broken"
  ansible.builtin.debug:
    msg: "WARNING: sshd config validation failed..."
  when: sshd_preflight.rc is defined and sshd_preflight.rc != 0
  tags: [always]
```

## Logging

**Ansible:**
- Use `ansible.builtin.debug` for informational output
- Use `msg:` with multi-line strings for formatted output:
  ```yaml
  - name: Display deployment info
    ansible.builtin.debug:
      msg: |
        ========================================
        Project: {{ project_display_name }}
        Environment: {{ target_env | default('prod') }}
        ========================================
  ```

**Python (in templates):**
- No explicit logging framework — use `print()` for cron job output (e.g., in `roles/obsidian-collector/templates/collector.py.j2`)
- Use `time` and `datetime` for timestamps
- Return status as exit code (0 = success, 1 = failure)

**Shell Scripts:**
- Use echo with section headers:
  ```bash
  echo "============================================"
  echo "  Smoke Tests — CI/CD"
  echo "  $(date)"
  echo "============================================"
  ```
- Prefix test result lines with `PASS`, `FAIL`, `SKIP`, `WARN` (see `scripts/smoke-test.sh`)

## Comments

**When to Comment:**

- REX (Return of Experience) callouts: mark workarounds and gotchas with `# REX:` prefix
  - Example: `# REX: Docker bridge frontend (172.20.1.0/24) — gateway utilisé par DNAT...`
- Critical security decisions: e.g., trusted proxies, VPN enforcement
- Non-obvious variable derivations: e.g., why a default is constructed from other variables
- Breaking changes from upgrades: e.g., `# REX: L'ancienne variable unique couplait 4 fonctions → découplement atomique.`
- Archival notes: e.g., `# caddy_kaneo_domain: archivé — Kaneo supprimé (Phase 16...)`

**When NOT to Comment:**

- Self-documenting code (task names, variable names are descriptive)
- Obvious loops and conditionals
- Standard Ansible module options (they're well-documented in module docs)

**JSDoc/Docstring Pattern:**

Python functions in templates:
```python
def livesync_id(path: str) -> str:
    """Génère le _id CouchDB au format LiveSync v2."""
    return "v2:plain:" + base64.b64encode(path.encode()).decode()
```

Use triple-quoted docstrings, English or French (French dominant in project).

## Variables Organization

**Defaults vs Fixed:**

`defaults/main.yml` (overridable):
- Role-scoped configuration (paths, image tags, feature toggles)
- Should reference global variables: `caddy_config_dir: "/opt/{{ project_name }}/configs/caddy"`
- Defaults should not leak implementation details

`vars/main.yml` (fixed, not typically used):
- Only for constants that should never be overridden
- Rare in this project

`meta/main.yml`:
- Only `galaxy_info` and `dependencies`

**Secrets:**

All secrets in `inventory/group_vars/all/secrets.yml` (Ansible Vault encrypted):
- Never in defaults, tasks, or templates as literals
- Reference as `{{ postgresql_password }}` (shared across all DB users)
- Environment variables injected via `env_file` or docker-compose

## Handlers

**Handler Naming:**

Action-oriented: "Restart X stack", "Update apt cache"

Example from `roles/caddy/handlers/main.yml`:
```yaml
- name: Restart caddy stack
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose-infra.yml
    services:
      - caddy
    state: restarted
  become: true
```

**Trigger Pattern:**

Tasks notify handlers via `notify:` keyword:
```yaml
- name: Deploy Caddyfile
  ansible.builtin.template:
    src: Caddyfile.j2
    dest: "{{ caddy_config_dir }}/Caddyfile"
    ...
  notify: Restart caddy stack
```

**Critical: env_file Handler Gotcha**

For services with `env_file`, use `state: present` with `recreate: always` (not `state: restarted`):
```yaml
# WRONG — doesn't reload env_file:
- name: Restart n8n
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    services:
      - n8n
    state: restarted

# CORRECT — recreates container with new env_file:
- name: Recreate n8n with new env
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    services:
      - n8n
    state: present
    recreate: always
```

See `CLAUDE.md` section "Docker — Convention critique" for full details.

## Testing & Validation

**Linting Before Deploy:**

```bash
make lint              # Runs yamllint + ansible-lint
make lint-yaml        # Only yamllint
make lint-ansible     # Only ansible-lint
```

**Code Quality Checks:**

```bash
make check-no-latest  # Ensures no :latest Docker tags
make check-hardcoded  # Verifies no hardcoded project names
```

**Dry-run Before Prod:**

```bash
ansible-playbook playbooks/site.yml --check --diff
```

---

*Convention analysis: 2026-02-28*
