# ComfyUI Concurrent Access — Design Spec

**Date**: 2026-03-22
**Status**: Approved
**Goal**: Enable human (browser UI) and Claude CLI to collaboratively create, edit, execute, and version ComfyUI workflows simultaneously.

---

## Problem Statement

ComfyUI runs on Waza (RPi5) at `studio.ewutelo.cloud`. Currently:
- The user edits workflows in the browser UI
- Claude CLI has a basic MCP (`comfy-ui-mcp-server`) with only `generate_image`
- Workflows saved in the UI are **lost on container recreation** (no volume mount for `/app/user`)
- No version history, no attribution of who changed what

**Target**: Both the user and Claude CLI can list, read, create, edit, execute, and version workflows on the same ComfyUI instance, with full git history and Gitea backup.

---

## Architecture

```
Browser (studio.ewutelo.cloud)
         |
    Caddy → ComfyUI (:8188) directly (unchanged)

Claude CLI / User terminal
         |
    ├── MCP (comfyui-studio) → calls CLI under the hood
    └── Bash → comfyui-cli → HTTP to ComfyUI API (:8188)
                    |
               git commit on write operations

inotify watcher (systemd service)
    → watches workflow directory
    → git commit "browser: modified X" on filesystem changes
    → debounce 5s window (background subprocess pattern)

Git remote: Gitea on Seko-VPN
    → auto-push every 5 minutes
```

### Design Decisions

1. **CLI-first, MCP-second**: The CLI is the foundation. The MCP wrapper calls the CLI. If MCP breaks, Claude falls back to Bash + CLI with zero downtime.
2. **No proxy**: The browser talks directly to ComfyUI (unchanged). Browser writes are captured by inotify on the filesystem. This avoids the risk of a reverse proxy breaking the UI (WebSocket, binary previews, multipart uploads).
3. **Attribution**: CLI commits are attributed to "Claude CLI". Browser commits (via inotify) are attributed to "Browser UI". Both use git author metadata.
4. **Gitea remote**: Workflows are backed up to Gitea on Seko-VPN, accessible from anywhere on the VPN mesh.

---

## Components

### 1. Docker Volume Fix (Critical)

**Problem**: `docker-compose-creative.yml.j2` does not mount `/app/user`. Workflows saved via the UI are stored inside the container and lost on recreation.

**Fix**: Add volume mount in `docker-compose-creative.yml.j2`:
```yaml
volumes:
  - {{ comfyui_data_dir }}/user:/app/user
```

Create host directory with correct permissions:
```bash
mkdir -p {{ comfyui_data_dir }}/user/default/workflows
chown -R 1000:1000 {{ comfyui_data_dir }}/user
```

**Note**: `/app/user` also contains `comfyui.db` (SQLite settings database) and custom node runtime assets (e.g., `comfy-api-liberation-assets/`). The volume mount persists all of this — which is a benefit (settings survive container recreation). The git repo MUST be scoped to the `workflows` subdirectory only, never at `/app/user` level.

### 2. CLI: `comfyui-cli`

Python CLI tool (using `click` or `typer`), installed on the Pi in a dedicated venv at `/opt/workstation/comfyui-cli/.venv/`.

**Dependencies**: `click`, `requests`, `pyyaml`, `qdrant-client`, `openai` (for embeddings). Installed via `requirements.txt` + Ansible `pip` task.

#### Commands

**Workflow CRUD:**
```
comfyui-cli workflows list [--json]
comfyui-cli workflows get <path> [--json | --raw]
comfyui-cli workflows save <path> [--file input.json | --stdin]
comfyui-cli workflows delete <path>
comfyui-cli workflows rename <old_path> <new_path>
```

**Execution:**
```
comfyui-cli exec <workflow_path> [--param key=value ...] [--wait] [--json]
comfyui-cli exec --prompt "text prompt" [--width 512] [--height 512] [--seed N] [--wait]
```

**Queue & History:**
```
comfyui-cli queue [--json]
comfyui-cli cancel [<prompt_id> | --all]
comfyui-cli history [--limit 10] [--json]
comfyui-cli output <prompt_id> [--save-to <dir>]
```

**Introspection:**
```
comfyui-cli nodes [<node_class>] [--json]
comfyui-cli models [<folder>] [--json]
comfyui-cli upload <image_path> [--subfolder <name>] [--json]
comfyui-cli status [--json]
```

**Documentation:**
```
comfyui-cli docs <query> [--limit 5] [--category <cat>] [--json]
```

