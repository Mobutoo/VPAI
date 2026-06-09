# État d'exécution — RAG memory_v3 (autonome) — 2026-06-10

GO utilisateur : implémenter toutes les recommandations de l'audit RAG 2026-06-09 + bulk ingestion
autonome (clé Headscale valide, confirmé). Contrat normatif :
`docs/superpowers/specs/2026-06-10-rag-v3-contracts.md`.

## Séquence

| # | Étape | Statut | Notes |
|---|---|---|---|
| 1 | Contrats figés | ✅ | spec 2026-06-10 |
| 2 | Workflow build (harness, core+search, hooks, ansible) | 🔄 EN COURS | runId `wf_e2d23e5d-ce8` |
| 3 | Baseline éval sur memory_v2 (dense) | ⏳ | `run_eval.py --collection memory_v2 --mode dense` AVANT toute bascule |
| 4 | Commits VPAI (par chantier) + push origin main | ⏳ | OBLIGATOIRE avant pod (REX #3 : pod clone GitHub). Remote = github-seko |
| 5 | Bootstrap memory_v3 (qdrant_bootstrap_v3.py) | ⏳ | idempotent, v2 intouchée |
| 6 | Deploy waza (`make deploy-workstation` ou rôle ciblé) | ⏳ | déploie worker mis à jour, collection_name reste memory_v2 |
| 7 | Pod GPU bulk → memory_v3 | ⏳ | `provision_pod.sh --create-gpu` + MEMORY_COLLECTION=memory_v3 ; watcher kill actif (REX #10) ; poll balises stage_* via Qdrant |
| 8 | Delta 13 repos via worker `--mode full --repos <delta>` → v3 | ⏳ | nohup nice, plusieurs heures OK |
| 9 | Éval v3 hybrid vs baseline v2 | ⏳ | flip seulement si recall@5 ne régresse pas |
| 10 | Flip `memory_collection_name=memory_v3` + redeploy + smoke | ⏳ | rollback = re-flip v2 |
| 11 | REX + commits finaux + MAJ mémoire | ⏳ | |

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
