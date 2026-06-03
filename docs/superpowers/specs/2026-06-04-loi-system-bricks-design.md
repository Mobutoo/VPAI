# SPEC — LOI comme système de briques : R0-Continu Phase 2, portabilité & fermeture de boucle

> Statut : **DESIGN — en revue** (2026-06-04)
> Étend : `docs/runbooks/SPEC-R0-CONTINU.md` (Phase 1 implémentée 2026-06-03)
> Cible : couche hooks globale `~/.claude/hooks/` (blast radius = toutes les sessions) + skill `Mobutoo`
> Origine : demande utilisateur — (1) réarmer un topic en longue session + appliquer les REX créés en cours de session ; (2) rendre le moteur mémoire portable cross-projet ; (3) prendre de la hauteur — voir le système entier comme des briques cohérentes et confronter aux best-practices Anthropic/OpenAI.
> Source de vérité opérationnelle : `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md`

---

## 1. Cadre — le système comme boucle agentique

Le système maison n'est pas 12 règles à plat : c'est une **boucle agentique** instrumentée par ~25 hooks, encerclée de guardrails entrée/sortie.

```
INPUT-guard → CONTEXT → VALIDATE → EXECUTE → DEBUG → VERIFY → MEASURE/LEARN
                                    (OUTPUT-guard sur la sortie)
```

Couverture réelle constatée (inventaire hooks, 2026-06-04) :

| # | Brique | Règles LOI | Enforcement réel | Verdict |
|---|---|---|---|---|
| 1 | INPUT guard | — | `prompt-preprocessor` normalise (ne valide pas) | gap mineur |
| 2 | CONTEXT | R0, R8, R4, R6 | R0-Continu (4 hooks) + worker mémoire | **FORT** |
| 3 | VALIDATE | R1, R3 | `loi-op-enforcer` **advisory** | **FAIBLE** |
| 4 | EXECUTE | R2, R7, R11 | R2/R7 **bloc dur**, `bash-lint`, `mcp-intent-guard` | FORT (méthode) / ABSENT (risque) |
| 5 | DEBUG | R5 | `error-escalator` | PARTIEL |
| 6 | VERIFY | — *(R10 = source de vérité)* | `stop-gate` (faible, sur STATE.md) | **GAP** |
| 7 | OUTPUT guard | Secrets (prose CLAUDE.md) | aucun | **GAP** |
| 8 | MEASURE | — | `session-memory-writer` **émet** vers n8n/Telegram | **boucle ouverte** |
| 9 | LEARN | — | `r0-rex-watcher` *(ce design)* | en design |

**Constat de cohérence central** : le système gate dur R0/R2/R7 (les règles faciles à regex) et laisse **R1 — `validate_workflow` avant `import:workflow`, la leçon fondatrice exacte du désastre 806 Bash / 0 MCP — en simple advisory**. On enforce le facile, pas la cause racine de l'incident d'origine.

**Principe directeur** (Anthropic — *effective context engineering*) : CLAUDE.md/LOI surchargés = règles ignorées. Donc on **n'ajoute pas R12/R13/R14 en prose** : on convertit advisory → mécanisme (hook) là où ça compte. *Moins de règles, plus dures.*

---

## 2. Objectifs / Non-objectifs

