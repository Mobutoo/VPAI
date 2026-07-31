# Plan — Parité du moteur de recherche mémoire (3 implémentations → 1)

> Statut : **à exécuter plus tard**. Écrit le 2026-07-31 en fin de chantier
> « démon de recherche résident » (VPAI `c9b4b21`, `11561f7`).
> Prérequis de lecture : aucun. Ce document est autoportant.

## Contexte

Le contrat de recherche mémoire (`memory_v3`, hybrid dense+BM25) est
**implémenté trois fois** dans ce repo :

| # | Fichier | Rôle | Consommateurs |
|---|---|---|---|
| 1 | `roles/llamaindex-memory-worker/files/mcp_search.py` | serveur MCP stdio, `_do_search_local()` | outil `mcp__qdrant__qdrant-find` (chemin R0 des agents), et le démon résident qui l'importe |
| 2 | `roles/llamaindex-memory-worker/templates/search_memory.py.j2` | CLI (382 lignes, `search()`, `build_boost_formula()`, `apply_scope_boost()`) | hooks `memory-search-start.sh`, `prompt-preprocessor.js`, protocole AI-Memory documenté dans `CLAUDE.md` |
| 3 | `scripts/memory/eval/run_eval.py` | harnais golden hebdomadaire | timer `memory-eval-golden.timer` (dimanche 02:00) |

Le troisième n'est pas un consommateur des deux premiers : **il les recopie**.
Son propre code le dit — *« Réplique FIDÈLEMENT `mcp_search.py::_apply_scope_boost` »*
(`run_eval.py:118`) et *« même pattern que `search_memory.py build_filter()` »*
(`run_eval.py:61`). Conséquence directe : **l'évaluation hebdomadaire de la
qualité du retrieval ne mesure aucun des deux chemins de production.** Les
chiffres `recall@1`/`recall@5` de `.planning/eval/eval-memory_v3-*.json`
décrivent une réplique, pas ce que les agents reçoivent réellement.

### La dérive n'est pas théorique

Heurtée le 2026-07-31 pendant la mise en place du démon résident :
`MEMORY_SCOPE_BOOST` valait **`true` côté CLI** (posé dans
`/opt/workstation/configs/ai-memory-worker/memory-worker.env`) et **`false`
côté MCP** (l'entrée `qdrant` de `~/.claude.json` ne porte que
`QDRANT_URL`/`QDRANT_API_KEY`/`HF_HUB_OFFLINE`, donc `mcp_search.py` tournait
sur le défaut du code). Deux chemins, deux classements, sur le même corpus et
la même requête — sans que rien ne le signale.

Le démon résident chargeant `memory-worker.env`, il aurait aligné le chemin MCP
sur `true` par effet de bord. Corrigé dans `11561f7` en restaurant `false`
explicitement, **mais ce n'est qu'un symptôme** : rien n'empêche la prochaine
divergence.

Précédent utile : côté **ingestion**, ce problème a déjà été résolu dans ce
repo. `memory_core.py` est décrit comme *« module PARTAGÉ avec le batch pod,
garantissant une parité STRICTE des payloads / node_id »*. La recherche n'a
jamais eu son équivalent.

## Ce que ce plan ne fait PAS

Brancher `search_memory.py` sur le démon résident **pour gagner de la latence**.
Ce serait ajouter un quatrième chemin sans réduire la dette. Le gain de latence
(≈14 s → ≈0,5 s sur les recherches froides des hooks) arrive en **sous-produit**
de l'unification, jamais comme objectif à part.

À noter : le coût résiduel actuel est déjà largement absorbé par le cache
SessionStart posé le 2026-07-31 (`~/.claude` `953c7c46`) — 28,6 s → 1,0 s, avec
invalidation exacte sur la mtime de `memory_state.json`. Il ne reste que les
*misses*, soit ~1 par topic et par run de worker.

## Étapes

### Étape 1 — Harnais différentiel (petit, sans risque, à faire en premier)

Objectif : **chiffrer** la dérive avant de décider quoi que ce soit.

- Un script qui, pour chaque question de `scripts/memory/eval/golden.yml`,
  exécute les trois chemins sur le **même** corpus et le **même** environnement,
  et diffe les listes de hits (ordre + identifiants, pas seulement le top-1).
- Contrainte non négociable : **normaliser l'environnement**. Les constantes
  `MEMORY_MIN_SCORE`, `MEMORY_FUSION_MODE`, `RERANK_ENABLED`,
  `MEMORY_RERANK_CANDIDATES`, `MEMORY_SCOPE_BOOST`, `MEMORY_SCOPE_BOOST_WEIGHT`
  sont lues **à l'import du module** dans `mcp_search.py` — une comparaison
  faite avec des env différents mesure les env, pas les implémentations.
  C'est exactement le piège qui a masqué la divergence de `SCOPE_BOOST` lors du
  test « byte-identique » du démon.
