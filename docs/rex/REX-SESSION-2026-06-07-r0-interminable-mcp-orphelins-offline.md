# REX Session — R0 interminable : serveurs MCP orphelins + offline HF (2026-06-07)

## Objectif

Une autre session Claude rapportait des **recherches R0 (Qdrant) interminables**. Question : le worker / le MCP `qdrant-find` arrivent-ils seulement à lire Qdrant ? **Contrainte forte** : vérifier *sans* se bloquer soi-même (un appel naïf à la recherche aurait hang la session de diagnostic aussi).

Résultat : oui, worker ET MCP lisent Qdrant ; l'« interminable » venait de **serveurs MCP orphelins coincés** + de l'absence d'offline HF. Corrigé.

---

## Méthode — diagnostiquer un hang sans se bloquer

Principe : **tout borné, tout isolé** (jamais l'outil suspect directement).
1. **Découpler les couches** et chronométrer chacune séparément : Qdrant RAW (curl `--max-time`) ≠ chargement modèle ≠ embed ≠ search.
2. **`timeout` partout** + `run_in_background` + poll → la commande revient au pire après N s, jamais de blocage indéfini.
3. **Ne PAS appeler `mcp__qdrant__qdrant-find`** depuis la session de diag (il pouvait hang 120s). À la place : reproduire le chemin en sous-process bornés, puis **parler au serveur MCP en JSON-RPC brut** sur stdin/stdout (instance fraîche) pour le test conclusif.

---

## Erreurs rencontrées et résolutions

### 1. R0 interminable = serveurs MCP orphelins coincés dans `_load()` ❌ → résolu
**Symptôme** : `mcp__qdrant__qdrant-find` n'aboutit jamais (≈120s par appel).
**Diagnostic** : `ps` → **3** process `mcp_search.py`. Deux à **14M/21M RSS, 14h/25h** = python nu, **modèle JAMAIS chargé** (torch même pas importé). Un à 1460M = sain.
**Cause** : `mcp_search.py._load()` (preload modèle en thread background) est `try/except Exception: pass; finally: _ready.set()`. Démarrés *sans* `HF_HUB_OFFLINE` et modèle pas encore en cache à l'époque → `SentenceTransformer(...)` **hang sur le réseau HF** → `_ready` jamais positionné → le handler `_ready.wait(120)` attend le timeout **à chaque appel**. Orphelins de sessions Claude mortes (stdio MCP pas reAPé à la sortie).
**Fix** : `kill` des 2 orphelins + **`HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`** garantis (le modèle est en cache → load 2.6s, zéro réseau, plus de hang). Redémarrer la session → MCP frais, preload ~10s puis ~0.6s/appel.

### 2. CLI `search_memory.py` lent (~14s/appel), pas un bug ⚠️
**Symptôme** : R0 via CLI « lent » quand enchaîné sur plusieurs topics.
**Mesure** : 15.8s sans offline → 13.9s avec offline. Le réseau HF n'était qu'~2s ; le gros = **import `sentence_transformers` 7s + load modèle 2.6s à CHAQUE invocation** (process neuf, ARM). C'est le **plancher du canal froid**, inhérent à un CLI sans persistance.
**Conséquence** : la voie rapide est le **MCP** (modèle persistant, ~0.6s/appel). Le CLI reste un fallback lent ; un R0-cascade qui l'enchaîne sur N topics = N×14s.

### 3. CLI sans `HF_HUB_OFFLINE` → dépendance réseau inutile ⚠️ → corrigé
**Cause** : `memory-worker.env` n'avait que `HF_HOME`, pas d'offline → chaque load interroge huggingface.co (modèle déjà en cache pourtant).
**Fix** : `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` dans `memory-worker.env` **ET** le template Ansible `roles/llamaindex-memory-worker/templates/memory-worker.env.j2` (sinon écrasé au prochain deploy). Commit `1ec9bc3`.

---

## Chiffres mesurés (preuves, bornés)

| Couche | Latence | Verdict |
|---|---|---|
| Qdrant RAW (curl count/scroll) | **0.078s** | lisible, rapide |
| Model load **offline** | **2.6s** | OK |
| Model load **sans offline** (réseau HF) | ~+2-10s | dépendance évitable |
| Embed 1 requête | 0.5s | OK |
| **MCP `qdrant-find`** (JSON-RPC, instance fraîche) | OK, hit pertinent (0.546) | **lit Qdrant** |
| CLI `search_memory.py` (cold, ARM) | ~14s | plancher import+load, pas un bug |
| Serveur MCP coincé (sans offline, _load hang) | **120s/appel** | = « interminable » |

## Leçons

- **Un hang se diagnostique borné + en couches** : isoler Qdrant / load / embed / search, chacun avec `timeout`, parler au serveur en JSON-RPC plutôt que d'appeler l'outil suspect.
- **`except Exception: pass` + `_ready.set()` en `finally`** masque les échecs de preload → serveur « prêt » mais modèle `None`, ou pire coincé avant `_ready` = 120s/appel. Anti-pattern d'observabilité.
- **MCP stdio = orphelins** : les sessions mortes laissent des serveurs `mcp_search.py` (vu 3, dont 2 zombies 14-25h). Penser à `ps | grep mcp_search` + `kill` lors de symptômes lents. (Reaping non garanti par le client.)
- **Offline obligatoire quand le modèle est caché** : supprime la dépendance réseau et le mode de panne « hang dans le load ». Cohérence CLI (memory-worker.env) ET MCP (env `.claude.json`, déjà offline).
- **Canal froid CLI ≈ 14s/appel sur ARM** : ne pas l'enchaîner ; privilégier le MCP persistant pour R0.

## Liens

Rebuild M3/M4 : [[REX-SESSION-2026-06-06-memory-bulk-gpu-bf16]]. Fichiers : `/opt/workstation/ai-memory-worker/mcp_search.py` (`_load`), `roles/llamaindex-memory-worker/templates/memory-worker.env.j2`. Commit fix : `1ec9bc3`.
