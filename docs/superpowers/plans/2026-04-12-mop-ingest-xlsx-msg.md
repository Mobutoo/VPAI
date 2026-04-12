# mop-ingest-v1 — xlsx + .msg Support Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend mop-ingest-v1 n8n workflow to index Excel spreadsheets (xlsx family) and Outlook MSG emails into the mop_kb Qdrant collection.

**Architecture:** Two independent components: (1) xlsx routes through the existing Gotenberg PDF-conversion path with a specialized telecom prompt; (2) msg routes through a new Python FastAPI sidecar (msg2md) that extracts structured markdown + images, with text going directly to the chunker and images optionally to Gemini for visual description.

**Tech Stack:** n8n (JS Code node), Ansible, Docker Compose, Python 3.12 + FastAPI + extract-msg, Gotenberg/LibreOffice

**LOI OP constraints:**
- R1: `mcp__n8n-docs__validate_workflow` BEFORE any n8n import
- R3: Edit JSON local → commit → CLI import + double restart
- R4: Test msg2md isolation BEFORE n8n integration
- R7: SSH/SCP via 100.64.0.14 only (Tailscale)

---

## File Map

### New files to create
- `roles/msg2md/meta/main.yml` — Galaxy metadata
- `roles/msg2md/defaults/main.yml` — msg2md_port: 3100, msg2md_python_base ref
- `roles/msg2md/tasks/main.yml` — Create /opt/project/msg2md/, copy Dockerfile + requirements.txt, template app.py
- `roles/msg2md/handlers/main.yml` — restart msg2md handler
- `roles/msg2md/files/Dockerfile` — python:3.12.10-slim, pip install, run app.py
- `roles/msg2md/files/requirements.txt` — pinned deps
- `roles/msg2md/templates/app.py.j2` — FastAPI /convert + /health

### Files to modify
- `scripts/n8n-workflows/mop-ingest-v1.json` — acceptFileTypes + MIME_MAP + INGEST_PROMPTS + xlsx branch + msg branch
- `roles/docker-stack/templates/docker-compose.yml.j2` — Add msg2md service after gotenberg block
- `inventory/group_vars/all/versions.yml` — Add msg2md_python_base: "python:3.12.10-slim"

---

## Phase 1: xlsx Support (no new infra)

### Task 1: Update n8n workflow JSON for xlsx

**Files:**
- Modify: `scripts/n8n-workflows/mop-ingest-v1.json`

The changes are all within the `jsCode` string of the "Process Files" Code node (around line 122 in the JSON).

- [ ] **Step 1.1: Update acceptFileTypes in FormTrigger node**

In `mop-ingest-v1.json`, find `"acceptFileTypes": ".pdf,.pptx,.docx"` and replace with:
```json
"acceptFileTypes": ".pdf,.pptx,.docx,.xlsx,.xls,.xlsm,.xlsb,.csv,.msg"
```

- [ ] **Step 1.2: Add xlsx MIME types to MIME_MAP**

In the jsCode string, find:
```js
const MIME_MAP = {
  pdf:  'application/pdf',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};
```
Replace with:
```js
const MIME_MAP = {
  pdf:  'application/pdf',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  xls:  'application/vnd.ms-excel',
  xlsm: 'application/vnd.ms-excel.sheet.macroEnabled.12',
  xlsb: 'application/vnd.ms-excel.sheet.binary.macroEnabled.12',
  csv:  'text/csv',
};
```

- [ ] **Step 1.3: Add xlsx prompt + MSG2MD constants to jsCode**

Add after the MIME_MAP (before `function mimeFromName`):
```js
const MSG2MD_HOST = 'msg2md';
const MSG2MD_PORT = 3100;
```

