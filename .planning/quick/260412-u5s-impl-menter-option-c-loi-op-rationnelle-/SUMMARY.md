# SUMMARY — Option C LOI OPÉRATIONNELLE gate reset

**Statut : SUPERSEDED** (2026-06-30)

Ce plan d'avril 2026 visait à rendre le gate R0 `loi-op-enforcer.js` auto-réarmant
multi-scénario (markers globaux `/tmp/claude-r0-done*`, réarmement aveugle).

Son intention a été **livrée puis dépassée** par le chantier R0-Continu / « système de
briques » de juin 2026 (cf MEMORY.md → `project_loi_system_bricks.md`,
`project_r0_continu.md`). Le travail effectif diffère et est supérieur :

| Plan avril (visé) | État réel juin (livré) |
|---|---|
| `SKILL.md` Step 4 = `rm -f /tmp/claude-r0-done*` (purge globale aveugle) | `Step 4 — Re-arm R0 (ledger-aware)` : ne purge que le marker global, **jamais** les markers per-topic `-<topic>` |
| 3 hooks à patcher (`loi-op-enforcer`, `r0-marker`, `error-escalator`) | les 3 réécrits (8–10 juin) + nouveaux : `r0-topic-injector.js`, `r0-usage-tracker.js`, `r0-rex-watcher.js` |
| L1 markers per-topic | livré : gate per-topic + auto-dérivation déterministe par projet (`topic-extract.js` + `regexFor(cwd)`) |
| L3 cascade reset | livré : cascade REX froid → context7/n8n-docs → WebSearch (R0/R5/R8) |

**Preuve** : `~/.claude/skills/Mobutoo/SKILL.md` (Step 4 ledger-aware, lignes 30-44) ;
hooks `~/.claude/hooks/r0-*.js` datés 8–10 juin.

**Commits de référence** (chantier briques) : `89aa26d` → `b8d315d` (13 commits),
spec+plan VPAI `4cd6a00`. Spec P6 :
`docs/superpowers/specs/2026-06-08-topics-portables-cross-projet.md`.

**Décision** : aucun travail à reprendre. Marqueur posé pour exclure ce plan des
scans « plans non implémentés ».
