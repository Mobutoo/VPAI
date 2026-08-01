# Design v3 — Refonte backup 3-2-1-1-0 : zerobyte (Seko) orchestrateur unique

> **Statut** : **APPROUVÉ 2026-07-23** (gate humain — 4 points validés : archi cible, déviation prémisse staging,
> exigences DR ajoutées, voie upstream-first + upgrade préprod). Convergé Codex 5 rounds (RESIDUAL, §9). L'implémentation
> (P0→FLIP, §7) peut démarrer **dans son ordre de phases, chacune avec son propre gate** — hors périmètre de cette piste B.
> **Date** : 2026-07-23
> **Périmètre** : artefact de conception uniquement. AUCUN code d'implémentation dans cette piste (piste B).
> **Dépendance amont** : « Couche 1 » (dumps cohérents) = **piste A, en cours** (code écrit + testé en sibling ;
> **déploiement prod = gate humain non encore franchi**) — `.planning/handoffs/2026-07-23-colmatage-dr-backup-urgent.md`.
> **P3 (Couche 2) est conditionné à des artefacts P1 réellement déployés et validés en prod**, pas seulement écrits.
> **Décisions figées** : `.planning/handoffs/2026-07-23-design-backup-v3-zerobyte.md` (3 scouts + advisor + arbitrage
> opérateur) — ne pas re-discuter ici.
> **Origine des exigences** : verdict NO-GO revue Opus 2026-07-21 sur le rôle abandonné `banga/roles/lxc-zerobyte`
> (`banga/.planning/STATE.md:217`).

---

## 1. Contexte & état réel

### 1.1 Ce qui est réellement en place (2026-07-23)

| Élément | État vérifié | Conséquence |
|---|---|---|
| App zerobyte (Seko-VPN) | Déployée en **v0.26.0** (`Seko-VPN/roles/zerobyte/defaults/main.yml:2`), UI :4096, ~511 Mo RSS | Orchestrateur présent mais sous-exploité |
| Rôle `banga/roles/lxc-zerobyte` (hub restic hand-rolled, modèle PULL) | **Jamais déployé — verdict NO-GO** | **Abandonné** (voir §5) |
| Dump cohérent Sese (`pre-backup.sh`) | **Cassé depuis le 17/02** : `set -euo pipefail` avorte à l'étape Redis (permission `dump.rdb`) → `qdrant/`, `n8n/`, `grafana/` **vides depuis des mois** | **Piste A** : correctif Redis+n8n **écrit** (`031008d`), **pas encore déployé** en prod |
| Backup coffre Vaultwarden (Seko, classe A) | **Inexistant EN PROD** — pas de timer/restic actif | **Piste A** : rôle `vaultwarden_backup` **écrit + testé sibling** (`64556f4`), **pas encore déployé** ; trou DR le plus urgent |
| Offsite (S3 Object-Lock) | **Absent** | Gate billing (voir §8) |
| Restore-drill (« le 0 » de 3-2-1-1-0) | **Absent** | H2 à ajouter (§5) |

> **Provenance des états « vérifié »** : colonne « État vérifié » = scouts read-only sur live (piste A) + mémoire projet
> (`banga/.planning/STATE.md:217` pour le NO-GO ; `Seko-VPN/roles/zerobyte/defaults/main.yml:2` pour v0.26.0). Les
> chiffres de capacité/RAM (105 Go libres Seko, 1,6 Go RAM dispo, ~511 Mo zerobyte — §6) proviennent d'audits antérieurs
> et **restent à re-mesurer** au moment de l'implémentation (commande + date + sortie), non re-capturés dans cette
> session de conception.

### 1.2 Ce que ce design remplace

La stratégie backup décrite dans les docs de février 2026 (modèle « zerobyte tire les données via VPN → push
Hetzner S3, NAS via sync S3 à T+6 mois ») est **périmée**. Docs **marqués « SUPERSÉDÉ » le 2026-07-23** (à l'approbation
du design) — bannière en tête pointant ce design :

- `TECHNICAL-SPEC.md` §5 (Zerobyte — pull VPN → S3).
- `docs/BACKUP-STRATEGY.md` (v1.0.0, fév 2026 — pull VPN → S3, NAS à T+6 mois).
- `docs/DISASTER-RECOVERY.md` (chemins de restore via pull S3 + NAS mirror T+6 mois).
- `banga/docs/superpowers/specs/2026-07-18-banga-x58-home-datacenter-design.md` §9 + §10 (modèle PULL hub sur banga —
  **abandonné**, voir §5).

---

## 2. Architecture 2 couches

La cause racine du NO-GO (**C1 — perte de données silencieuse**) est neutralisée *structurellement* en séparant
**la capture cohérente** (Couche 1) de **l'orchestration restic** (Couche 2). zerobyte ne backupe **jamais** une DB
vivante — uniquement des chemins de **dumps statiques cohérents**.

### 2.1 Schéma

