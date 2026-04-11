# REX Session — MOP Generator E2E debugging (2026-04-11)

## Objectif

Terminer la Wave 3 du projet **MOP Machinery** (Task 3.4) : activer le workflow n8n `mop-generator-v1` et valider un E2E complet (formulaire multi-step → PDF téléchargé) sur Sese-AI, puis committer `scripts/n8n-workflows/mop-generator-v1.json`.

Deux workflows sont déployés et actifs :
- `mop-generator-v1` (CP5gJrn1e2zZbPxh) — Form multi-step Intake → Context → Steps → Aggregate → POST webhook local → Read PDF → Done
- `mop-webhook-render-v1` (Vts5Yid05Qapiwk1) — Webhook → Code (Prepare & Allocate) → HTTP Request (Gotenberg multipart) → Code (Persist) → Respond

Infrastructure : Sese-AI OVH VPS, containers `javisi_n8n`, `javisi_gotenberg`, `javisi_postgresql`, template/output volume `/data/mop/{templates,pdf,index}`.

## Ce qui fonctionne déjà (avant cette session)

**7 PDFs générés avec succès** (`/data/mop/pdf/MOP-2026-0001..0007.pdf`, 23-29 KB chacun), **tous via appel direct au webhook** `/webhook/mop-render` avec payload JSON (bypass du formulaire multi-step). Cela valide :

- Webhook `mop-render` → Code `Prepare & Allocate` (validation + allocate ID + mini-Jinja render)
- HTTP Request Gotenberg multipart (`files` = `index.html` + `mop.css`) → PDF
- Code `Persist` (helpers.getBinaryDataBuffer + fs.writeFileSync + append CSV + cleanup pending)
- Respond to Webhook avec `statusCode` dynamique

**Jamais testé E2E** : le chemin formulaire multi-step (soumission navigateur simulée).

## Problèmes rencontrés

### P1 — Simulateur E2E : protocole de soumission du formulaire mal compris (ROOT CAUSE)

**Symptôme** : STEP1 (Intake) passe, STEP2 (Context) time out à 60s.

**Hypothèse initiale (fausse)** : n8n form multi-step = POST page 1 → `formWaitingUrl` dans la réponse → POST page 2 vers cette URL → …

**Ce qui se passe réellement** (extrait du JS client dans le HTML de `/form-waiting/<execId>`) :

```js
// 1. POST page
fetch(postUrl, { method: 'POST', body: formData })
  .then(async (response) => {
    const json = JSON.parse(await response.text());
    if (json?.formWaitingUrl) {
      formWaitingUrl = json.formWaitingUrl;
      timeoutId = setTimeout(checkExecutionStatus, interval);  // start polling
    }
  });

// 2. Poll until next page is ready (backend has resumed execution)
const checkExecutionStatus = async () => {
  const r = await fetch(`${formWaitingUrl}/n8n-execution-status`);
  const text = (await r.text()).trim();
  if (text === "form-waiting") {
    window.location.replace(formWaitingUrl);  // 3. GET next page HTML
    return;
  }
  interval = Math.round(interval * 1.1);  // exponential backoff
  timeoutId = setTimeout(checkExecutionStatus, interval);
};
```

**Protocole réel** : `POST → poll /n8n-execution-status jusqu'à "form-waiting" → GET la page suivante → POST → poll → …`

Ma simulation chaîne directement les POSTs sans passer par le polling, donc le serveur n'a pas encore "publié" le handler de la page 2 → le POST suivant atterrit sur l'ancien endpoint → la fonction de wait n'existe pas → timeout.

**Cause première** : `responseMode=onReceived` (défaut depuis form v2.2+) — le node form répond dès qu'il a reçu la soumission, **avant** que le nœud suivant soit prêt. C'est pour ça que le polling existe côté client.

**Fix** : réécrire le simulateur avec la boucle de polling (`/tmp/mop-e2e-v3.js`). Pas encore exécuté au moment du REX.

### P2 — Noms de champs HTML vs JSON server-side

**Symptôme** : après avoir corrigé les noms de champs, STEP1 passe mais les données semblent vides dans l'exécution.

**Cause** : n8n form génère des `<input name="field-0">`, `name="field-1">`, etc. (indexés), mais la sortie JSON côté serveur les remappe sur les `fieldLabel` du node (→ `$('Intake').item.json.title` au lieu de `.field-0`). Le client doit **envoyer `field-N`**, le workflow manipule les **labels**.