**Versioning:**
```
comfyui-cli versions <workflow_path> [--limit 10] [--json]
comfyui-cli revert <workflow_path> <commit_sha>
comfyui-cli diff <workflow_path> [<commit_sha>]
```

**Note**: `--json` is a global flag available on all commands. Claude uses this flag for machine-parseable output.

#### Configuration

File `/home/mobuone/.comfyui-cli.yaml` (deployed by Ansible from `roles/comfyui/templates/comfyui-cli.yaml.j2`):
```yaml
comfyui_url: http://localhost:8188
workflows_dir: /opt/workstation/data/comfyui/user/default/workflows
git_enabled: true
git_author_name: "Claude CLI"
git_author_email: "claude@localhost"
qdrant_url: https://qd.ewutelo.cloud
qdrant_api_key: "{{ qdrant_api_key }}"
qdrant_collection: comfyui-docs
litellm_url: https://llm.ewutelo.cloud/v1
litellm_api_key: "{{ litellm_api_key }}"
```

Or env vars: `COMFYUI_URL`, `COMFYUI_WORKFLOWS_DIR`.

**Note**: The `workflows_dir` path (`/app/user/default/workflows`) is specific to ComfyUI v0.17.1+ where `default` is the default user profile. Verify on upgrade. The path is configurable in this config file so it can be changed without modifying scripts.

#### Output Format

- Default: human-readable table/text
- `--json`: machine-parseable JSON (Claude uses this flag)
- `--raw`: raw API response (for debugging)

#### UI-to-API Format Conversion

The `exec` command handles conversion from ComfyUI UI format to API format:

1. Load workflow JSON (UI format with `nodes`, `links`, `widgets_values`)
2. Query `GET /object_info` to get node class metadata (input names, types, defaults)
3. For each node, map positional `widgets_values` to named inputs using `object_info` metadata
4. Resolve `links` array to `["source_node_id", output_index]` references
5. Output flat API format: `{ "node_id": { "class_type": "...", "inputs": {...} } }`

If the workflow is already in API format (detected by presence of `class_type` keys), skip conversion.

**Risk**: Custom nodes may have non-standard widget layouts. Mitigation: `/object_info` provides the authoritative input spec for all installed nodes including custom ones.

#### Git Integration

