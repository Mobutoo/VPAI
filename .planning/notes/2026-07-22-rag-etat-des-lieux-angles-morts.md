# RAG memory_v3 — état des lieux, angles morts, priorités — 2026-07-22

Question opérateur : « que peut-on faire de mieux en RAG ? nouveautés ? angles morts ? »
Sources : audit empirique local (rapports `.planning/eval/`, Qdrant read-only, transcripts
`~/.claude`) + veille 2025-2026 (Qdrant, arXiv, HF). Chiffres re-vérifiés en direct.

## 0. Corrections de faits

| Croyance | Réalité vérifiée 2026-07-22 |
|---|---|
| « ~30k chunks » | **88 720 points** (`GET /collections/memory_v3`) — l'auto-découverte tourne toutes les 30 min |
| « le sweep scope-boost dort » | **déployé** : `MEMORY_SCOPE_BOOST=true`, `WEIGHT=0.2` (`memory-worker.env:53-54`, `defaults/main.yml:110-111`) |
| « `--boost-usage` est un levier prêt » | **inexploitable en l'état** : 9 occurrences dans `search_memory.py` (CLI), **0 dans `mcp_search.py`** (le chemin réellement utilisé par les agents), **0 dans `run_eval.py`** (donc jamais mesurable) |

Commentaire périmé à corriger : `defaults/main.yml:346` affirme « `scope_boost_enabled: false` ci-dessus »
alors que la ligne 110 dit `true`.

## 1. Le diagnostic central : ce n'est pas un problème de rappel

Rapport `eval-memory_v3-hybrid-golden-weekly-20260719T000827Z.json` (89 q, base sans boost) :

| | rank 1 | rank 2-5 | rank 6-10 | jamais top-10 |
|---|---|---|---|---|
| base | 58 | **29** | 0 | 2 |
| boost w0.2 | 60 | 27 | 1 | 1 |

**29/89 = récupéré mais mal classé. 2/89 seulement = jamais récupéré.**
L'écart `recall@1 0,65` vs `recall@5 0,98` est **à 100 % un problème de classement**.