In `INGEST_PROMPTS`, add after the `docx` entry:
```js
  xlsx: "Tu es un expert en systèmes télécom (DWDM, SDH, IP/MPLS). Ce document est un tableau de base de connaissances NOC converti en PDF. Chaque ligne est un type d'incident ou une procédure. Les colonnes typiques sont : type de perte, réseau, descriptif, impact, cause probable, étapes de résolution, processus de communication, criticité, exemples d'alarmes.\n\nExtrais chaque entrée non-vide en markdown structuré :\n- H2 pour chaque type d'incident/perte\n- Sous chaque H2 : listes des champs renseignés (Cause, Résolution, Criticité, Exemples d'alarmes, etc.)\n- Préserve les codes alarme, noms d'équipements, références opérateurs.\n- Ignore les lignes entièrement vides.\nRetourne UNIQUEMENT le markdown, sans préambule ni commentaire.",
  msg_images: "Tu es un expert en systèmes télécom (DWDM, SDH, IP/MPLS, Ribbon). Ces captures d'écran proviennent d'un échange de support technique NOC. Décris chaque image en markdown structuré :\n- Ce que l'interface affiche (type d'outil : NMS, CLI, alarme, PM counters, etc.)\n- Les éléments techniques visibles : nœuds, ports, valeurs PM, états d'alarmes, commandes CLI et leur output, timestamps\n- Toute valeur numérique ou code d'alarme lisible\n\nFormat : une section H3 par image, titrée \"Capture N\".\nRetourne UNIQUEMENT le markdown, sans préambule ni commentaire.",
```

After INGEST_PROMPTS definition, add:
```js
// xlsx family all use xlsx prompt
['xls', 'xlsm', 'xlsb', 'csv'].forEach(e => INGEST_PROMPTS[e] = INGEST_PROMPTS.xlsx);
```

- [ ] **Step 1.4: Extend gotenbergConvert() branch to include xlsx family**

Find in jsCode:
```js
  if (['docx', 'doc', 'pptx', 'ppt'].includes(fileExt)) {
```
Replace with:
```js
  if (['docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls', 'xlsm', 'xlsb', 'csv'].includes(fileExt)) {
```

- [ ] **Step 1.5: Add msg branch BEFORE the existing Gotenberg/LLM block**

Find the comment `// 1a. Convert non-PDF` in the jsCode for-loop. Insert BEFORE it:

```js
  // ── .msg: msg2md sidecar → markdown + optional image descriptions ──────────
  if (fileExt === 'msg') {
    const rawBuf = Buffer.from(file.base64, 'base64');
    // POST to msg2md
    const boundary2 = 'Msg2mdBoundary' + Date.now();
    const CRLF2 = '\r\n';
    const msgHeader = Buffer.from(
      '--' + boundary2 + CRLF2 +
      'Content-Disposition: form-data; name="file"; filename="' + file.filename + '"' + CRLF2 +
      'Content-Type: application/vnd.ms-outlook' + CRLF2 + CRLF2
    );
    const msgFooter = Buffer.from(CRLF2 + '--' + boundary2 + '--' + CRLF2);
    const msgBody = Buffer.concat([msgHeader, rawBuf, msgFooter]);
    const msg2mdResp = await new Promise((resolve, reject) => {
      const req = require('http').request(
        { hostname: MSG2MD_HOST, port: MSG2MD_PORT, path: '/convert', method: 'POST',
          headers: { 'Content-Type': 'multipart/form-data; boundary=' + boundary2, 'Content-Length': msgBody.length } },
        (res) => {
          const chunks2 = [];
          res.on('data', c => chunks2.push(c));
          res.on('end', () => {
            const text2 = Buffer.concat(chunks2).toString();
            try { resolve({ status: res.statusCode, data: JSON.parse(text2) }); }
            catch (e) { resolve({ status: res.statusCode, data: text2 }); }
          });
        }
      );
      req.on('error', reject);
      req.write(msgBody);
      req.end();
    });
    if (msg2mdResp.status !== 200) {
      throw new Error(`msg2md conversion failed (${file.filename}): HTTP ${msg2mdResp.status} — ` + JSON.stringify(msg2mdResp.data).slice(0, 200));
    }
    const { markdown: msgMarkdown, images: msgImages } = msg2mdResp.data;

    let fullMarkdown = msgMarkdown;

    // Call Gemini for images if any
    if (msgImages && msgImages.length > 0) {
      const imageContent = [
        { type: 'text', text: INGEST_PROMPTS.msg_images },
        ...msgImages.map((img, idx) => ({
          type: 'image_url',
          image_url: { url: `data:${img.mimeType};base64,${img.base64}` },
        })),
      ];
      const imgResp = await llm('/v1/chat/completions', {
        model: 'mop-ingest',
        max_tokens: 4096,
        messages: [{ role: 'user', content: imageContent }],
      });
      if (imgResp.status === 200) {
        const imageDescriptions = imgResp.data.choices[0].message.content;
        fullMarkdown = msgMarkdown + '\n\n## Descriptions visuelles\n' + imageDescriptions;
      }
    }

    // Chunk + embed + delete old + upsert (same pipeline as other formats)
    const titleM2 = fullMarkdown.match(/^#\s+(.+)/m);
    const docTitle2 = titleM2 ? titleM2[1].trim() : file.filename.replace(/\.msg$/i, '');
    const contentHash2 = sha256hex(fullMarkdown);
    const refDocId2 = sha256hex(`${namespace}:${file.filename}:${indexedAt}`);
    const chunks2 = chunkMarkdown(fullMarkdown);
    if (chunks2.length === 0) throw new Error(`Aucun chunk produit pour ${file.filename}`);

    await qdrant('POST', `/collections/${COLLECTION}/points/delete`, {
      filter: { must: [
        { key: 'filename',  match: { value: file.filename } },
        { key: 'namespace', match: { value: namespace } },
      ]},
    });

    const allVecs2 = [];
    for (let i = 0; i < chunks2.length; i += EMBED_BATCH) {
      const batch = chunks2.slice(i, i + EMBED_BATCH);
      const embResp = await llm('/v1/embeddings', { model: 'mop-embed', input: batch });
      if (embResp.status !== 200) throw new Error('Embedding échoué (msg): ' + JSON.stringify(embResp.data).slice(0, 300));
      const sorted = [...embResp.data.data].sort((a, b) => a.index - b.index);
      allVecs2.push(...sorted.map(e => e.embedding));
    }

    const points2 = chunks2.map((chunk, idx) => ({
      id: toUUID(sha256hex(`${refDocId2}:${idx}:${chunk.slice(0, 64)}`)),
      vector: allVecs2[idx],
      payload: {
        schema_version: '1.0', embedding_model: 'text-embedding-004', embedding_dim: 768,
        chunking_strategy_version: '1.0', ref_doc_id: refDocId2, repo: '', namespace,
        host_origin: 'sese-ai', source_kind: sourceKind, doc_kind: category, topic: '',
        severity: '', category, phase: '', relative_path: file.filename, filename: file.filename,
        language, tags: [], git_commit_sha: '', content_hash: contentHash2,
        chunk_index: idx, chunk_count: chunks2.length, chunking_kind: 'markdown_paragraph',
        section: sectionHeader(chunk), title: docTitle2, indexed_at: indexedAt, text: chunk,
      },
    }));

    for (let i = 0; i < points2.length; i += UPSERT_BATCH) {
      const r = await qdrant('PUT', `/collections/${COLLECTION}/points`, { points: points2.slice(i, i + UPSERT_BATCH) });
      if (r.status !== 200) throw new Error('Qdrant upsert échoué (msg): ' + JSON.stringify(r.data).slice(0, 300));
    }

    results.push({ filename: file.filename, chunks: chunks2.length, ref_doc_id: refDocId2 });
    continue;  // skip the rest of the loop for .msg files
  }
  // ── end .msg branch ─────────────────────────────────────────────────────────
```

**Important:** The `continue` statement requires the `for...of` loop to be converted. Currently the code uses:
```js
const files = await Promise.all(...);
...
for (const file of files) {
```
The existing loop uses `for (const file of files)` — check if it's actually a `for...of` or a different pattern. If it's a `Promise.all` + mapping pattern, restructure to use `for...of` with async to allow `continue`.

Look at the actual jsCode end to confirm the loop structure:
```js
for (const file of files) {
  // ... existing code
}
```
The `continue` works in `for...of`. ✅

- [ ] **Step 1.6: Validate workflow with MCP**

```
mcp__n8n-docs__validate_workflow on the modified scripts/n8n-workflows/mop-ingest-v1.json
```
Expected: zero blocking errors. Fix any syntax issues before proceeding.

- [ ] **Step 1.7: Commit Phase 1 changes**

```bash
cd /home/mobuone/VPAI
git add scripts/n8n-workflows/mop-ingest-v1.json
git commit -m "feat(mop-ingest): add xlsx/csv support via Gotenberg + .msg branch stub (msg2md)"
```

- [ ] **Step 1.8: Import workflow to n8n + double restart**