On every `workflows save`, `workflows delete`, `workflows rename`:
1. Execute the ComfyUI API call
2. Wait for filesystem sync (the volume mount propagates the change)
3. `git add <path>` + `git commit -m "cli: <action> <path>"` with author attribution
4. Non-blocking (git errors logged but don't fail the CLI command)

### 3. inotify Watcher (`comfyui-watcher.service`)

Systemd service that watches the workflows directory for browser-initiated changes.

**Implementation**: Bash script using `inotifywait` (from `inotify-tools` package). Template: `roles/comfyui/templates/comfyui-watcher.sh.j2` (uses `{{ comfyui_workflows_dir }}` variable, not hardcoded paths).

```bash
#!/bin/bash
set -euo pipefail
WATCH_DIR="{{ comfyui_workflows_dir }}"
cd "$WATCH_DIR"

inotifywait -m -r -e modify,create,delete,moved_to,moved_from \
  --exclude '\.git/' \
  --format '%w%f' "$WATCH_DIR" | while read -r file; do
    # Skip .git directory events (belt and suspenders with --exclude)
    [[ "$file" == *"/.git/"* ]] && continue
    # If no pending commit, schedule one via background subprocess
    if ! [ -f /tmp/comfyui-watcher-pending ]; then
        touch /tmp/comfyui-watcher-pending
        (
            sleep 5
            rm -f /tmp/comfyui-watcher-pending
            # Skip if last CLI commit was recent (avoid double-committing)
            last_cli=$(git log -1 --author="Claude CLI" --format=%ct 2>/dev/null || echo 0)
            now=$(date +%s)
            if [ $((now - last_cli)) -lt 10 ]; then exit 0; fi
            cd "$WATCH_DIR"
            git add -A
            git diff --cached --quiet || \
              git -c user.name="Browser UI" -c user.email="browser@localhost" \
                commit -m "browser: modified workflows"
        ) &
    fi
done
```

**Key behavior**:
- **inotify `--exclude '\.git/'`**: Prevents git operations from triggering new events (avoids feedback loop)
- **Background subprocess debounce**: The first event spawns a 5s delayed commit in the background. Subsequent events during the window are ignored (pending file exists). After commit completes, the next event starts a new cycle.
- **CLI attribution check**: Skips if last commit author was "Claude CLI" within 10s (avoids double-committing CLI changes detected by inotify)
- Non-fatal: git errors are logged to journald but don't crash the watcher

### 4. Git Setup + Gitea Remote

**Init** (Ansible task):
```bash
cd {{ comfyui_workflows_dir }}
git init
git remote add origin git@seko-vpn:mobuone/comfyui-workflows.git
```

**`.gitignore`** (created by Ansible in the workflows git repo):
```
*.tmp
*.bak
.DS_Store
__pycache__/
*.pyc
```

**Initial commit + push** (Ansible task, handles first-time setup):
```bash
cd {{ comfyui_workflows_dir }}
git add -A
git diff --cached --quiet || git commit -m "init: workflow repository"
git push -u origin main 2>/dev/null || true
```

**Auto-push** (cron, installed in `mobuone` user's crontab via `ansible.builtin.cron`):
```
*/5 * * * * cd {{ comfyui_workflows_dir }} && git push --quiet origin main 2>/dev/null || git push --quiet -u origin main 2>/dev/null || true
```

**Gitea repo**: Created on Seko-VPN (`87.106.30.160`). SSH key `~/.ssh/seko-vpn-deploy` for push access.

### 5. MCP Wrapper (`comfyui-studio`)

Thin Python MCP server (~100 lines) that calls the CLI subprocess.

**Tools** (map 1:1 to CLI commands):

| MCP Tool | CLI Command |
|----------|------------|
| `list_workflows` | `comfyui-cli workflows list --json` |
| `get_workflow` | `comfyui-cli workflows get <path> --json` |
| `save_workflow` | `echo '<json>' \| comfyui-cli workflows save <path> --stdin` |
| `execute_workflow` | `comfyui-cli exec <path> --wait --json` |
| `generate_image` | `comfyui-cli exec --prompt "..." --wait --json` |
| `get_queue` | `comfyui-cli queue --json` |
| `get_history` | `comfyui-cli history --json` |
| `get_output` | `comfyui-cli output <prompt_id> --json` |
| `get_versions` | `comfyui-cli versions <path> --json` |
| `get_status` | `comfyui-cli status --json` |
| `get_nodes` | `comfyui-cli nodes --json` |
| `upload_image` | `comfyui-cli upload <path> --json` |
| `search_docs` | `comfyui-cli docs <query> --json` |

**Config in `.claude.json`** (replaces both `comfy-ui` and `comfy-pilot` MCP entries):
```json
{
  "comfyui-studio": {
    "type": "stdio",
    "command": "/opt/workstation/comfyui-cli/.venv/bin/python3",
    "args": ["/opt/workstation/comfyui-studio/mcp_server.py"],
    "env": {}
  }
}
```

### 6. ComfyUI Documentation Access (Qdrant)

**Problem**: Claude CLI needs access to ComfyUI documentation (node specs, API reference, tutorials) to build and debug workflows effectively. Loading full docs into context each time is wasteful.

**Solution**: Index ComfyUI docs into Qdrant (semantic search), query via CLI/MCP on demand.

**Existing asset**: `scripts/index-comfyui-docs.py` already handles:
- Download `llms-full.txt` from `docs.comfy.org`
- Chunk by markdown sections (with overlap)
- Generate embeddings via LiteLLM (`embedding` model)
- Store in Qdrant collection `comfyui-docs` at `https://qd.ewutelo.cloud`
- Categories: built-in-nodes, custom-nodes, api-reference, tutorials, development, etc.

**CLI command**:
```
comfyui-cli docs <query> [--limit 5] [--category <cat>] [--json]
```

Queries Qdrant `comfyui-docs` collection via semantic search. Returns title, URL, relevant text excerpt, and similarity score.

**MCP tool**: `search_docs` → `comfyui-cli docs <query> --json`

**Indexing**: Run `scripts/index-comfyui-docs.py` as an Ansible task or manual cron. Re-index on ComfyUI version upgrades.

### 7. Ansible Role Changes

**Modified files**:
- `roles/comfyui/templates/docker-compose-creative.yml.j2` — add user volume mount
- `roles/comfyui/tasks/main.yml` — create user directory, install CLI, init git, setup watcher, run doc indexing

**New files**:
- `roles/comfyui/files/comfyui-cli/` — CLI source code + `requirements.txt`
- `roles/comfyui/files/comfyui-studio/` — MCP wrapper source
- `roles/comfyui/templates/comfyui-watcher.sh.j2` — inotify watcher script (templatized paths)
- `roles/comfyui/templates/comfyui-watcher.service.j2` — systemd unit for watcher
- `roles/comfyui/templates/comfyui-cli.yaml.j2` — CLI config (deployed to `/home/mobuone/.comfyui-cli.yaml`)
- `roles/comfyui/files/comfyui-git-push.sh` — cron push script

**Existing file** (no change needed):
- `scripts/index-comfyui-docs.py` — Qdrant doc indexer (already written)

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| UI→API format conversion fails on custom nodes | Medium-High | Use `/object_info` for authoritative metadata. Log conversion errors with node details. Allow `--raw` API format input as escape hatch. |
| inotify watcher feedback loop (git ops trigger new events) | Medium | `inotifywait --exclude '\.git/'` + bash guard `[[ "$file" == *"/.git/"* ]]`. Background subprocess debounce avoids blocking the pipe reader. |
| inotify watcher creates duplicate commits (CLI change detected by watcher) | Medium | Skip commit if last "Claude CLI" commit was <10s ago. Background subprocess pattern ensures clean debounce. |
| Git conflicts on push to Gitea | Low | Push uses `--quiet` and is non-fatal. Manual resolution if needed. Single-user git, conflicts unlikely. |
| ComfyUI container recreation loses `user/` data | Critical (current bug) | Volume mount fix is Phase 1 priority. |
| Permissions mismatch on user directory | Low | Dockerfile uses uid 1000:1000. Ansible creates dir with same ownership. |
| inotifywait not available on Pi | Low | `inotify-tools` is a standard Debian package. Ansible installs it. |
| Qdrant docs collection empty or stale | Low | Indexing script is idempotent (upsert). Re-run on ComfyUI upgrades. CLI `docs` command returns helpful error if collection missing. |
| Embedding cost for doc indexing | Low | One-time cost (~200-400 chunks). Re-index only on version upgrades. |
| Workflow path changes on ComfyUI upgrade | Low | Path is configurable in `~/.comfyui-cli.yaml` and templatized in watcher script. Verify on version bumps. |

---

## Implementation Phases

### Phase 1: Foundation (Volume fix + CLI core)
- Fix Docker volume mount for `/app/user`
- Create directory structure with correct permissions
- Build CLI with workflow CRUD (`list`, `get`, `save`, `delete`)
- Build CLI `exec` with simple prompt shortcut (no UI→API conversion yet)
- Build CLI `queue`, `history`, `status`
- Test manually: save workflow in browser, read it with CLI, submit a prompt

### Phase 2: Versioning (Git + inotify)
- Init git repo in workflows directory with `.gitignore`
- Create Gitea repo on Seko-VPN
- Add git integration to CLI (auto-commit on save/delete)
- Create inotify watcher service (with `--exclude .git/` and background debounce)
- Create cron push script (handles initial push with `-u` fallback)
- Build CLI `versions`, `revert`, `diff` commands
- Test: make changes in browser and CLI, verify git log shows both with attribution

### Phase 3: Advanced Execution (UI→API conversion)
- Implement `exec <workflow_path>` with UI→API format conversion
- Query `/object_info` for widget-to-input mapping
- Support `--param key=value` overrides
- Support `--wait` (poll until completion)
- Build `output` command to retrieve generated files
- Build `nodes`, `models`, `upload` commands

### Phase 4: Documentation Access (Qdrant)
- Run `scripts/index-comfyui-docs.py` to populate Qdrant `comfyui-docs` collection
- Add `docs` command to CLI (semantic search via Qdrant)
- Add Qdrant config to CLI config file
- Test: `comfyui-cli docs "KSampler parameters"` returns relevant results

### Phase 5: MCP Wrapper
- Build thin MCP server calling CLI subprocess
- Configure in `.claude.json`
- Test all MCP tools (including `search_docs`)
- Remove old `comfy-ui` and `comfy-pilot` MCP entries from `.claude.json`

---

## Success Criteria

1. User can save a workflow in browser UI → CLI can list and read it immediately
2. Claude CLI can create/modify a workflow → user sees it in browser UI immediately
3. Both changes are tracked in git with correct attribution (browser vs CLI)
4. Git history is pushed to Gitea on Seko-VPN
5. Claude CLI can execute workflows and retrieve outputs
6. `comfyui-cli versions` shows interleaved browser and CLI changes
7. `comfyui-cli revert` restores a previous version
8. MCP tools work as fallback for generate_image (backward compatible)
9. If MCP fails, Claude can use CLI via Bash with identical functionality
10. `comfyui-cli docs "KSampler"` returns relevant documentation from Qdrant
11. MCP `search_docs` tool provides contextual ComfyUI knowledge to Claude during workflow creation
