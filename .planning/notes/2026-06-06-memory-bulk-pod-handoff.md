# Handoff — Ingestion bulk mémoire (pod CPU RunPod) — 2026-06-06

## TL;DR
- **403 Qdrant RÉSOLU** (pont socat IP-pin tailnet). Validé par `probe_ok` écrit en 40s.
- **Bulk #2 bloqué** : `memory_v2.points=0` pendant 1h40, pod jamais EXITED → **hang** (pas un abort parité G7). Indiagnosticable faute de témoins → **tous pods éteints** (consigne).
- **Fix livré** (commit `6506dde`) : balises `stage_*` + timeouts clone/pip → le **prochain run se diagnostique depuis Waza** sans logs console.
- État Qdrant : `memory_v2` green, **0 point**. Aucune collection `stage_*`/`probe_ok` résiduelle (run bloqué tournait l'ancien bootstrap sans balises).

## Ce qui marche (acquis, ne pas refaire)
| Élément | Preuve |
|---|---|
| Pont socat `qd.ewutelo.cloud:443 → 100.64.0.14:443` via proxy `:1055` | `probe_ok` écrit en 40s (pod `l40a97nnkvhzw7`) |
| Clé Headscale éphémère `2164b58…` | réutilisable, join OK |
| PAT GitHub read-only (clone repos) | probe a cloné VPAI |
| Egress public direct (pas de proxy global) | préambule apt OK ; self-stop fiable |
| Préambule : retry git clone x5 | corrige le `rc=128` transitoire du bulk #1 |

## Le blocage (à élucider au prochain run)
Run `3bovrtxfj7sylc` (commit `af7f08b`, **avant** balises) : socat OK (sinon pod EXITED à G2),
puis hang entre G3 et G8. `points=0` 1h40 alors que `pod_ingest.py:230-264` upsert **par batch
de 128 incrémental** ⇒ G8 n'a jamais flushé. Suspects, par ordre :
1. **G3 clone `typebot.io`** (gros monorepo, aucun timeout dans l'ancien code) — le plus probable.
2. **G4 `pip install` torch/transformers** (lock lourd).
3. **G8 embedding** : download/charge `embeddinggemma-300m` (gated, HF_TOKEN) ou débit CPU
   trop lent (300M fp32, 16 vCPU, ~78,5k chunks). ⚠️ l'estimation README "$0.10-0.20" est
   probablement fausse si c'est ça (pod à **$0.48/h**).

## Reprise (étape suivante)
```bash
cd /home/mobuone/VPAI/scripts/memory/gpu_ingest
git pull                                   # avoir 6506dde (balises)
./provision_pod.sh --create                # WATCHDOG_MAX=14400 (4h) injecté par défaut
```
Puis **poll depuis Waza** (canal observable) :
```bash
set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a
Q="${QDRANT_URL%/}"; H=(-H "api-key: ${QDRANT_API_KEY}")
curl -fsS "${H[@]}" "$Q/collections" | jq -r '.result.collections[].name' | grep -E 'stage_|memory_v2|ingest_done'
curl -fsS "${H[@]}" "$Q/collections/memory_v2" | jq '.result.points_count'
```
**Arbre de décision** (quelle balise présente) :
- `stage_g2_qdrant_ok` seul, longtemps → hang **G3 clone** (typebot) → le timeout 300s le tuera maintenant ; lire quel repo dans logs console.
- `stage_g3_clone_done` mais pas `g4_*` → hang **pip** (timeout 1800s le tuera).
- `stage_g8_bulk_start` mais `points=0` longtemps → **embedding** (modèle HF ou CPU). Décision : pod **GPU** ou accepter run long (allonger watchdog).
- `stage_g8_bulk_start` + `points` qui grimpent → **sain**, laisser finir → `ingest_done` → self-stop.

## Reste à faire (après bulk OK)
1. **Teardown** : `--terminate <id>` ; **révoquer clé Headscale** (Headplane) ; révoquer **PAT** ; `rm /opt/workstation/configs/ai-memory-worker/pod-ingest.env` ; supprimer collections `stage_*` + `probe_ok` si restantes.
2. **Rotation secrets fuités en transcript** : `HF_TOKEN`, `QDRANT_API_KEY`, `RUNPOD_API_KEY`.
3. **M4** : repointer `search_memory.py` + `mcp__qdrant__qdrant-find` sur `memory_v2` ; **retirer** `r0-rebuild.flag` + le bloc `r0Rebuild` de `~/.claude/hooks/loi-op-enforcer.js` ; purger `.bak` state/spool.
4. **Plan B** : réorg `~/work` + manifeste M5.

## REX à durcir (noté, pas bloquant)
- Self-stop du **préambule** échoue sous la flakiness réseau qui cause l'échec (`curl -s …/dev/null`) → pod `lxwpqe80brlkrb` resté UP 13 min. Ajouter retry au self-stop préambule, OU watchdog adaptatif court tant que le bootstrap n'a pas posé `stage_g2_qdrant_ok`.

## Coûts engagés
probe ~$0.05 + bulk #1 (rc=128, ~13min) ~$0.10 + bulk #2 (hang 1h40) ~$0.80 ≈ **$0.95**.

## Commits
- `af7f08b` fix socat IP-pin (403 résolu)
- `6506dde` balises stage_* + timeouts clone/pip
