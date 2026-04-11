# Research: Gotenberg + n8n Multi-step Forms — NOC MOP Generation

**Date:** 2026-04-11  
**Scope:** Factual validation for Ansible deployment spec (Sese-AI, Docker Compose, behind Caddy VPN-only)

---

## Part 1 — Gotenberg

### 1. Latest stable version

**`8.30.1`** (released 2026-04-06)  
Source: https://github.com/gotenberg/gotenberg/releases/latest

Pin tag: `gotenberg/gotenberg:8.30.1`

### 2. Multi-arch Docker images

Both `amd64` and `arm64` are present in every stable versioned tag:

```
8.30.1           → ['386', 'amd64', 'arm', 'arm64', 'ppc64le']
8.30.1-chromium  → ['386', 'amd64', 'arm', 'arm64', 'ppc64le']
```

Source: Docker Hub `gotenberg/gotenberg` tags API

### 3. HTML→PDF API endpoint

```
POST /forms/chromium/convert/html
Content-Type: multipart/form-data
```

**Required field:** `index.html` (mandatory, verified in source `routes.go` line 502: `MandatoryPath("index.html", &inputPath)`)

**Additional assets** (CSS, images, fonts): upload as extra multipart files alongside `index.html`. They must be flat (no subdirectory paths) — Gotenberg serves them all from the same temp directory and the HTML references them by filename only.

**Optional PDF rendering fields** (all via multipart): `landscape`, `printBackground`, `scale`, `paperWidth`, `paperHeight`, `marginTop/Bottom/Left/Right`, `nativePageRanges`, `header.html`, `footer.html`, `waitDelay`, `waitForExpression`, `emulatedMediaType`, etc.

**curl example:**
```bash
curl -s \
  --request POST "http://localhost:3000/forms/chromium/convert/html" \
  --form "index.html=@/path/to/index.html" \
  --form "style.css=@/path/to/style.css" \
  --form "printBackground=true" \
  -o output.pdf
```

Source: `pkg/modules/chromium/routes.go` in gotenberg/gotenberg repo

### 4. Hyperlink preservation

Gotenberg uses Chromium's native print-to-PDF pipeline (since v8.22.0, all architectures use Chromium — previously `amd64` used Google Chrome). Chromium's PDF renderer **does preserve `<a href>` tags as clickable PDF hyperlinks**. No open GitHub issues report link breakage. This is standard Chromium behaviour and applies to both internal anchor links and external URLs.

### 5. Memory footprint and container limits

| Context | Minimum | Recommended |
|---|---|---|
| Kubernetes | 512Mi RAM, 0.2 CPU | — |
| Cloud Run / general | 512 MB | 1 GB for smooth experience |
| Chromium concurrency | up to 6 parallel | scale horizontally for load |

**For Sese-AI (8 GB VPS), recommended container limits:**
- `mem_limit: 1g` / `memswap_limit: 1g`
- `cpus: 1.0` (Chromium is CPU-heavy during render)

Chromium restarts every 100 conversions by default (configurable via `--chromium-restart-after`).

### 6. Default port

**3000** (via `--api-port` flag or `API_PORT` env var, binds `0.0.0.0:3000` by default).

### 7. ARM64 caveats

None specific to self-hosted. Since v8.22.0, ARM64 uses the same Chromium binary as amd64 (previously used a different build). No performance delta documented. Sese-AI is `amd64` so this is moot for production.

Sources:
- https://gotenberg.dev/docs/getting-started/installation
- https://gotenberg.dev/docs/configuration
- https://github.com/gotenberg/gotenberg (source code)

---

## Part 2 — n8n Multi-step Forms

### 1. Multi-step Form support — version and minimum

