# REX Session — mop-ingest-v1 E2E debugging (2026-04-12)

## Objectif

Déboguer le workflow n8n `mop-ingest-v1` jusqu'à l'E2E complet :
formulaire web (PDF upload) → extraction LLM multimodal → chunking → embedding → upsert Qdrant `mop_kb`.

Workflow : `FormTrigger(Intake)` → `Code(Setup KB)` → `Code(Process Files)` → `Form(Done | Done Error)`

Infrastructure : Sese-AI, containers `javisi_n8n`, `javisi_litellm`, `javisi_qdrant`, n8n 2.7.3 en mode filesystem-v2 binary storage.

## Problèmes rencontrés et fixes

### P1 — `headers` construit mais non passé à `http.request` (ROOT CAUSE — 401 Qdrant + LiteLLM)

**Symptôme** : Setup KB échoue avec `"Must provide an API key or an Authorization bearer token"` (Qdrant HTTP 401), malgré que le IIFE `/proc/1/environ` lit bien la clé (`len=24, preview=sk-qd-…` confirmé via `console.log`).

**Cause** : dans la fonction `qdrantReq`, l'objet `headers` était **construit** mais **pas inclus** dans les options passées à `http.request` :

```javascript
// AVANT (cassé) — headers déclarés mais omis
const headers = { 'Content-Type': 'application/json', 'api-key': QDRANT_KEY };
const req = http.request(
  { hostname, port, path, method },   // ← headers absents
  (res) => { ... }
);

// APRÈS (correct)
const req = http.request(
  { hostname, port, path, method, headers },   // ← headers inclus
  (res) => { ... }
);
```

**Portée** : le même bug existait dans **3 workflows** sur la même fonction `httpReq` :
- `mop-ingest-v1` → Setup KB (`qdrantReq`) + Process Files (`httpReq`)
- `mop-search-v1` → Search (`httpReq`)

Tous corrigés dans le même commit `5b0a35b`.

**Leçon** : Node.js `http.request(options, cb)` n'a aucun avertissement si une propriété de l'objet `options` est oubliée — les headers sont silencieusement ignorés. Vérifier systématiquement que l'objet options passé à `http.request` contient bien `headers`.

---

### P2 — `binary[key].data` n'est PAS du base64 en mode filesystem-v2 (ROOT CAUSE — 400 Gemini)

**Symptôme** : après fix P1, nouvelle erreur à la ligne 134 de Process Files :
`INVALID_ARGUMENT: Base64 decoding failed for "filesystem-v2"` (Google Gemini API via LiteLLM).

**Cause** : depuis n8n 1.x, n8n peut stocker les données binaires sur disque plutôt qu'en mémoire (`filesystem-v2` mode). Dans ce mode, `item.binary[key].data` ne contient **pas** les bytes du fichier en base64 — c'est une **référence de stockage** :

```
filesystem-v2:workflows/bnokIWFxoydTRbDH/executions/temp/binary_data/<uuid>
```

Ce string opaque a été envoyé directement à l'API Gemini comme `inline_data.data`, qui a (légitimement) refusé.

**Fix** : utiliser `helpers.getBinaryDataBuffer(itemIndex, binaryKey)` qui résout la référence et retourne un vrai `Buffer` :

```javascript
// AVANT (cassé en filesystem-v2)
const files = Object.entries(binary)
  .filter(([, v]) => v && v.data)
  .map(([key, v]) => ({
    ...
    base64: v.data,   // ← référence filesystem-v2, pas du base64 !
  }));

// APRÈS (correct)
const files = await Promise.all(
  Object.entries(binary)
    .filter(([, v]) => v && v.data)
    .map(async ([key, v]) => {
      const buf = await helpers.getBinaryDataBuffer(0, key);
      return { ..., base64: buf.toString('base64') };
    })
);
```

**Ce pattern est identique** à celui déjà utilisé dans `mop-webhook-render-v1` → nœud Persist. La référence correcte est dans ce fichier.

**Commit** : `49a880b`

**Leçon** : ne jamais supposer que `binary[key].data` contient des bytes exploitables. En filesystem-v2 (défaut en prod depuis n8n 1.x), c'est toujours une référence opaque. `helpers.getBinaryDataBuffer` est l'API unique et stable pour lire les bytes binaires dans un Code node.

---

