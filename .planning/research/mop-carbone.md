# Carbone.io — Self-Hosted Validation for NOC MOP PDF Generation

**Date:** 2026-04-11  
**Target:** Sese-AI VPS (amd64, Debian 13, Docker Compose behind Caddy)  
**Use case:** ODT master template + JSON data → PDF, callable from n8n + bash CLI

---

## 1. License & Self-Hosting Viability

**Verdict: Viable for internal on-premise use. NOT viable if you resell it as a hosted service.**

Carbone uses a dual-license model:

- **carbone-ee Docker image** (Docker Hub `carbone/carbone-ee`): Community features run **free without any license key** on-premise. No phone-home required for community mode. A `CARBONE_EE_LICENSE` env var is only needed to unlock Enterprise features (dynamic images, barcodes, charts, Studio auth, S3 storage).
- **carboneio/carbone npm package** (open-source engine): Licensed under **CCL (Carbone Community License)**. You may use and modify it freely, including in commercial products, as long as you do **not** offer it as a hosted Document-Generator-as-a-Service competing with Carbone Cloud. Internal MOP generation within your own infrastructure is fully permitted.

**Sources:**
- [Is Carbone On-premise available?](https://help.carbone.io/en-us/article/is-carbone-on-premise-available-2d3tay/)
- [CCL License text](https://github.com/carboneio/carbone/blob/master/LICENSE.md)
- [Deploy with Docker](https://carbone.io/documentation/developer/self-hosted-deployment/deploy-with-docker.html)

---

## 2. Docker Image — Version & Architecture

**Recommended tag for amd64 production (Sese-AI):**

```
carbone/carbone-ee:full-4.26.3
```

- **full-4.26.3**: 262 MB compressed — includes LibreOffice 25.2 (required for ODT→PDF). Updated 2026-04-09.
- **full-5.4.4**: 509 MB — Enterprise v5 engine (community features only without license). Updated 2026-04-08.
- **slim-4.26.3**: 91 MB — **no LibreOffice, no PDF generation**. Unusable for this use case.

**Architecture:** All tags ship `amd64` + `arm64` multi-arch manifests. Both architectures confirmed in Docker Hub metadata.

**Tag naming convention:** `full-{engine_version}-L{libreoffice_version}[-fonts]`
- `-fonts` variant adds Google Fonts (+1 GB): only needed for DOCX/PPTX with custom fonts.
- For ODT MOPs, `full-4.26.3` (no fonts suffix) is sufficient.

**Note on v4 vs v5:** The community Docker image runs the same engine regardless of tag. v5 (`full-5.4.4`) requires an Enterprise license to unlock its additional features; the community feature set is identical in practice between v4.x and v5.x tags. Use `full-4.26.3` to avoid the extra 247 MB overhead.

**Source:** [Docker Hub carbone/carbone-ee](https://hub.docker.com/r/carbone/carbone-ee)

---

## 3. Template Syntax (ODT)

Carbone templates use `{d.field}` markers inside any ODT (or DOCX, XLSX, etc.) document edited in LibreOffice Writer.

### Field access
```
{d.fieldName}
{d.nested.field}
```

### Conditions (inline)
```
{d.status:ifEQ(active):show(ACTIVE):elseShow(INACTIVE)}
{d.priority:ifEqual(high, 'URGENT')}
```
Switch-case chain: `{d.val:ifEQ(1):show(A):ifEQ(2):show(B):elseShow(C)}`

Older syntax `{d.x:ifEqual(value):show(...):elseShow(...)}` still works.

### Loops (arrays)
```
{d[i].field}        ← loop start marker, first row
{d[i+1].field}      ← loop end marker, removed from output
```
Nested loops also use `[i]`/`[i+1]` (not `j`).

**Sources:**
- [Template getting started](https://carbone.io/documentation/design/overview/getting-started.html)
- [Inline conditions](https://carbone.io/documentation/design/conditions/inline-conditions.html)
- [DEV cheat sheet](https://dev.to/carbone/cheat-sheet-for-carbone-2ikd)

---

## 4. REST API

Port: **4000** (no auth by default in community mode).

### Step 1 — Upload template (once)
```
POST /template
Content-Type: multipart/form-data
Body: template=<odt-file>

Response: { "success": true, "data": { "id": "<templateId>", "versionId": "<sha256>" } }
```

### Step 2 — Render to PDF
```
POST /render/{templateId}
Content-Type: application/json
Body:
{
  "data": { "field1": "value1", "items": [...] },
  "convertTo": "pdf",
  "converter": "L"
}

Response: { "success": true, "data": { "renderId": "<renderId>" } }
```
`converter: "L"` forces LibreOffice (correct for ODT→PDF). Omit for default.

### Step 3 — Download result
```
GET /render/{renderId}
Response: binary PDF stream (Content-Type: application/pdf)
```
**Important:** The render is available for **1 hour** and can be downloaded **once only**. For n8n workflows, download immediately after render.

**Shortcut (inline template, no pre-upload):** Pass `"template": "<base64-odt>"` directly in the render body instead of a templateId. Useful for the bash CLI wrapper.

**Sources:**
- [HTTP API introduction](https://carbone.io/documentation/developer/http-api/introduction.html)
- [Upload templates](https://carbone.io/documentation/developer/http-api/manage-templates.html)
- [Generate reports](https://carbone.io/documentation/developer/http-api/generate-reports.html)

---

## 5. Template Storage

Templates are stored **server-side persistently** under a stable `templateId` (UUID). Multiple versions are tracked; the latest deployed version is used automatically. Volume to persist: `/app/template`.

For MOP use: upload the ODT master once → store the `templateId` in n8n/config → reuse for all renders. No need to re-upload per render.

---

## 6. Memory & Resource Footprint

- **Recommended:** 1 vCPU, 1024 MB RAM
- **Image size:** 262 MB compressed (full-4.26.3), ~800 MB on disk after extraction
- LibreOffice spawns a subprocess per render; concurrent renders will spike memory. On Sese-AI (8 GB), a single instance with `mem_limit: 1.5g` is safe for sequential MOP generation.

---

## 7. Recommendation

**Use `carbone/carbone-ee:full-4.26.3`.** It is:
- Free for internal commercial on-premise use (CCL license, no SaaS restriction triggered)
- No license key required for ODT→PDF rendering
- amd64 multi-arch (arm64 bonus for Waza Pi testing)
- REST API identical to Carbone Cloud (n8n HTTP Request node works as-is)
- Template stored by ID (upload once, reference forever)

**If Carbone proves unsuitable** (e.g., LibreOffice rendering instability, complex table layout issues), the closest community alternative is:

| Alternative | Templating | WYSIWYG | PDF |
|---|---|---|---|
| [docxtemplater](https://docxtemplater.com/) | DOCX/PPTX `{field}` syntax | LibreOffice Writer | Via LibreOffice CLI (`--headless --convert-to pdf`) |
| LibreOffice headless + Python-docx + Jinja2 | Full Jinja2 in ODT via search/replace | LibreOffice Writer | Native `--convert-to pdf` |
| [gotenberg](https://gotenberg.dev/) | No templating, HTML/DOCX conversion only | N/A | Chrome/LibreOffice |

For NOC MOP generation with an existing ODT master and WYSIWYG editing in LibreOffice, **docxtemplater (OSS core, MIT) + LibreOffice CLI** is the best fallback: same `{field}` authoring experience, no vendor lock-in, Python/Node SDK available.
