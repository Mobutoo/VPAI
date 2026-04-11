# REX — MOP Ingest — Bug n8n Task Runner env isolation — 2026-04-11

## Résumé

Debug session sur l'erreur **"Must provide an API key or an Authorization bearer token [line 41]"**
dans le workflow `mop-ingest-v1` (Setup KB node).

**Statut en fin de session : NON RÉSOLU** — cause racine identifiée, prochaine fix documentée.

---

## Symptôme initial

```
"Must provide an API key or an Authorization bearer token" [line 41]
```

Dans le node **Setup KB** de `mop-ingest-v1`, l'appel Qdrant échoue car `QDRANT_KEY = ''`.

---

## Diagnostic — Cause racine confirmée (3 couches)

### Couche 1 — `$env` vide (bug envProviderState)

`$env.QDRANT_API_KEY` retourne toujours `''` même avec `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.

**Cause** : le Task Runner interne (`N8N_RUNNERS_MODE=internal`) initialise `envProviderState`
à `{ env: {} }` — vide — indépendamment de la config `N8N_BLOCK_ENV_ACCESS_IN_NODE`.

### Couche 2 — `process` non défini dans le VM sandbox

Tentative `process.env.QDRANT_API_KEY` → `ReferenceError: process is not defined [line 8]`.

**Cause** : `vm.runInNewContext()` ne fournit pas `process` comme global dans le sandbox du
task runner.

### Couche 3 — `execSync('printenv KEY')` retourne `''` ← NOUVEAU

Fix implémenté dans cette session :
```javascript
const { execSync } = require('child_process');
function getenv(name) {
  try { return execSync('printenv ' + name, { encoding: 'utf8', shell: '/bin/sh' }).trim(); }
  catch (e) { return ''; }
}
```

**Résultat** : toujours `''`. L'exécution `execSync` renvoie vide sans lever d'exception.

**Cause racine confirmée** : le process n8n Task Runner (PID 25 dans le container,
lancé par n8n comme subprocess) est spawné avec un **environnement filtré**. Les vars
`QDRANT_API_KEY`, `LITELLM_API_KEY`, `MOP_PUBLIC_BASE` **ne sont pas héritées** par le
subprocess task runner.

**Preuve** : `docker exec javisi_n8n cat /proc/1/environ | tr '\0' '\n' | grep QDRANT`
→ retourne `sk-qd-08...` ✅ (PID 1 = n8n main process a bien la var)

Mais dans le Code node, `execSync('printenv QDRANT_API_KEY')` → `''` car le task runner
(PID 25) ne l'a pas dans son propre `process.env`.

### Architecture n8n task runner confirmée

```
PID 1 — node n8n (main)           → process.env complet (QDRANT_API_KEY, LITELLM_API_KEY...)
  └─ PID 25 — @n8n/task-runner    → process.env FILTRÉ (subset limité, sans les custom vars)
       └─ VM sandbox (Code node)   → $env vide, process non défini
            └─ execSync(printenv)  → shell hérite du PID 25 filtré → retourne ''