```
COUCHE 1 — dump cohérent par source (piste A)          COUCHE 2 — zerobyte (Seko) orchestre restic
=============================================          ============================================

┌─ Sese-AI (OVH, 100.64.0.14) ──────────┐
│ pg_dump/pg_dumpall · Qdrant snapshot   │
│ n8n export · Grafana · Redis (fix perm)│──dump──►  /opt/javisi/backups/  (fichiers statiques, non-vides ou alerte)
│ chaque dump : non-vide OU alerte (½ C1)│                    │
└────────────────────────────────────────┘                    │  (VPN Tailscale, lecture des dumps)
                                                               ▼
┌─ Seko-VPN (Ionos, hub) ────────────────┐        ┌──────────────────────────────┐
│ Vaultwarden /vaultwarden backup         │──dump─►│  zerobyte (app, :4096)        │
│ Headscale VACUUM INTO · Gitea dump      │        │  1 source à la fois (séquentiel)│
└────────────────────────────────────────┘        │  gate fraîcheur+plancher (C1)  │
                                                   │            │                  │
                                                   │            ▼                  │
                                       transit     │  restic repo LOCAL Seko       │  ← STAGING (transit, non compté)
                                     (non compté)  │  (« tampon », rétention courte)│     capacité = accumulation pendant
                                                   └───────┬───────────────────────┘     indispo banga ; purgé au drain
                                                           │ drain opportuniste (banga joignable)
                                                           │ SFTP/restic sur SSH:22 (rest-server si perf l'exige)
                                                           ▼
                                       COPIE 2     ┌──────────────────────────────┐
┌─ Waza (Pi, 192.168.1.8) ───────────────┐        │  banga NAS (192.168.1.18/24)  │  ← GFS 7d/4w/6m/2y
│ ~/work (hors caches/binaires)           │──SSH/restic LAN direct──────────────►│  tank/backups (ZFS, HDD)      │
│ ~/.claude (secrets exclus)              │  (même /24, sharenfs/sharesmb=off)   │  sharenfs/sharesmb=off        │
└────────────────────────────────────────┘        └───────┬───────────────────────┘
                                                           │ réplication offsite (restic copy)
                                                           │ SNAPSHOTS TAGGÉS « verified » UNIQUEMENT
                                                           ▼
                                    COPIE 3 (immuable) ┌──────────────────────────┐
                                                       │  S3 Object-Lock COMPLIANCE │  ← offsite sélectif · GFS ≥ lock
                                                       │  (Falkenstein, DC distinct)│
                                                       └──────────────────────────┘

VÉRIFICATION (« le 0 ») : restore-drill automatique + restic check → tag « verified » → réplication offsite ;
échec = quarantaine du repo + alerte, les repos sains continuent (§5, H2)
```

### 2.2 Topologie & planning (décisions figées)

- **Séquentiel, 1 source à la fois** : le repo restic **Seko = staging transitoire** (rétention courte, purgé après
  drain confirmé vers banga) — il ne conserve **pas** l'historique GFS (qui vit sur **banga + offsite**). Il ne conserve
  **pas** GFS, mais il doit **absorber l'accumulation** quand banga est injoignable (collecte sur timer fixe pendant que
  le drain est opportuniste).