```bash
# SSH via Tailscale (R7)
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "n8n import:workflow --input=/opt/javisi/n8n/workflows/mop-ingest-v1.json || true"

# Copy first if needed
scp -i ~/.ssh/seko-vpn-deploy -P 804 \
  scripts/n8n-workflows/mop-ingest-v1.json \
  mobuone@100.64.0.14:/tmp/mop-ingest-v1.json

ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker exec javisi_n8n n8n import:workflow --input=/tmp/mop-ingest-v1.json && \
   docker restart javisi_n8n && sleep 5 && docker restart javisi_n8n"
```

---

## Phase 2: msg2md Ansible Role

### Task 2: Create msg2md role files

**Files:**
- Create: `roles/msg2md/meta/main.yml`
- Create: `roles/msg2md/defaults/main.yml`
- Create: `roles/msg2md/files/Dockerfile`
- Create: `roles/msg2md/files/requirements.txt`
- Create: `roles/msg2md/templates/app.py.j2`
- Create: `roles/msg2md/tasks/main.yml`
- Create: `roles/msg2md/handlers/main.yml`
- Modify: `inventory/group_vars/all/versions.yml`

- [ ] **Step 2.1: Create `roles/msg2md/meta/main.yml`**

```yaml
---
galaxy_info:
  author: mobuone
  description: msg2md — Outlook MSG to markdown sidecar (FastAPI)
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions: [bookworm]
dependencies: []
```

- [ ] **Step 2.2: Create `roles/msg2md/defaults/main.yml`**

```yaml
---
msg2md_port: 3100
msg2md_memory_limit: "256M"
msg2md_cpu_limit: "0.5"
# Base image pinned in versions.yml under msg2md_python_base
```

- [ ] **Step 2.3: Create `roles/msg2md/files/Dockerfile`**

```dockerfile
FROM python:3.12.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 3100
CMD ["python", "app.py"]
```

Note: Port 3100 is hardcoded in CMD because this is a static file (no Jinja2). The env var `MSG2MD_PORT` can override at runtime.

- [ ] **Step 2.4: Create `roles/msg2md/files/requirements.txt`**

```
extract-msg==0.55.0
fastapi==0.115.12
uvicorn==0.34.2
python-multipart==0.0.20
```

- [ ] **Step 2.5: Create `roles/msg2md/templates/app.py.j2`**