Corollaire — **avec une réserve majeure explicitée au §2** : sur ce harnais, il ne reste que
2,25 pts de rappel à gagner, donc toute technique côté rappel y est invérifiable (SIRA,
Contextual Retrieval dont le « −49 % d'échecs » est une métrique de rappel, changement
d'embedder).

⚠️ **Mais « le rappel est saturé » est lui-même un artefact du golden-89.** `recall@5 = 0,9775`
est mesuré sur le benchmark que le §2 démontre non représentatif. Sur les requêtes réelles
(mots-clés courts), le rappel est **inconnu** et peut différer nettement : le dense avec
`prompt_name="Retrieval-query"` peut se dégrader sur des listes de mots-clés, le sparse BM25
peut au contraire s'y comporter mieux. Ça coupe dans les deux sens.

Conclusion cohérente : le travail côté rappel n'est pas *à faible valeur*, il est **bloqué sur
la priorité 1** — c'est la reconstruction du jeu d'éval qui dira si le rappel est réellement
saturé. La décomposition « 29 mal classés / 2 jamais récupérés » est elle aussi propre au
golden-89 ; le cadre *classement* y survit mieux (« si le doc est récupéré, le problème est
son rang » est plus robuste au changement de distribution que le plafond de rappel).

Signal secondaire : `by_doc_kind` → `rex` recall@1 **0,8235** (n=17) vs `doc` **0,6111** (n=72).
Les REX (courts, mono-sujet, incident daté) se classent nettement mieux que les docs
multi-sujets. Le format du document influence le classement plus que le modèle.

## 2. L'angle mort n° 1 : on optimise sur la mauvaise distribution

Comparaison golden-89 vs **47 requêtes réelles** extraites des transcripts (`qdrant-find.query`
+ `search_memory.py --query`) :

| | n | mots (médiane) | contient « ? » | forme |
|---|---|---|---|---|
| Requêtes réelles | 47 | **8** | **0/47** | listes de mots-clés techniques concaténés |
| Golden-89 | 89 | **14** | 61/89 (68,5 %) | phrases interrogatives FR/EN |

Exemple réel : `"ansible proxmox-host handler command chemin absolu FQCN changed_when idempotence rôle banga"`.
**Aucune requête réelle n'est phrasée en question.** Le golden l'est aux deux tiers.

**C'est le mismatch de forme qui porte la démonstration** (8 vs 14 mots, 0/47 vs 68,5 %
d'interrogatives) : il est mesuré des deux côtés sur des données indépendantes.

Concentration, second grief solide :
- **45/89 questions (50,6 %) ciblent un seul fichier**, `VPAI:docs/TROUBLESHOOTING.md`.

Corroboration faible seulement : le **0/4** recouvrement entre documents réellement consultés
(`use_count>0`) et cibles du golden — le §3 montre que ce signal `use_count` est lui-même
famélique, donc il ne peut pas servir de preuve forte ici. À ne pas surinterpréter.

Conséquence : **chaque décision d'optimisation prise jusqu'ici** (flip DBSF +3-4 pts, scope-boost
+3,4 pts, rejet du reranker) **a été mesurée sur une distribution qui n'est pas la nôtre**. Ce
n'est pas une raison de les annuler — c'est une raison de ne pas empiler la suivante à l'aveugle.

Bruit de mesure à connaître : le corpus grossit en continu, d'où une dérive de **−1,1 à −2,2 pts
de recall@1 en moins de 24 h** entre deux rapports (07-17 → 07-19). Tout gain inférieur à ~2 pts
mesuré à des dates différentes est ininterprétable.

## 3. L'angle mort n° 2 : la boucle de feedback est structurellement affamée

`~/.claude/hooks/r0-usage-tracker.js:89-145` n'incrémente `use_count` qu'en lisant le
**transcript de la session courante**. Or la **LOI R6 impose de déléguer toute investigation
> 5 lectures / > 10 Bash à un subagent** — dont les recherches vivent dans des `.jsonl`
séparés que le hook ne lit jamais.

Résultat mesuré : **215 points sur 88 720 (0,24 %)** ont `use_count > 0`, **tous à
exactement 1**, sur **4 fichiers** seulement, fenêtre 02/07→21/07.

Donc : notre règle d'architecture (R6) **rend probablement aveugle** notre boucle
d'apprentissage — c'est le mécanisme le plus intéressant mis au jour ici.

**Réserve sur le coût du correctif** : il dépend d'un point non tranché (cf Inconnues) — les
subagents déclenchent-ils un Stop hook exploitable ? Si oui, la correction est quasi gratuite
(élargir la lecture aux `.jsonl` de subagents) ; sinon il faut un autre point d'accroche et ce
n'est plus un quick win. **À vérifier avant de chiffrer la priorité 2.**

## 4. L'angle mort n° 3 : les distracteurs sont identifiés et non traités

Ce qui passe **devant** la bonne réponse (`details[].top_files[0]` quand rank≠1) :
- `VPAI:docs/GOLDEN-PROMPT.md` (136 chunks) — apparaît dans le top_files de **15/89 questions**,
  et n'est la cible attendue d'**aucune** (0/89). Pur distracteur.
- `wiki:caddy.md`, `wiki:n8n.md` — idem, jamais cibles.
- **Quasi-doublons cross-repo** : `flash-studio:.planning/research/STACK.md` (Postgres 18) et le
  runbook Redis-8/PG-17 de flash-studio concurrencent `VPAI:docs/TROUBLESHOOTING.md` sur le même
  stack générique.

Test de plafond révélateur (`eval-…-scoped-topic-*.json`, oracle) : filtre dur par `topic` →
**recall@1 = 1.0, recall@5 = 1.0, mrr@10 = 1.0**. Autrement dit : **si l'on sait de quel topic
relève la requête, le classement est parfait.** Tout le problème restant est du routage.

## 5. Veille — ce qui existe et ce qui tombe

| Piste | Verdict Pi5 CPU / cap $5j |
|---|---|
| **Rerank late-interaction (ColBERT-style, jina-colbert-v2)** | seul candidat sérieux : vecteurs token précalculés à l'ingestion, **MaxSim seul à la requête** (pas de forward pass). Multilingue FR+code, Matryoshka 64/96/128. **Aucune mesure ARM publiée** → à mesurer, coût RAM à vérifier (`on_disk=True`) |
| Formula queries / score-boosting natif (Qdrant 1.14) | déjà utilisé (scope-boost) ; coût latence ~nul ; d'autres règles encodables gratuitement |
| miniCOIL | **out** — vocabulaire figé 30k mots **anglais**, gains +0,005 à +0,018 nDCG même en anglais |
| HyDE / réécriture LLM à la requête | **out** — latence secondes + coût par requête vs cap $5/j |
| ColBERT en retrieval primaire | **out** — RAM token-level ; MUVERA = post-traitement FastEmbed, pas dans la Query API |
| Re-chunking sémantique | **out** — littérature 2025-26 contradictoire, ~14× plus lent à l'ingestion |
| Granite R2 / Qwen3-Embedding-0.6B | Qwen3 hors seuil ; Granite meilleur multilingue mais **moins bon en code**, impose une réingestion des 88 720 points |

## 6. Priorités — dans cet ordre, pas un autre

1. **Reconstruire le jeu d'éval à partir des requêtes réelles.** Sans ça, rien de ce qui suit
   n'est décidable. Forme : requêtes en mots-clés (médiane 8 mots), cibles réparties, plafond de
   ~15 % par fichier. Garder golden-89 en série historique, ne pas l'écraser.
2. **Réparer la boucle `use_count`** : faire lire au hook les transcripts de subagents. Coût
   quasi nul, débloque à la fois le signal d'usage et la matière première de la priorité 1.
   Tant que `--boost-usage` est absent de `mcp_search.py` et de `run_eval.py`, le levier
   n'existe ni en prod ni en mesure — deux greffes, pas une.
3. **Attaquer le classement, pas le rappel** — dans l'ordre de coût croissant :
   a. dépondérer les distracteurs identifiés (§4) — gratuit, formula query native ;
   b. rerank **top-5** seulement (≈2,5 s estimé vs 9,8 s sur 20 candidats) ;
   c. rerank late-interaction, à mesurer sur ARM.
4. **Routage par topic** — le test oracle donne 1.0/1.0/1.0. Fiabiliser l'inférence du topic
   à la requête est le plafond théorique de tout le reste.
5. **Différer le côté rappel** (SIRA, contextual retrieval, changement d'embedder) — non pas
   parce que c'est sans valeur, mais parce que **c'est bloqué sur la priorité 1** : sur le
   golden-89 il n'y a que 2,25 pts de marge (sous le bruit de dérive de 2 pts/24 h), et sur la
   vraie distribution le rappel n'a **jamais été mesuré**. La priorité 1 est ce qui rendra ce
   verdict prononçable — dans un sens ou dans l'autre.

## Inconnues assumées

- Les subagents déclenchent-ils un Stop hook séparé ? (transcripts présents, exploitation
  plateforme non tranchée) — conditionne la difficulté de la priorité 2.
- Ce que les 47 requêtes réelles ont effectivement retourné : non journalisé (seul l'input
  du tool_use est récupérable).
- Écart inexpliqué : hook `r0-usage-tracker` annoncé live le 10/06, premier `last_used_at`
  observé le 02/07.
- Aucune mesure ARM/Pi5 publiée pour le late-interaction — le §5 ligne 1 est une hypothèse
  de faisabilité, pas un résultat.