### P3 — Quota Gemini free-tier épuisé (limit: 0) + OpenRouter 401

**Symptôme** : après fix P2, le binary PDF est correctement envoyé mais LiteLLM retourne 429/404/400 sur tous les backends `mop-ingest` :
- `gemini/gemini-2.5-pro` → 429 `RESOURCE_EXHAUSTED` (`limit: 0` free tier)
- `gemini/gemini-2.0-flash` → 429 identique (même clé, même projet GCP)
- `openrouter/deepseek/deepseek-chat-v3-0324:free` → 401 `User not found` (clé OpenRouter partagée invalide pour ce compte)

**Cause** : la clé `GOOGLE_GEMINI_API_KEY` est associée à un projet GCP dont la free-tier quota est à `limit: 0` (quota journalier et par-minute tous à zéro). L'`OPENROUTER_API_KEY` partagée entre tous les modèles LiteLLM avait un problème d'authentification côté compte OpenRouter.

**Fix** : clé OpenRouter **dédiée** pour les modèles MOP, isolée de l'`OPENROUTER_API_KEY` des autres workflows :

1. Nouveau var `OPENROUTER_MOP_API_KEY` dans `litellm.env.j2` (conditionné sur `openrouter_mop_api_key`)
2. Entrées `mop-ingest` dans `litellm_config.yaml.j2` migrent vers `os.environ/OPENROUTER_MOP_API_KEY`
3. Modèles : `openrouter/google/gemini-2.5-pro` (primary) + `openrouter/google/gemini-2.0-flash-001` (fallback)
4. Secret stocké dans Ansible Vault : `openrouter_mop_api_key`

**Commits** : `5c2ca28` (ajout), `fcc5f13` (correction nom modèle)

**Leçon** : isoler les clés API par "domaine fonctionnel" dans LiteLLM — une clé partagée cassée bloque tous les workflows qui l'utilisent. `os.environ/VAR_NAME` dans `litellm_params.api_key` permet une granularité par modèle.

---

### P4 — Nom de modèle OpenRouter incorrect : `google/gemini-flash-1.5` inexistant

**Symptôme** : après déploiement de la clé dédiée, premier appel `mop-ingest` retourne `404: No endpoints found for google/gemini-flash-1.5`.

**Cause** : j'ai utilisé `google/gemini-flash-1.5` comme ID de fallback, qui n'existe pas sur OpenRouter. Le nom correct est `google/gemini-2.0-flash-001`.

**Diagnostic** : interroger l'API OpenRouter `/api/v1/models` directement avec la nouvelle clé depuis le container n8n :
```bash
docker exec javisi_n8n wget -qO- \
  --header="Authorization: Bearer $OPENROUTER_MOP_KEY" \
  https://openrouter.ai/api/v1/models | python3 -c \
  "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data'] if 'gemini' in m['id']]"
```

Résultat : `google/gemini-2.5-pro`, `google/gemini-2.0-flash-001`, `google/gemini-2.5-flash`, etc.

**Fix** : `google/gemini-flash-1.5` → `google/gemini-2.0-flash-001` (`fcc5f13`)

**Leçon** : toujours vérifier les IDs de modèles OpenRouter via `/api/v1/models` avant de les écrire dans la config — les noms ne suivent pas un schéma prévisible (`gemini-2.0-flash-001` ≠ `gemini/gemini-2.0-flash`).

---

### P5 — `mcp__n8n-docs__validate_workflow` : session expirée (récurrent)

**Symptôme** : appels `validate_workflow` retournent `Session not found or expired` (code -32000) dans ~80% des tentatives de cette session.

**Cause** : le client MCP maintient une session HTTP avec le serveur n8n-docs (port 3001). Les sessions expirent après quelques minutes d'inactivité. Le serveur lui-même est sain (`/health` répond), mais la session cliente est perdue.

**Contournement** : validation structurelle Python3 comme fallback acceptable :
```python
import json
d = json.load(open('scripts/n8n-workflows/mop-ingest-v1.json'))
nodes = {n['name'] for n in d['nodes']}
conns = set(d['connections'].keys())
missing = conns - nodes   # doit être vide
```
Confirme la validité JSON + cohérence des connexions, sans les vérifications sémantiques du MCP.

