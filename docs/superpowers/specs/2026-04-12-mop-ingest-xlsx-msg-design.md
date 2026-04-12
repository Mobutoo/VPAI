# Design : mop-ingest-v1 — support xlsx et .msg

**Date:** 2026-04-12
**Statut:** Validé par l'utilisateur — révision post-review (B1/B2/B3/I4/I5/I6/I7)
**Scope:** Étendre le nœud Process Files de `mop-ingest-v1` (n8n) pour indexer les fichiers Excel et les emails Outlook MSG dans `mop_kb` (Qdrant).

---

## Contexte

Le workflow `mop-ingest-v1` (id: `bnokIWFxoydTRbDH`) indexe actuellement :
- `.pdf` → Gemini multimodal direct (inline_data)
- `.docx` / `.pptx` → Gotenberg `/forms/libreoffice/convert` → PDF → Gemini

Deux nouveaux formats à supporter :

| Format | Usage NOC | Particularité |
|---|---|---|
| `.xlsx` / `.xls` | Base de connaissances incidents (causes, procédures, criticité) | Tableau 11 colonnes, cellules multi-lignes |
| `.msg` | Échanges incident/résolution avec support constructeur (Ribbon, etc.) | Thread email + captures techniques en pièces jointes |

**Vérifications empiriques effectuées avant spec :**
- `xlsx` → Gotenberg HTTP 200, 261 KB PDF produit ✅
- `.msg` → Gotenberg HTTP 400 (non supporté — absent de la liste LibreOffice) ✅
- `extract-msg==0.55.0` installé sur Sese-AI, extraction réussie de `telehouse.msg` ✅
- LibreOffice 26.2.2.2 dans le container Gotenberg ✅

---

## Architecture cible

```
Process Files (Code node n8n)
  ├─ .pdf               → Gemini multimodal (inline_data)              [existant]
  ├─ .docx / .pptx      → Gotenberg → PDF → Gemini                     [existant]
  ├─ .xlsx / .xls /
  │   .xlsm / .xlsb /
  │   .csv              → Gotenberg → PDF → Gemini                     [nouveau — Composant 1]
  └─ .msg               → msg2md sidecar → markdown + images
                            ├─ markdown → chunker direct (pas de LLM)
                            └─ images   → Gemini (description visuelle)
                            → concaténation → chunker → embed → upsert  [nouveau — Composant 2]
```

---

## Composant 1 : xlsx (et formats tableur)

### Principe

Gotenberg/LibreOffice convertit nativement `.xlsx` → PDF (testé : HTTP 200, 261 KB).
Même fonction `gotenbergConvert()` déjà en place pour docx/pptx. Aucune infrastructure nouvelle.

### Formats couverts

Ajouter dans la branche `gotenbergConvert()` :
- `.xlsx`, `.xls`, `.xlsm`, `.xlsb` — Excel
- `.csv` — CSV (LibreOffice l'accepte)

### MIME_MAP à compléter

```js
xlsx:  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
xls:   'application/vnd.ms-excel',
xlsm:  'application/vnd.ms-excel.sheet.macroEnabled.12',
xlsb:  'application/vnd.ms-excel.sheet.binary.macroEnabled.12',
csv:   'text/csv',
```

### Prompt Gemini dédié xlsx

```
Tu es un expert en systèmes télécom (DWDM, SDH, IP/MPLS). Ce document est
un tableau de base de connaissances NOC converti en PDF. Chaque ligne est
un type d'incident ou une procédure. Les colonnes typiques sont : type de
perte, réseau, descriptif, impact, cause probable, étapes de résolution,
processus de communication, criticité, exemples d'alarmes.

Extrais chaque entrée non-vide en markdown structuré :
- H2 pour chaque type d'incident/perte
- Sous chaque H2 : listes des champs renseignés (Cause, Résolution, Criticité,
  Exemples d'alarmes, etc.)
- Préserve les codes alarme, noms d'équipements, références opérateurs.
- Ignore les lignes entièrement vides.
Retourne UNIQUEMENT le markdown, sans préambule ni commentaire.
```

---

## Composant 2 : msg2md (micro-service)

### Rôle

Service Python qui transforme un fichier `.msg` Outlook en JSON structuré consommable par le nœud n8n. Il fait le travail d'extraction, de nettoyage et de structuration — le texte nettoyé va directement au chunker sans passer par Gemini (évite la double facturation et la perte d'information). Seules les images sont envoyées à Gemini pour description visuelle.

### Déploiement (B1 — Phase B, comme Gotenberg)

msg2md est un sidecar de conversion identique à Gotenberg : il va dans `docker-compose.yml` (Phase B), section `# === MOP MACHINERY ===`, après le bloc Gotenberg.

**Pattern de build : in-place (comme palais-app) — pas de GHCR push (B2)**

Le role Ansible dépose les fichiers de build dans `/opt/{{ project_name }}/msg2md/`.
Le `docker-compose.yml.j2` contient une directive `build:` pointant vers ce contexte.

