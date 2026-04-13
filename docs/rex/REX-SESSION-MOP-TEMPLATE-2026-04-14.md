# REX Session — MOP Template Wizy : cartouche, phases, REX terrain
**Date** : 2026-04-14
**Durée** : ~2h30
**Scope** : `roles/mop-templates/files/` — template GrapeJS + datafields YAML + alignment incidents

---

## Objectifs de session

1. Intégrer mises à jour cartouche (doc_owner, doc_approbateur, doc_verificateur, signataires révision)
2. Corriger référence document : format `OPSSD-03.03.M0.20-P-V1`
3. Restructurer phases 3.1.1–3.1.4 en sous-titres L3 (numérotation TOC correcte)
4. Supprimer italique sur zones texte 1.0–4.0
5. Déplacer REX terrain de section 4 vers s3_content (entre 3.0 et 3.1)
6. Générer `docs/mop-incidents-alignment.yml` (5 familles × 40 incidents × wizy data-fields)

Tous objectifs atteints.

---

## Ce qui a fonctionné

### Approche patch Python via API wizy
- Script Python (`/tmp/patch-wizy-vN.py`) avec cycle `GET /api/html` → modifier HTML/CSS → `POST /api/html`
- Cycle propre, répétable, versionnable — meilleur que UI GrapeJS pour modifications structurelles
- Snapshot local après chaque push : `GET /api/html` → `mop-wizy-template.html` + `mop-wizy-template.css`

### Hiérarchie TOC GrapeJS (résolution numérotation 3.1.1)
- **Problème** : phases à `data-toc-level="2"` donnaient `3.2`, `3.3`... pas `3.1.1`
- **Solution** : créer un bloc L2 parent `3.1 Phases d'intervention` + 4 blocs L3 enfants
- `data-toc-level="3"` sous un L2 donne automatiquement `3.1.1`, `3.1.2`, etc.
- Règle : L1=`X.0`, L2=`X.Y`, L3=`X.Y.Z` — GrapeJS calcule en comptant les blocs du même niveau

### Correction header (data-bind → data-field)
- Header utilisait `data-bind` (attribut natif GrapeJS non injecté par n8n)
- Fix : remplacer `data-bind` par `data-field` + pré-remplir le contenu des spans
- Après fix : `is6i` = span référence, `header_title` = span titre — tous deux injectables

### Position s3_content (REX terrain)
- Div `s3_content` existait déjà entre le titre 3.0 et le bloc L2 3.1
- Injection format attendu : `"Contexte terrain (REX [période]) : [N] incidents [type] — [cause]. TTR moyen : [X] min."`
- Style : `font-style: normal` — sobre, technique, sans emphase

---

## Ce qui a posé problème

### Bug Python `set object is not subscriptable`
```python
# FAUX — set n'est pas subscriptable
', '.join(set(str(d.get('Alarme Lightsoft','—')) for d in fam_incidents)[:5])
# CORRECT
', '.join(list(set(str(d.get('Alarme Lightsoft','—')) for d in fam_incidents))[:5])
```
- Mineur, corrigé immédiatement en session suivante

### Découverte header row XLSX décalée
- Row 1 = titre du fichier (`RÉFÉRENTIEL INCIDENTS OTN/OOB — v1.0`)
- Row 2 = vrais headers — `min_row=2` pour l'index, `min_row=3` pour les données
- Toujours inspecter les premières lignes avant d'assumer `min_row=1`

### Hook R0 gate (Qdrant memory search)
- Hook bloque Write si mention n8n sans `search_memory.py --query "n8n"` préalable
- Normal par design — contournement : exécuter la requête memory puis relancer
- TTL ~15 min — peut être redemandé plusieurs fois en longue session

### Commits subject > 72 chars
- Hook rejet automatique. Solution : reformuler en < 72 chars avant commit
- Bonne pratique : préparer le message avant `git commit`

---

## État final des fichiers

| Fichier | Statut | Contenu |
|---------|--------|---------|
| `roles/mop-templates/files/mop-wizy-template.html` | Commité | Header data-field, L3 phases 3.1.1–3.1.4, s3_content REX |
| `roles/mop-templates/files/mop-wizy-template.css` | Commité | Italic supprimé 7 IDs, CSS phase blocks |
| `roles/mop-templates/files/mop-wizy-datafields.yml` | Commité | Format ref OPSSD, s3_phase1-4 data-fields, s3_content format |
| `docs/mop-incidents-alignment.yml` | À commiter | 5 familles × 40 incidents × wizy data-fields |

---

## Prochaines étapes recommandées

1. **Valider `mop-incidents-alignment.yml`** dans wizy : tester injection d'une famille (ex: SUPERVISION)
2. **Compléter les champs `À compléter`** : dates vigueur/révision, SOPs Phase 2 par famille
3. **Génération en lot n8n** : 1 workflow → 5 appels → 5 PDF MOP (OPSSD-03.03.M0.20 à M0.24)
4. **SOP references** : sheet `SOPs` dans XLSX → à mapper dans `_sops_references` de chaque famille

---

## Commits de session

```
ea1d622 feat(mop): add static context and rex brief zone before phase 1 in fiche mop
(+ 2 commits précédents : italic fix, phase restructure)
```