**À documenter** : le MCP `validate_workflow` est le meilleur outil disponible mais pas fiable sur des sessions longues. Toujours avoir le fallback python3 en tête.

---

### P6 — `ansible-vault encrypt_string` : erreur si plusieurs vault-ids configurés sans `--encrypt-vault-id`

**Symptôme** :
```
[ERROR]: The vault-ids default,default are available to encrypt.
Specify the vault-id to encrypt with --encrypt-vault-id
```

**Cause** : `ansible.cfg` déclare `vault_identity_list = default@.vault_password`. Avec plusieurs identités (même la même listée deux fois), ansible-vault exige d'indiquer explicitement laquelle utiliser pour chiffrer.

**Fix** : ajouter `--encrypt-vault-id default` :
```bash
printf 'valeur' | ansible-vault encrypt_string \
  --encrypt-vault-id default \
  --vault-id default@.vault_password \
  --stdin-name 'ma_variable'
```

**Workflow alternatif** (plus propre pour ajouter une variable) : decrypt → edit → re-encrypt :
```bash
ansible-vault decrypt secrets.yml --vault-id default@.vault_password --output /tmp/dec.yml
echo 'nouvelle_var: "valeur"' >> /tmp/dec.yml
ansible-vault encrypt /tmp/dec.yml --encrypt-vault-id default \
  --vault-id default@.vault_password --output secrets.yml
rm /tmp/dec.yml
```

---

### P7 — `make deploy-role` timeout sur IP publique 137.74.114.167

**Symptôme** : `make deploy-role ROLE=litellm ENV=prod` → `Connection timed out` port 804.

**Cause** : chemin réseau direct vers l'IP publique OVH intermittent (problème réseau waza → OVH, pas lié au VPN).

**Fix** : override `ansible_host` avec l'IP Tailscale :
```bash
ansible-playbook playbooks/stacks/site.yml \
  -e "target_env=prod" \
  -e "ansible_host=100.64.0.14" \
  --tags "litellm"
```

**Leçon** : toujours avoir ce one-liner sous la main. Tailscale (100.64.0.14) est plus fiable que la route publique pour les déploiements depuis waza.

---

## Résultat final

**E2E validé** : formulaire `/form/mop-ingest` → upload `test-noc.pdf` → extraction Gemini 2.5 Pro (OpenRouter) → 1 chunk → embedding → upsert Qdrant.

```
Page résultat : "Indexation terminée — 1 chunks indexés dans mop_kb pour 1 fichier(s)."
Qdrant mop_kb : status=green, points_count=1
```

| Commit | Fix |
|--------|-----|
| `5b0a35b` | Headers manquants dans `http.request` (Setup KB, Process Files, mop-search) |
| `49a880b` | `getBinaryDataBuffer` remplace `v.data` (filesystem-v2 storage reference) |
| `5c2ca28` | Clé OpenRouter dédiée MOP + gemini-2.5-pro via OpenRouter |
| `fcc5f13` | Correction nom modèle `gemini-flash-1.5` → `gemini-2.0-flash-001` |

## Règles à ajouter à TROUBLESHOOTING.md

### n8n Code nodes — Règles critiques (section à créer ou compléter)

**R-BIN-1 — `binary[key].data` n'est PAS du base64 en mode filesystem-v2**

```javascript
// ❌ NE PAS FAIRE
const b64 = item.binary['file'].data;

// ✅ TOUJOURS faire
const buf = await helpers.getBinaryDataBuffer(itemIndex, 'file');
const b64 = buf.toString('base64');
```

**R-HTTP-1 — `http.request` : toujours inclure `headers` dans l'objet options**

```javascript
// ❌ silencieusement cassé
const headers = { Authorization: `Bearer ${key}` };
http.request({ hostname, port, path, method }, cb);

// ✅ correct
http.request({ hostname, port, path, method, headers }, cb);
```

### LiteLLM — Règles (section existante)

**LiteLLM-OR-1 — IDs modèles OpenRouter** : toujours vérifier via `GET /api/v1/models` avant d'écrire dans la config. Pas de schéma standard entre les providers.

**LiteLLM-ISO-1 — Clés API par domaine** : utiliser des variables env distinctes (`OPENROUTER_MOP_API_KEY`, `OPENROUTER_API_KEY`) pour isoler les quotas et éviter qu'une clé cassée bloque plusieurs domaines fonctionnels.
