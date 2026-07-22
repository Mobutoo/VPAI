# Handoff — exécution des priorités RAG memory_v3 — 2026-07-22

> **GELÉ — lancement reporté au lundi 2026-07-27** (décision opérateur du 2026-07-22 :
> préserver le quota hebdo ; ce chantier améliore un système déjà fonctionnel).
> Ne pas lancer avant. Jauges à relever d'abord.

## Objectif

Rendre le RAG `memory_v3` mesurable sur la vraie distribution de requêtes, puis attaquer le
classement — en composant et arbitrant les 9 tâches du plan, sans les exécuter soi-même.

## Décisions prises — ne pas re-discuter

- **Le problème est le CLASSEMENT, pas le rappel** : 29/89 questions ont le bon doc récupéré mais
  mal classé, 2/89 seulement ne le récupèrent jamais.
- **P1 (éval) ne dépend PAS de P2 (boucle `use_count`)** : les requêtes réelles s'extraient
  directement des transcripts `.jsonl`. Les deux chantiers sont parallèles.
- **T2-A est le jalon qui débloque tous les verdicts** : mêmes 89 cibles, formulation réécrite
  en style mots-clés. Rien d'autre ne se décide avant son résultat.
- **Le côté rappel (SIRA, contextual retrieval, changement d'embedder) est GELÉ** — condition de
  levée chiffrée dans le plan (T9). Ne pas rouvrir le sujet SIRA.
- **`golden.yml` (89 q) ne s'écrase jamais** : série historique, les nouveaux jeux sont des
  fichiers distincts.
- **Toute mesure A/B se fait ingestion gelée** (`llamaindex-memory-worker.timer` arrêté,
  `points_count` relevé avant/après, ré-armement dans un `trap`).
- **Les requêtes brutes récoltées ne rentrent jamais dans git** ni chez un tiers.
- Plan déjà convergé : 3 rounds Codex, arrêt en RESIDUAL assumé, résiduels rejetés avec
  justification dans le plan (section « État de convergence »). **Ne pas relancer la boucle.**

## Chemins / artefacts

| Rôle | Chemin absolu |
|---|---|
| **Plan à exécuter** | `/home/mobuone/work/infra/VPAI/.planning/plans/2026-07-22-rag-priorites-execution.md` |
| Diagnostic source | `/home/mobuone/work/infra/VPAI/.planning/notes/2026-07-22-rag-etat-des-lieux-angles-morts.md` |
| Seed SIRA (gelé) | `/home/mobuone/work/infra/VPAI/.planning/seeds/2026-07-22-sira-corpus-enrichment-rag-v3.md` |
| Revues Codex | `/home/mobuone/work/ops/loops/reviews/REVIEW-FILE-2026-07-22-rag-priorites-execution-*.md` |
| Harnais d'éval | `/opt/workstation/ai-memory-worker/eval/run_eval.py` |
| Golden 89 (intouchable) | `/opt/workstation/ai-memory-worker/eval/golden.yml` |
| Recherche CLI / MCP | `/opt/workstation/ai-memory-worker/search_memory.py` · `mcp_search.py` |
| Cœur worker (sparse, payload) | `/opt/workstation/ai-memory-worker/memory_core.py` |
| Tracker `use_count` | `/home/mobuone/.claude/hooks/r0-usage-tracker.js` |
| Rôle Ansible | `/home/mobuone/work/infra/VPAI/roles/llamaindex-memory-worker/` |
| Rapports d'éval | `/home/mobuone/work/infra/VPAI/.planning/eval/` |

Venv obligatoire pour tout run d'éval : `/opt/workstation/ai-memory-worker/.venv/bin/python`.

## Prochaine étape

Lancer en parallèle les trois entrées indépendantes du plan :

1. **T1** — écrire `scripts/memory/eval/harvest_queries.py` (récolte des requêtes réelles dans
   les `.jsonl` sessions **et** subagents, `umask 077`, sortie hors git).
2. **T3** — spike binaire timeboxé : les transcripts de subagents sont-ils exploitables par un
   Stop hook, ou faut-il un autre point d'accroche ?
3. **T8 gate** — vérifier dans `run_eval.py` si le `topic` oracle descend de la cible attendue
   (fuite de label). Si oui, T8 s'arrête là.

Puis **T2-A**, qui conditionne tout le reste.

## Gates humains

| # | Gate | Quand |
|---|---|---|
| G1 | Validation du plan | **prérequis au lancement de cette session** — si elle tourne, G1 est franchi |
| G2 | Stratégie d'annotation des cibles pour T2-B | après le résultat de T2-A |
| G3 | Activation du boost `use_count` en prod — 3 conditions cumulatives | après T4 |
| G4 | Téléchargement d'un modèle pour le spike T7 (place disque, licence) | avant T7 |

Notifier chaque gate via `/home/mobuone/work/ops/loops/scripts/notify-gate.sh --artifact <chemin>`.
Aucun secret ne circule dans ce chantier ; aucune mutation destructive de Qdrant n'est prévue.