- Sortie : un tableau `question | chemin | rang des hits attendus`, plus un
  compteur global « N questions sur 89 où les trois ne rendent pas la même
  liste ».
- Ce harnais est aussi **le filet** de l'étape 3 : sans lui, toucher au
  retrieval se fait à l'aveugle.

### Étape 2 — Décider sur le chiffre

- **Divergence nulle ou epsilon** → la dette est cosmétique. On s'arrête,
  on documente que les trois sont alignés et on ajoute le harnais différentiel
  au timer hebdomadaire comme garde-fou anti-régression. Fin du plan.
- **Divergence réelle** → l'eval hebdo ne mesure pas ce que reçoivent les
  agents. Ce n'est plus un sujet de performance mais de **fiabilité de R0** :
  on continue en 3.

### Étape 3 — Extraire `memory_search_core.py`

Seulement si l'étape 2 le justifie.

- Un module unique portant : construction du filtre, requête hybride
  (prefetch dense + sparse, fusion DBSF/RRF), floor sur le cosinus dense,
  boost in-scope, rerank optionnel.
- Les trois appelants deviennent des **façades minces** : `mcp_search.py`
  (transport MCP + format compact), `search_memory.py` (CLI + flags + format
  JSONL), `run_eval.py` (scoring golden). Aucun ne reimplémente la recherche.
- Déployé par le rôle au même titre que `memory_core.py`
  (`roles/llamaindex-memory-worker/tasks/main.yml`, tâche
  « Deploy memory_core.py »), pour garantir que les trois consomment
  physiquement le même fichier.
- Critère d'acceptation : le harnais de l'étape 1 rend **zéro divergence**, et
  les chiffres golden avant/après sont identiques à l'epsilon près.

### Étape 4 — Sous-produits, une fois 3 faite

- Brancher `search_memory.py` sur le démon résident devient trivial : une seule
  logique, donc une seule op côté démon, et la question du format de sortie
  disparaît (le format vit dans la façade, pas dans le moteur).
- Le harnais différentiel peut alors devenir un test de non-régression permanent.

## Pièges connus (appris à la dure)

1. **Les flags sont lus à l'import.** Toute comparaison entre chemins doit
   normaliser l'environnement, sinon on mesure les env.
2. **Le levier de réglage a déménagé** depuis le démon résident : servi par le
   démon, ce sont les `Environment=` de
   `roles/llamaindex-memory-worker/templates/memory-search-daemon.service.user.j2`
   qui font foi, plus l'entrée MCP de la session. Le « rollback instantané
   `MEMORY_FUSION_MODE=rrf` » documenté dans `mcp_search.py` se fait là.
3. **Ne jamais éditer `/opt/workstation/ai-memory-worker/*` en place** : tout
   est rendu par le rôle Ansible (`files/` pour `mcp_search.py`,
   `memory_search_daemon.py`, `memory_core.py` ; `templates/` pour
   `search_memory.py.j2`, `index.py.j2`).
4. **Le rerank reste OFF** (+9,8 s médiane par requête sur Pi, mesuré) — le
   moteur unifié doit le garder câblé mais désactivé, pas le supprimer.
5. Le démon sort du processus après 2 h d'inactivité (`Restart=always` en
   relance un neuf) : un harnais qui tourne longtemps peut voir la socket
   disparaître ~5 s. Les clients retombent en propre — le prévoir dans les
   mesures de latence.

## Vérification

```bash
# Étape 1 — le harnais doit tourner sur les 3 chemins avec le MÊME env
scripts/memory/eval/golden.yml            # jeu de questions (source unique)
.planning/eval/eval-memory_v3-*.json      # historique des chiffres à ne pas casser

# Étape 3 — non-régression golden avant/après extraction
systemctl --user start memory-eval-golden.service
journalctl --user -u memory-eval-golden.service --since "-10min" --no-pager

# Ansible, obligatoire avant de clore
source .venv/bin/activate && make lint
ansible-playbook playbooks/hosts/workstation.yml --tags llamaindex-memory-worker   # 2e run = 0 changed
```

## Reste à faire avant gate humain

Ce plan n'a pas encore été passé au consultant Codex
(`~/work/ops/loops/scripts/review-file.sh --sol <ce fichier>`, LOI règle 4).
Aucun secret n'y figure, il est donc éligible. À faire au moment de le sortir
du placard.
