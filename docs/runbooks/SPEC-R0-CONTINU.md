# SPEC — R0 Continu : recherche mémoire continue & multi-source

> Statut : **IMPLÉMENTÉ (Phase 1) — 2026-06-03**, hooks dans repo `~/.claude` (branch main).
> Note de design ajoutée à l'implémentation : le ledger distingue `isFresh` (présence, usage
> INJECTOR anti-spam) de `isConsulted` (`result !== 'pending'`, usage ENFORCER hard-block) —
> sinon le `'pending'` posé par l'injector désarmerait le gate deploy. Cf `lib/ledger.js`.
> Auteur : session remote-control 2026-06-03
> Origine : bug marker-writer (regex `\s+` cassée par `\` de continuation) + demande
> « rester à jour REX/doc sur tous les sujets, sur sessions longues avec /clear /compact ».
> Cible : couche de hooks globale `~/.claude/hooks/` (blast radius = **toutes les sessions**).
> Source de vérité opérationnelle : `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` (R0).

---

## 1. Problème

### 1.1 Bugs constatés (corrigés hors-SPEC, déjà shippés)

| # | Fichier | Bug | Fix |
|---|---------|-----|-----|
| F1 | `r0-marker.js:31` | `/search_memory\.py\s+--/` — `\s` ne matche pas le `\` de continuation de ligne → marker jamais écrit sur la commande canonique multi-lignes (celle que `[R0-GATE]` dicte lui-même) → boucle | `[\s\\]+` |
| F2 | `memory-search-start.sh:8` | reset session ne supprimait que le marker global → markers per-topic survivent, acceptés 25 min → **bypass R0 cross-session** | `rm -f /tmp/claude-r0-done*` |
| F3 | `loi-op-enforcer.js:59,82` | messages « 15 min » alors que `R0_MAX_AGE_MS = 25 min` | → « 25 min » |

### 1.2 Défauts de fond (objet de ce SPEC)

1. **Marker global = 1 recherche couvre tous les topics.** Une recherche `caddy` déverrouille R0 pour `n8n`, `litellm`… 25 min, sans jamais les consulter. → Claude agit sur un sujet jamais vérifié.
2. **R0 one-shot, pas continu.** Les topics changent en cours de session ; le bug aussi. Aucun re-déclenchement quand un **nouveau** topic apparaît à mi-session.
3. **Marker découplé du contexte.** Le marker `/tmp` survit à `/clear` et `/compact`, mais le REX en contexte est perdu → la gate croit R0 satisfait alors que Claude a perdu l'info. C'est le « débug interminable » : Claude suppose au lieu de relire le REX.
4. **REX chaud invisible.** Le worker `llamaindex-memory-worker` ingère dans Qdrant en **asynchrone** (timer non actif sur waza → lag possiblement grand). Le REX qu'on vient d'écrire — *celui qui résout le bug courant* — n'est pas encore indexé. `qdrant-find` ne le trouve pas.
5. **Drift de `KNOWN_TOPICS`.** La regex est dupliquée dans 3 hooks (`r0-marker.js`, `loi-op-enforcer.js`, `error-escalator.js`) et a déjà divergé (`form\s*multi` présent dans 1 seul).
6. **Debug = lectures.** La gate ne bloque que Write/Edit + Bash state-modifying. Un debug est surtout des lectures (grep, cat, docker logs) → rien ne force la consultation mémoire au moment précis du debug.

---

## 2. Objectifs / Non-objectifs

### Objectifs
- **G1** Garantie REX **par topic** (pas globale) : chaque sujet abordé a sa propre fraîcheur.
- **G2** R0 **continu** : un nouveau topic à mi-session re-déclenche la consultation.
- **G3** Survie `/clear` + `/compact` : le REX des topics travaillés est **ré-injecté** quand le contexte est perdu.
- **G4** REX **chaud + froid** : consultation 2 sources — Qdrant (froid, indexé) **+** grep disque (chaud, non indexé).
- **G5** **Cascade** : REX → (si vide) doc officielle → (si vide) forums.
- **G6** Déclenchement au **moment du debug** (cascade d'échecs), pas seulement à l'écriture.
- **G7** Source unique de `KNOWN_TOPICS` (fin du drift).

### Non-objectifs (Phase 2+)
- Daemon de recherche chaud HTTP (push REX <1s en PreToolUse). Phase 1 délègue le froid au MCP warm de Claude.
- Réécriture du worker / indexation temps-réel.
- Hybride sparse+dense dans Qdrant (gap réel pour identifiants exacts, REX-59, `javisi_n8n`, `-32000` — tracé mais hors scope).

---

## 3. Architecture

### 3.1 Donnée unique — le ledger

Fichier : `/tmp/claude-r0-ledger.json`

```json
{
  "version": 1,
  "session_started": "2026-06-03T10:00:00Z",
  "topics": {
    "n8n":     { "ts": "2026-06-03T10:04:12Z", "result": "hit",   "source": "qdrant+hot" },
    "caddy":   { "ts": "2026-06-03T10:11:33Z", "result": "empty", "source": "cascade" }
  }
}
```

- `result: "hit"` = REX trouvé ; `"empty"` = rien (cascade déclenchée).
- **Reset uniquement sur `SessionStart:startup`** (vraie nouvelle session). **Préservé** sur `clear` / `compact` / `resume` → la liste des topics travaillés survit au context-loss.
- Remplace : le marker global `/tmp/claude-r0-done` ET les markers per-topic épars. (Markers conservés en parallèle 1 version pour rollback safe, puis retirés.)

### 3.2 Fraîcheur — quand un topic redevient « à consulter »

> **[PARAM-1 — à valider]** Proposition : **fraîcheur = toute la session**, invalidée par *événements* et non par horloge :
> - invalidée pour **tous** les topics sur `/clear` et `/compact` (context-loss) ;
> - invalidée pour **un** topic sur cascade de debug (≥2 échecs, §3.6) ;
> - jamais d'expiration à l'horloge (le TTL 25 min actuel disparaît).
>
> Alternative écartée : TTL horloge (re-search toutes les 25 min) = friction sans gain, le REX ne périme pas en 25 min.

### 3.3 Modules partagés (neufs)

`~/.claude/hooks/lib/known-topics.js`
```js
// Source unique. require()'d par r0-marker, loi-op-enforcer, error-escalator, r0-topic-injector.
module.exports = /(n8n|webhook|gotenberg|caddy|litellm|openclaw|kitsu|nocodb|postgres|qdrant|headscale|tailscale|typebot|firefly|plane|molecule|form\s*multi|ansible|remotion|comfyui|runpod)/i;
```
`~/.claude/hooks/lib/ledger.js` — `read()`, `stampTopic(topic, result, source)`, `isFresh(topic)`, `reset()`, `invalidate(topic)`, `allTopics()`. Tout fail-open (retourne `{}` sur erreur, ne throw jamais).

### 3.4 Grep REX chaud (la source non-indexée)

> **[PARAM-2 — à valider]** Cibles de grep (corpus petit, grep exhaustif acceptable) :
> - `/home/mobuone/VPAI/docs/rex/`, `/home/mobuone/VPAI/docs/runbooks/`, `/home/mobuone/VPAI/docs/audits/`
> - `/home/mobuone/VPAI/.planning/` (REX-*.md, notes)
> - `/home/mobuone/VPAI/docs/TROUBLESHOOTING.md`
>
> Commande : `rg -l -i "<topic>" <dirs>` → top 5 par mtime décroissant (récent = probablement non indexé).
> Pas de fenêtre temporelle dure : on grep tout, on **trie par récence**. Le but est d'attraper le REX fraîchement écrit que Qdrant n'a pas encore.

### 3.5 Hook `r0-topic-injector.js` (neuf — PreToolUse, matcher `Bash|Write|Edit`)

Entrée : `tool_name`, `tool_input.{command,file_path,content}`, `session_type`.
Logique :
1. `isSubagent` (`session_type==='task'`) → exit 0 (les subagents n'ont pas à gérer R0).
2. `haystack = cmd + filePath + content[:500]`. `topics = matchAll(KNOWN_TOPICS, haystack)`.
3. Pour chaque topic **non-frais** dans le ledger (≤ [PARAM-3] : cap **2** topics/appel pour borner le coût) :
   - grep REX chaud (§3.4) → liste de chemins.
   - `stampTopic(topic, 'pending', 'injector')`.
   - accumuler une directive (§3.7).
4. Sortie **non-bloquante** :
```json
{ "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "additionalContext": "<directives cascade + hits grep chaud>"
} }
```
5. Aucune directive → exit 0 silencieux. Toute erreur → exit 0 (fail-open).

> Le froid (qdrant-find) n'est **pas** lancé par le hook (latence) : il est **demandé** à Claude dans la directive (MCP warm, sub-seconde). Le hook ne fait que l'instant (grep) + l'instruction.

### 3.6 Hook `error-escalator.js` (étendu — déclencheur debug)

À la `THRESHOLD`-ième erreur consécutive **sur un cmd matchant un topic** :
- grep REX chaud du topic ;
- injecter directive cascade **forcée** (§3.7, ton « STOP supposer ») ;
- `invalidate(topic)` au ledger → la prochaine action re-consulte ;
- (conserve le reset de compteur anti-boucle existant).
Utilise `lib/known-topics.js` (fin du `KNOWN_TOPICS_L3` divergent).

### 3.7 Directive cascade injectée (texte canonique)

```
[R0-CONTINU] Topic "<X>" non consulté cette session (ou debug en échec).
REX CHAUD (disque, non encore indexé Qdrant) :
  - <path1>
  - <path2>