```python
"""msg2md — Outlook MSG to structured markdown converter.
FastAPI service listening on port {{ msg2md_port }}.
"""
import os
import re
import base64
import io
import json

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import extract_msg

PORT = int(os.environ.get("MSG2MD_PORT", {{ msg2md_port }}))

app = FastAPI(title="msg2md", version="1.0.0")

# ── Constants ────────────────────────────────────────────────────────────────
IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'gif'}
IMAGE_MIN_BYTES = 5 * 1024  # 5 KB — ignore tracking pixels and small logos

# SR number patterns: Ribbon/Salesforce (SR#NNNNNN-NNNNNN) and generic
SR_PATTERN = re.compile(r'SR#?\d{6}-\d{6}', re.IGNORECASE)

# Alarm line pattern: MAJOR/MINOR/CRITICAL/WARNING severity + node + description
ALARM_PATTERN = re.compile(
    r'(MAJOR|MINOR|CRITICAL|WARNING)\s+([\w\-]+(?::[\w\/\.]+)?)\s+(.+)',
    re.IGNORECASE
)

# Outlook thread delimiter (multiline: From/Sent/To/Subject block)
THREAD_DELIMITER = re.compile(
    r'(?:From|De)\s*:[ \t]*.+\n'
    r'(?:Sent|Envoy[eé])\s*:[ \t]*.+\n'
    r'(?:To|[AÀ])\s*:[ \t]*.+\n'
    r'(?:(?:Cc|Subject|Objet)\s*:[ \t]*.+\n)*',
    re.IGNORECASE | re.MULTILINE
)

# Banners to strip
DISCLAIMER_PATTERN = re.compile(
    r'CAUTION\s*:.*?(?=\n\n|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Salesforce tracking URLs
SALESFORCE_URL_PATTERN = re.compile(
    r'https?://[^\s]*salesforce\.com[^\s]*',
    re.IGNORECASE
)

# Signature triggers (cut body here)
SIGNATURE_TRIGGERS = [
    'thank you', 'thanks,', 'regards,', 'best regards', 'cordialement',
    'cdlt,', 'sincèrement', 'bien cordialement',
]

NOC_DOMAIN = 'fr.telehouse.net'
SALESFORCE_DOMAINS = {'apex.salesforce.com', 'salesforce.com', 'force.com'}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_email_addr(raw: str) -> str:
    """Extract bare email address from 'Name <email>' or 'email' format."""
    m = re.search(r'<([^>]+)>', raw)
    return m.group(1).strip().lower() if m else raw.strip().lower()


def _is_noc(raw: str) -> bool:
    addr = _get_email_addr(raw)
    return NOC_DOMAIN in addr


def _is_salesforce(raw: str) -> bool:
    addr = _get_email_addr(raw)
    return any(d in addr for d in SALESFORCE_DOMAINS)


def _sender_role(raw: str) -> str | None:
    """Return 'NOC Telehouse', company name, or None for Salesforce addresses."""
    if _is_noc(raw):
        return 'NOC Telehouse'
    if _is_salesforce(raw):
        return None
    addr = _get_email_addr(raw)
    domain = addr.split('@')[-1] if '@' in addr else addr
    parts = domain.split('.')
    # Take second-to-last part as company (e.g., 'rbbn' from 'rbbn.com')
    company = parts[-2].capitalize() if len(parts) >= 2 else domain
    return f'Support {company}'


def _clean_body(text: str) -> str:
    """Remove disclaimers, signatures, RTF artifacts, and tracking URLs."""
    # Remove disclaimer banners
    text = DISCLAIMER_PATTERN.sub('', text)
    # Remove Salesforce URLs
    text = SALESFORCE_URL_PATTERN.sub('', text)
    # Remove RTF bullet artifacts (lines starting with * + tab)
    text = re.sub(r'^\*\t.*$', '', text, flags=re.MULTILINE)
    # Cut at signature
    lower = text.lower()
    cut_idx = len(text)
    for trigger in SIGNATURE_TRIGGERS:
        idx = lower.find(trigger)
        if 0 < idx < cut_idx:
            cut_idx = idx
    text = text[:cut_idx]
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _tag_alarms(text: str) -> str:
    """Wrap alarm lines in inline code."""
    def _replacer(m):
        return f'`{m.group(0)}`'
    return ALARM_PATTERN.sub(_replacer, text)


def _split_thread(body: str) -> list[dict]:
    """Split Outlook thread into list of {header, body} dicts, chronological order."""
    splits = THREAD_DELIMITER.split(body)
    headers = THREAD_DELIMITER.findall(body)

    parts = []
    if splits[0].strip():
        parts.append({'header': None, 'body': splits[0].strip()})
    for h, b in zip(headers, splits[1:]):
        parts.append({'header': h.strip(), 'body': b.strip()})

    parts.reverse()  # oldest first
    return parts


def _parse_thread_header(header: str) -> tuple[str, str]:
    """Extract (date_str, from_raw) from thread delimiter block."""
    date_m = re.search(r'(?:Sent|Envoy[eé])\s*:[ \t]*(.+)', header, re.IGNORECASE)
    from_m = re.search(r'(?:From|De)\s*:[ \t]*(.+)', header, re.IGNORECASE)
    date_str = date_m.group(1).strip()[:16] if date_m else ''
    from_raw = from_m.group(1).strip() if from_m else ''
    return date_str, from_raw


# ── API endpoints ────────────────────────────────────────────────────────────

@app.get('/health')
def health():
    return {'status': 'ok'}


@app.post('/convert')
async def convert(file: UploadFile = File(...)):
    content = await file.read()

    try:
        msg = extract_msg.Message(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'Failed to parse .msg: {exc}')

    # ── 1. Metadata ──────────────────────────────────────────────────────────
    subject = (msg.subject or '').strip()
    sender_raw = (msg.sender or '').strip()
    date_str = str(msg.date)[:10] if msg.date else ''
    to_raw = (msg.to or '').strip()
    cc_raw = (msg.cc or '').strip()

    sr_m = SR_PATTERN.search(subject)
    sr_number = sr_m.group(0) if sr_m else ''

    sev_m = re.search(r'\b(Minor|Major|Critical|Warning)\b', subject, re.IGNORECASE)
    severity = sev_m.group(1).capitalize() if sev_m else ''

    # ── 2. Header block ──────────────────────────────────────────────────────
    title = f'{sr_number} — {subject}' if sr_number else subject
    lines = [f'# {title}', '']

    meta_parts = []
    if severity:
        meta_parts.append(f'**Sévérité ticket:** {severity}')
    if date_str:
        meta_parts.append(f'**Date:** {date_str}')
    if meta_parts:
        lines.extend([' | '.join(meta_parts), ''])

    # ── 3. Stakeholders ──────────────────────────────────────────────────────
    lines.append('## Parties prenantes')
    all_addr_raws = [a for a in [sender_raw, to_raw, cc_raw] if a]
    noc_addrs = [a for a in all_addr_raws if _is_noc(a)]
    ext_addrs = [a for a in all_addr_raws if not _is_noc(a) and not _is_salesforce(a)]

    if noc_addrs:
        lines.append(f'- **NOC Telehouse**: {", ".join(noc_addrs)}')
    if ext_addrs:
        lines.append(f'- **Support externe**: {", ".join(ext_addrs)}')
    lines.append('')

    # ── 4. Thread body ───────────────────────────────────────────────────────
    body = (msg.body or '').strip()
    # Fallback to HTML-stripped body if plain text is empty
    if not body:
        html_body = getattr(msg, 'htmlBody', None) or b''
        if html_body:
            body = re.sub(r'<[^>]+>', '', html_body.decode('utf-8', errors='replace'))

    thread_parts = _split_thread(body)
    for part in thread_parts:
        if part['header']:
            part_date, from_raw_part = _parse_thread_header(part['header'])
            role = _sender_role(from_raw_part)
            if role is None:
                continue  # skip Salesforce-only messages
            lines.extend([f'## [{part_date}] {role}', ''])

        cleaned = _clean_body(part['body'])
        tagged = _tag_alarms(cleaned)
        if tagged.strip():
            lines.extend([tagged, ''])

    # ── 5. Attachments ───────────────────────────────────────────────────────
    images = []
    skipped = []

    for att in (msg.attachments or []):
        att_name = (att.longFilename or att.shortFilename or 'attachment').strip()
        ext = att_name.rsplit('.', 1)[-1].lower() if '.' in att_name else ''

        if ext == 'msg':
            skipped.append({'filename': att_name, 'reason': 'nested_msg'})
            continue

        if ext not in IMAGE_EXTS:
            skipped.append({'filename': att_name, 'reason': 'non_image'})
            continue

        data = att.data
        if not data or len(data) < IMAGE_MIN_BYTES:
            continue  # tracking pixel or empty

        mime = 'image/jpeg' if ext == 'jpg' else f'image/{ext}'
        size_kb = len(data) // 1024
        images.append({
            'filename': att_name,
            'mimeType': mime,
            'base64': base64.b64encode(data).decode('utf-8'),
        })
        lines_to_add_later = True  # signal to add section

    if images:
        lines.extend(['## Pièces jointes techniques (captures)'])
        for img in images:
            size_kb = len(base64.b64decode(img['base64'])) // 1024
            lines.append(f'- {img["filename"]} ({size_kb} KB)')
        lines.append('')

    if skipped:
        print(f'[msg2md] skipped_attachments: {json.dumps([s["filename"] for s in skipped])}',
              flush=True)

    markdown = '\n'.join(lines)
    return JSONResponse({'markdown': markdown, 'images': images})


# ── Entrypoint ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=PORT)
```

