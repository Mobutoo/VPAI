# SPEC — Topics portables cross-projet : base globale agnostique + auto-dérivation

> Statut : **DESIGN — en revue** (2026-06-08)
> Étend : `docs/superpowers/specs/2026-06-04-loi-system-bricks-design.md` (P1–P5 shippés)
> Cible : couche hooks globale `~/.claude/hooks/` (blast radius = TOUTES les sessions, tous projets)
> Origine : demande utilisateur — « les hooks/LOI doivent s'appliquer à toutes sessions, tous projets ; Claude doit vérifier les sujets dans Qdrant ; on a restructuré pour le rendre cross-projet ».
> Source de vérité opérationnelle : `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md`

---

## 1. Constat — le verrou résiduel après P1–P5

P1–P5 ont rendu **portable** : la recherche mémoire au SessionStart (`sources.detect` + grep multi-repo), le split CORE/BINDING, Mobutoo. Mais un verrou subsiste dans le chemin **PreToolUse** (le gate R0 lui-même).

**Preuves (2026-06-08)** :

| Test | Commande | Résultat |
|---|---|---|
| Activation cross-projet | `ansible-playbook deploy-n8n.yml`, `cwd=/tmp` | **R0-GATE exit 2** ✅ — les hooks tirent partout, déclenchés sur le CONTENU, jamais sur le cwd |
| Vocab VPAI hors VPAI | topic `n8n`, `cwd=flash-studio` | **BLOQUE** ✅ |
| Topic propre au projet | `stripe nextjs prisma`, `cwd=flash-studio` | **exit 0, aucun gate** ❌ |

**Cause racine** : `lib/known-topics.js` n'est pas un vocabulaire de topics — c'est **l'inventaire des services déployés de VPAI** :

```
n8n|webhook|gotenberg|caddy|litellm|openclaw|kitsu|nocodb|postgres|qdrant|
headscale|tailscale|typebot|firefly|plane|molecule|form-multi|ansible|remotion|comfyui|runpod
```

Manquent des topics tech légitimes et universels : `docker`, `redis`, `kubernetes`, `terraform`, `stripe`, `nextjs`, `react`, `python`, `fastapi`, … L'enforcer + l'injector reconnaissent **uniquement** ce regex statique ; ils ne lisent pas `binding.topics`. Donc R0 ne tire sur les topics *propres* à un autre repo que s'ils coïncident par hasard avec la stack VPAI.

**Recadrage (utilisateur)** : un topic est un topic, peu importe le projet. Comme `memory_v2` est **cross-repo** (23 692 pts multi-repo), interroger Qdrant sur `docker` ou `runpod` est valide partout. Le défaut n'est donc PAS « il faut des bindings par projet » — c'est que la **liste globale est incomplète** et que le **gate pointe vers la mémoire VPAI** au lieu du canal cross-repo.

**N1 ne peut pas être le moteur d'auto-dérivation** : `memory-search-start.sh:28` fait `kt.allTopics(REX)` → il n'extrait que des termes **déjà dans l'allowlist** (circulaire ; ne découvrira jamais `stripe`). Il faut une vraie source d'extraction.

---

## 2. Objectifs / Non-objectifs

