# SPEC — Harness d'autoring n8n (chantier A / Volet B) — 2026-07-18

**Statut** : spec Fable v2 (corrigée après inventaire Lane 3), à implémenter par agent Sonnet, revue adversariale Opus avant merge.
**Réf amont** : `ops/loops/plans/2026-07-18-HANDOFF-n8n-fiabilite-et-memoire.md` §Volet B ; périmètre validé `.planning/CHANTIERS-AUTONOMES-SANS-NAS.md` (commit 9eb7610) ; MCP natif câblé `4690c86` ; runbook `docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md` §8.

## Déjà livré — NE PAS REFAIRE (Lane 3 Sidecar)
- `scripts/n8n-validate-fallback.sh` : validateur R1 session-indépendant (structurel Python autoritaire + n8n-mcp HTTP best-effort, sentinel `[N8N-VALIDATE-CLI] PASS`).
- `scripts/deploy-workflow.sh` : REST PUT (R11) + publish (R10) + tolérance IF v2 existants (R9 déploiement).
- Gate R1 double marqueur MCP/CLI (LOI-OP).
- R9 : pattern string IF v2 prouvé `fixed` sur 2.30.7 (staging run 3, workflow `r9-probe`).

## But
Fermer la boucle **build → validate → deploy → verify → LEARN** : ce qui manque n'est pas l'outillage validate/deploy, c'est (1) la connaissance build-time curée, (2) la capture automatique des échecs en REX, (3) la doctrine d'usage du MCP natif comme autorité de schéma, (4) statuer R9 boolean.

## Livrables
1. **`docs/runbooks/GOTCHAS-N8N-2.30.md`** — fiche curée build-time, source unique injectée aux agents d'autoring : R9 scopé (string fixed / boolean non statué), R10/activeVersionId, R3-bis (import strip webhookId/onError → SQL), 1 webhook par path+méthode (collisions connues REX Sidecar L132-148), Save/Publish 2.x, Code node sandboxé/task runners ($env vide REX-MOP-TASKRUNNER), webhookPath corrompu (REX-2026-04-12b). Chaque entrée cite son REX/doc source.
2. **`scripts/n8n-authoring/rex-capture.sh`** — appelé sur tout échec validate/deploy/verify : append daté dans `docs/rex/REX-N8N-AUTORING.md` (workflow, étape, erreur brute, correction éventuelle). Brancher : `deploy-workflow.sh` et `n8n-validate-fallback.sh` l'invoquent sur FAIL (variable opt-out `REX_CAPTURE=0`).
3. **`docs/runbooks/RUNBOOK-N8N-AUTORING.md`** — doctrine de la boucle pour agents : ordre exact MCP natif (`get_sdk_reference` → `search_nodes`/`get_node_types` sur NOTRE instance → `create_workflow_from_code`/JSON file-first → `validate_workflow` instance) ; fallback CLI ; deploy ; verify exécution ; renvoi vers GOTCHAS. Court (~1 page), actionnable.
4. **R9 boolean — revalidation staging** (runbook §8 procédure) : rejouer le cas **boolean** IF v2 sur staging 2.30.7 (le cas string est déjà statué). Verdict → proposer le diff de scoping/retrait R9 dans CLAUDE.md + LOI-OP.md + hook enforcer **sans l'appliquer** (édition LOI = gate humain).
5. **Preuve E2E** : 1 workflow réel mineur via la boucle complète (build file-first → validate PASS → deploy → publish → exécution verte) + 1 échec simulé (fixture cassée) → entrée REX auto.

## Non-buts
Pas de génération auto de workflows ; pas de bump n8n-mcp docs-only ; pas d'édition UI ni `n8n import:workflow` ; pas de retrait unilatéral de R9.

## Critères d'acceptation
- GOTCHAS + RUNBOOK relus par Opus (revue adversariale) sans contresens vs REX cités.
- `rex-capture.sh` : échec simulé → entrée REX horodatée ; opt-out fonctionne ; aucun impact sur exit codes existants.
- R9 boolean : verdict staging documenté §8 + diff LOI proposé (non appliqué).
- E2E : preuve exécution verte + idempotence (re-deploy sans diff = no-op).