- [ ] **Step 2.6: Create `roles/msg2md/tasks/main.yml`**

```yaml
---
# msg2md — Tasks

- name: Create msg2md build context directory
  ansible.builtin.file:
    path: "/opt/{{ project_name }}/msg2md"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true
  tags: [msg2md, phase3]

- name: Copy msg2md Dockerfile
  ansible.builtin.copy:
    src: Dockerfile
    dest: "/opt/{{ project_name }}/msg2md/Dockerfile"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true
  notify: Rebuild msg2md
  tags: [msg2md, phase3]

- name: Copy msg2md requirements.txt
  ansible.builtin.copy:
    src: requirements.txt
    dest: "/opt/{{ project_name }}/msg2md/requirements.txt"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true
  notify: Rebuild msg2md
  tags: [msg2md, phase3]

- name: Template msg2md app.py
  ansible.builtin.template:
    src: app.py.j2
    dest: "/opt/{{ project_name }}/msg2md/app.py"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true
  notify: Rebuild msg2md
  tags: [msg2md, phase3]
```

- [ ] **Step 2.7: Create `roles/msg2md/handlers/main.yml`**

```yaml
---
# msg2md — Handlers

- name: Rebuild msg2md
  ansible.builtin.command:
    cmd: docker compose -f /opt/{{ project_name }}/docker-compose.yml up -d --build msg2md
  become: true
  changed_when: true
  tags: [msg2md, phase3]
```

