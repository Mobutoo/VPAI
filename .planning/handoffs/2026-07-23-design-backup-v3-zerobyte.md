# Handoff — Design v3 refonte backup (piste B, en parallèle du colmatage piste A)

## Objectif

Produire le **design v3** de la refonte backup 3-2-1-1-0 (artefact texte), le faire **converger via Codex** (LOI règle 4), puis le présenter au **gate humain d'approbation** — prêt à exécuter, mais AUCUN code d'implémentation dans cette piste.

## Décisions prises (figées — ne pas re-discuter, sortie de 3 scouts + advisor + arbitrage opérateur)

- **Orchestrateur unique = l'app `nicotsx/zerobyte` sur Seko-VPN.** PAS le hub restic *hand-rolled* du rôle `banga/roles/lxc-zerobyte` (jamais déployé, NO-GO) → celui-ci est **abandonné** ; ses scripts de dump (`remote-export-seko.sh.j2`) restent une simple référence.
- **Upgrade zerobyte v0.26.0 → dernière (v0.41+)** = risque FAIBLE confirmé (aucun breaking DB destructif, tables VIDES sur l'instance, 0 `DROP` détecté, restic bumpé v0.19 sans migration repo). À valider en **préprod** : boot + 18 migrations Drizzle sans erreur + login admin post-upgrade.
- **2 briques manquantes, contribution UPSTREAM-FIRST (PR avec code), fork = fallback seulement** (seule voie compatible avec « toujours latest » ; PR-avec-code mergées en ~2 j chez ce mainteneur, feature-request-sans-code dorment — cf #305) :
  - **Brique A (séquentialité)** : `app/server/jobs/backup-execution.ts` (~l.25-29) remplacer la boucle fire-and-forget `for … executeBackup().catch()` par une boucle **`await`**. ~10 lignes, 0 migration. À rattacher à l'issue upstream **#305** « Avoid overlapping backups ».
  - **Brique B (drain auto)** : les primitives `getMirrorSyncStatus` + `syncMirror` existent déjà sur `main` (PR #755, backfill **manuel** UI). Il manque un **job périodique** (`*/5`) + une requête d'énumération des mirrors → rattrapage automatique dès que la cible revient. Bâtir sur `main`/≥v0.27.
- **Archi 2 couches (neutralise C1)** :
  - **Couche 1 — dump cohérent par source** (fichiers statiques) : réparée/créée par la **piste A** (voir handoff `2026-07-23-colmatage-dr-backup-urgent.md`). zerobyte ne backupe JAMAIS une DB vivante, seulement des chemins de dumps cohérents.
  - **Couche 2 — zerobyte (Seko)** backupe les chemins de dumps → **tampon restic local Seko** → **drain vers NAS banga** → **offsite S3 Object-Lock**.
- **Topologie** : séquentiel **1 source à la fois** (tampon = 1 backup max, 105 Go libres sur Seko = large) ; **Waza → banga direct LAN** (`192.168.1.18/24`, même /24 que waza `192.168.1.8`, transport **SSH/restic** — `sharenfs/sharesmb=off`, PAS de NFS/SMB) ; **Hetzner sélectif** (cas par cas, pas tout). Planning = **collecte à horaire fixe** (timers) + **drain opportuniste** (détection banga joignable). Transport drain Seko→banga = **SFTP sur SSH:22** (dispo), `rest-server` seulement si la perf l'exige.
- **Exigences non négociables du design** : **C1** = cohérence-à-la-capture (Couche 1, piste A) ; **H2** = restore-drill automatique réel (`restic dump latest | tar -tzf` ou équivalent) — zerobyte ne le fournit pas nativement, à ajouter. Traiter aussi M1 (`no_log`/passphrase), M2 (var healthcheck), M4 (rétention) hérités du NO-GO.
- **Risques à documenter** : (1) upgrade v0.26→v0.41 (valider préprod, pas in-place-prod à l'aveugle) ; (2) **RAM Seko** — 1,6 Go dispo, zerobyte déjà 511 Mo, sur le **hub VPN** → borne mémoire du process backup + éviter de scanner de gros arbres ; swap 2 Go préventif présent.

## Chemins / artefacts (absolus)

- Design à écrire : `/home/mobuone/work/infra/VPAI/docs/design/2026-07-23-refonte-backup-zerobyte-orchestrateur-seko.md` (créer `docs/design/` si absent).
- Docs à réconcilier / marquer périmées : `/home/mobuone/work/infra/VPAI/TECHNICAL-SPEC.md` (§5 Zerobyte), `/home/mobuone/work/infra/VPAI/docs/BACKUP-STRATEGY.md` (fév 2026, « push to Hetzner S3 » — périmé), `/home/mobuone/work/infra/banga/docs/superpowers/specs/2026-07-18-banga-x58-home-datacenter-design.md` (« zerobyte = hub restic banga » — abandonné).
- Code refs zerobyte (repo `github.com/nicotsx/zerobyte`, re-cloner si besoin) : `app/server/jobs/backup-execution.ts` (Brique A) ; `app/server/modules/backups/backups.execution.ts:330-430` (mirror) ; `backups.service.ts` `getMirrorSyncStatus`/`syncMirror` (Brique B). Licence AGPLv3 + CLA (OK usage interne).
- Handoff piste A (dépendance Couche 1) : `/home/mobuone/work/infra/VPAI/.planning/handoffs/2026-07-23-colmatage-dr-backup-urgent.md`.
- Accès (lecture, si vérif live nécessaire) : Sese `ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14` ; Seko `ssh -i ~/.ssh/seko-vpn-deploy mobuone@87.106.30.160` (`sudo -n docker`).

## Prochaine étape (action concrète)

1. Rédiger le design v3 dans `docs/design/2026-07-23-refonte-backup-zerobyte-orchestrateur-seko.md`, sections : Contexte & état réel (backup cassé/absent) · Archi 2 couches (schéma) · Les 2 briques upstream (A/B, fichiers:lignes, plan de PR) · Plan d'upgrade v0.26→v0.41 en préprod · 3-2-1-1-0 + traitement C1/H2/M1/M2/M4 · Risques (upgrade, RAM) · Phases de mise en œuvre · Gates humains.
2. Convergence Codex : `~/work/ops/loops/scripts/review-file.sh --sol docs/design/2026-07-23-refonte-backup-zerobyte-orchestrateur-seko.md` — intégrer les findings HIGH (rejeter un finding faux AVEC justification), boucler jusqu'à zéro bloquant.
3. Présenter au gate humain via `~/work/ops/loops/scripts/notify-gate.sh --artifact <chemin du design>`.

## Gates humains

- **Approbation du design** (après convergence Codex) via `notify-gate.sh --artifact`.
- **Bucket offsite S3 Object-Lock** + **clés SSH forced-command** = gates externes (billing / décision) — à lister dans le design, pas à trancher.
- **Aucun secret** dans le design (il part chez OpenAI à la convergence) ni dans un transcript.
- Ne PAS démarrer l'implémentation (upgrade, PR, déploiement) sans l'approbation du design.
