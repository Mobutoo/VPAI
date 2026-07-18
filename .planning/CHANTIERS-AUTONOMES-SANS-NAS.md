# Chantiers autonomes (sans NAS) — backlog post-n8n

**Date** : 2026-07-18 (après cutover n8n 2.30.7 + MCP natif câblé)
**Contexte** : le programme Loops (`~/work/ops/loops/PLAN.md`) est NAS-centrique — Phases 1/2/3/6/7/8
dépendent du PX58 (livraison WE 18-19/07). Ci-dessous ce qui est faisable **maintenant, sans NAS
ni gate humain bloquant**.

## Autonomes (Claude peut exécuter)

| # | Chantier | Valeur | Notes |
|---|---|---|---|
| A | **Volet B — harness d'autoring n8n** | ⭐ haute | Débloqué par le MCP natif câblé ce jour. Boucle déterministe create/validate/deploy de workflows via l'instance (schéma de nœuds à jour). Cœur du chantier n8n. |
| B | **RAG doc n8n 2.x** | moyenne | Plan prêt : `.planning/quick/260718-n8n-rag-docs-refresh/PLAN.md`. `git pull` du clone `~/work/refdocs/n8n-docs` + réingestion `memory_v3`. Réversible. |
| C | **n8n — webhooks dupliqués** | moyenne | Instagram/OpenCut/Meta partagent des paths webhook → échecs d'activation. Investigation + dédup/désactivation. |
| D | **n8n — déployer fix healthcheck `fa2bffa`** | basse | MCP réparé ; pousser les 2 workflows (`NZZ9Ke6DXJTlkasa`+`VNVPc1F0CVbVi2iT`). |
| E | **Hygiène disque** | basse | Prod Sese 81 % (overlay Sidecar +1.8G) ; zone morte 80-90 % (`project_sese_disk_2026_07_17_zone_morte`). Purge disk-guard. |
| F | **Loops Phase 4 — review loop Codex (PR)** | moyenne | Codex CLI dispo (T1.5 fait), pas de NAS. Seule phase loops sans dépendance NAS (avec Phase 5). |

## Bloqués (NAS ou gate humain — NE PAS attaquer)

- Loops Phases 1/2/3/6/7/8 → **NAS PX58** (livraison WE).
- Loops Phase 5 (Plane partout) → gate **rotation token Plane** (fuite 2×).
- CC Improvement Lab **P0-1** (scrubbing 46 876 secrets JSONL) → réservé/gate humain.
- Coffre agents **P1b/P2/P3/P4** → gate humain.
- Branche `audit/remediation-2026-07-02` (8 commits) → merge+deploy = gate humain.
- Bascule remotes SSH `*-new` + révocation `seko-vpn-deploy` → gate humain.

## Recommandation d'ordre
A (prolonge n8n + exploite le MCP tout juste câblé) → C+D (fiabilité n8n, rapides) → B (RAG) →
E (hygiène) → F (review loop).

## ✅ PÉRIMÈTRE VALIDÉ (humain, 2026-07-18) — à attaquer après redémarrage de `claude`
Sélection retenue : **A (Volet B autoring n8n)**, **C+D (Fiabilité n8n : webhooks dupliqués +
healthcheck fa2bffa)**, **E+F (Hygiène disque + review loop Codex)**.
**Écarté pour l'instant** : B (RAG doc n8n 2.x) — plan reste prêt si besoin.
Ordre suggéré au démarrage : C+D (rapides, ferment les follow-ups) → A (haute valeur) → E+F.
⚠️ Prérequis : QUITTER puis relancer `claude` (le MCP `n8n-native` n'est chargé qu'au démarrage
du process — `/clear` seul ne suffit pas).