- [ ] **Step 2.8: Add msg2md_python_base to `inventory/group_vars/all/versions.yml`**

After the `gotenberg_image` line (~line 123), add:
```yaml
msg2md_python_base: "python:3.12.10-slim"
```

- [ ] **Step 2.9: Commit msg2md role**

```bash
git add roles/msg2md/ inventory/group_vars/all/versions.yml
git commit -m "feat(msg2md): new Ansible role — FastAPI .msg to markdown sidecar"
```

---

### Task 3: Add msg2md to docker-compose.yml.j2

**Files:**
- Modify: `roles/docker-stack/templates/docker-compose.yml.j2`

- [ ] **Step 3.1: Add msg2md service block after gotenberg**

In `roles/docker-stack/templates/docker-compose.yml.j2`, find the line:
```
  carbone:
    image: {{ carbone_image }}
```
(which comes right after the gotenberg block ending around line 952)

Insert BEFORE it:
```yaml
  msg2md:
    build:
      context: /opt/{{ project_name }}/msg2md
      dockerfile: Dockerfile
    container_name: "{{ project_name }}_msg2md"
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
    networks:
      - backend
    environment:
      - MSG2MD_PORT={{ msg2md_port }}
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:{{ msg2md_port }}/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: {{ msg2md_memory_limit }}
          cpus: "{{ msg2md_cpu_limit }}"

```

- [ ] **Step 3.2: Commit docker-compose change**

```bash
git add roles/docker-stack/templates/docker-compose.yml.j2
git commit -m "feat(docker-stack): add msg2md sidecar service (Phase B, backend network)"
```

---

## Phase 3: Deploy + Test

### Task 4: Deploy msg2md to Sese-AI

**Prerequisites:** Phase 2 commits pushed. SSH via Tailscale (100.64.0.14).

- [ ] **Step 4.1: Push commits to remote**

```bash
git push github-seko main
```

- [ ] **Step 4.2: Deploy msg2md role (creates build context + files)**

```bash
source .venv/bin/activate
make deploy-role ROLE=msg2md ENV=prod
```
Expected: No errors. Build context files appear in `/opt/javisi/msg2md/` on Sese-AI.

- [ ] **Step 4.3: Deploy docker-stack role (builds + starts msg2md container)**

```bash
make deploy-role ROLE=docker-stack ENV=prod
```
Expected: `msg2md` container appears in `docker ps` output on Sese-AI.

- [ ] **Step 4.4: Verify msg2md health**

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker inspect --format='{{.State.Health.Status}}' javisi_msg2md"
```
Expected: `healthy`

- [ ] **Step 4.5: R4 isolation test — msg2md convert**

From Waza (via Tailscale to 100.64.0.14), msg2md is on backend-only network (no exposed port).
Test via docker exec on Sese-AI:

```bash
# Copy test file to Sese-AI
scp -i ~/.ssh/seko-vpn-deploy -P 804 \
  /home/mobuone/VPAI/telehouse.msg \
  mobuone@100.64.0.14:/tmp/telehouse.msg

# Test from within n8n container (same backend network as msg2md)
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker cp /tmp/telehouse.msg javisi_n8n:/tmp/telehouse.msg && \
   docker exec javisi_n8n node -e \"