The **n8n Form** node (separate from Form Trigger) was introduced in **n8n v1.65.0** (2024-10-24) as "n8n Form Page Node: New node" (PR #10390).

Your deployed version **n8n 2.7.3** fully supports multi-step forms — the feature has been shipping since v1.65 and has been continuously improved (binary response added ~v1.91, CSS customization, etc.).

Multi-step architecture: `Form Trigger` (page 1) → `Form` nodes (subsequent pages) → `Form` node with operation=`completion` (final page/response).

Source: https://github.com/n8n-io/n8n/releases/tag/n8n%401.65.0

### 2. Conditional branching between form pages

**Yes.** Standard IF/Switch nodes can be placed between Form nodes. The workflow pauses at each Form node (`putExecutionToWait`), and when the user submits, execution resumes and continues through any downstream logic including IF branches. The form session is maintained by a signed `resumeFormUrl`.

The n8n docs describe "Workflows with mutually exclusive branches" and "Workflows that may execute multiple branches" as supported patterns.

Source: n8n Form node source `Form.node.ts` + docs.n8n.io Form node page

### 3. Aggregating inputs across pages into a single JSON

**Yes, but requires explicit merging.** Each Form node's POST handler calls `prepareFormReturnItem()` which returns the current page's fields as a new item. The node's `execute()` method returns `context.getInputData()` — meaning it carries the upstream item through unchanged.

In practice: each Form page appends its fields to the workflow item's `.json` object. By the time you reach the final node, all fields from all pages are accessible via expressions like `{{ $('Form Trigger').item.json.fieldName }}` and `{{ $('Form').item.json.fieldName }}`. A **Merge** or **Set** node before the Completion step can consolidate all fields into one flat object.

**Limitation:** There is no automatic deep-merge across pages. Fields from page 1 live in the Form Trigger's output; fields from page 2 live in the first Form node's output. You must reference them explicitly by node name or use a Merge node.

### 4. Calling Gotenberg from form flow and returning PDF as file download

Pattern:
1. `HTTP Request` node → `POST http://gotenberg:3000/forms/chromium/convert/html` with multipart body containing rendered HTML.
2. The HTTP Request node receives the binary PDF response — store it in a binary field (e.g. `data`).
3. Connect to a Form node (operation=`completion`, `respondWith: returnBinary`).
4. Set `inputDataFieldName` = `data` (the binary field name from step 2).

The user's browser receives the PDF as a file download directly from the form completion page.

**Source:** `Form.node.ts` completion properties — `returnBinary` option with `inputDataFieldName` confirmed in source code.

### 5. CSV append via Write Binary File or Execute Command

**Write Binary File node** can write a binary (e.g. a CSV buffer) to disk — it does not append, it overwrites. For appending to a CSV:

- **Execute Command node**: `echo "{{ $json.col1 }},{{ $json.col2 }}" >> /data/output.csv` — works but requires the n8n container to have write access to the mounted path.
- **Read Binary File → append → Write Binary File**: read existing CSV, manipulate in Code node, write back. Fragile under concurrency.
- **Recommended alternative**: use the **Spreadsheet File** node (read/write XLSX or CSV) or write directly to NocoDB/PostgreSQL which is already in your stack.

**Limitation:** n8n has no native CSV-append node. Execute Command requires `N8N_RUNNERS_ENABLED` or direct shell access in the container. The cleanest approach for your stack is to POST the JSON row to NocoDB's API v2 endpoint directly from n8n.

Sources:
- https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.form/
- https://github.com/n8n-io/n8n (Form node source)
- https://github.com/n8n-io/n8n/releases/tag/n8n%401.65.0

---

## Summary Table

| Question | Answer |
|---|---|
| Gotenberg latest tag | `8.30.1` |
| Gotenberg port | `3000` |
| HTML→PDF endpoint | `POST /forms/chromium/convert/html` |
| Required multipart field | `index.html` (mandatory); assets = additional files |
| Hyperlinks preserved | Yes (Chromium native PDF, standard behaviour) |
| Memory minimum | 512 MB; recommend 1 GB limit on Sese-AI |
| ARM64 support | Full (same Chromium binary since v8.22.0) |
| n8n multi-step forms min version | v1.65.0 (Oct 2024); v2.7.3 fully supported |
| Conditional branching | Yes (IF/Switch nodes between Form nodes) |
| Input aggregation across pages | Yes, via node references or Merge node |
| PDF file download to user | Yes (`returnBinary` completion option) |
| CSV append | No native node; use Execute Command or NocoDB API |
| `N8N_RESTRICT_FILE_ACCESS_TO` separator | `;` (semicolon) — NOT `:` (colon) |
| `import:workflow` updates | DRAFT only (`workflow_entity.nodes`) — NOT `workflow_history` |
| How to make import take effect at runtime | `publish:workflow --id=<id>` after import |
| env_file reload after change | `docker compose up -d --force-recreate <svc>` — NOT `docker restart` |

---

## Addendum — Session MOP2 (2026-04-11)

### P11 — `import:workflow` updates DRAFT only, NOT `workflow_history`

**n8n 2.7.3 dual-table architecture:**
- `workflow_entity.nodes` = DRAFT (what `import:workflow` writes)
- `workflow_history[activeVersionId].nodes` = ACTIVE VERSION (what n8n executes at runtime)

`import:workflow` alone does NOT update `workflow_history`. If `activeVersionId` still points
to an old history entry, that old version runs regardless of how many restarts you do.

**Root cause discovery (exec 11740/11752):** `export:workflow` returned the correct 8-node draft;
but execution_data showed node names from the old 6-node definition. DB query confirmed:
`workflow_history` at `activeVersionId=e9e442d3` had the original definition from 11:01:03;
the draft was updated at 13:xx:xx and never published.

**Fix:** `n8n publish:workflow --id=<WF_ID>` — snapshots current draft into a new `workflow_history`
entry and sets `workflow_entity.activeVersionId` to it. This is what n8n actually loads at runtime.
The deploy script (`scripts/mop/deploy-mop-generator.sh`) includes `publish:workflow` as step 6.

### P12 — `update:workflow --active=true` deprecated; use `publish:workflow`

`n8n update:workflow --id=<id> --active=true` activates the workflow but does NOT snapshot a new
`workflow_history` entry. Use `publish:workflow` which both publishes (draft → history) and activates.

### P13 — `N8N_RESTRICT_FILE_ACCESS_TO` uses SEMICOLON separator (not colon)

Source (`file-system-helper-functions.js`, `getAllowedPaths()`):
```js
return (process.env.N8N_RESTRICT_FILE_ACCESS_TO || '').split(';').map(p => p.trim()).filter(Boolean);
```

Using `:` makes `"/home/node/.n8n-files:/data/mop"` one invalid path instead of two. The error
message lists the raw env value so it looks correct, but access still fails.

**Correct value:**
```
N8N_RESTRICT_FILE_ACCESS_TO=/home/node/.n8n-files;/data/mop
```

Updated in `roles/n8n/templates/n8n.env.j2`.

### P14 — `env_file` changes require `--force-recreate`, not `docker restart`

`docker restart` does NOT reload the docker compose `env_file`. Use:
```bash
docker compose up -d --force-recreate n8n
```

### P15 — n8n healthz returns too early; poll the form URL instead

`/healthz` returns `{"status":"ok"}` within ~1-3s of start, but FormTrigger webhook registration
is async. Poll `http://127.0.0.1:5678/form/mop-generator` until HTML contains `"Generate MOP"`.

**E2E results (2026-04-11):**
- Exec 11759: happy path PASS — `MOP-2026-0016.pdf` (32 KB), `status=success`, `lastNode=Done (PDF)`
- Exec 11761: error branch PASS (Gotenberg stopped) — `EAI_AGAIN gotenberg`, `lastNode=Done (Error)`