### Objectifs
- **G1** Réarmement événementiel d'un topic en longue session (sans horloge).
- **G2** Les REX créés en cours de session sont réinjectés plus loin (boucle d'apprentissage intra-session).
- **G3** Portabilité : moteur mémoire piloté par `sources.yml`, fin du `case $PROJECT` cloué VPAI.
- **G4** Cross-projet : les REX/doc des autres repos remontent sur le topic courant.
- **G5** Split LOI CORE (agnostique R0–R8) / BINDING (faits projet).
- **G6** Fermer les gaps de cohérence : R1 hard-gate, boucle MESURE, VERIFY-gate, risk-tier + OUTPUT guard.

### Non-objectifs
- N3 (croisement archi : déduire la version déployée d'un topic → matcher doc de CETTE version). Phase ultérieure.
- Infra eval greenfield (on **ferme** la boucle existante, on ne reconstruit pas).
- Réécriture du worker mémoire / indexation temps réel.

---

## 3. Modèle de données — ledger v2

`/tmp/claude-r0-ledger.json` gagne un **compteur d'actions global** (moteur du réarmement sans horloge) :

```json
{
  "version": 2,
  "session_started": "...",
  "action_count": 47,
  "topics": {
    "n8n":   { "ts": "...", "result": "hit",   "source": "qdrant+hot", "last_action": 31 },
    "caddy": { "ts": "...", "result": "empty", "source": "cascade",    "last_action": 12 }
  }
}
```

| Champ | Rôle |
|---|---|
| `action_count` | horloge logique de session (déterministe, robuste au temps réel), +1 par PreToolUse Bash/Write/Edit |
| `topic.last_action` | valeur du compteur au dernier contact du topic |
| `isFresh(topic)` | **frais SI** `(action_count − last_action) < DECAY_N` ET pas d'invalidation événementielle en attente |

- `DECAY_N` = défaut **20** tool-calls (param). Re-toucher un topic rafraîchit `last_action`.
- Migration : un ledger v1 est du JSON valide → lu **tel quel** (pas de reseed automatique). `isFresh` doit donc tolérer `last_action === undefined` → traité comme **stale** (le topic se ré-arme au prochain contact, `bumpAction` repeuple). Seul un fichier corrompu → `{}` fail-open.
- `lib/ledger.js` gagne : `bumpAction()`, `lastAction(topic)`, `isFresh` décroissant (en plus de `read/stampTopic/invalidate/reset/allTopics` existants).

---

## 4. Partie A — Réarmement (3 déclencheurs)

Trois chemins indépendants remettent un topic à `stale`. Aucun n'utilise d'horloge (cohérent SPEC PARAM-1).

| Déclencheur | Hook | Mécanique | Couvre |
|---|---|---|---|
| **A. Décompte d'actions** | `r0-topic-injector.js` (étendu) | `bumpAction()` à chaque appel ; `isFresh` faux si dérive ≥ `DECAY_N` | réarmer en longue session |
| **B. Écriture REX/doc** | `r0-rex-watcher.js` **(neuf, PostToolUse `Write\|Edit`)** | si `file_path` ∈ {docs/rex, docs/runbooks, docs/audits, TROUBLESHOOTING} → extrait topic(s) via `known-topics` → `invalidate(topic)` | **REX créés mais pas appliqués plus loin** |
| **C. 1er échec outil** | `error-escalator.js` (seuil abaissé) | échec **#1** sur cmd matchant un topic → grep chaud + ré-injecte + `invalidate(topic)`. Compteur anti-boucle reste à **#3** pour le STOP-architecture (R5) | matcher au moment du bug |

> **Changement délibéré de seuils** (l'implémenteur ne doit pas croire que le spec décrit l'existant) : `error-escalator.js` shippé invalide aujourd'hui au seuil **2** (`R0_DEBUG_THRESHOLD`) et STOP-archi à **5**. Ce design les passe à **1** (ré-injection plus précoce) et **3** (STOP-archi R5 conforme à la LOI « 3 fixes »). Ce sont des modifs de valeurs, pas une description.

**Point clé B** : on écrit `REX-X.md` à T0 → watcher invalide le topic → la **prochaine action** sur ce topic re-grep le chaud → le REX frais remonte en tête (tri mtime) et est réinjecté. Le savoir de la session reboucle dans la session.

**Garde-fou anti-spam B** : invalidation ≠ recherche immédiate. Elle arme ; la consultation se fait au prochain tool-call (cap 2 topics/appel inchangé). Écrire 5 REX d'affilée ne déclenche pas 5 recherches.

**Distinction C** : ré-injection à l'échec #1 ≠ STOP-architecture à #3. Corrige l'axe « debug = lectures » sans casser R5.

---

## 5. Partie B — Portabilité N1+N2 (piloté par `sources.yml`)

`sources.yml` du worker (`/opt/workstation/configs/ai-memory-worker/sources.yml`) est **déjà le registre faisant autorité** : 5 sources, chacune `{name, root, tags(scope+kind)}`. Deux sont `kind:official-docs` (DOCS, typebot-docs).

Nouveau module `~/.claude/hooks/lib/sources.js` :

```js
sources.all()        // [{name, root, scope, kinds}] — parse sources.yml
sources.detect(cwd)  // match cwd vs root (préfixe le plus long) → source courante
sources.docRoots()   // sources kind:official-docs
```

Fail-open : illisible → `[{name: basename(cwd), root: cwd, kinds:[]}]` (comportement actuel préservé).

### N1 — détection projet + topics-amorce portables

| Avant | Après |
|---|---|
| `case "$PROJECT"` cloué (VPAI/flash-studio/story-engine) dans `memory-search-start.sh` | `sources.detect(cwd).name` |
| topics hardcodés par projet | termes `known-topics` trouvés dans les **N=5 REX les plus récents** du projet détecté (grep `docs/rex` du `root`, tri mtime) → zéro hardcode |

### N2 — grep chaud multi-repo + palier doc-officielle local

`grep_hot(topic)` itère **tous les `root`** de `sources.all()` :

```
REX CHAUD — projet courant (VPAI) :
  - docs/rex/REX-...-2026-06-02.md
REX CHAUD — autres projets :
  - [flash-studio] docs/rex/REX-n8n-deploy.md
DOC OFFICIELLE (local, kind:official-docs) :
  - [DOCS] n8n/webhooks.md
  - [typebot-docs] integrations/n8n.md
```

Apports : (1) cross-projet étiqueté `[source]` (signale que ça vient d'ailleurs, peut ne pas s'appliquer) ; (2) palier doc-officielle **chaud/local** avant context7/WebSearch dans la cascade R0 ; (3) le froid Qdrant reste cross-repo (déjà sans `--repo`).

**Garde-fou coût** : grep chaud cross-repo borné à **top-5 hits total**, projet courant prioritaire, tri mtime. Corpus REX petit → grep exhaustif OK.

**Garde-fou portabilité** : hors repo connu (ex. `~/macgyver`) → `sources.detect` fail-open basename + grep du seul cwd. Jamais de crash, dégradation propre.

**Garde-fou amorce vide** : un projet connu sans `docs/rex/` (vérifié : `flash-studio` n'a pas de `docs/rex/`, seul VPAI en a) → seed-topics **vide**, pas d'erreur. On s'appuie alors sur le seul `r0-topic-injector` (PreToolUse) qui détecte les topics à l'usage. G3 dégrade proprement : la portabilité n'est pas un no-op, elle bascule juste de l'amorce-au-boot vers la détection-à-l'usage.

---

## 6. Partie C — Split LOI CORE / BINDING

Les 12 règles confondent **principe** (le « comment travailler », portable) et **instanciation** (faits VPAI/n8n).

| Règle | Essence portable (CORE) | Binding VPAI |
|---|---|---|
| R0 | interroger la mémoire avant un topic connu, citer la source, ne pas inventer | chemin `search_memory.py`, `memory_v1` |
| R1 | valider l'artefact via l'outil faisant autorité avant de déployer | `validate_workflow`, :3001 |
| R2 | vrai navigateur pour flux web multi-étapes | paths `/form/*` |
| R3 | éditer la source canonique → valider → commit → deploy ; zéro UI | JSON n8n, REST PUT |
| R4 | valider chaque dépendance en isolation | — |
| R5 | systematic-debugging au 1er symptôme, STOP à 3 fix | — |
| R6 | subagent pour investigation >5 reads/10 Bash | — |
| R7 | accéder à l'infra par le canal sécurisé sanctionné, jamais l'endpoint public brut | Tailscale `100.64.0.14` / interdit IP publique |
| R8 | preuve (doc/source/sortie) > souvenir avant feature tierce | — |
| **R9/R10/R11** | *aucune — ce sont des REX, pas des principes* | **100% n8n** |

### Structure cible

| Couche | Contenu | Lieu | Portée |
|---|---|---|---|
| **LOI-CORE** | R0–R8 en principes paramétrés : `{MEMORY_CMD, VALIDATOR, SECURE_CHANNEL, DEPLOY_METHOD, BROWSER_DRIVER}` | `~/.claude/loi/CORE.md` | tous projets |
| **LOI-BINDING** | remplit les params + règles dures projet (VPAI : R9/R10/R11, commandes concrètes) | `<root>/.loi-binding.yml`, résolu via `sources.detect` | par projet |

- **Mobutoo devient le moteur portable** : charge CORE + binding du projet détecté → rend la table effective. Hors-VPAI sans binding → CORE seul (9 principes universels). Sur VPAI → identique à aujourd'hui pour l'utilisateur.
- **R9/R10/R11 reclassés en REX** → tombent sous le moteur R0-Continu (grep chaud + Qdrant). Résout l'axe « règles couplées à `n8n 2.7.3` sans gate de revue » : quand n8n monte en version, le REX se périme via la mémoire, pas via un doc à éditer à la main.
- Corrige les 2 défauts Mobutoo : Step 4 `rm` aveugle → réarmement ledger-aware (ne nuke pas les topics consultés) ; chemin LOI résolu via `sources.detect` (dégrade hors-VPAI au lieu de crasher).

---

## 7. Partie D — Fermeture des gaps (phasée)

### D1 — R1 hard-gate *(Phase 1)*
`loi-op-enforcer.js` : convertir R1 advisory → **bloc dur** via `process.exit(2)` + message stderr — **mécanisme identique aux gates R0/R2/R7 existants** (PAS `permissionDecision:"deny"` : les gates shippés bloquent par exit-code, lignes 100/147/173) — sur `n8n import:workflow` / `docker cp *.json javisi_n8n` quand aucun `validate_workflow` du même JSON n'a été vu dans le ledger/transcript récent. Message : commande validate à lancer. Ferme la leçon fondatrice. Fail-open.

### D2 — Fermer la boucle MESURE *(Phase 2)*
`session-memory-writer.sh` émet déjà `bash_pct`, counts tools/erreurs/compacts à chaque Stop — mais **personne n'agrège**. Ajouter un agrégateur (ledger persistant `~/.claude/metrics/sessions.jsonl` + seuil) : alerte si `mcp_calls == 0 && bash_calls > 50` (signature exacte de l'incident fondateur 806/0). **Pas d'infra eval neuve** — on ferme la boucle déjà câblée.

### D3 — VERIFY Stop-gate *(Phase 3)*
Hook `Stop` (neuf, ou extension `stop-gate.sh`) : si la dernière réponse contient une assertion de complétion (`fait|réglé|corrigé|passe|déployé|✅`) **sans** trace de commande de vérification (test/lint/validate/curl avec sortie) dans le tour → advisory « preuve avant done » (pattern `verification-before-completion`). Non-bloquant d'abord (advisory), durcissable ensuite.

### D4 — Risk-tier + OUTPUT guard *(Phase 4)*
- **Risk-tier** (OpenAI tool-safeguards) : table outils → niveau (low/med/high) par réversibilité. `high` = `make deploy-prod`, SQL `UPDATE/DELETE`, `ctr leases delete`, `docker ... rm -v`. PreToolUse → gate HITL (confirmation) sur `high`.
- **OUTPUT guard** : Stop-hook scan secrets/PII en sortie (la règle Secrets existe, l'enforcement non).

---

## 8. Inventaire hooks (neufs / modifiés)

Invariant absolu (SPEC §4) : **tout hook fail-open** — exit 0 sur erreur, jamais de throw non-catché.

| Hook | État | Phase | Changement |
|---|---|---|---|
| `lib/sources.js` | **neuf** | P1 | parse `sources.yml` → `all/detect/docRoots` |
| `r0-rex-watcher.js` | **neuf** | P1 | PostToolUse `Write\|Edit` → invalidate topic sur écriture REX (décl. B) |
| `lib/ledger.js` | modifié | P1 | `action_count`, `last_action`, `isFresh` décroissant, migration v1→v2 |
| `r0-topic-injector.js` | modifié | P1 | `bumpAction()` + check décroissance (décl. A) |
| `error-escalator.js` | modifié | P1 | invalidate+ré-injecte à l'échec #1, STOP-archi maintenu à #3 (décl. C) |
| `memory-search-start.sh` | modifié | P1 | `sources.detect` au lieu de `case $PROJECT` ; grep chaud multi-repo ; amorce portable |
| `loi-op-enforcer.js` | modifié | P1 | R1 advisory → bloc dur (D1) ; lit CORE/BINDING résolu |
| `Mobutoo/SKILL.md` | modifié | P1 | moteur CORE+BINDING ; Step 4 ledger-aware ; chemin via `sources.detect` |
| `~/.claude/loi/CORE.md` | **neuf** | P1 | R0–R8 paramétrés |
| `<root>/.loi-binding.yml` (VPAI) | **neuf** | P1 | params + R9/R10/R11 |
| metrics-aggregator | **neuf** | P2 | agrège `session-memory-writer`, seuil 806/0 |
| verify-stop-gate | **neuf** | P3 | Stop, preuve avant « done » |
| risk-tier guard + output-guard | **neuf** | P4 | gate HITL high-risk + scan secrets/PII sortie |

**Câblage `settings.json`** : 1 entrée neuve PostToolUse `matcher: "Write|Edit"` (r0-rex-watcher) en P1 ; entrées Stop additionnelles en P3/P4.

---

## 9. Tests (par hook, avant câblage `settings.json` — SPEC §5)

1. `lib/sources.js` : detect VPAI/flash-studio ; cwd inconnu → fail-open basename ; yml corrompu → `[]`.
2. `lib/ledger v2` : décroissance (frais < DECAY_N, stale ≥) ; migration v1 → reseed ; corrompu → `{}`.
3. `r0-rex-watcher` : Write REX n8n → `invalidate('n8n')` ; Write hors REX-dirs → rien ; 5 REX → pas 5 searches.
4. `error-escalator` : échec #1 topic → ré-inject+invalidate ; #3 → STOP-archi ; non-topic → rien.
5. `memory-search-start` multi-repo : hit flash-studio étiqueté `[flash-studio]` ; doc-officielle séparée.
6. `loi-op-enforcer` D1 : `import:workflow` sans validate préalable → deny ; avec validate dans le ledger → allow.
7. Mobutoo : hors-VPAI → CORE seul ; sur VPAI → CORE+binding ; Step 4 ne nuke pas un topic consulté.
8. Régression : F1/F2/F3 + déclencheurs SPEC existants (clear/compact) + R0/R2/R7 blocs toujours OK.
9. *(P2)* metrics-aggregator : run 806/0 simulé → alerte ; run sain → silence.

---

## 10. Rollout / Rollback

- Commits atomiques : 1 hook = 1 commit (SPEC §6), repo `~/.claude` branch `main`.
- **Phasage strict** : P1 ship et se valide seul avant P2. Chaque phase indépendamment rollback-able (retrait des entrées `settings.json` neuves → hooks legacy reprennent).
- Markers legacy conservés 1 version en parallèle du ledger v2.
- Spec VPAI committée ; hooks committés dans `~/.claude`.

## 11. Hors-scope tracé (Phase ultérieure)
- N3 croisement archi (version déployée → doc de cette version).
- Durcissement bloquant de D3/D4 (advisory d'abord, mesurer avant de durcir — Anthropic « start simple »).
- Daemon de recherche chaud HTTP (déjà tracé SPEC §8).