- **Dimensionnement du staging** (pas « 1 snapshot ») = **volume initial d'une passe complète des sources** + (**débit
  quotidien de nouvelles sauvegardes** × **durée max d'indisponibilité banga tolérée**) + marge — à raffiner avec la
  fréquence réelle des collectes ; 105 Go libres = confortable, mais pas illimité. Deux garde-fous obligatoires :
  - **Backpressure** : si le staging franchit un seuil haut (ex. 80 %), la collecte se **met en pause** (plutôt que
    saturer le disque du hub VPN) + **alerte de capacité** (dead-man M2).
  - **Gel sur quarantaine / drain bloqué** : si banga est en quarantaine ou injoignable, le staging **NE purge PAS**
    (rétention gelée/étendue) pour préserver le RPO tant que le drain n'a pas repris — c'est le **seul filet avant
    FLIP** (pas d'offsite de secours tant que P6b/FLIP non faits). Au-delà de la capacité staging, le backpressure
    protège le hub au prix d'un RPO dégradé **signalé** (jamais de perte silencieuse).
- **Dimensionnement banga/offsite** = pire cas **après GFS + prune** (§5.2, M4).
- **Waza → banga en LAN direct** (`192.168.1.8` → `192.168.1.18`, même `/24`) : transport **SSH/restic**,
  `sharenfs/sharesmb=off` (**pas** de NFS/SMB). Waza ne transite **pas** par Seko.
- **Hetzner (Prod Apps CX22) = offsite sélectif** (cas par cas, pas « tout »).
- **Planning** = **collecte à horaire fixe** (timers) + **drain opportuniste** (déclenché sur détection de banga
  joignable — banga n'est pas 24/7).
- **Transport drain Seko→banga** = **SFTP sur SSH:22** (déjà disponible) ; `rest-server` seulement si la performance
  l'exige (décision de mise en œuvre, pas de conception).
- **Cycle drain→purge ATOMIQUE** (la purge du staging n'est jamais une suppression aveugle) : (1) `restic copy`
  staging → banga ; (2) **preuve de copie** = marqueur **`drained`** = le snapshot cible **existe sur banga** ET passe
  `restic check` (**distinct** du marqueur `verified` de §5.2 : `drained` n'exige PAS le restore-drill — il ne gate que
  la purge, pas la réplication offsite ; c'est pourquoi la purge **ne dépend pas de P7**) ; (3) **confirmation** ;
  (4) **seulement alors** expiration côté staging, avec **rétention plancher** (garder ≥ 1 snapshot récent tant que non
  re-drainé) ; (5) **gel sur toute erreur** (staging conservé, alerte) — jamais d'`forget` staging sans (2)+(3). Ce
  cycle est un **livrable de phase** (P4 manuel / P5 auto, §7), pas seulement une intention.

---

## 3. Les 2 briques manquantes — contribution UPSTREAM-FIRST

**Voie unique compatible avec la doctrine « toujours latest »** : PR **avec code** au dépôt `github.com/nicotsx/zerobyte`.
Heuristique (décisions figées, à re-confirmer sur l'historique réel du dépôt avant de s'y fier) : chez ce mainteneur les
PR-avec-code sont traitées vite, les *feature-requests sans code* dorment (cf #305). Le choix upstream-first ne **dépend
pas** de ce délai : **fork = fallback** si la PR traîne. Licence **AGPLv3 + CLA** — OK pour usage interne.

> **État de vérification (scout, 2026-07-22)** : le clone consulté était dans le scratchpad d'une **session tierce**
> (éphémère, à re-cloner au moment de la PR). Refs ci-dessous confirmées sur **v0.26.0** ET sur `origin/main`@`c1929be`
> (2026-07-22) — à re-confirmer sur le HEAD réel au moment du travail.

### 3.1 Brique A — séquentialité (anti-chevauchement)

- **Fichier** : `app/server/jobs/backup-execution.ts`.
- **Problème** : boucle *fire-and-forget* — chaque backup lancé sans attendre le précédent :
  ```ts
  // v0.26.0 l.25-29 / origin/main l.25-27 (service renommé backupsExecutionService → backupsService)
  for (const scheduleId of scheduleIds) {
      backupsService.executeBackup(scheduleId).catch((err) => { logger.error(...); });
  }
  ```
- **Correctif** : remplacer par une boucle **`await`** (séquentielle). **~10 lignes, 0 migration.**
- **Rattachement** : issue upstream **#305 « Avoid overlapping backups »**.
- **Confirmé non corrigé upstream** entre v0.26.0 et 2026-07-22 → pertinent sur la cible d'upgrade.
- **Rôle dans le design** : garantit le « 1 source à la fois » côté app (le séquentiel de collecte côté staging en
  dépend — le staging **accumule** néanmoins pendant une indispo banga, §2.2, ce n'est **pas** « 1 backup max »).

### 3.2 Brique B — drain automatique

- **Primitives déjà présentes sur `main`** (PR **#755**, commit `d2f65716`), **ABSENTES de v0.26.0** :
  - `backups.service.ts:681` — `getMirrorSyncStatus(scheduleIdOrShortId, mirrorShortId)`
  - `backups.service.ts:728` — `syncMirror(scheduleIdOrShortId, mirrorShortId, snapshotIds?)`
- **Manque** : ces primitives ne sont appelées **que par le contrôleur HTTP** (`backups.controller.ts:166-177`,
  backfill **manuel** via UI). **Aucun job périodique** sous `app/server/jobs/` ne les invoque (confirmé `git grep`).
- **Correctif** : ajouter un **job périodique** (`app/server/jobs/mirror-sync.ts`, cadence `*/5 * * * *` = toutes les
  5 min, fuseau du conteneur) qui **énumère les mirrors** et appelle `syncMirror` pour ceux en retard → rattrapage
  automatique dès que la cible (banga) revient.
- **Base** : primitives présentes sur `main` (PR #755) et **absentes de v0.26.0** ⇒ **vérifier leur présence sur le TAG
  cible exact** retenu en P0 (ne pas présumer un simple « ≥ v0.27 » générique). **Brique B dépend de l'upgrade** (§4).
- **Rôle dans le design** : réalise le **drain opportuniste** Seko-tampon → banga sans intervention (banga non-24/7).

### 3.3 Verrou singleton (transverse A + B)

La boucle `await` (Brique A) garantit le séquentiel **au sein d'une exécution**, mais **deux exécutions planifiées** (ou
le job `mirror-sync` `*/5` qui recouvre un backup encore en cours) peuvent **se chevaucher**. Exigence : un **verrou
singleton persistant** (lockfile/verrou applicatif avec **expiration contrôlée** anti-lock-zombie) **couvrant à la fois
`backup-execution` et `mirror-sync`** ; une exécution qui ne prend pas le verrou **s'abstient** (pas d'attente
illimitée). **Test de chevauchement** requis. À porter dans les PR A/B ou en glue de déploiement.

### 3.4 Plan de PR (les deux briques)

1. Re-cloner le dépôt, brancher sur le tag/HEAD de la version cible.
2. Brique A : PR isolée (séquentialité) rattachée à #305. Brique B : PR isolée (job `*/5`).
3. Test local (build + boot + migrations) avant soumission.
4. **Si non mergé sous délai raisonnable → fork épinglé** (`zerobyte_version` pointant le fork) — dette explicite à
   re-synchroniser à chaque upstream.

**État Brique A (2026-07-28)** : PR soumise — [nicotsx/zerobyte#1077](https://github.com/nicotsx/zerobyte/pull/1077),
fork `Mobutoo/zerobyte`, branche `fix/sequential-backup-execution`, re-clonée fraîche sur `main` (pas le clone
éphémère de la session de conception — risque R3 traité). Diff d'une ligne (`await` ajouté), le contexte englobant
était déjà `async`. **En attente** : merge mainteneur (CLA bot va commenter au premier push, signature = action
opérateur, pas automatisable) — si pas mergé sous délai raisonnable, décision fork épinglé à prendre (§8). **Résiduel
non traité par cette PR** : le **verrou singleton inter-exécutions** (§3.3) — la boucle `await` sérialise *au sein*
d'une exécution de `BackupExecutionJob`, mais ne protège pas contre deux exécutions planifiées qui se chevaucheraient
(ou `mirror-sync` en Brique B recouvrant un backup en cours). Le "test de chevauchement" exigé par §3.3 reste à faire
avant P3/le déploiement effectif de la séquentialité multi-source.

---

## 4. Plan d'upgrade v0.26.0 → v0.41.x (préprod d'abord)

**Risque = NON ÉVALUÉ tant que P0 n'a pas réussi** ; **hypothèse de départ = FAIBLE** sur les éléments suivants,
**provisoires jusqu'à preuve préprod sur le tag retenu** : aucun breaking DB destructif attendu, tables **vides** sur
l'instance, **0 `DROP`** détecté (extrait), restic bumpé v0.19 réputé **sans migration de repo**, **~18 migrations
Drizzle** (nombre à re-compter sur la cible). L'évaluation finale du risque est **consignée à l'issue de P0**. **Jamais
in-place-prod à l'aveugle.**

> **À confirmer en P0** : la **version stable cible exacte** (tags `v0.41.0-beta.1/2/3` observés ; stable `v0.41.0` non
> confirmé dans l'extrait — `git tag --sort=-creatordate | head`), la **liste réelle des migrations**, et les **sorties de
> validation** (boot, migrations, login). **Brique B exige que le TAG cible contienne les primitives PR #755** — à
> confirmer sur ce tag exact, pas via un « ≥ v0.27 » présumé (§3.2). Ces preuves reproductibles sont le livrable du gate
> GO préprod (§8) — le « risque faible » n'est acté qu'après.

### Validation préprod (critères GO/NO-GO)

- [x] Boot du conteneur sans crash.
- [x] **Toutes les migrations Drizzle du tag retenu** appliquées sans erreur (**nombre observé : 4** — `00004-concat-path-name`, `00005-split-backup-include-paths`, `00006-map-smb-files-to-container-uid-gid`, `00007-require-recovery-key-redownload` — le repo de test partait déjà au checkpoint `00003` via un boot v0.26.0 préalable ; **~18 était une estimation, non confirmée** — le nombre réel de migrations à appliquer depuis v0.26.0 est 4).
- [x] Login admin fonctionnel **post-upgrade** (logout/login réel avec les identifiants créés sous v0.26.0, testé via Playwright).
- [x] restic embarqué = v0.19 (**0.19.1 confirmé**, `restic version` dans le conteneur v0.41.0). **Résiduel non couvert** : aucun repository restic réel n'a été configuré dans ce drill (uniquement onboarding + admin) — la lecture d'un **repo restic existant** après upgrade reste à valider avec un volume/repository réellement créé.
- [ ] (si Briques A/B intégrées via fork) build + boot du fork OK — hors périmètre de ce drill (Brique A pas encore intégrée).

**Preuve (2026-07-28)** : drill local sur waza, `docker --context local`, image `ghcr.io/nicotsx/zerobyte:v0.26.0` bootée avec `APP_SECRET` fixe et un volume vierge → admin créé (Playwright) → conteneur remplacé par `ghcr.io/nicotsx/zerobyte:v0.41.0` **sur le même volume** (même `APP_SECRET`) → migrations rejouées en clair dans les logs → login post-upgrade confirmé. Aucun conteneur/volume prod touché ; tout supprimé après le test. **Tag stable cible confirmé : `v0.41.0`** (`git ls-remote --tags` — le doute du §4 sur l'existence d'un stable est levé).

**GO préprod = prérequis de l'upgrade prod** (gate humain, §8). **Verdict : GO préprod** sur les 3 critères couverts ; le résiduel restic-repo est à couvrir avant le déploiement prod P2 (test complémentaire léger, pas bloquant pour le reste de la préparation P2).

**P2 DÉPLOYÉ EN PROD 2026-07-28** (Seko, par l'opérateur — `--ask-vault-pass` hors de portée de l'agent). Vérifié live : conteneur `zerobyte:v0.41.0-vpai-fixA` up, **4 migrations rejouées identiques au drill préprod** (`00004`→`00007`, 0 erreur), page `/login` opérationnelle. Image = **fork épinglé** (`Mobutoo/zerobyte` + Brique A cherry-pickée sur le tag `v0.41.0` exact), pas l'image upstream — cf. §3.4 pour l'état de la PR #1077 et la dette de resynchronisation.

---

## 5. 3-2-1-1-0 & traitement C1 / H2 / M1 / M2 / M4

### 5.1 Couverture 3-2-1-1-0

> Le **staging Seko est un transit**, PAS une copie durable (purgé après drain) — il **n'est jamais compté** comme copie.
> Les copies durables sont **la donnée vive + banga NAS + offsite**. Conséquence : une source **NAS-seul** n'a que
> **2 copies durables** (vive + NAS) → elle est **« 2-1 »** (pas encore 3-2-1), et n'atteint 3-2-1-1-0 **que** si elle
> est répliquée hors site. La matrice §5.1.1 est explicite par source.

| Chiffre | Réalisation dans ce design (source couverte offsite) |
|---|---|
| **3 copies** | donnée **vive** · **banga NAS** (`tank/backups`, GFS) · **offsite S3** (le staging Seko = transit, non compté) |
| **2 média** | HDD ZFS banga **+** stockage objet S3 (+ NVMe de la source) — média physiquement distincts |
| **1 offsite** | S3 Hetzner (Falkenstein), DC distinct de Seko/banga/waza |
| **1 immuable** | Bucket **Object-Lock mode COMPLIANCE** (à la création, non rétroactif) — seul mécanisme fermant « Seko compromis + creds volés efface tout » |
| **0 erreur** | **Restore-drill automatique** (H2) + `restic check` + dead-man → échec = **quarantaine repo + alerte** |

#### 5.1.1 Matrice de couverture par source

> Le périmètre offsite est **sélectif** (décision figée : « Hetzner cas par cas, pas tout »). La colonne offsite ci-dessous
> est une **proposition à arbitrer** au gate P6, pas une valeur figée. **Toute source retenue pour l'offsite au gate P6
> doit se voir attribuer une cadence de vérification** produisant des snapshots `verified` (la réplication d'une source
> non vérifiée est interdite — H2) : la vérif « hebdo sur sources critiques » (§5.2) est un **plancher**, pas la liste
> exhaustive.

| Source (Couche 1) | Capture cohérente | banga NAS (GFS) | Offsite (immuable) | Niveau |
|---|---|---|---|---|
| Seko — **Vaultwarden** (classe A) | `/vaultwarden backup` **+ répertoire de données** (voir note) | ✅ | ✅ (critique) | 3-2-1-1-0 |
| Seko — **Headscale** | `VACUUM INTO` | ✅ | ✅ (critique) | 3-2-1-1-0 |
| Seko — Gitea | `gitea dump` | ✅ | ⚠️ à arbitrer | **2-1** (vive+NAS) → 3-2-1-1-0 si retenu offsite au gate P6 |
| Sese — **pg** (n8n/openclaw/litellm) | `pg_dump`/`pg_dumpall` | ✅ | ✅ (critique) | 3-2-1-1-0 |
| Sese — Qdrant / n8n / Grafana / Redis | snapshot / export / RDB | ✅ | ⚠️ à arbitrer (volumineux) | **2-1** (vive+NAS) → 3-2-1-1-0 si offsite |
| Waza — `~/work` + `~/.claude` (secrets exclus) | copie | ✅ (LAN direct) | ⚠️ à arbitrer | **2-1** (vive+NAS) → 3-2-1-1-0 si offsite |
| Hetzner Prod Apps (CX22) | cas par cas | ⚠️ sélectif | ⚠️ sélectif | selon décision |

> **Vaultwarden — composants complets** : `/vaultwarden backup` ne couvre que la **base SQLite** (+ `config.json`). La
> restauration complète exige aussi le **répertoire de données** : `attachments/`, `sends/`, `rsa_key*` (clés JWT),
> `icon_cache/` (optionnel). La capture Couche 1 (**piste A**, rôle `vaultwarden_backup`) **doit** inclure ces fichiers
> et le **restore-drill (H2) doit les vérifier** — **point de coordination avec la piste A** (rôle **écrit/testé, pas
> déployé** ; à auditer sur ce périmètre avant de compter Vaultwarden comme « 3-2-1-1-0 »).

> **Waza `~/.claude` — « secrets exclus » doit être exécutable** : définir une **liste d'exclusion exhaustive** (ou une
> allowlist) — a minima `~/.claude/**/*.credentials.json`, tokens, `.env`, clés — et un **contrôle post-snapshot**
> (scan de motifs de secrets) **avant réplication** ; un snapshot où le scan détecte un secret **n'est pas répliqué**.
> Sans liste ni test, « secrets exclus » n'est pas une garantie.

### 5.2 Traitement des exigences du NO-GO

> Sévérités : **C1 = CRITICAL** (littéral dans le verdict). H2/M1/M2/M4 non labellisés littéralement — sévérité lue par
> convention de préfixe (**H = HIGH, M = MEDIUM**). Le verdict cite aussi **H1** (snapshot tronqué committé) et **M3**
> (offsite réplique un repo corrompu) — couverts ci-dessous par les mêmes correctifs.

**C1 — perte de données silencieuse (CRITICAL)**
- *Origine* : `restic backup --stdin` rapporte `OK` sur flux vide/tronqué (`tar -C /dossier-vide .` = rc=0, archive ~45 o) ;
  le commentaire de `remote-export-sese.sh.j2` qui prétendait s'en protéger était **FAUX**.
- *Neutralisation structurelle* : zerobyte v3 backupe des **fichiers statiques**, **pas** de pipe `--stdin` → le vecteur
  exact disparaît.
- *Risque résiduel* (dump vide/périmé backupé silencieusement) traité en **deux gardes** :
  - **Amont (Couche 1, piste A)** : chaque dump doit produire un fichier **non-vide** ou lever une **alerte explicite**
    (échec par-étape non masqué par un `set -e` global).
  - **Amont — manifeste atomique** : la Couche 1 (piste A) **produit chaque dump atomiquement** (écriture temporaire →
    `fsync` → rename) et **écrit un manifeste horodaté** listant, **par artefact attendu** : nom, `mtime`, **taille** et
    **somme de contrôle** (ex. sha256). Le manifeste n'est écrit **qu'après** succès de tous les dumps.
  - **Aval (Couche 2, ce design) — mécanisme exécutable** : un **wrapper `pre-backup-gate`** s'exécute **avant chaque
    snapshot** zerobyte (hook pre-backup, ou wrapper enveloppant l'appel restic). Il valide **le manifeste et CHAQUE
    artefact individuellement** (table de seuils versionnée par source) : (a) **présence** de tous les artefacts
    attendus ; (b) **fraîcheur par artefact** (`mtime` de **chaque** fichier < seuil — pas seulement le plus récent du
    répertoire) ; (c) **taille ≥ plancher** par artefact ; (d) **somme de contrôle recalculée = manifeste** (détecte un
    dump **tronqué même au-dessus du plancher** — c'est ce qui ferme **H1**). **Échec → code non nul → snapshot AVORTÉ
    (jamais committé) + alerte** (dead-man M2). Seuils, codes et **test d'intégration validés en P3** (source vide,
    périmée, **et tronquée-mais-volumineuse** doivent toutes faire échouer le gate).
- *Gate dur* : `backup_offsite_enabled=true` **interdit** tant que C1 n'est pas levé (héritage NO-GO).

**H2 — le « 0 » (restore-drill absent) (HIGH)**
- *Origine* : `restic check` valide les **packs**, pas le **payload** ; aucun restore-drill.
- *Correctif — méthode* : **restore réel vers un répertoire temporaire** puis **assertion de contenu explicite** —
  `restic restore <snapshot> --target <tmp> --include <chemin-canari>` (ou `restic dump <snapshot> <fichier>` pour un
  **fichier** unique — `restic dump` d'un **répertoire** émet un **tar** brut, pas gzip : ne pas présumer `tar -tzf`).
  Pour les **dumps SQL**, l'assertion `count(*)` **exige un import réel** : restaurer le dump → l'**importer dans une
  instance jetable/isolée** (conteneur pg éphémère, VW/HS sur volume temporaire) → démarrer le service le temps de la
  requête → vérifier avec des **requêtes complètes + seuil attendu**, ex. `SELECT count(*) FROM users;` (VW) attendu
  **> 0 et cohérent avec la prod**, `SELECT count(*) FROM <table_clé>;` (pg) ≥ seuil connu, `PRAGMA integrity_check;`
  (SQLite VW/HS/Gitea) = `ok` → détruire l'instance. Pas de validation « à froid » sur le seul fichier pour les bases.
- *Marqueur de snapshot validé* (résout la course entre contrôles hebdo/mensuels et réplication) : un snapshot passe
  `verified` **dans un workflow unique** qui exige DEUX conditions au moment du marquage : (1) **son** restore-drill OK
  (lecture réelle du payload canari), **et** (2) une **lecture intégrale prouvée des packs de CE snapshot** —
  `restic check --read-data` (ou `--read-data-subset` ciblant explicitement les packs du snapshot) **postérieur** à sa
  création. Un `restic check` **par défaut ne lit pas les données** (structure/métadonnées seulement) : il **ne suffit
  pas** ; un check antérieur au snapshot ne le valide pas non plus.
  **Seuls les snapshots `verified` sont répliqués vers l'offsite** (referme aussi M3 : un snapshot non vérifié ne part
  jamais vers le bucket immuable).
- *Où / cadence / échec* :
  | Contrôle | Hôte | Repo cible | Cadence | Échec |
  |---|---|---|---|---|
  | Restore-drill contenu (canari) → tag `verified` | banga (compute + copie NAS) | banga NAS | ≥ hebdo sur sources critiques | **quarantaine du repo NAS** (voir ci-dessous) |
  | Restore-drill DoD complet (VW+HS+pg) | banga + hôte de test | **NAS ET offsite** | trimestriel | quarantaine + alerte |
  | `restic check --read-data-subset=n/T` (rotation déterministe, 100 % des packs sur T mois) + `check --read-data` **complet annuel** | banga | chaque repo | mensuel (sous-ensemble tournant) + annuel (complet) | quarantaine + alerte |
  | Dead-man (cron muet) | healthchecks.io/self-hosted | tous les jobs | continu | alerte (dead-man off = fail-loud) |
- *Comportement sur échec (quarantaine, pas d'aggravation du RPO)* :
  - Le repo défaillant est **marqué en quarantaine** : réplication offsite **depuis ce repo suspendue**, mais les
    backups **continuent vers les repos sains** (on stoppe l'alimentation de **ce** repo, **pas** toute la chaîne).
  - **Déblocage manuel après diagnostic** uniquement (jamais de reprise automatique silencieuse) ; alerte à chaque
    passage en quarantaine.
- *Aligné* sur la doctrine « +0 vérifié » déjà actée (`docs/plans/2026-07-16-nas-tier-build-plan.md:49` ; banga §9) :
  **échec de vérif = arrêter les backups vers ce repo, pas juste alerter.**
- *Gate dur* : `backup_offsite_enabled=true` interdit tant que H2 n'est pas implémenté (héritage NO-GO ; voir aussi la
  **validation offsite contrôlée pré-FLIP**, §7 P6b).

**M1 — passphrase en clair / staging non nettoyé (MEDIUM)** (+ escrow DR)
- Les passphrases restic des repos gérés par l'app sont **dans la config chiffrée de zerobyte**, jamais en clair côté
  Ansible.
- Toute glue Ansible (scripts de drain, creds offsite, restore-drill) qui manipule une passphrase/env restic : source
  **Vault** + **`no_log: true`** + **aucun staging en clair** (pas de fichier temporaire world-readable).
- **Escrow HORS-Seko (exigence DR — HIGH)** : si **Seko est perdu intégralement**, les passphrases stockées uniquement
  dans la config zerobyte **disparaissent** → NAS et offsite deviennent **irrécupérables**. Piège aggravant : le coffre
  classe A (**Vaultwarden**) est **lui-même sur Seko** → il **ne peut pas** servir d'escrow. Les passphrases restic
  (staging/NAS/offsite) + la clé de déchiffrement doivent être **séquestrées hors de Seko** (ex. `rbw`/Vaultwarden côté
  **Waza** + **une copie scellée hors-ligne**), et **leur récupération testée dans le drill DR** (un restore depuis
  l'offsite doit être prouvé en n'utilisant **que** l'escrow, sans Seko). Gestion des valeurs = gate humain (secrets),
  jamais dans ce design.

**M2 — dead-man silencieusement off (MEDIUM)**
- Interdiction de var morte type `backup_healthcheck_url`. Tous les jobs périodiques (collecte, drain, offsite,
  restore-drill, `restic check`) pinguent une **var dead-man réelle** (pattern `vault_healthchecks_url`), **fail-loud**
  si absente (pas de `default('')` silencieux).

**M4 — rétention (MEDIUM)** (+ M3)
- **GFS différencié** (la cadence de vérif/réplication ≥ hebdo interdit un palier *daily* offsite cohérent) :
  - **banga NAS** (reçoit chaque snapshot drainé) : `--keep-daily 7 --keep-weekly 4 --keep-monthly 6 --keep-yearly 2
    --prune`. Le **palier quotidien (récupération J-1..J-7) est une capacité NAS-locale**.
  - **offsite** (reçoit uniquement les snapshots `verified`, ≥ hebdo) : `--keep-weekly 4 --keep-monthly 6 --keep-yearly 2`
    — **pas de palier daily** (aligné sur la cadence de vérification). Pour un palier daily offsite, il faudrait
    **vérifier quotidiennement** les sources critiques → décision de dimensionnement au gate P6.
  - **staging Seko** : pas de GFS (rétention courte, purge après drain — §2.2).
- **Interaction Object-Lock ↔ prune** (offsite COMPLIANCE) : un objet ne peut être supprimé **avant** l'expiration de
  **son** lock.
  - **Fenêtre de rétention offsite ≥ durée du lock** ; la seule comparaison de fenêtres **ne suffit pas** : la stratégie
    de prune doit tenir compte de l'**âge réel de chaque objet** et **traiter les refus de suppression** (logguer,
    re-tenter après expiration, **ne pas** compter comme erreur mettant le repo en quarantaine).
  - **Schéma à valider par un test complet AVANT provisioning** du bucket (un mode COMPLIANCE est irréversible) — la
    compatibilité `restic forget --prune` ↔ Object-Lock est une **hypothèse à prouver en préprod**, pas un acquis.
- **M3** (offsite réplique un repo corrompu) : couvert par le **marqueur `verified`** (H2) — seuls les snapshots
  vérifiés sont répliqués ; un repo en quarantaine ne réplique rien. Chaînage de jobs surveillé par le dead-man (M2).

> **Réserve de revue (finding rejeté, remonté au gate)** : la revue Codex round 2 a re-signalé « traitement des refus de
> suppression non défini » — **rejeté** : il **est** défini ci-dessus (logguer / re-tenter / ne pas mettre en
> quarantaine). Seul le **mécanisme d'implémentation** est différé, cohérent avec le périmètre *conception uniquement*.
> La validation en préprod (ci-dessus) lève le résiduel avant tout provisioning irréversible.

---

## 6. Risques

| # | Risque | Détail | Mitigation (design) |
|---|---|---|---|
| R1 | **Upgrade v0.26 → v0.41** | Pas de breaking destructif détecté, mais migrations Drizzle + login à valider | **Préprod obligatoire** (§4) ; version stable cible à confirmer ; Brique B ⇒ dépend de l'upgrade |
| R2 | **RAM Seko** | 1,6 Go dispo, zerobyte déjà ~511 Mo, **sur le hub VPN** (process critique) | **Élément de conception** : (a) **borne mémoire** du process backup (`MemoryMax` systemd / `mem_limit` conteneur) ; (b) **séquentiel 1 source** ; (c) restic opère sur des **répertoires de dumps pré-faits**, **jamais** de scan d'arbres volumineux live ; (d) swap 2 Go préventif présent |
| R3 | **Clone zerobyte éphémère** | Refs code confirmées dans un scratchpad de session tierce | Re-cloner + re-confirmer les refs au moment de la PR (§3) |
| R4 | **banga non-24/7** | Le drain ne peut pas être synchrone | Drain **opportuniste** (Brique B, détection joignabilité) ; tampon Seko absorbe l'attente |
| R5 | **Object-Lock irréversible** | COMPLIANCE non rétroactif, non désactivable | Dimensionner rétention ≥ lock **avant** création ; gate billing/décision (§8) |

---

## 7. Phases de mise en œuvre

> Chaque déploiement prod = gate humain (§8). Ordre pensé pour que la **Couche 1 (piste A)** referme le trou DR immédiat
> indépendamment de la Couche 2.

| Phase | Contenu | Dépend de | Gate |
|---|---|---|---|
| **P0** | Validation **préprod** de l'upgrade (boot + migrations + login) + **preuves** + confirmer version stable cible. **Valider l'IMAGE EXACTE destinée à P2 — Brique A incluse** (mode PR-mergée **ou** fork décidé) : l'artefact testé = l'artefact déployé, jamais un binaire différent | — | GO préprod |
| **P1** | **Couche 1** — dumps cohérents + vérif non-vide par source (**piste A** : code écrit/testé, **pas déployé**) | — | Deploy prod Sese/Seko (piste A) — **P3 exige ces artefacts déployés+validés** |
| **P-prov** | **Provisioning** : dataset `tank/backups` (banga phase1), **init des repos restic staging Seko + NAS** (l'**offsite est initialisé en P6**, après création du bucket), permissions/forced-command SFTP, **hôte de restore isolé/jetable** pour les drills | banga phase1 | Clé SSH ; accès banga |
| **P2** | **Upgrade prod** zerobyte v0.26 → cible, **incluant la Brique A (séquentialité)** — intégrée à la version déployée (fork épinglé si PR non mergée à temps) | P0 | Deploy prod Seko ; PR merge / fork |
| **P3** | Couche 2 — jobs zerobyte sur **chemins de dumps** + repo restic **staging Seko** + **gate C1** (manifeste par artefact). **Prérequis : Brique A déployée (P2)** — à défaut, **P3 limité à UNE source active** jusqu'à validation de la séquentialité | P1, P2, **P-prov** | Deploy prod Seko |
| **P4** | **Drain Seko→banga** + **cycle drain→vérif→confirm→purge** (marqueur `drained`, §2.2) — backfill **manuel** en attendant B | P2, P3, P-prov | Clé SSH forced-command |
| **P5** | **Brique B** (job `*/5 * * * *` drain **auto** + purge `drained`) | P4 (**tag cible**, primitives vérifiées P0) | PR merge / fork ; **validation préprod image exacte** (build/boot/**concurrence**/reprise) |
| **P6** | **Offsite — création seule** : (a) **test prune↔lock sur un bucket JETABLE de préprod** configuré comme la cible → (b) création du **bucket prod** Object-Lock COMPLIANCE + config **M4** rétention (≥ lock) → (c) **init du repo restic offsite**. **Ne contient AUCUNE alimentation** (première alim = P6b) | P4, P-prov | **Bucket + billing** (externe) |
| **P7** | **H2** restore-drill auto (canari hebdo → tag `verified` ; DoD trimestriel **NAS** — la **branche offsite du drill n'est activée qu'après P6b**) + quarantaine sur échec + **M2** dead-man + `restic check` mensuel | **P4**, P-prov | — |
| **P6b** | **Validation offsite contrôlée (pré-FLIP)** : réplication **one-shot autorisée** d'un snapshot `verified` **de CHACUNE des 3 sources critiques (VW, HS, pg — snapshots distincts, hôtes distincts)** vers l'offsite + **restore-test offsite des 3** (contenu vérifié). Casse la circularité FLIP↔offsite ; couvre le DoD offsite | P6, P7 | **Autorisation ponctuelle** |
| **P7b** | **Job de réplication offsite récurrent** — défini **et testé** (**avant** que FLIP ne l'active) : hôte, **cadence**, **sélection des seuls snapshots `verified`**, **idempotence**, **reprises**, **dead-man**. C'est le job que le flag FLIP bascule | P6, P7, P6b | — |
| **P⊥** | **Waza → banga** LAN direct (indépendant ; ne couvre PAS VW+HS+pg) | banga NAS up | Clé SSH ; banga joignable |
| **FLIP** | `backup_offsite_enabled=true` (**active** le job P7b en routine/auto) | **C1 + H2 levés** (P3 + P7), **P6b réussie**, **P7b testé** | **Gate dur** (héritage NO-GO) |

> **Ordonnancement clé (corrections de revue)** : la **Brique A précède** l'activation multi-source (P2 avant P3, sinon
> P3 mono-source) ; **P6/P7 dépendent de P4** (l'offsite et les drills sont alimentés par le drain qui peuple banga) ;
> **P6 = création du bucket seule** (dépend de P4 pour le dimensionnement, **pas** d'un snapshot `verified`) — la
> **première alimentation** de l'offsite exige un snapshot `verified` (P7) et se fait en **P6b** (envoi de validation
> autorisé) **avant** le FLIP routine → aucune dépendance circulaire, aucun ordre P6-avant-P7 problématique.

**DoD global** : `restic restore` prouvé (Vaultwarden + Headscale + pg) **depuis le NAS banga** (P7) **ET depuis
l'offsite** (P6b — un snapshot `verified` **par source critique**), avec **import dans des instances jetables isolées** +
démarrage du service + contenu vérifié par **requêtes complètes + seuils** (ex. `SELECT count(*) FROM users;`,
`PRAGMA integrity_check;` — tables/requêtes exactes par produit, cf. §5.2 H2). = referme le risque #1 (perte de données
silencieuse).

---

## 8. Gates humains

| Gate | Nature | Quand |
|---|---|---|
| **Approbation de ce design** | Décision | Après convergence Codex — via `notify-gate.sh --artifact` |
| **GO préprod upgrade** | Technique arbitrable | Fin P0 |
| **Upgrade prod zerobyte** | Deploy prod Seko | P2 |
| **Bucket offsite S3 Object-Lock COMPLIANCE** | **Billing / décision** (externe) | P6 — dimensionnement rétention ≥ lock inclus |
| **Clés SSH forced-command** (drain Seko→banga ; Waza→banga) | Sécurité (externe) | P4 / P⊥ |
| **Merge PR upstream A/B (ou décision fork)** | Externe (mainteneur) | **P2 (A)** / P5 (B) |
| **Validation offsite contrôlée (envoi one-shot autorisé)** | Autorisation ponctuelle | **P6b** (pré-FLIP) |
| **FLIP `backup_offsite_enabled=true`** | **Gate dur** | Seulement après **C1 + H2 levés ET P6b réussie** |

**Contraintes transverses**
- **Aucun secret** dans ce design (il part chez OpenAI à la convergence Codex) — variables/chemins uniquement, jamais de
  valeur.
- Ne PAS démarrer l'implémentation (upgrade, PR, déploiement) sans l'**approbation de ce design**.
- Réconciliation des 4 docs périmés (§1.2) = **action post-approbation**, pas avant.

---

## 9. Réserves de revue — arrêt RESIDUAL & points remontés au gate

**Convergence Codex** : 5 rounds (`review-file.sh --sol`, gpt-5.6-sol). Trajectoire HIGH : 4→8→6→5→4. Arrêt **RESIDUAL**
(doctrine convergence) : plateau — un outil de *revue de code* mesure un *design* à l'aune de la complétude
d'implémentation, que le périmètre d'un design exclut explicitement. Les rounds 1-4 ont fermé les gaps **structurels**
(escrow hors-Seko, circularité FLIP↔offsite, dépendances P4/P6/P7, cycle drain atomique, gate C1 par manifeste) ; le
reste = détail d'implémentation, à traiter en **phase de plan**, pas ici.

### 9.1 Différé à l'implémentation / au plan (non bloquant pour l'approbation du design)

- **Valeurs de seuils** du `pre-backup-gate` C1 (âge max, plancher, algo de somme) **par source** — table à établir en P3.
- **Mécanisme exact** du verrou singleton (§3.3), du prune-avec-refus-de-suppression sur Object-Lock (§5.2 M4), et du
  ratio `--read-data-subset=n/T` couvrant 100 % en T mois (§5.2).
- **Format** du manifeste atomique (§5.2 C1) et **liste d'exclusion exhaustive** `~/.claude` (§5.1.1).
- **Requêtes canaris exactes** par produit (tables Headscale/Gitea réelles) — à figer sur le schéma cible en P7.
- **Gestion des valeurs** de passphrases/escrow (§5.2 M1) = gate humain secrets, hors de tout artefact.

### 9.2 Findings de revue rejetés (avec justification — remontés au gate)

- **Round 2 — « refus de suppression Object-Lock non défini »** : REJETÉ, il **est** défini (§5.2 M4 : logguer /
  re-tenter / ne pas mettre en quarantaine) ; seul le mécanisme est différé (§9.1).
- **Round 5 — « le `verified` s'appuie sur un check mensuel »** : REJETÉ (escalade Claude d'accord) — la condition (2)
  du marquage exige un `restic check --read-data` **par snapshot, postérieur, à la cadence hebdo** (§5.2 H2) ; le contrôle
  mensuel tournant est un contrôle **distinct et supplémentaire** du repo.

### 9.3 Déviations vs décisions figées (à valider explicitement par l'opérateur)

- **Staging « = 1 backup max, 105 Go = large »** (handoff figé) → **révisé** en « staging dimensionné pour
  l'**accumulation** pendant l'indispo banga + **backpressure** + gel » (§2.2). Raison : la collecte tourne sur timer
  fixe pendant que le drain est opportuniste (banga non-24/7) → « 1 backup max » sous-dimensionne. **L'opérateur doit
  approuver ce changement de prémisse.**
- **Restore-drill « `restic dump latest | tar -tzf` ou équivalent »** (handoff) → **révisé** en restore-vers-tmp +
  **import dans une instance jetable** + requête canari (§5.2 H2). Raison : `restic dump` d'un répertoire émet un tar
  brut (pas gzip) et un `count(*)` exige une base vivante, pas un fichier.

---

## Annexe — Références abandonnées (ne pas déployer)

Rôle `banga/roles/lxc-zerobyte` (hub restic PULL SSH forced-command → `tank/backups` + offsite), **jamais déployé,
NO-GO**. Templates conservés en **simple référence** (`banga/roles/lxc-zerobyte/templates/`) :
`backup-pull-all.sh.j2`, `offsite-replicate.sh.j2`, `remote-export-{seko,sese,waza}.sh.j2`, `restic-check.sh.j2`,
`ssh_config.j2`, `zerobyte-backup-pull.{service,timer}.j2`, `zerobyte-offsite-replicate.{service,timer}.j2`,
`zerobyte-restic-check.{service,timer}.j2`.

> Exception : `remote-export-seko.sh.j2` reste cité par la **piste A** comme pattern de référence pour le rôle
> `vaultwarden_backup` (`.planning/handoffs/2026-07-23-colmatage-dr-backup-urgent.md:22`) — abandon du rôle `lxc-zerobyte`
> ≠ abandon de ce pattern.
