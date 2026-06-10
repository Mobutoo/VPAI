# État d'exécution — RAG memory_v3 (autonome) — 2026-06-10

GO utilisateur : implémenter toutes les recommandations de l'audit RAG 2026-06-09 + bulk ingestion
autonome (clé Headscale valide, confirmé). Contrat normatif :
`docs/superpowers/specs/2026-06-10-rag-v3-contracts.md`.

## Séquence

| # | Étape | Statut | Notes |
|---|---|---|---|
| 1 | Contrats figés | ✅ | spec 2026-06-10 |
| 2 | Workflow build (harness, core+search, hooks, ansible) | ✅ | 4/4 PASS + intégration PASS (2 correctifs). 118 pytest, golden 76 q, hooks 9/9 |
| 3 | Baseline éval sur memory_v2 (dense) | ✅ | **r@1=0.6711 r@5=0.9474 MRR@10=0.7887** (76 q) → `.planning/eval/baseline-memory_v2-dense-full.json` |
| 4 | Commits + push | ✅ | VPAI 5 commits `14d7bf7..031cb98` pushés origin/main ; hooks ~/.claude `e224b4f` (local) |
| 5 | Bootstrap memory_v3 | ✅ | dense 768 cosine + bm25 idf, 11 index payload, 0 pt, v2 intouchée |
| 6 | Deploy waza (`make deploy-memory-worker`) | ✅ | ok=40 changed=14 failed=0 ; fastembed 0.8.0 live, eval/ déployé, timer consolidation dim 04:41 |
| 7 | Pod GPU bulk → memory_v3 | ✅ | RTX 4090 pod `tqey6cpnain08m` : **24 403 pts en 17 min** (G7 parité OK, bf16 drift 0.99990, 175.7 ch/s). Pod 1 `bcrrl718k3vy1v` tué à tort par watcher v1 (diag_gpu=INFO, pas échec) → watcher corrigé. Teardown : 15 balises supprimées, pods TERMINATED HTTP 204 |
| 8 | Delta 14 repos → v3 | 🔄 | unit `memory-delta-v3.service` (systemd-run, MemoryMax=4G, Nice=19, seuil loadavg 24 via /tmp/config-v3-delta.yml — 5 sessions Claude = load>13 structurel). Watcher `/tmp/watch_delta_v3.sh` ré-arme le timer worker à la fin. NOTE : run worker 30h obsolète (pid 3666222, cible v2) tué |
| 9 | Éval v3 hybrid vs baseline v2 | ✅ | **r@1 0.6711→0.7237, r@5 0.9474→0.9868, MRR@10 0.7887→0.8432 — zéro régression** (avant même le delta DOCS) |
| 10 | Flip `memory_collection_name=memory_v3` + redeploy + smoke | ✅ | inventory/group_vars/all/main.yml + redeploy (changed=1) ; smoke : hit exact GUIDE-CADDY §3.2 Deux CIDRs, floor → "not found" |
| 11 | REX + commits finaux + MAJ mémoire | 🔄 | |

## Post-session (rappels)

- Timer worker : ré-armé automatiquement par `/tmp/watch_delta_v3.sh` à la fin du delta (suspendu pendant, lock unique).
- MCP `qdrant-find` : les process MCP déjà lancés gardent v2 en cache → v3 effectif au prochain démarrage de session.
- Rotation secrets (HF/QDRANT/RUNPOD + clé Headscale + PAT) : toujours gate humain, inchangé.
- `--boost-usage` : à activer après accumulation de use_count (hook Stop r0-usage-tracker live depuis ce soir).
- `--rerank` : déposer bge-reranker-v2-m3 ONNX int8 dans le cache HF de waza pour l'activer (no-op sinon).
- Worker incrémental post-flip : nouveaux points v2→v3 cohérents (state per-fichier partagé, node_id stables).

## Faits critiques (ne pas redécouvrir)

- Secrets pod OK : `/opt/workstation/configs/ai-memory-worker/pod-ingest.env` (HEADSCALE_AUTHKEY,
  LOGIN_SERVER, GITHUB_PAT, SESE_TAILNET_IP) ; RUNPOD_API_KEY dans `/home/mobuone/work/saas/fantrad/.env`
  (ancien défaut `~/projects/` corrigé par chantier B).
- Procédure pod prouvée : REX-SESSION-2026-06-06-memory-bulk-gpu-bf16.md (bf16 batch 64, ~53 ch/s L4,
  arbre de décision balises dans 2026-06-06-memory-bulk-pod-handoff.md §Reprise).
- Self-stop pod = 403 possible → TOUJOURS `provision_pod.sh --stop <id>` depuis waza en filet.
- git HEAD local 45d190f > origin 4cd6a00 au démarrage — push requis (étape 4).
- Hooks ~/.claude : repo dirty préexistant (modifs gsd-*) — commits hooks SÉLECTIFS (seulement
  fichiers R0/usage-tracker), jamais `git add -A`.
- memory_v2 = 37 696 pts live (23 692 canoniques 7 sources + delta auto-découverte). Pod couvre
  les 7 sources de sources.pod.yml ; delta = repos auto-découverts restants via worker --repos.
- Interdit pendant build : mutation Qdrant, deploy, commits (c'est l'orchestrateur qui committe).