**Fix** : script v3 utilise `field-0`, `field-1`, `field-2` en POST. Les expressions dans `Aggregate` (`$('Intake').item.json.title`) restent inchangées côté workflow.

**Doc gap** : la recherche préalable (`.planning/research/mop-gotenberg-n8n.md`) couvre le concept multi-step depuis v1.65 mais **pas** ce détail de nommage HTML vs JSON.

### P3 — n8n form multi-step : résilience des `$('NodeName').item.json.xxx` cross-page

**Risque identifié** (non encore déclenché) : le nœud Aggregate référence `$('Intake')`, `$('Context')`, `$('Steps')` — ces expressions ne fonctionnent que si tous les pages vivent dans **la même exécution**. Vérifié empiriquement : l'exécution 11730 avait `lastNodeExecuted=Context` et les pages étaient bien des nœuds de cette exécution unique (pas de re-trigger).

**Conclusion** : n8n form multi-step = **une seule exécution** qui s'interrompt (`waitTill=3000-01-01`) entre les pages. Les `$('X').item.json.y` marchent donc cross-page tant qu'ils sont dans la même exécution.

### P4 — n8n-docs MCP : nom d'outil erroné

**Symptôme** : premier appel `get_node_essentials` → `Unknown tool: get_node_essentials`.

**Cause** : le serveur MCP `n8n-docs` expose `get_node`, pas `get_node_essentials`. J'avais guessé le nom depuis une doc intermédiaire.

**Fix** : `tools/list` pour lister les outils exacts :
```
tools_documentation, search_nodes, get_node, validate_node,
get_template, search_templates, validate_workflow
```

### P5 — n8n-docs MCP : rate limiting post-burst

**Symptôme** : en envoyant 5 appels `get_node` en parallèle, 4/5 retournent `{"error": -32000, "message": "Too many authentication attempts"}`.

**Cause** : le serveur MCP limite le débit d'auth/requêtes par session.

**Fix** : séquentialiser avec `sleep 4` entre appels. Après ~30s de cooldown, les requêtes repassent.

### P6 — n8n-docs MCP : session TTL

**Symptôme** : première tentative d'appel → `Unauthorized` silencieux (code -32001).

**Cause** : session cachée dans `/tmp/n8n-mcp-session` expirée.

**Fix** : réinitialiser la session avec `initialize` + `notifications/initialized`, sauver le nouveau `mcp-session-id`.

```bash
TOK="<bearer token from ~/.claude/mcp.json>"
curl -sD /tmp/hdr.txt -X POST http://localhost:3001/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $TOK" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"claude-cli","version":"1.0"}}}'
SID=$(grep -i mcp-session-id /tmp/hdr.txt | awk '{print $2}' | tr -d '\r')
```

### P7 — Script de test E2E pointé sur `localhost:5678`

**Symptôme** : curl `http://localhost:5678/` → `code=000` (connection refused).

**Cause** : waza (Pi workstation) n'a aucun n8n local. n8n est sur Sese-AI uniquement, **exposé via Caddy** sur `https://mayi.ewutelo.cloud` qui résout via **split DNS Headscale** vers `100.64.0.14` (Tailscale).

**Fix** : pointer le script E2E sur `https://mayi.ewutelo.cloud`. Le trafic passe automatiquement par Tailscale grâce au split DNS (pas besoin de tunnel manuel).

**Vérification** :
```bash
getent hosts mayi.ewutelo.cloud   # → 100.64.0.14 (Tailscale IP)
curl -sI https://mayi.ewutelo.cloud/ | head -1   # → HTTP/2 200
```

### P8 — Port 5678 pas exposé sur Tailscale

**Observation** : `curl http://100.64.0.14:5678/` → connection refused.

**Cause** : n8n est accessible **uniquement** via Caddy (ports 80/443). Le port 5678 est bind sur `127.0.0.1` dans le compose file, pas sur l'interface Tailscale.

**Conséquence** : toute communication vers n8n depuis l'extérieur de Sese-AI doit passer par HTTPS via mayi.ewutelo.cloud, ou via `docker exec javisi_n8n` depuis Sese-AI.

### P9 — Set v3.4 raw mode : bug validateur expressions