const http = require('http');
const fs = require('fs');
const buf = fs.readFileSync('/tmp/telehouse.msg');
const boundary = 'B' + Date.now();
const header = Buffer.from('--' + boundary + '\r\nContent-Disposition: form-data; name=\"file\"; filename=\"telehouse.msg\"\r\nContent-Type: application/vnd.ms-outlook\r\n\r\n');
const footer = Buffer.from('\r\n--' + boundary + '--\r\n');
const body = Buffer.concat([header, buf, footer]);
const req = http.request({hostname:'msg2md',port:3100,path:'/convert',method:'POST',headers:{'Content-Type':'multipart/form-data; boundary='+boundary,'Content-Length':body.length}},(res)=>{const c=[];res.on('data',d=>c.push(d));res.on('end',()=>{const r=JSON.parse(Buffer.concat(c).toString());console.log('markdown_len='+r.markdown.length+' images='+r.images.length);console.log(r.markdown.slice(0,500));});});req.on('error',e=>console.error(e));req.write(body);req.end();
\""
```
Expected output: `markdown_len=<N> images=<M>` with non-zero markdown, followed by markdown preview starting with `# SR#...` or the email subject.

- [ ] **Step 4.6: Import updated workflow (with msg branch) to n8n**

```bash
scp -i ~/.ssh/seko-vpn-deploy -P 804 \
  /home/mobuone/VPAI/scripts/n8n-workflows/mop-ingest-v1.json \
  mobuone@100.64.0.14:/tmp/mop-ingest-v1.json

ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker exec javisi_n8n n8n import:workflow --input=/tmp/mop-ingest-v1.json && \
   docker restart javisi_n8n && sleep 8 && docker restart javisi_n8n"
```

- [ ] **Step 4.7: E2E test — submit incidents.xlsx**

Use Playwright MCP (R2) to submit the form:
- Navigate to the mop-ingest form URL (get from n8n webhook: look for FormTrigger webhookId in workflow JSON)
- Fill: category=sp, namespace=mop, language=fr, source_kind=reference
- Upload: `/home/mobuone/VPAI/incidents.xlsx`
- Submit and verify "Done" page

Then verify Qdrant has new points:
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "curl -s -H 'api-key: <QDRANT_KEY>' http://localhost:6333/collections/mop_kb/points/scroll \
   -d '{\"filter\":{\"must\":[{\"key\":\"filename\",\"match\":{\"value\":\"incidents.xlsx\"}}]},\"limit\":3}' | \
   python3 -c 'import sys,json; d=json.load(sys.stdin); print(f\"Points found: {len(d[\"result\"][\"points\"])}\")'"
```

- [ ] **Step 4.8: E2E test — submit telehouse.msg**

Use Playwright MCP (R2) to submit the form:
- Same form
- Upload: `/home/mobuone/VPAI/telehouse.msg`
- Submit and verify "Done" page

Then verify Qdrant:
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "curl -s -H 'api-key: <QDRANT_KEY>' http://localhost:6333/collections/mop_kb/points/scroll \
   -d '{\"filter\":{\"must\":[{\"key\":\"filename\",\"match\":{\"value\":\"telehouse.msg\"}}]},\"limit\":3}'"
```
Expected: points with `doc_kind: 'sp'`, markdown text containing the email thread content.

- [ ] **Step 4.9: Final commit — mark complete**

```bash
git tag mop-ingest-xlsx-msg-v1 -m "mop-ingest-v1: xlsx + .msg support complete"
git push github-seko main --tags
```

---

## Notes for Executor

### Finding the form URL
```bash
python3 -c "
import json
wf = json.load(open('scripts/n8n-workflows/mop-ingest-v1.json'))
for node in wf.get('nodes', []) + [wf] if isinstance(wf, dict) else []:
    if isinstance(node, dict) and node.get('type') == 'n8n-nodes-base.formTrigger':
        print(node.get('webhookId',''), node.get('parameters',{}).get('path',''))
"
```

### Getting QDRANT_KEY for verification
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "grep QDRANT_API_KEY /opt/javisi/n8n/n8n.env | cut -d= -f2"
```

### If msg2md container fails to build
Check logs:
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker logs javisi_msg2md 2>&1 | tail -30"
```

### If validate_workflow returns errors
Fix the JSON syntax before importing. Common issues:
- `continue` inside `for...of` in async context — verify the loop is `for (const file of files)`
- Escaped characters in the JSON string — double-check backslash escaping

### Checking n8n form webhook URL
Form is accessible at: `https://mayi.ewutelo.cloud/form/<webhookId>`
The webhook ID is visible in the n8n workflow JSON node with type `n8n-nodes-base.formTrigger`.