### Objectifs
- **G7** Vocabulaire de topics **global, tech-agnostique, complet** (fin de l'inventaire-services-VPAI).
- **G8** Auto-dérivation du **long-tail jargon** par projet, depuis des signaux déterministes (manifests deps, rôles, services compose, noms de fichiers REX), cachée par session, unionnée dans les hooks per-call.
- **G9** R0-GATE par défaut → `mcp__qdrant__qdrant-find` (cross-repo). Le `MEMORY_CMD` du binding devient un override *optionnel* (chemin local plus rapide), pas le canal primaire.

### Non-objectifs
- **N4** `binding.topics` **obligatoire** par projet → rejeté. Il reste du sucre **optionnel** (jargon vraiment propre à un repo, non dérivable).
- **N5** Extraction NLP/LLM de topics → non. **Déterministe uniquement** (manifests + dirs + filenames).
- **N6** Détection « large » (tout state-modifying = topic) → écartée (friction maximale ; cf option rejetée).
- Réécriture du worker mémoire / indexation temps réel (déjà hors-scope spec 2026-06-04).

---

## 3. Invariants (hérités spec 2026-06-04 §8)

- **Fail-open absolu** : tout hook exit 0 sur erreur, jamais de throw non-catché. Extraction illisible/corrompue → dynamique vide → **base seule** (= comportement actuel).
- **VPAI byte-identique** : la base globale est un **SUR-ENSEMBLE** des 21 termes actuels (on n'en retire aucun). VPAI inchangé pour l'utilisateur. Locké par test de régression.
- **1 hook = 1 commit**, branche `main` repo `~/.claude`. Spec + plan dans VPAI.
- **Gate = `exit(2)` + stderr** (jamais `permissionDecision:deny`), cohérent avec R0/R1/R2/R7 existants.
- **Linchpin vérifié OK** : un `qdrant-find` **vide** → `r0-marker.js` stampe le ledger `result='searched'` → `isConsulted=true` → le gate clôt. Donc « armé partout » ne crée **jamais** de blocage permanent sur un topic que Qdrant ignore (coût = un search par topic par fenêtre `DECAY_N`).

---

## 4. Phase 6a — base globale enrichie + Qdrant par défaut

> Shippe et se valide **seule**. Faible risque (additif). Couvre ~90 % du besoin « vérifier les sujets dans Qdrant ».

### 6a.1 — Enrichir `lib/known-topics.js` (base globale)

`KNOWN_TOPICS` devient une base **tech-agnostique**, sur-ensemble de l'actuel. Catégories proposées (curées : *un topic = un système/outil/service avec du REX accumulé potentiel, pas un verbe générique*) :

| Catégorie | Termes ajoutés (exemples) |
|---|---|
| Conteneurs/orchestration | `docker`, `compose`, `kubernetes`, `k8s`, `helm`, `podman` |
| Data/cache | `redis`, `mysql`, `mariadb`, `mongodb`, `sqlite`, `elasticsearch`, `clickhouse` |
| Web frameworks | `nextjs`, `react`, `vue`, `svelte`, `astro`, `vite`, `fastapi`, `django`, `flask`, `express`, `nestjs` |
| Langages/runtimes | `python`, `node`, `golang`, `rust`, `deno`, `bun` |
| Infra/IaC | `terraform`, `nginx`, `traefik`, `vault`, `consul`, `prometheus`, `grafana`, `loki` |
| Paiement/SaaS | `stripe`, `paddle`, `supabase`, `clerk`, `auth0` |
| ORM/data-access | `prisma`, `drizzle`, `sqlalchemy`, `typeorm` |
| Existants VPAI | *(les 21 actuels — conservés tels quels)* |

> **Garde-fou bruit** : exclure les verbes/termes ultra-génériques qui matcheraient en permanence sans valeur mémoire (`git`, `make`, `curl`, `ssh`, `bash`). Le coût d'un faux-positif reste borné (gate clôt sur search vide), mais on évite le nag inutile. La liste exacte est tranchée à l'implémentation ; principe directeur ci-dessus.

### 6a.2 — R0-GATE par défaut → `qdrant-find` (G9)

Le message de blocage R0-GATE de `loi-op-enforcer.js` (actuellement chemin `search_memory.py` codé en dur VPAI) devient **agnostique** :

```
[R0-GATE] BLOQUÉ — topic "<topic>" détecté, mémoire non consultée cette session.
Vérifier d'abord (cross-repo) :
  mcp__qdrant__qdrant-find  query: "<topic>"
(Optionnel, chemin local plus rapide si défini : <binding.MEMORY_CMD>)
Puis relancer.
```

- Défaut = `qdrant-find` (cross-repo, satisfait par `r0-marker.js`).
- SI `sources.detect(cwd)` résout un binding avec `MEMORY_CMD` → l'ajouter en option (ne remplace pas le défaut).
- Hors projet bindé → `qdrant-find` seul. Plus de référence VPAI hors VPAI.

### 6a.3 — Tests 6a (harness existant)
1. `known-topics` : `docker`, `stripe`, `nextjs` → `hasTopic` true ; les 21 VPAI toujours true (régression) ; `git`/`curl` → false (anti-bruit).
2. `enforcer` : `cwd=/x`, Write touchant `stripe` + pas de search → **BLOQUE** ; message cite `qdrant-find` et **pas** `/opt/workstation` (sauf si cwd=VPAI).
3. Régression : `test-enforcer-gates.js` (R0/R1/R2/R7) + toutes suites P1–P5 → **vertes** ; VPAI `n8n`/`ansible` bloquent toujours.

---

## 5. Phase 6b — auto-dérivation du long-tail (G8)

> Shippe après 6a validée. Complexité moyenne, isolée dans un lib testable + un cache.

### 5.1 — Modèle de données : cache de topics de session

`/tmp/claude-session-topics.json` (seam env `R0_SESSION_TOPICS_PATH` pour les tests) :

```json
{ "version": 1, "ts": "...", "roots": {
  "/home/mobuone/work/saas/flash-studio": ["stripe","nextjs","prisma","tailwind"],
  "/home/mobuone/work/infra/VPAI": ["caddy","comfyui","carbone","..."]
} }
```

- Clé par **root** (`sources.detect(cwd).root`) : une session peut traverser plusieurs projets ; on n'unionne pas aveuglément.
- Fail-open : fichier absent/corrompu → `{}` → **base seule**.

### 5.2 — Extracteur : `lib/topic-extract.js` (neuf, déterministe)

`extract(root) -> string[]`. Scanne le `root` (profondeur ≤ 2, timeouts, jamais de récursion non-bornée) :

| Source | Extraction |
|---|---|
| `package.json` | clés de `dependencies` + `devDependencies` |
| `requirements.txt` / `pyproject.toml` | noms de paquets |
| `go.mod` / `Cargo.toml` / `composer.json` | noms de modules/paquets |
| `roles/*/` (Ansible) | noms de répertoires de rôles |
| `docker-compose*.yml` / `compose*.yml` | noms de services |
| `docs/rex/REX-<topic>-*.md` | token `<topic>` du nom de fichier |

Pipeline : union → `normalize` (lowercase, strip scope `@org/`, strip versions) → **STOPLIST** → **cap N** (défaut 30) → tri par fréquence d'apparition.

**STOPLIST** (outillage/build, pas des topics) : `eslint`, `prettier`, `typescript`, `vitest`, `jest`, `mocha`, `husky`, `lint-staged`, `@types/*`, `ts-node`, `nodemon`, `webpack`, `babel`, `rollup`, `esbuild`, `dotenv`, `chalk`, `lodash`, … (liste exacte à l'implémentation).

### 5.3 — Production du cache : au SessionStart

`memory-search-start.sh` (déjà au SessionStart, appelle déjà `sources.detect`) invoque `topic-extract.js` sur le root détecté et écrit la clé du cache. **Remplace le seed N1 circulaire** par cette extraction réelle (N1 `kt.allTopics(REX)` supprimé comme moteur de découverte ; le grep chaud N2 reste inchangé).

> Garde-fou : extraction bornée (timeout total ≤ 3 s, fail-open). flash-studio sans manifest racine → extrait vide → base seule (dégradation propre, déjà le cas aujourd'hui).

### 5.4 — Consommation : `known-topics.js` devient cwd-aware

API étendue (rétro-compatible) :

```js
// base statique inchangée (sur-ensemble VPAI)
KNOWN_TOPICS                      // RegExp — base globale
regexFor(cwd)                     // RegExp = base ∪ cache[detect(cwd).root]  (fail-open → base)
hasTopic(haystack, cwd)           // cwd optionnel → base si absent
firstTopic(haystack, cwd)
allTopics(haystack, cwd)
```

Les 4 appelants passent `data.cwd` :

| Hook | Usage actuel | Après |
|---|---|---|
| `loi-op-enforcer.js` | `_kt.KNOWN_TOPICS` (statique) | `_kt.regexFor(data.cwd)` |
| `r0-topic-injector.js` | `_kt.allTopics(h)` | `_kt.allTopics(h, data.cwd)` |
| `r0-marker.js` | `_kt.allTopics(h)` | `_kt.allTopics(h, data.cwd)` |
| `error-escalator.js` | `_kt.firstTopic(h)` | `_kt.firstTopic(h, data.cwd)` |

> Rétro-compat : `cwd` absent → base seule (= comportement P1–P5). Aucun appelant ne casse si non migré.

### 5.5 — Tests 6b
1. `topic-extract` : `package.json` deps → extraits ; STOPLIST appliquée (`eslint` absent) ; scope `@scope/x`→`x` ; cap respecté ; manifest absent → `[]` ; JSON corrompu → `[]`.
2. `topic-extract` Ansible : `roles/*/` → noms de rôles ; compose → services.
3. `known-topics` cwd-aware : cache contient `stripe` pour root flash-studio → `regexFor('/…/flash-studio/x')` matche `stripe` ; cwd inconnu → base seule ; cache absent → base seule.
4. `enforcer` E2E : cache seedé d'un topic **hors-base** (ex. `flashpay` — PAS `supabase-x` : `supabase` est en base, le tiret est une frontière de mot → matcherait cwd-blind) pour flash-studio → Write le touchant depuis ce root → **BLOQUE** ; depuis `cwd=VPAI` (pas au cache VPAI, pas en base) → **PAS de match** (preuve que le dynamique est bien scopé au root). NB : un topic de la **base globale** (ex. `stripe`) matche PARTOUT, VPAI inclus — c'est voulu (cf §8 décision M1).
5. Régression complète P1–P5 + 6a → vertes ; VPAI byte-identique.

---

## 6. Inventaire hooks (neufs / modifiés)

| Hook/fichier | État | Phase | Changement |
|---|---|---|---|
| `lib/known-topics.js` | modifié | 6a+6b | base enrichie (6a) ; `regexFor(cwd)` + cwd-aware API + lecture cache (6b) |
| `loi-op-enforcer.js` | modifié | 6a+6b | message R0-GATE → `qdrant-find` défaut + binding option (6a) ; `regexFor(data.cwd)` (6b) |
| `lib/topic-extract.js` | **neuf** | 6b | extracteur déterministe manifests/roles/compose/filenames |
| `memory-search-start.sh` | modifié | 6b | invoque `topic-extract` → écrit cache ; retire le seed N1 circulaire |
| `r0-topic-injector.js` | modifié | 6b | `allTopics(h, data.cwd)` |
| `r0-marker.js` | modifié | 6b | `allTopics(h, data.cwd)` |
| `error-escalator.js` | modifié | 6b | `firstTopic(h, data.cwd)` |

**Câblage `settings.json`** : aucune entrée neuve (tous ces hooks sont déjà câblés). 6a/6b sont des modifications internes.

---

## 7. Rollout / Rollback

- **Phasage strict** : 6a ship + valide seule (enrichissement base + qdrant défaut) AVANT 6b. Chaque phase rollback-able indépendamment (git revert des commits de la phase → hooks reprennent l'état précédent).
- **6a d'abord** car valeur immédiate (docker/stripe/nextjs déclenchent R0 partout) et risque bas.
- **6b** isolé dans `topic-extract.js` + cache : si l'extraction déraille, fail-open → base 6a (déjà bonne). Le cache `/tmp` se régénère au SessionStart suivant.
- Commits atomiques 1 fichier = 1 commit, repo `~/.claude` branche `main`. Spec + plan committés dans VPAI (`git@github-seko`).

## 8. Décisions tranchées (revue interne + revue Codex 2026-06-08)
- Topic = global tech-agnostique, PAS inventaire VPAI (G7).
- `binding.topics` reste **optionnel** (sucre jargon), pas le mécanisme (N4).
- Auto-dérivation **déterministe** depuis manifests/roles/compose/filenames (N5), cachée par root.
- R0-GATE défaut = `qdrant-find` cross-repo ; `MEMORY_CMD` binding = override **différé** (Low : `sources.detect` ne rend pas le binding aujourd'hui — un lecteur `.loi-binding.yml` viendra plus tard, cf §9).
- Base = sur-ensemble strict des 21 termes VPAI → régression byte-identique lockée par test.

### Contrats verrouillés post-revue Codex
- **M1 — base autoritaire partout.** Un topic de la base globale matche dans TOUS les projets, VPAI inclus (toucher `stripe` dans VPAI déclenche bien R0 — cohérent avec « vérifier les sujets dans Qdrant »). Le dynamique n'ajoute QUE des termes **hors-base** propres à un repo. Les tests du chemin dynamique utilisent des termes hors-base **vraiment discriminants** (`flashpay` — surtout pas `supabase-x`, car `supabase` est en base et le `-` est une frontière de mot → matcherait sans cwd, prouvant rien), jamais un terme de base.
- **M2 — multi-root réel (lazy).** Le cache n'est pas seulement écrit au SessionStart du root de départ. `regexFor(cwd)` résout `root = sources.detect(cwd).root` ; si le cache n'a pas ce root → **extraction lazy in-process, bornée, écrite (write-through, y compris `[]` = negative cache pour ne pas re-scanner), atomique (temp+rename)**. Une session qui passe de VPAI à flash-studio obtient le long-tail flash-studio au 1er tool-call sous ce root. Fail-open → base.
- **M3 — gate per-topic (démotion du marker global).** L'enforcer NE traite PLUS `/tmp/claude-r0-done` global comme satisfaisant un topic arbitraire (sinon, base élargie = un `qdrant-find docker` satisferait `stripe` 25 min → feature morte). Autorité = `ledger.isConsulted(topic)` (stampé per-topic par `r0-marker.js`) + marker per-topic fichier en fallback. Test obligatoire : « search topic A ne satisfait PAS topic B ». Changement du gate fondateur → met à jour les tests D1 (qui seedaient le marker global) pour seeder le ledger per-topic. `r0-marker.js` peut continuer d'écrire le marker global (legacy/rollback) ; l'enforcer l'ignore.
- **M5 — canonicalisation deps.** Avant STOPLIST/cap : pour `@scope/name` → émettre le **scope** (`@prisma/client`→`prisma`, `@nestjs/core`→`nestjs`, `@aws-sdk/*`→`aws`) ; table d'alias (`tailwindcss`→`tailwind`, `next`→`nextjs`, `pg`→`postgres`, …). Sinon les vrais topics sont perdus (`client`, `core`).
- **M6 — inventaire appelants complet.** Migrer cwd-aware AUSSI `r0-rex-watcher.js` (`allTopics`) — sinon un REX sur un topic dynamique ne le ré-arme pas. `loi-op-enforcer.js:118` (advisory DOC_CREATION) réutilise le `const KNOWN_TOPICS` déjà rendu dynamique par l'edit ligne 38 → couvert sans edit séparé.
- **Med4 — regex sûr.** Nouveaux termes de base **word-boundaried** (`\bdocker\b`) → pas de faux positif sous-chaîne (`react`≠`reaction`, `rust`≠`frustrating`). Termes dynamiques : `escapeRegExp` + `\b…\b`. Tests anti-FP requis (incl. topic dynamique avec `.`, ex. `next.js`).

## 9. Hors-scope tracé
- `binding.topics` consommé par `regexFor` (sucre optionnel) — trivial à ajouter plus tard si un jargon non-dérivable apparaît.
- Per-file correlation validate→import (déjà tracé spec 2026-06-04 §7 Task 7, N3-adjacent).
- Extraction sémantique/LLM des topics (N5).
- **Projet non-enregistré accédé depuis un sous-répertoire** (revue finale 2026-06-08, mineur, fail-open) : `sources.detect(cwd)` fait du longest-prefix sur `sources.yml` ; un repo absent de `sources.yml`, accédé depuis un subdir, fail-open sur `root=subdir` → `extract(subdir)=[]` → jargon dynamique silencieusement absent (la **base 6a marche quand même**, jamais unsafe). Les 9 repos enregistrés sont OK (vrai root via longest-prefix). Fix futur trivial : ajouter le repo à `sources.yml`, ou faire remonter `detect` jusqu'à un marqueur (`.git`/manifest) en fail-open. Non bloquant.
- **Fallback `perTopicMarker` inerte** (pré-existant) : rien n'écrit `/tmp/claude-r0-done-<topic>` ; l'autorité du gate est `ledger.isConsulted`. À nettoyer un jour (mort, inoffensif).
