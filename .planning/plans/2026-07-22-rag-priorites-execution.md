# Plan d'exécution — RAG memory_v3 : 5 priorités éclatées en 9 tâches — 2026-07-22

> ## 🅶 STATUT : GELÉ — lancement reporté au **lundi 2026-07-27**
>
> **G1 : plan validé, exécution ajournée par l'opérateur (2026-07-22).**
> Motif : préserver le quota hebdo pour d'autres chantiers. Ce plan améliore un système
> **déjà fonctionnel** — il n'a pas de caractère d'urgence et ne bloque personne.
> Reprise prévue sur une fenêtre de quota fraîche.
>
> **Ne pas lancer la session `factor` avant cette date.** Relever les jauges
> (`~/work/ops/loops/scripts/claude-usage-guard.sh`) avant le lancement : le plan suppose une
> marge confortable, plusieurs tâches dispatchent des sous-agents.
> Commande de lancement et handoff : voir la fin de ce fichier.

| Priorité (note diagnostic) | Tâches de ce plan |
|---|---|
| P1 — reconstruire le jeu d'éval | **T1**, **T2-A**, **T2-B** |
| P2 — réparer la boucle `use_count` | **T3** (spike), **T4** (3 greffes) |
| P3 — attaquer le classement | **T5** (distracteurs), **T6** (rerank top-5), **T7** (late-interaction) |
| P4 — routage par topic | **T8** |
| P5 — côté rappel, différé | **T9** |


Diagnostic source : `/home/mobuone/work/infra/VPAI/.planning/notes/2026-07-22-rag-etat-des-lieux-angles-morts.md`
Seed connexe (différé) : `/home/mobuone/work/infra/VPAI/.planning/seeds/2026-07-22-sira-corpus-enrichment-rag-v3.md`

## Objectif

Rendre le RAG **mesurable sur la vraie distribution de requêtes**, puis attaquer le classement.
Aucune optimisation supplémentaire n'est décidable tant que T2 n'a pas tourné.

## Décision structurante : P1 ne dépend PAS de P2

Le diagnostic a été lu comme « réparer la boucle `use_count` fournit la matière première de
l'éval ». **C'est faux.** Les requêtes réelles sont extractibles **directement des transcripts
`.jsonl`** — l'audit en a déjà sorti 47 sans toucher au hook. Le hook `use_count` ne sert qu'au
**signal de boost**, pas à la récolte des requêtes.

Conséquence : T1/T2 (éval) et T3/T4 (boucle de feedback) sont **deux chantiers indépendants**,
parallélisables. L'ordre du diagnostic (P1 puis P2) n'est plus contraignant.

## Contrainte méthodologique — non négociable

Le corpus grossit en continu : **dérive mesurée de −1,1 pt (base) et −2,2 pts (boost) de
recall@1 en ≈ 25 h** — `eval-…-golden-enriched-89-fixup2-20260718T012000Z.json` horodaté
**2026-07-17T23:09Z** → `eval-…-golden-weekly-20260719T000827Z.json` horodaté
**2026-07-19T00:09Z**. Donc :

> Toute comparaison A/B doit être produite **sur un état de collection prouvé identique**.
> Jamais de comparaison à un JSON daté d'un autre jour.

**Le « même run » ne suffit pas** : le worker ingère toutes les 30 min
(`llamaindex-memory-worker.timer`) et une mesure T5/T6 avec rerank peut dépasser cette fenêtre.
Protocole obligatoire pour toute mesure comparative :

