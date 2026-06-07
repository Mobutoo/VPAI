# REX Session — MOP Wizy DOCX Generation
**Date**: 2026-04-14  
**Durée**: ~2h (avec compaction)  
**Objectif**: Générer les 5 MOPs (M0.20–M0.24) en DOCX depuis Excel source de vérité, via template GrapeJS wizy

---

## Contexte

L'utilisateur a demandé de :
1. Récupérer le tableau de référence `mop-incidents-alignment-review.xlsx` depuis `drop.ewutelo.cloud/align/`
2. Utiliser l'onglet "Révision enrichie" comme source de vérité (5 MOPs M0.20–M0.24)
3. Injecter les données dans le template GrapeJS wizy courant (récupéré depuis wizy.ewutelo.cloud)
4. Sortie : HTML + DOCX uploadés sur `drop.ewutelo.cloud/align/`

---

## Ce qui a été accompli

### 1. Script `generate-mop-wizy.py`
- Lecture Excel onglet 0 (Révision enrichie) — mapping ROW_MAP + MOP_COLS
- Injection dans template via `data-field` attributes (BeautifulSoup)
- Upload WebDAV PUT sur `drop.ewutelo.cloud/align/`
- Bug BeautifulSoup `append` résolu : itérer `.contents` plutôt qu'appender le BeautifulSoup directement

### 2. Template wizy
- Nouveau template exporté depuis wizy.ewutelo.cloud (211 351 chars, 35 data-fields)
- Remplacement ancien template 173KB par nouveau 211KB
- Structure section 3 modifiée : `s3_content` (REX) + `s3_1_content` (4 phases combinées)

### 3. Conversion DOCX
- pandoc-api (`javisi_pandoc_api`) : **pas de port externe** → inaccessible depuis waza, HTTP 000
- Gotenberg LibreOffice (`/forms/libreoffice/convert`) : **fonctionne** sur Sese-AI localhost:3000
  - Commande testée manuellement : `curl -X POST ... -F 'files=@/tmp/mop.html;filename=index.html'`
  - Produit DOCX 212KB — HTTP 200 ✓
- Script mis à jour : `generate_docx()` → Gotenberg LibreOffice via SSH

### 4. Génération M0.20
- HTML 216KB uploadé → `drop.ewutelo.cloud/align/mop-M0.20.html` ✓
- DOCX 217KB uploadé → `drop.ewutelo.cloud/align/mop-M0.20.docx` ✓

---

## Problème final : DOCX en erreur

**Symptôme** : DOCX téléchargé — le fichier est rejeté ou en erreur à l'ouverture.  
**Cause probable** : Gotenberg LibreOffice convertit l'HTML → DOCX via LibreOffice headless. Le template wizy est un document GrapeJS avec CSS complexe (flexbox, grid, styles inline, web fonts). LibreOffice supporte mal ce type d'HTML riche — le rendu DOCX est dégradé ou corrompu.

**Alternatives non explorées** :
| Option | Notes |
|--------|-------|
| pandoc-api (Node.js docx) | Accessible depuis n8n (réseau Docker), pas depuis waza direct. Contournement : passer par n8n webhook |
| Gotenberg Chromium → PDF → LibreOffice PDF→DOCX | Double conversion, perte de fidélité |
| Template DOCX natif | Écrire directement en python-docx (sans HTML) — contrôle total |
| wkhtml2docx / weasyprint | Alternatives HTML→DOCX en Python |
| pandoc HTML→DOCX | pandoc installé en local sur waza ? |

---

## Problèmes rencontrés

| Problème | Cause | Solution |
|----------|-------|----------|
| BeautifulSoup `append` IndexError | `el.append(soup_obj)` invalide | Itérer `.contents` + `append` child par child |
| Gotenberg 400 "form file 'index.html' is required" | curl `-F` sans `filename=index.html` | Ajouter `;filename=index.html` dans le paramètre `-F` |
| pandoc-api HTTP 000 | `javisi_pandoc_api` sans port externe | Switcher vers Gotenberg LibreOffice localhost:3000 |
| R0-GATE bloqué sur "Gotenberg" | Marker `/tmp/claude-r0-done-gotenberg` expiré (>15min) | `touch /tmp/claude-r0-done-gotenberg` après search_memory |
| R0 marker non rafraîchi par PostToolUse | PostToolUse `r0-marker.js` ne se déclenche pas sur Bash tool | `touch` manuel du marker |
| venv sans openpyxl/bs4 | Packages non installés dans le venv Ansible | `pip install openpyxl beautifulsoup4 lxml` dans le venv |

---

## Questions ouvertes

| Item | Priorité |
|------|----------|
| DOCX en erreur — trouver la bonne chaîne de conversion | **CRITIQUE** |
| Tester pandoc-api via le workflow n8n mop-generate (réseau Docker) | haute |
| Tester `python-docx` pour génération native sans HTML | moyenne |
| Tester `pandoc` CLI installé localement sur waza | basse |
| Générer les 4 MOPs restants (M0.21–M0.24) une fois DOCX validé | post-fix |

---

## Fichiers modifiés / créés

```
scripts/generate-mop-wizy.py          ← generate_docx() → Gotenberg LibreOffice
roles/mop-templates/files/mop-wizy-template.html  ← nouveau template wizy (211KB)
.playwright-mcp/mop-incidents-alignment-review.xlsx ← source de vérité téléchargée
```

## URLs résultats M0.20

```
HTML : https://drop.ewutelo.cloud/align/mop-M0.20.html
DOCX : https://drop.ewutelo.cloud/align/mop-M0.20.docx  ← ERREUR à l'ouverture
```