| Attribut | Valeur |
|---|---|
| Build context | `/opt/{{ project_name }}/msg2md/` (déposé par le role) |
| Réseau Docker | `backend` uniquement |
| Port interne | `3100` |
| Accessible depuis n8n | `http://msg2md:3100` |
| Limites | 256 MB RAM, 0.5 CPU |
| Base image (B3) | `python:3.12.10-slim` — tracké dans `versions.yml` sous `msg2md_python_base` |
| Dépendances Python | `extract-msg==0.55.0`, `fastapi`, `uvicorn` (pinnées dans requirements.txt) |

### Définition Docker complète (I6)

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
    - MSG2MD_PORT=3100   # lu au runtime par app.py via os.environ.get("MSG2MD_PORT", 3100)
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3100/health"]
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
        memory: 256M
        cpus: "0.5"
```

### Endpoint

```
POST /convert
Content-Type: multipart/form-data
Champ : file — binaire du .msg

GET /health → {"status": "ok"}
```

Réponse JSON :

```json
{
  "markdown": "# SR#260319-949395 — ...\n**Sévérité:** Minor\n...",
  "images": [
    { "filename": "image001.jpg", "mimeType": "image/jpeg", "base64": "..." }
  ]
}
```

### Logique de nettoyage et structuration

Le service applique dans l'ordre :

**1. Extraction des métadonnées**
- Subject → extraction SR number (`SR#\d{6}-\d{6}` — pattern Ribbon/Salesforce, S8 : à compléter pour Cisco/Nokia/Ciena), sévérité, équipementier, titre alarme
- From / To / Cc / Date

