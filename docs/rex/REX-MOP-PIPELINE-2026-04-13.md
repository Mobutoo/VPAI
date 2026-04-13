# REX — Pipeline MOP n8n (2026-04-13)

**Contexte**: Première génération réelle d'un MOP via le pipeline n8n (mop-route + mop-generate).  
**Résultat**: Succès — PDF généré pour incident N1 (PORT NNI, CRITIQUE).

---

## Incidents rencontrés

### P1 — Parsing Excel incorrect (header décalé)

**Symptôme**: Les SOPs extraites du xlsx étaient décalées — les catégories tombaient sur la mauvaise colonne.  
**Cause**: `rows[0]` est le titre du tableau (`RÉFÉRENTIEL INCIDENTS OTN/OOB — v1.0`), pas les headers. Les vrais headers sont en `rows[1]`, les données commencent en `rows[2]`.  
**Fix**: Toujours vérifier les 3 premières lignes d'un xlsx avant de parser (`print(rows[:3])`).

### P2 — Session MCP `validate_workflow` expirée (-32000)

**Symptôme**: `mcp__n8n-docs__validate_workflow` retournait `-32000 Session not initialized`.  
**Cause**: La session MCP s'était expirée entre les deux appels.  
**Fix appliqué**: Validation Python structurelle en fallback (vérification connections + IF v2). Fonctionnel mais moins complet que le MCP.  
**Fix définitif**: Si `-32000`, réinitialiser la session MCP via `POST /mcp` initialize avant de retenter.

### P3 — API Key n8n manquante (scope `workflow:list`)

**Symptôme**: `deploy-workflow.sh` retournait HTTP 403 sur le preflight `GET /api/v1/workflows`.  
**Cause**: La clé API `claude-code-deploy` avait les scopes `workflow:read` et `workflow:update` mais pas `workflow:list`.  
**Fix**: Playwright → n8n UI Settings → API → éditer la clé → ajouter `workflow:list`.  
**Règle**: Scopes minimaux requis pour deploy-workflow.sh : `workflow:read`, `workflow:update`, `workflow:list`, `workflow:activate`.

### P4 — PUT /api/v1/workflows → HTTP 400 "additional properties"

**Symptôme**: `deploy-workflow.sh` retournait HTTP 400 avec message "additional properties not allowed".  
**Cause**: Le script envoyait le JSON complet du workflow incluant `id`, `pinData`, `meta`, `versionId`, etc. L'API PUT n'accepte que 5 champs.  
**Fix**: Construire le payload minimal avant d'envoyer :

```python
payload = {
    'name': d['name'],
    'nodes': d['nodes'],
    'connections': d['connections'],
    'settings': d.get('settings', {}),
    'staticData': d.get('staticData'),
}
```

**Impact**: `deploy-workflow.sh` a été mis à jour pour appliquer ce filtrage automatiquement.

### P5 — Playwright bloqué par notification "One click credential setup"

**Symptôme**: Le clic sur un élément de dropdown ne fonctionnait pas — Playwright cliquait dans le vide.  
**Cause**: Une alerte modale n8n ("One click credential setup") flottait par-dessus l'UI et interceptait les événements de clic.  
**Fix**: Cliquer d'abord sur l'alerte pour la dismiss, puis procéder à l'action.  
**Règle générale**: Avant toute interaction Playwright sur l'UI n8n, faire un snapshot pour détecter les modales actives.

---

## Ce qui a bien fonctionné

- **REST API PUT** (R11) : méthode correcte — met à jour `workflow_entity` ET `workflow_history` simultanément. Ne jamais utiliser CLI import seul.
- **Playwright pour l'administration UI** : fiable pour les actions non disponibles via API (gestion des API keys).
- **Gotenberg** : génération PDF sans friction — le nœud "Write PDF" + `mop-dl.ewutelo.cloud` fonctionne bout en bout.
- **Structure PHASE_MAP** : le regroupement SOP → phase dans mop-generate produit un document lisible et structuré.

---

## Consignes pour les prochaines sessions

### C1 — Toujours vérifier les 3 premières lignes avant de parser un xlsx

```python
rows = list(ws.iter_rows(values_only=True))
print(rows[:3])  # titre, header, première donnée
# header = rows[1], data = rows[2:]
```

### C2 — Payload minimal pour PUT /api/v1/workflows

Le script `deploy-workflow.sh` le fait automatiquement depuis cette session. Pour un appel manuel, utiliser uniquement `{name, nodes, connections, settings, staticData}`.

### C3 — Scopes API key n8n pour le pipeline MOP

La clé `claude-code-deploy` dans n8n doit avoir : `workflow:read`, `workflow:update`, `workflow:list`, `workflow:activate`.

### C4 — Ne jamais utiliser `n8n import:workflow` sans `publish:workflow` après

CLI import seul ne met pas à jour `workflow_history`. Toujours préférer REST API PUT (R11). Si CLI obligatoire : `n8n import:workflow` + `n8n publish:workflow --id=<id>` + double restart.

### C5 — mop-route est une matrice agrégée (TYPE, pas sous-type)

La matrice actuelle regroupe par catégorie (SUPERVISION, PORT NNI…) — elle ne distingue pas S1 de S2. Si le MOP doit être précis par sous-type, enrichir MATRIX avec les 40 IDs du xlsx.

### C6 — Snapshot Playwright avant toute interaction UI n8n

Modales actives (notifications, "credential setup") interceptent les clics. Toujours faire `browser_snapshot` avant `browser_click` sur un dropdown ou un formulaire n8n.

### C7 — Structure fichiers MOP

```
scripts/n8n-workflows/
  mop-route.json       # routing incident_type × criticite → SOPs
  mop-generate.json    # génération HTML → Gotenberg → PDF
  mop-get.json         # récupération MOP existant (non testé)

docs/mop/
  EXCEL-EXPLOITATION.md   # analyse xlsx + guide exploitation

docs/rex/
  SESSION-MOP-PIPELINE-2026-04-13.md  # rapport de session
  REX-MOP-PIPELINE-2026-04-13.md      # ce fichier

incidents-otn-oob-v1.xlsx  # source de vérité (à déplacer vers docs/referentiel/)
```

---

## Prochaines étapes recommandées

| Priorité | Action | Effort |
|----------|--------|--------|
| P1 | Clarifier les "5 MOPs" mentionnés — sont-ils les 5 scénarios prioritaires ? | 5 min |
| P2 | Enrichir `mop-route` avec routing par ID incident (40 entrées) | 30 min |
| P3 | Ajouter les étapes détaillées des SOPs dans le PDF (feuille `SOPs` du xlsx) | 1h |
| P4 | Script batch pour générer tous les MOPs CRITIQUE (18 incidents) | 15 min |
| P5 | Stocker `N8N_API_KEY` dans `secrets.yml` (vault) | 10 min |
| P6 | Déplacer `incidents-otn-oob-v1.xlsx` → `docs/referentiel/` + commiter | 5 min |
