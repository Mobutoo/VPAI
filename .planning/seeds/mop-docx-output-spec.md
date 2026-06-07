# SPEC — Sortie DOCX parallèle pour le workflow MOP
**Date** : 2026-04-13  
**Statut** : DRAFT — en attente finalisation template  
**Scope** : Sese-AI (prod), workflow `mop-generate`

---

## 1. Contexte

Le workflow n8n `mop-generate` produit actuellement un PDF via Gotenberg/Chromium.  
Besoin : sortir **aussi** un DOCX à partir du même HTML, en copie carbone, sans modifier la logique métier.

Gotenberg est **PDF-only** — il ne peut pas produire de DOCX.

---

## 2. Solution retenue : Pandoc HTTP service

**Pandoc** (`pandoc/core`) convertit HTML → DOCX natif sans LibreOffice lourd.  
Wrappé par un microservice Express Node.js exposant une API HTTP simple.

### Pourquoi Pandoc
| Critère | Pandoc | LibreOffice | html-to-docx (npm) |
|---------|--------|-------------|-------------------|
| Taille image | ~70 MB | ~800 MB | ~40 MB (Node) |
| Qualité DOCX | Excellente | Bonne | Moyenne |
| Maintenance | Actif | Actif | Faible |
| API HTTP native | Non (wrapper) | Non (wrapper) | Oui |
| Styles Word natifs | Oui (reference.docx) | Partiel | Non |

Avantage clé : Pandoc supporte un **`reference.docx`** — on peut injecter les styles Telehouse pour que le DOCX soit aux couleurs de la charte dès la sortie.

---

## 3. Architecture

```
n8n (mop-generate)
  │
  ├─ Build HTML (Code node)
  │       │
  │       ├─ [branche A] Convert to PDF
  │       │    POST http://gotenberg:3000/forms/chromium/convert/html
  │       │    → Write PDF
  │       │
  │       └─ [branche B] Convert to DOCX
  │            POST http://pandoc_api:3001/convert/html-to-docx
  │            body: { html, reference_docx: "telehouse" }
  │            → Write DOCX
  │
  └─ Merge (combine) → Respond to Webhook
```

---

## 4. Pandoc API — contrat d'interface

### Endpoint
```
POST /convert/html-to-docx
Content-Type: application/json

{
  "html": "<html>...</html>",
  "reference_docx": "telehouse"   // optionnel
}
```

### Réponse succès
```
200 OK
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="document.docx"
<binary DOCX>
```

### Réponse erreur
```
400 { "error": "html field required" }
500 { "error": "<message pandoc>" }
```

---

## 5. Nouveau rôle Ansible : `pandoc-api`

### Structure
```
roles/pandoc-api/
├── defaults/main.yml
├── tasks/main.yml
├── files/
│   ├── Dockerfile
│   ├── server.js
│   ├── package.json
│   └── reference/
│       └── telehouse.docx     # à créer — styles heading/table Telehouse
└── templates/
    └── docker-compose.yml.j2
```

### `defaults/main.yml`
```yaml
pandoc_api_port: 3001
pandoc_api_docker_dir: "/opt/{{ project_name }}/docker/pandoc-api"
pandoc_api_container_name: "pandoc_api"
pandoc_api_network: "javisi_backend"
```

### Dockerfile
```dockerfile
FROM pandoc/core:3.6
RUN apk add --no-cache nodejs npm
WORKDIR /app
COPY package.json .
RUN npm install --production
COPY server.js .
COPY reference/ ./reference/
CMD ["node", "server.js"]
```

### `server.js`
```javascript
const express  = require('express')
const { execFile } = require('child_process')
const fs   = require('fs')
const path = require('path')
const os   = require('os')

const app = express()
app.use(express.json({ limit: '10mb' }))

app.post('/convert/html-to-docx', (req, res) => {
  const { html, reference_docx } = req.body
  if (!html) return res.status(400).json({ error: 'html field required' })

  const tmpDir  = fs.mkdtempSync(path.join(os.tmpdir(), 'pandoc-'))
  const inFile  = path.join(tmpDir, 'input.html')
  const outFile = path.join(tmpDir, 'output.docx')
  const refFile = reference_docx
    ? path.join(__dirname, 'reference', `${reference_docx}.docx`)
    : null

  fs.writeFileSync(inFile, html)
  const args = ['-f', 'html', '-t', 'docx', '-o', outFile, inFile]
  if (refFile && fs.existsSync(refFile)) args.push('--reference-doc', refFile)

  execFile('pandoc', args, (err) => {
    fs.unlinkSync(inFile)
    if (err) {
      fs.rmSync(tmpDir, { recursive: true })
      return res.status(500).json({ error: err.message })
    }
    res.setHeader('Content-Type',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    res.setHeader('Content-Disposition', 'attachment; filename="document.docx"')
    const stream = fs.createReadStream(outFile)
    stream.pipe(res)
    stream.on('end', () => fs.rmSync(tmpDir, { recursive: true }))
  })
})

app.listen(3001, () => console.log('[pandoc-api] ready on :3001'))
```

---

## 6. Modifications workflow n8n

### Fichier : `scripts/n8n-workflows/mop-generate.json`

3 nœuds ajoutés en branche parallèle après `Build HTML` :

| Nœud | Type | Paramètres clés |
|------|------|-----------------|
| `Convert to DOCX` | `httpRequest` | POST `http://pandoc_api:3001/convert/html-to-docx` · body JSON `{html}` · response `file` → field `docx` |
| `Write DOCX` | `writeBinaryFile` | même répertoire que PDF, extension `.docx` |
| `Merge PDF+DOCX` | `merge` mode `combine` | input 0 = Write PDF · input 1 = Write DOCX |

### Connexions
```
Build HTML ──→ Convert to PDF  → Write PDF  ─┐
           └─→ Convert to DOCX → Write DOCX ─┴─→ Merge → Respond
```

---

## 7. Déploiement

```bash
# 1. Build + déployer pandoc-api
make deploy-role ROLE=pandoc-api ENV=prod

# 2. Déployer workflow modifié
scripts/deploy-workflow.sh mop-generate

# 3. Test smoke
curl -X POST https://mayi.ewutelo.cloud/webhook/mop-generate \
  -H "Content-Type: application/json" \
  -d '{"sop_id":"SOP-01"}' \
  -o test_out.zip
```

---

## 8. Prérequis avant implémentation

- [ ] **Finaliser template Wizy v4** — listes (type, département) + dates dans schema
- [ ] Valider que `Build HTML` ne contient pas d'images base64 >5 MB (pandoc timeout)
- [ ] Créer `telehouse.docx` reference template (heading1/2/3 + tables aux couleurs Telehouse)
- [ ] Confirmer réseau : `pandoc_api` sur `javisi_backend` (même réseau que n8n/gotenberg)
- [ ] Confirmer Caddy n'expose pas le port 3001 publiquement

---

## 9. Hors scope

- Conversion DOCX → PDF (Gotenberg LibreOffice route si besoin)
- Édition post-génération du DOCX
- Signature électronique