**2. Identification des parties prenantes**
- Domaine `@fr.telehouse.net` → NOC interne
- Autre domaine → Support constructeur (label = nom de domaine de l'entreprise)
- Adresses Salesforce CRM (pattern `*.apex.salesforce.com`) → ignorées

**3. Découpage du thread**
- Délimiteur Outlook : bloc `From: ... Sent: ... To: ... Subject: ...`
- Thread reconstitué en ordre chronologique (le plus ancien d'abord)
- Chaque email labellisé : date + rôle expéditeur (NOC / Constructeur)

**4. Nettoyage du body**

Suppressions :
- Bandeaux CAUTION/disclaimer (`CAUTION: This email originated from outside...`)
- Signatures : blocs téléphone/adresse/logo après la conclusion (`Thank you`, `Regards`, `Cordialement`)
- Lignes `*\t` isolées (artefacts RTF des puces Outlook)
- Références images Outlook inline dans le texte
- URLs de tracking Salesforce

**5. Balisage des alarmes**

Regex : `/(MAJOR|MINOR|CRITICAL|WARNING)\s+([\w\-]+(?::[\w\/\.]+)?)\s+(.+)/`
→ Chaque alarme détectée formatée en bloc code :
```
`MAJOR TH3-OP9608-VHB-08:ge-ua/0.14680328 No OSPF hello packets received`
```

**6. Filtrage des pièces jointes**

- Images (jpg, jpeg, png, gif) ≥ 5 Ko → incluses dans `images[]` en base64
- Images < 5 Ko → ignorées (logos, pixels tracking)
- Autres types (PDF, TXT, etc.) → ignorés et loggués (non récursif) — décision documentée : les pièces jointes non-image sont hors scope v1
- `.msg` imbriqués (email-dans-email) → ignorés, non récursifs

**7. Cas limites (I7)**

| Cas | Comportement |
|---|---|
| Body vide, images seulement | Produit markdown avec headers + section "Pièces jointes" uniquement — pipeline continue |
| `.msg` sans pièces jointes | `images: []` — pipeline continue normalement |
| `.msg` imbriqué en pièce jointe | Ignoré, loggué comme `skipped_attachment` |
| Pièce jointe PDF/TXT | Ignorée, loggée comme `skipped_attachment` |

### Format markdown produit par msg2md

```markdown
# SR#260319-949395 — No OSPF hello packets received from neighbor

**Sévérité ticket:** Minor | **Équipementier:** Ribbon | **Date:** 2026-03-24

## Parties prenantes
- **NOC Telehouse** (Magny): operations.magny@fr.telehouse.net
- **Support Ribbon L2 India**: Riddhi Patil <ripatil@rbbn.com>
- CC: Paris OTN NOC, Erwin Mombili, Hassan Bellahcen, Ribbon France Support

## [2026-03-19 21:32] NOC Telehouse → Support Ribbon
**Alarmes signalées:**
- `MAJOR TH3-OP9608-VHB-08:ge-ua/0.14680328 No OSPF hello packets received`

[corps nettoyé]

## [2026-03-24 01:20] Support Ribbon → NOC Telehouse
[corps nettoyé de la réponse avec analyse root cause]

## Pièces jointes techniques (captures)
- image001.jpg (102 KB)
- image.png (121 KB)
```

---

## Composant 3 : nœud n8n — branche .msg (pipeline splitté, I4)

Le pipeline .msg est différent des autres formats : le texte ne passe PAS par Gemini (msg2md produit déjà un markdown structuré de qualité). Seules les images passent par Gemini pour description visuelle. Les deux sont concaténés avant le chunker.

### Flux d'exécution

```
1. Détecter ext === 'msg'
2. POST binaire → http://msg2md:3100/convert  (HTTP 200 sinon throw)
3. Récupérer { markdown, images }

4a. Si images.length > 0 :
    → Appel Gemini multimodal (INGEST_PROMPTS.msg_images) avec les images
    → Obtenir imageDescriptions (markdown des captures)
    → fullMarkdown = markdown + "\n\n## Descriptions visuelles\n" + imageDescriptions

4b. Si images.length === 0 :
    → fullMarkdown = markdown

5. Chunk fullMarkdown → embed → delete old → upsert mop_kb
   (pipeline identique aux autres formats)
```

### Prompt Gemini dédié images .msg (INGEST_PROMPTS.msg_images)

```
Tu es un expert en systèmes télécom (DWDM, SDH, IP/MPLS, Ribbon). Ces captures
d'écran proviennent d'un échange de support technique NOC. Décris chaque image
en markdown structuré :
- Ce que l'interface affiche (type d'outil : NMS, CLI, alarme, PM counters, etc.)
- Les éléments techniques visibles : nœuds, ports, valeurs PM, états d'alarmes,
  commandes CLI et leur output, timestamps
- Toute valeur numérique ou code d'alarme lisible

Format : une section H3 par image, titrée "Capture N".
Retourne UNIQUEMENT le markdown, sans préambule ni commentaire.
```

---

## Composant 4 : Ansible — role msg2md (I5/S10)

### Structure du role

```
roles/msg2md/
  meta/main.yml          — galaxy_info, dependencies: []
  defaults/main.yml      — msg2md_port: 3100, msg2md_python_base (ref versions.yml)
  tasks/main.yml         — créer /opt/{{ project_name }}/msg2md/, copier Dockerfile + requirements.txt,
                           template app.py.j2 (rendu avec msg2md_port), signal handler
  handlers/main.yml      — restart msg2md (docker compose up -d --build msg2md)
  files/
    Dockerfile           — FROM python:3.12.10-slim, COPY requirements.txt, pip install, COPY app.py
    requirements.txt     — extract-msg==0.55.0, fastapi==0.115.x, uvicorn==0.34.x
  templates/
    app.py.j2            — FastAPI /convert + /health (variable Jinja2 : {{ msg2md_port }})
```

**Variables rendues dans `app.py.j2` :** `{{ msg2md_port }}` uniquement (constante PORT dans uvicorn). Les autres paramètres (seuil image 5KB, regex SR, etc.) sont des constantes Python hardcodées dans le template.

### Intégration `docker-compose.yml.j2`

Ajout après le bloc `gotenberg:`, dans la section `# === MOP MACHINERY ===` :

```jinja2
  msg2md:
    build:
      context: /opt/{{ project_name }}/msg2md
      dockerfile: Dockerfile
    container_name: "{{ project_name }}_msg2md"
    restart: unless-stopped
    ...
```

### Entry dans `versions.yml` (B3)

```yaml
msg2md_python_base: "python:3.12.10-slim"
```

### Tags Ansible

```yaml
tags: [msg2md, phase3]
```

---

## Ordre de livraison (S9 — commandes corrigées)

| Étape | Livrable | Commande |
|---|---|---|
| 1 | Role `msg2md` (Dockerfile, app.py, tasks) + entry `versions.yml` | — commit |
| 2 | Deploy role + build image sur Sese-AI | `make deploy-role ROLE=msg2md ENV=prod` |
| 3 | Rebuild docker-compose avec nouveau service | `make deploy-role ROLE=docker-stack ENV=prod` |
| 4 | Test isolation msg2md | `curl -X POST http://100.64.0.14:3100/convert -F file=@telehouse.msg` (depuis Waza via Tailscale) |
| 5 | Mise à jour `mop-ingest-v1.json` | éditer `scripts/n8n-workflows/mop-ingest-v1.json` |
| 6 | Valider workflow | `mcp__n8n-docs__validate_workflow` |
| 7 | Import + double restart n8n | CLI + `docker restart javisi_n8n` x2 |
| 8 | Test E2E formulaire | soumettre `incidents.xlsx` + `telehouse.msg` |

---

## Contraintes LOI OP (rappel)

- **R1** : `validate_workflow` (étape 6) avant tout import n8n
- **R3** : éditer `scripts/n8n-workflows/mop-ingest-v1.json` → commit → import CLI
- **R4** : tester msg2md en isolation (étape 4) avant intégration n8n
- **R7** : SSH/SCP via `100.64.0.14` uniquement (Tailscale)