```

---

## Fixes tentés (tous échoués)

| Fix | Résultat | Raison |
|-----|----------|--------|
| `$env.QDRANT_API_KEY` | `''` | envProviderState bug dans task runner |
| `process.env.QDRANT_API_KEY` | `ReferenceError` | `process` non exposé dans VM sandbox |
| `execSync('printenv QDRANT_API_KEY')` | `''` | Task runner subprocess n'hérite pas des vars custom |

---

## Solution recommandée pour la prochaine session

### Option A — Désactiver le task runner (recommandée)

Modifier `roles/n8n/templates/n8n.env.j2` :

```diff
-N8N_RUNNERS_ENABLED=true
-N8N_RUNNERS_MODE=internal
+N8N_RUNNERS_ENABLED=false
```

Avec `N8N_RUNNERS_ENABLED=false`, les Code nodes s'exécutent dans le **process n8n principal**
où `$env` est correctement peuplé (pas de bug `envProviderState`). Revenir à `$env.QDRANT_API_KEY`
dans les 3 workflows.

Déploiement : `make deploy-role ROLE=n8n ENV=prod`

**Trade-off** : légère régression sécurité (Code nodes dans le main process, pas isolés).
Acceptable car les workflows MOP sont internes.

### Option B — Lire depuis `/proc/1/environ`

```javascript
function getenv(name) {
  try {
    const fs = require('fs');
    const env = require('fs').readFileSync('/proc/1/environ', 'utf8').split('\0');
    const entry = env.find(e => e.startsWith(name + '='));
    return entry ? entry.slice(name.length + 1) : '';
  } catch(e) { return ''; }
}
```

PID 1 (n8n main process) a les vars dans `/proc/1/environ`. Accessible en lecture
par les subprocesses du même user (`node`). Pas besoin de redéployer Ansible.

**Trade-off** : hacky, dépend de l'architecture PID du container. À tester d'abord.

---

## État des workflows en fin de session

| Workflow | ID | Active | Code |
|---|---|---|---|
| mop-ingest-v1 | `bnokIWFxoydTRbDH` | ✅ true | `getenv()` via execSync (non fonctionnel) |
| mop-search-v1 | `Jot7Djz71QAYxbkY` | ✅ true | `getenv()` via execSync (non fonctionnel) |
| mop-webhook-render-v1 | `Vts5Yid05Qapiwk1` | ✅ true | `getenv()` via execSync (non fonctionnel) |

Les 3 workflows sont actifs en DB mais la collecte des clés API est cassée.
L'erreur est passée de `[line 41]` à `[line 46]` (décalage dû au `getenv` helper ajouté)
— confirme que le code a bien changé, mais le problème de fond persiste.

---

## Pièges opérationnels découverts (à ajouter au TROUBLESHOOTING)

### P9 — `docker cp <dir> container:/tmp/<dir>` niche le répertoire si la destination existe

```bash
# ❌ Crée /tmp/wf-import/wf-import/ si /tmp/wf-import/ existe déjà dans le container
docker cp /tmp/wf-import javisi_n8n:/tmp/wf-import

# ✅ Copier fichier par fichier pour écraser
docker cp /tmp/wf-import/foo.json javisi_n8n:/tmp/wf-import/foo.json
```

**Cause** : comportement Docker — si destination existe et est un dossier, la source est
copiée *dans* le dossier (comme `cp -r src dst/`). Après un container restart, le
writable layer persiste → l'ancien `/tmp/wf-import/` est toujours là.

### P10 — JSON workflow sans champ `id` crée une nouvelle ligne à chaque import

Si `id` est absent du JSON, `n8n import:workflow` crée un **nouveau workflow** au lieu
de mettre à jour l'existant. Résultat : doublons inactifs en DB.

**Solution** : toujours ajouter `"id": "<uuid>"` dans le JSON avant commit.
Commande pour vérifier : `python3 -c "import json; wf=json.load(open('wf.json')); print(wf.get('id', 'MISSING'))"`.

### P11 — `update:workflow --active=true` est déprécié → utiliser `publish:workflow`

```bash
# Déprécié (fonctionne encore mais warning)
docker exec javisi_n8n n8n update:workflow --id=XXX --active=true

# Correct
docker exec javisi_n8n n8n publish:workflow --id=XXX
```

---

## Commits de cette session

| Commit | Contenu |
|---|---|
| `b126dab` | fix(n8n): replace process.env/\$env with execSync getenv() in mop workflows |
| `cdce20d` | fix(n8n): add workflow IDs to mop-search-v1 and mop-webhook-render-v1 |

---

## Prochaine session — Checklist

1. **Choisir Option A ou B** (recommandé : A — désactiver task runner)
2. Si Option A :
   - Modifier `roles/n8n/templates/n8n.env.j2` : `N8N_RUNNERS_ENABLED=false`
   - Modifier les 3 workflows : remplacer `getenv('KEY')` par `$env.KEY`
   - `make deploy-role ROLE=n8n ENV=prod`
   - Import + activate + double restart
3. Si Option B :
   - Modifier `getenv()` pour lire `/proc/1/environ` à la place de `execSync(printenv)`
   - Import + activate + restart (sans redeploy Ansible)
   - Tester avec le form Playwright
4. E2E Playwright test final sur `https://mayi.ewutelo.cloud/form/mop-ingest`
5. Nettoyer `/home/mobuone/VPAI/test-mop.pdf` (fichier temporaire)