AVANT d'agir/continuer, dans CET ordre (cascade — ne suppose pas) :
  1. REX froid : mcp__qdrant__qdrant-find query "<X>" (+ lire les REX chauds ci-dessus).
  2. SI vide/insuffisant → doc officielle : context7 (resolve-library-id+get-library-docs)
     ou mcp__n8n-docs__* (get_node/tools_documentation) selon le sujet.
  3. SI toujours vide → forums : WebSearch "<X> <symptôme>".
Cite le chemin/source retenu. Référence LOI R0/R5/R8.
```

> **Addendum T1.3 (2026-07-18, plan `ops/loops/plans/2026-07-17-scoped-retrieval-implementation.md`)** :
> la ligne 1 (`REX froid`) porte désormais, quand le CWD de session est connu
> (`~/work/<wing>/<repo>`, via `lib/cwd-scope.js`, T1.2), des arguments
> suggérés `scope_repo="<repo>" scope_wing="<wing>"` pour l'appel
> `mcp__qdrant__qdrant-find` — consommés par le BOOST de score in-scope
> (T1.1, `mcp_search.py`/`search_memory.py`), no-op tant que
> `MEMORY_SCOPE_BOOST=false` (défaut). CWD hors `~/work/*` → ligne
> strictement identique au texte canonique ci-dessus (non-régression).
> Contrainte de conception : boost additif, jamais un filtre exclusif — les
> résultats hors-scope restent classés et éligibles.

### 3.8 `memory-search-start.sh` (étendu — SessionStart par source)

| `source` | Comportement |
|----------|--------------|
| `startup` | `ledger.reset()` ; search **multi-topic** (tous les topics projet, pas seulement le 1er) ; seed ledger ; injecte résultats. |
| `clear` / `compact` | **pas de reset** ; relit le ledger ; pour chaque topic : grep chaud + (re)search → **ré-injecte le REX** dans le contexte neuf. |
| `resume` | idem clear/compact (contexte neuf). |

> Implémentation : soit `$source`/`$1` lu dans le hook, soit 2 entrées `SessionStart` avec `matcher: "startup"` vs `matcher: "clear|compact|resume"` dans `settings.json` (matcher par source confirmé supporté).

> **Addendum T1.3-bis (2026-07-18, plan `ops/loops/plans/2026-07-17-scoped-retrieval-implementation.md`)** :
> contrairement à `r0-topic-injector.js` (qui ne fait que SUGGÉRER l'appel
> `qdrant-find` au modèle via un nudge textuel), `memory-search-start.sh`
> EXÉCUTE réellement `search_memory.py` (bloc `emit_topic`/`$SEARCH_CMD`) à
> chaque `startup`/`clear`/`compact`/`resume`. Le scope CWD->{repo,wing}
> (`lib/cwd-scope.js`, T1.2 — même source que le hook JS et que
> `memory_core.derive_scope_from_cwd` côté Python) y est donc passé
> **directement en argv CLI** (`--scope-repo`/`--scope-wing`, T1.1), sans
> dépendre de la fidélité d'un modèle à recopier un nudge — mécanisme plus
> robuste que celui de `r0-topic-injector.js` pour ce chemin, puisqu'il n'y a
> aucun modèle dans la boucle. No-op côté `search_memory.py` tant que
> `MEMORY_SCOPE_BOOST=false` (défaut). CWD hors `~/work/*` → invocation
> `SEARCH_CMD` strictement inchangée (non-régression).

### 3.9 `loi-op-enforcer.js` & `r0-marker.js` (adaptés)

- `r0-marker.js` : sur search réelle détectée → `ledger.stampTopic(topic,'hit'|'empty','marker')` au lieu d'écrire les markers per-topic fichiers.
- `loi-op-enforcer.js` : la **R0-GATE bloquante** (deploy state-modifying) lit `ledger.isFresh(topic)` au lieu du marker global. Bloc dur **conservé** pour deploy non-vérifié ; advisories R1–R11 inchangées. Importe `lib/known-topics.js`.

---

## 4. Contrats hooks (récap — champs verbatim confirmés)

| Hook | Event | Sortie | Effet |
|------|-------|--------|-------|
| `r0-topic-injector.js` | PreToolUse | `hookSpecificOutput.permissionDecision:"allow"` + `additionalContext` | inject non-bloquant |
| `loi-op-enforcer.js` (deploy gate) | PreToolUse | `permissionDecision:"deny"` + `permissionDecisionReason` | bloc dur |
| `memory-search-start.sh` | SessionStart | stdout / `additionalContext` | inject au boot + après clear/compact |
| `error-escalator.js` | PostToolUse | stdout | directive debug |

Règle invariante : **tout hook fail-open** (exit 0 sur erreur, jamais de throw non-catché). Un hook cassé ne doit jamais bloquer une session.

---

## 5. Plan de test (avant câblage settings.json)

Chaque hook testé au `node`/`bash` avec JSON d'exemple, **avant** ajout dans `settings.json` :
1. `lib/known-topics.js` : matche `n8n`, `caddy`, `ansible`, `form multi` ; ne matche pas un mot anodin.
2. `lib/ledger.js` : reset/stamp/isFresh/invalidate ; fichier corrompu → `{}` (fail-open).
3. `r0-topic-injector.js` : (a) topic frais → exit 0 silencieux ; (b) topic neuf → additionalContext avec grep hits ; (c) subagent → exit 0 ; (d) JSON invalide → exit 0 ; (e) cap 2 topics respecté.
4. `error-escalator.js` : 2 échecs topic → directive + invalidate ; non-topic → rien.
5. `memory-search-start.sh` : `startup` reset+multi ; `compact` ré-injecte sans reset.
6. Régression : F1/F2/F3 toujours OK.

## 6. Rollout / Rollback

- Commits atomiques par hook (1 hook = 1 commit).
- Markers legacy conservés 1 version (parallèle ledger) → rollback = retirer les 2 entrées `settings.json` neuves, les hooks legacy reprennent.
- Les hooks sont hors repo VPAI (`~/.claude/hooks/`) — versionner via le mécanisme de backup existant (`gsd-user-files-backup/`) ou un commit dédié si ces hooks sont trackés ailleurs. **[PARAM-4 — à valider]** : où committe-t-on les hooks `~/.claude/hooks/` ? (repo dédié ? backup ansible `llamaindex-memory-worker` ?)

## 7. Paramètres — VALIDÉS (2026-06-03)

| Param | Sujet | Décision |
|-------|-------|----------|
| PARAM-1 | Fraîcheur | ✅ session entière, invalidée par événements (clear/compact/debug ≥2 échecs), **pas** d'horloge |
| PARAM-2 | Cibles grep chaud | ✅ docs/rex, docs/runbooks, docs/audits, .planning, TROUBLESHOOTING.md ; tri mtime |
| PARAM-3 | Cap topics/appel PreToolUse | ✅ 2 |
| PARAM-4 | Lieu de commit des hooks | ✅ repo git `~/.claude` (branch `main`, track déjà `hooks/` + `skills/Mobutoo/`) |
| PARAM-5 | Topics ajoutés | ✅ +`remotion`, +`comfyui`, +`runpod` |

---

## 8. Hors-scope tracé (Phase 2)

- Daemon de recherche chaud (push REX <1s).
- Qdrant hybride sparse+dense (rappel identifiants exacts).
- Dé-duplication logique search `search_memory.py` ↔ `mcp_search.py`.
- Forcer le canal doc-officielle en amont (au-delà de la cascade sur REX vide).