**Rappel** (déjà connu, confirmé pendant l'audit) : Set v3.4 en mode `raw` (JSON output) fait buguer le validateur MCP n8n quand il y a des expressions `{{...}}` dans le JSON. Le workflow actuel utilise `mode: manual` avec `assignments` → évite le bug.

### P10 — Research doc incomplet

**Observation** : `.planning/research/mop-gotenberg-n8n.md` couvre le concept multi-step (supported depuis v1.65, `returnBinary` completion) mais **ne couvre pas** :
- Le protocole HTTP réel de soumission (POST → poll → GET → POST)
- Le nommage `field-N` côté HTML vs labels côté JSON
- `responseMode=onReceived` par défaut et ses implications
- La différence entre l'URL `formWaitingUrl` dans la réponse JSON et l'URL physique de la page suivante

**Action de suivi** : mettre à jour ce research doc avec les findings de cette session après run E2E réussi.

## Findings sur le workflow (audit contre doc officielle)

Audit de tous les nodes de `mop-generator-v1.json` contre les docs MCP n8n-docs :

| Node | Configuration | Verdict |
|---|---|---|
| Intake (formTrigger 2.5) | path=mop-generator, 3 champs | ✅ conforme |
| Context (form 2.5 page) | 2 champs (keywords, incident) | ✅ conforme |
| Steps (form 2.5 page) | 1 textarea | ✅ conforme |
| Aggregate (set 3.4) | mode=manual + 6 assignments | ✅ conforme, évite bug raw mode |
| HTTP Request (4.4) | POST webhook local, sendBody+json, onError=continueErrorOutput | ✅ conforme |
| Read PDF (readWriteFile 1.1) | operation=read, fileSelector avec expression, options.dataPropertyName=data | ✅ conforme |
| Done (PDF) (form 2.5 completion) | respondWith=returnBinary, inputDataFieldName=data | ✅ conforme, match Read PDF output |
| Done (Error) (form 2.5 completion) | respondWith=showText, responseText dynamique | ✅ conforme |

Même audit sur `mop-webhook-render-v1.json` : **tous les nodes conformes et validés empiriquement** par les 7 PDFs générés.

## État à la fin de session

- ✅ Root cause du blocage E2E identifiée (P1)
- ✅ Script v3 avec polling rédigé (`/tmp/mop-e2e-v3.js`)
- ✅ Audit complet des 2 workflows contre la doc officielle n8n v2.5/v3.4/v4.4/v1.1
- ⏳ Script v3 pas encore corrigé pour HTTPS + mayi.ewutelo.cloud (prochaine étape)
- ⏳ Run E2E pas encore effectué
- ⏳ Commit de `scripts/n8n-workflows/mop-generator-v1.json` pas encore fait

## Prochaines actions

1. Corriger `/tmp/mop-e2e-v3.js` : HTTPS, host=`mayi.ewutelo.cloud`, propagation des cookies entre POST/GET (si présents)
2. Nettoyer les exécutions bloquées dans la DB (execution 11730 et autres `waiting`)
3. Lancer le run E2E depuis waza vers mayi.ewutelo.cloud
4. Observer : (a) cross-page node refs, (b) push binary vs lien, (c) cookies
5. Commit workflow + push research doc updates + ce REX

---

## Addendum — Session MOP2 (2026-04-11, afternoon) — Bugs découverts post-déploiement

### P11 — `import:workflow` ne met PAS à jour `workflow_history` (ROOT CAUSE des fantômes)

**Symptôme** : après deploy complet (import + wave2 restart), les exécutions tournent encore avec l'**ancien** workflow de 6 nœuds ("Render & Load" code node + "Done (PDF)" form) alors que `workflow_entity.nodes` a bien 8 nœuds.

**Diagnostic** : `n8n export:workflow` lit `workflow_entity.nodes` (le **draft**) et montre la bonne définition. Mais n8n **exécute** depuis `workflow_history[activeVersionId].nodes` — table séparée qui stocke les versions publiées.

**Flux n8n 2.7.3 :**
```
workflow_entity.nodes          = DRAFT (mis à jour par import:workflow)
workflow_history[activeVersionId].nodes = VERSION ACTIVE (ce que n8n charge en mémoire)
activeVersionId               = FK vers la version que n8n lit réellement
```

`import:workflow` → met à jour le draft seulement → `workflow_history` NON mis à jour → n8n continue à exécuter l'ancienne version.

**Fix** : toujours chaîner `publish:workflow --id=<WF_ID>` après `import:workflow`. `publish:workflow` snapshote le draft courant dans un nouvelle entrée `workflow_history` ET met à jour `workflow_entity.activeVersionId`.

**Fix de secours (si publish:workflow ne crée pas de nouvelle entrée)** :
```sql
UPDATE workflow_history
SET nodes = (SELECT nodes FROM workflow_entity WHERE id='<WF_ID>'),
    connections = (SELECT connections FROM workflow_entity WHERE id='<WF_ID>'),
    "updatedAt" = CURRENT_TIMESTAMP(3)
WHERE "versionId" = '<activeVersionId>';
```
Puis `docker restart`.

**Règle** : `import:workflow` SEUL est insuffisant. Le protocol correct est :
```
import:workflow → publish:workflow → restart → vérifier workflow_history node count
```

### P12 — `n8n update:workflow --active=true` est déprécié et insuffisant

La commande avertit : *"Please use: publish:workflow"*. Elle ne crée pas d'entrée `workflow_history` non plus. Utiliser `publish:workflow` exclusivement.

### P13 — `N8N_RESTRICT_FILE_ACCESS_TO` : séparateur est `;` (point-virgule), PAS `:`

**Symptôme** : Read PDF node échoue avec `Access to the file is not allowed. Allowed paths: /home/node/.n8n-files:/data/mop` — le message montre `/data/mop` comme chemin autorisé mais l'accès est quand même refusé.

**Cause** : dans `file-system-helper-functions.js`, la fonction `getAllowedPaths()` utilise `.split(';')` (point-virgule). Notre env var `/home/node/.n8n-files:/data/mop` est parsée comme **un seul chemin invalide** car on a utilisé `:` (deux-points).

**Source** :
```js
const allowedPaths = restrictFileAccessTo
    .split(';')    // ← POINT-VIRGULE obligatoire
    .map((path) => path.trim())
    ...
```

**Fix** :
```
N8N_RESTRICT_FILE_ACCESS_TO=/home/node/.n8n-files;/data/mop
```

**Piège** : n8n affiche les allowed paths dans le message d'erreur en les joignant avec `, ` — si vous voyez `Allowed paths: /home/node/.n8n-files:/data/mop` (un seul élément avec `:`), c'est que le split a échoué.

**Règle** : toujours utiliser `;` pour séparer les chemins dans `N8N_RESTRICT_FILE_ACCESS_TO`.

### P14 — Container recreate nécessaire pour recharger `env_file` (déjà documenté P section Docker)

`docker restart` ne recharge **pas** l'`env_file` dans docker compose. Pour appliquer un changement de `.env` : `docker compose up -d --force-recreate <service>`. Le service n8n redémarre, charge le nouvel env, et ré-enregistre tous les webhooks.

### P15 — Healthz retourne "ok" trop tôt (1s) — webhook pas encore enregistré

Après recreate/restart, `GET /healthz` peut retourner `{"status":"ok"}` avant que le FormTrigger webhook `/form/mop-generator` soit enregistré. Solution : poll `/form/mop-generator` directement (HTML doit contenir "Generate MOP") plutôt que healthz seul. Implémenté dans le script de déploiement mis à jour.

## Lessons transversales

- **Toujours vérifier la doc officielle des nodes AVANT de coder un test E2E** — 2h perdues sur un protocole HTTP inventé là où la doc + lecture du JS client HTML donnait la réponse en 5min.
- **n8n MCP server a ses propres limites** : session TTL, rate limiting, noms d'outils exacts. Cacher la session, séquentialiser les appels, toujours `tools/list` en premier si doute sur les noms.
- **Split DNS Headscale est transparent** : `mayi.ewutelo.cloud` résout en local sur Tailscale → HTTPS direct, pas de tunnel manuel nécessaire.
- **Les ports non-HTTP ne sont pas exposés sur Tailscale** : n8n:5678 bindé sur 127.0.0.1 dans Docker, inaccessible même en VPN. Tout passe par Caddy.
- **Lecture du JS client d'un form n8n** : quand un protocole n'est pas documenté, `curl /form-waiting/X | grep script` donne souvent la spec exacte que le navigateur exécute.
- **Preuve d'existence > spéculation** : découvrir 7 PDFs déjà générés dans `/data/mop/pdf/` change radicalement le diagnostic — la pipeline marche, c'est juste le simulateur navigateur qui est fautif. Toujours vérifier les traces d'exécutions passées avant de diagnostiquer.
- **Multi-step form = une seule exécution** : les `$('NodeName').item.json.xxx` cross-page fonctionnent parce que n8n garde **une exécution unique** qui se met en pause (`waitTill`) entre les pages. Pas besoin d'agrégation explicite.