1. `systemctl --user stop llamaindex-memory-worker.timer` (gel de l'ingestion) ;
2. relever `points_count` via `GET /collections/memory_v3` → **valeur N₀** ;
3. lancer baseline **et** variante ;
4. re-relever `points_count` → si ≠ N₀, **la mesure est invalide**, on recommence ;
5. ré-armer le timer (`start`) — dans un `trap`, pour qu'un échec ne laisse pas
   l'ingestion à l'arrêt.

**Seuil de significativité — à établir, pas à postuler.** L'écart de 2,2 pts observé entre
07-17 et 07-19 provient d'**une seule comparaison inter-dates**, sans variance mesurée : ce
n'est pas un intervalle de confiance. Première action de T2-A : **répéter deux fois la même
éval sur état gelé** pour mesurer la variance propre du harnais (elle devrait être nulle en
`--exact`, à confirmer), puis fixer le seuil de déclaration à partir de cette mesure. Tant
qu'il n'est pas établi, le seuil provisoire est de **2 pts** et il est signalé comme provisoire
dans tout rapport qui s'en sert.

---

## T1 — Récolte des requêtes réelles

**But** : un corpus daté de requêtes réellement soumises au RAG, condition de tout le reste.

- Script `scripts/memory/eval/harvest_queries.py` (nouveau, repo VPAI).
- Source : tous les `.jsonl` sous `~/.claude/projects/**` — **sessions ET subagents**
  (les subagents sont dans des fichiers séparés ; c'est là que vit la majorité des recherches,
  cf LOI R6).
- Extraire : `tool_use` `mcp__qdrant__qdrant-find`.query et `Bash … search_memory.py --query`,
  + horodatage, + repo/wing de la session appelante.
- Sortie : **hors du dépôt git** — `/opt/workstation/data/ai-memory-worker/queries/real-queries-<STAMP>.jsonl`,
  une requête par ligne. Ce fichier n'entre **jamais** dans `.planning/` (versionné).
- **Critère de fin** : ≥ 150 requêtes uniques extraites, ou constat chiffré que le gisement
  historique est épuisé (avec le décompte réel).

### ⚠️ T1 manipule des données potentiellement sensibles

Les transcripts contiennent tout ce qui a transité en session — y compris, potentiellement, des
secrets collés ou affichés. Un harvester qui les scanne et **écrit un fichier** crée une
surface de fuite nouvelle. Non négociable :

- **N'extraire que le champ requête**, jamais le contexte environnant, jamais un `tool_result`.
- **Caviardage avant écriture** : filtre de motifs (`api[_-]?key`, `token`, `secret`, `passwd`,
  `Bearer `, `-----BEGIN`, chaînes ≥ 32 car. en base64/hex) → la requête est **rejetée**, pas
  masquée, et comptée dans un total de rejets.
- **Permissions dès la création, jamais après** : `os.umask(0o077)` en tête de script **et**
  ouverture par `os.open(path, O_WRONLY|O_CREAT|O_EXCL, 0o600)`. Un `chmod` post-écriture
  laisse une fenêtre où le fichier est lisible — interdit.
- **Séparation stricte brut / versionné** — le mode `0600` n'est de toute façon pas préservé
  par git, donc la protection ne peut pas reposer dessus :

  | Artefact | Emplacement | Git |
  |---|---|---|
  | requêtes brutes récoltées | `/opt/workstation/data/ai-memory-worker/queries/` | **jamais** |
  | jeu d'éval dérivé, relu ligne à ligne | `.planning/eval/` | oui, après relecture humaine |

  Le passage du premier au second est une **action de relecture explicite**, pas une copie
  automatique. Ajouter `.planning/eval/real-queries-*` à `.gitignore` en filet de sécurité.
- Le corpus produit ne part **jamais** chez un tiers (pas de `review-file.sh`, pas d'essaim).

Référence de départ : l'audit a extrait 47 requêtes uniques (médiane 8 mots, 0/47 interrogatives)
en scannant les 400 `.jsonl` les plus récents — élargir la fenêtre et inclure les subagents.

## T2 — Golden v2 : isoler la variable « style de requête »

**But** : savoir si nos métriques tiennent quand la requête ressemble à une vraie requête.

**Étape A (prioritaire, bon marché)** — `golden-89-keywords` : reprendre **les 89 cibles
existantes**, réécrire **uniquement la formulation** en style mots-clés (médiane ~8 mots, aucune
forme interrogative), en s'appuyant sur le corpus T1 pour le style.
Cibles constantes ⇒ A/B qui **vise à** isoler le style, sans travail d'annotation.

**Limite à ne pas masquer** : une reformulation manuelle peut modifier l'information disponible
(perte d'un terme discriminant, ajout d'un mot-clé absent de l'original) — l'A/B ne serait plus
« à sémantique constante ». Garde-fous : conserver **chaque paire (original, reformulé)
tracée dans le même fichier**, et faire relire l'appariement par un tiers (Codex,
`review-file.sh` sur le jeu reformulé — **pas** sur les requêtes brutes) avant toute mesure.
Une paire jugée non équivalente est **corrigée, jamais retirée** : les deux jeux doivent garder
**exactement les mêmes 89 cibles**, sans quoi la comparaison T9 porterait sur des populations
différentes. Si une paire résiste à la correction, elle est conservée et **exclue du calcul des
deux côtés** (sous-ensemble apparié identique), et le décompte des exclusions figure au rapport.

C'est cette étape qui tranche la question restée ouverte : **le rappel est-il réellement saturé,
ou seulement saturé sur des questions bien formulées ?**

**Étape B (après A)** — élargir avec de vraies requêtes de T1 dont la cible est annotée. Plafond
**15 % des questions par fichier cible** (le golden-89 en concentre 50,6 % sur
`docs/TROUBLESHOOTING.md`). Stratégie d'annotation à arbitrer au vu de A.

**Interdits** : ne jamais écraser `golden.yml` (89 q) — c'est la série historique. Les nouveaux
jeux sont des fichiers distincts, et les seuils de gate de `memory-eval-golden.sh` restent
adossés au golden-89 tant que la v2 n'est pas validée.

**Livrable de mesure** : un rapport unique comparant, dans la même fenêtre, golden-89 vs
golden-89-keywords sur `recall@1 / recall@5 / mrr@10`.

## T3 — Spike : les transcripts de subagents sont-ils exploitables ? (binaire)

**But** : lever l'inconnue qui décide du coût de T4. **Timeboxé.**

Question exacte : un subagent déclenche-t-il un Stop hook exploitable, ou faut-il un autre point
d'accroche (scan périodique des `.jsonl`, lecture post-hoc) ?
Sortie attendue : **OUI/NON + le point d'accroche retenu**, rien d'autre.
Fichier concerné : `~/.claude/hooks/r0-usage-tracker.js:89-145`.

## T4 — Réparer la boucle `use_count` — **trois greffes, pas une**

Vérifié 2026-07-22 : `use_count` = 9 occurrences dans `search_memory.py`, **0 dans
`mcp_search.py`**, **0 dans `run_eval.py`**.

1. **Récolte** : le tracker doit voir les recherches des subagents (point d'accroche de T3).
2. **Production** : greffer le boost dans `mcp_search.py`. **Les deux chemins sont utilisés** —
   l'audit a compté **26 appels MCP `qdrant-find` et 23 appels CLI `search_memory.py`** sur
   47 requêtes réelles. Ne pas traiter le MCP comme « le seul chemin » : T1 fournira la part
   exacte de chacun, et le boost doit se comporter **identiquement** sur les deux (sinon deux
   agents obtiennent des classements différents pour la même requête).
3. **Mesure** : greffer le flag dans `run_eval.py` — sans ça le levier n'est pas évaluable.

État actuel du signal : **215 points / 88 720 (0,24 %)**, tous à `use_count = 1`, 4 fichiers.
**Ne pas activer le boost en prod tant que le signal est à ce niveau** — il ne peut que faire du
bruit. T4 installe la plomberie ; l'activation est un gate ultérieur (G3) dont le seuil est
**fixé ici, pas plus tard** :

| Condition d'activation (toutes requises) | Métrique | Vérification |
|---|---|---|
| volume | ≥ **3 %** des points ont `use_count > 0` (≥ ~2 660 sur 88 720) | `POST /collections/memory_v3/points/count` avec filtre `use_count > 0` |
| discrimination | ≥ **10 %** de ces points ont `use_count ≥ 2` | même appel, filtre `use_count >= 2` |
| non-régression | `mrr@10` ≥ baseline sur les deux jeux d'éval, état gelé | `run_eval.py` avec le flag greffé en T4 |

Aujourd'hui : 0,24 % et **0 point** à `use_count ≥ 2` — les trois conditions échouent.

## T5 — Dépondérer les distracteurs (classement, coût ~nul)

Cibles identifiées : `VPAI:docs/GOLDEN-PROMPT.md` (dans le top de **15/89** questions, cible
d'**aucune**), `wiki:*.md` (idem), quasi-doublons cross-repo (`flash-studio:.planning/research/STACK.md`).

Moyen : *formula query* / score-boosting natif Qdrant (déjà utilisé pour le scope-boost) —
aucun modèle, coût latence ~nul.

**Piège à éviter** : ne pas coder en dur une liste de fichiers. Chercher le **critère
généralisable** (doc_kind, ratio chunks/cible, `.planning/research/**`), sinon on optimise le
golden-89 au lieu du RAG — exactement le biais que ce plan combat.

Mesure : golden-89 **et** golden-89-keywords, même fenêtre.

## T6 — Rerank top-5 (classement)

Aujourd'hui le site d'appel passe **tous** les candidats retenus au reranker
(`/opt/workstation/ai-memory-worker/search_memory.py:340`). Le benchmark rédhibitoire
(+9,8 s médiane) portait sur **20 candidats** ⇒ ≈ 0,49 s/paire.

- Rendre le nombre de candidats reranké **paramétrable**, mesurer la latence réelle à 5 et 10.
- Le modèle est déjà en cache (`onnx-community/bge-reranker-v2-m3-ONNX`, int8).
- **Piège connu** : côté MCP, `MEMORY_RERANK_MODEL_ID` n'est pas dans le bloc `env` de
  `~/.claude.json` → si le rerank est activé sans l'ajouter, retombée silencieuse sur un repo HF
  sans artefact ONNX = **no-op muet**.
- **Critère GO** : latence ajoutée < 1,5 s **et** gain `mrr@10` **≥ le seuil de significativité
  établi en T2-A** (provisoirement 2 pts) sur les deux jeux d'éval, état gelé. Un gain positif
  mais sous le seuil = NO-GO, comme partout ailleurs dans ce plan.
  Latence hors budget ⇒ NO-GO, quel que soit le gain de qualité.

## T7 — Late-interaction (ColBERT-style) — spike faisabilité, pas adoption

**Hypothèse à évaluer, pas fait établi** : c'est la seule piste que *notre* veille du 22/07 ait
retenue après filtrage CPU/ARM — un balayage non exhaustif, sans étude comparative dédiée à
ARM. Principe : vecteurs token précalculés à l'ingestion, **MaxSim seul à la requête**.
Candidat : `jina-colbert-v2` (multilingue FR + code, Matryoshka 64/96/128), arXiv 2408.16672.
**Aucune mesure ARM publiée** — le spike répond à : latence MaxSim sur 20 candidats en CPU ARM,
et coût RAM/disque des vecteurs par token sur 88 720 points (`on_disk=True` requis ?).
**Règle unique** : T7 ne démarre **que si T6 est NO-GO**. Un GO de T6 clôt la question du
reranking — pas de « optionnel », pas de comparaison des deux.

## T8 — Routage par topic (le plafond théorique)

Le filtre oracle par `topic` donne **recall@1 = 1.0 / mrr@10 = 1.0**
(`.planning/eval/eval-memory_v3-hybrid-scoped-topic-*.json`).

**Ce que cela démontre exactement** : *sur le golden-89, avec le topic fourni par un oracle*,
le classement est parfait. Ça ne démontre **pas** que le routage est tout le problème restant
en production — deux réserves : (a) le résultat est propre à un benchmark dont on sait qu'il
n'est pas représentatif, (b) un score de 1.0 sur les trois métriques est le profil typique
d'une **fuite de label** (le topic oracle est dérivé de la cible attendue). **Première action de
T8 : vérifier cette fuite** — comment le topic oracle est-il produit dans `run_eval.py` ? S'il
descend de la cible, le test de plafond ne vaut rien et T8 s'arrête là.

Piste à vérifier avant de coder : un dériveur de topic **déterministe** existe déjà côté hooks
(`topic-extract.js`, dérivation par projet) — mesurer son taux d'accord avec le topic oracle du
golden **avant** d'écrire quoi que ce soit. Si l'accord est faible, T8 est un chantier de
recherche, pas une tâche.

## T9 — Côté rappel : différé, avec une condition de levée explicite

SIRA, contextual retrieval, changement d'embedder : **gelés**, non par faible valeur mais parce
que le verdict dépend de T2-A.

**Condition de levée chiffrée** — les deux jeux mesurés dans la **même fenêtre**, mêmes 89
cibles, seule la formulation change (donc pas de dérive de corpus entre les deux mesures) :

| `recall@5` de golden-89-keywords | Verdict |
|---|---|
| **< 0,930** (écart > 4,75 pts, soit > 2× le bruit de dérive de 2,2 pts) | rappel **non saturé** sur la vraie distribution → T9 **dégelé et prioritaire** |
| 0,930 – 0,970 | zone grise → refaire la mesure sur le jeu élargi T2-B avant de trancher |
| **> 0,970** (≈ parité avec 0,9775) | rappel confirmé saturé → T9 reste gelé |

Le bruit de dérive ne s'applique pas *entre* les deux jeux (même run) mais borne la
significativité qu'on peut revendiquer : un écart de moins de ~2 pts ne sera pas déclaré.

---

## Dépendances

```
T1 ──► T2-A ──► T2-B
        │
        ├──► T5 (mesure)
        ├──► T6 (mesure)
        └──► T9 (condition de levée)

T3 ──► T4

T6 ──► T7 (seulement si T6 NO-GO)
T8 : indépendant — gate fuite de label D'ABORD, accord topic ensuite
```

Parallélisable immédiatement : **T1**, **T3**, et le **gate fuite de label de T8**.

## Ordre d'exécution recommandé

1. T1 + T3 + gate fuite de label T8 (en parallèle) — la mesure d'accord des topics ne
   commence que si ce gate est franchi
2. T2-A ← **le jalon qui débloque les verdicts**
3. T5 et T6 (mesurés sur les deux jeux)
4. T4 (plomberie), T2-B
5. T7 / T9 selon les verdicts de T6 et T2-A

## Gates humains

| # | Gate | Quand |
|---|---|---|
| G1 | Validation de ce plan | avant tout lancement |
| G2 | Stratégie d'annotation des cibles pour T2-B | après le résultat de T2-A |
| G3 | Activation du boost `use_count` en prod | après T4, conditionnée aux **trois** conditions cumulatives du tableau T4 (volume ≥ 3 %, discrimination ≥ 10 % à `use_count ≥ 2`, non-régression `mrr@10`) |
| G4 | Téléchargement d'un modèle pour T7 (place disque, licence) | avant le spike T7 |

Rien de sortant vers l'extérieur, aucune mutation Qdrant destructive prévue. Les nouvelles
collections d'essai éventuelles sont créées à côté, jamais en écrasement.

**Sur les secrets — formulation exacte** : ce plan ne manipule aucun secret *volontairement*,
mais **T1 lit des transcripts qui peuvent en contenir**. Le risque est réel et traité par le
garde-fou de T1 (extraction du seul champ requête + caviardage par rejet + `0600` + relecture
avant commit). Aucun artefact de ce chantier ne doit être envoyé à un tiers : ni le corpus de
requêtes, ni un extrait de transcript — cela exclut `review-file.sh` et tout essaim sur ces
fichiers.

## État de convergence (LOI règle 4) — 3 rounds Codex `gpt-5.6-sol`

| Round | Verdict | Rapport |
|---|---|---|
| 1 | 0 HIGH / 4 MED / 1 LOW — **tous intégrés** | `REVIEW-FILE-…-1040.md` |
| 2 | 2 HIGH (confirmés) / 6 MED — **tous intégrés** | `REVIEW-FILE-…-1043.md` |
| 3 | 3 HIGH → **2 réfutés par l'escalade**, 1 confirmé et intégré ; 4 MED intégrés | `REVIEW-FILE-…-1048.md` |

Rapports dans `/home/mobuone/work/ops/loops/reviews/`.

**Boucle arrêtée en RESIDUAL, volontairement.** Les findings croissent (5 → 8 → 10) parce que
chaque correctif ajoute de la surface relisible, pas parce que le plan se dégrade. Findings
restants **rejetés avec justification** — ils remontent ici au gate humain, ils ne sont pas
masqués :

| Finding résiduel | Rejet motivé |
|---|---|
| « 2 exécutions ne suffisent pas à estimer la variance » | l'éval tourne en `--exact` (recherche exhaustive, pas HNSW) : la variance attendue est **nulle par construction**. Deux exécutions servent à *vérifier* cette nullité, pas à l'estimer statistiquement. Si elles divergent, alors seulement un protocole de répétition devient nécessaire — c'est écrit ainsi dans T2-A. |
| « `points_count` ne prouve pas un état identique (des mises à jour peuvent conserver le compte) » | **valide sur le fond**, écarté sur le coût : la parade propre est un snapshot Qdrant, lourd pour 88 720 points sur ce Pi. Le worker étant arrêté pendant la mesure, un remplacement à compte constant supposerait un writer tiers — inexistant ici. **Risque accepté et tracé.** |
| « le trap doit être installé avant l'arrêt du timer » | **réfuté par l'escalade** : l'étape 4 (re-contrôle de `points_count` et invalidation) couvre le cas d'une ingestion résiduelle, quelle qu'en soit l'origine. |
| « contradiction : relecture Codex du jeu reformulé vs interdiction d'envoi à un tiers » | **réfuté par l'escalade** : l'interdiction porte sur les *requêtes brutes issues des transcripts*. Le jeu `golden-89-keywords` est une reformulation des 89 cibles existantes, artefact distinct, sans lien avec les transcripts. |

## Lancement (à faire le 2026-07-27, pas avant)

```bash
~/work/ops/loops/scripts/claude-usage-guard.sh        # jauges d'abord
~/.claude/skills/factor/factor-launch.sh \
  --repo /home/mobuone/work/infra/VPAI \
  --subject rag-priorites \
  --handoff /home/mobuone/work/infra/VPAI/.planning/handoffs/2026-07-22-rag-priorites.md
```

Modèle : `claude-fable-5` par défaut (session amiral — elle dispatche et arbitre 9 tâches et
4 gates, elle n'exécute pas). `--model sonnet` si l'on préfère préserver le cap Fable, au prix
d'une session exécutante plutôt qu'arbitre.

Le lanceur est idempotent : relancé sur le même `--subject`, il rend l'URL existante. Pour
repartir de zéro : `tmux kill-session -t factor-rag-priorites`.

## Correction à porter au passage

`roles/llamaindex-memory-worker/defaults/main.yml:346` — commentaire périmé affirmant
`scope_boost_enabled: false` alors que la ligne 110 dit `true`.
