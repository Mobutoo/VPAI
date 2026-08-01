# Plan — zerobyte « native DB-source » (backup unifié, upstream-first)

> **Statut** : DRAFT — **à converger Codex avant exécution** (LOI règle 4). **Exécution différée** : « quand on aura du
> quota » (jauge hebdo à 87 % au 2026-07-23).
> **But** : combler le seul gap qui empêche zerobyte d'être notre **backup unifié** — le **dump cohérent par moteur**.
> Une fois comblé, la Couche 1 hand-rollée (piste A) **disparaît dans zerobyte** : dump cohérent → **plain** → restic
> (dédup) → mirror banga → offsite Object-Lock → verify. Un seul outil.
> **Réfs** : `2026-07-23-refonte-backup-zerobyte-orchestrateur-seko.md` (design v3 approuvé) ·
> `2026-07-23-eval-databasement-vs-zerobyte-backup.md` (source des flags de dump).

## 1. Constat (source-vérifié)

- zerobyte **n'a AUCUN dump-moteur natif** : son schéma ne connaît que des **volumes/chemins** (`schema.ts:238-427`) ;
  les backup-hooks sont des **webhooks HTTP** (pas d'exec local). Le dump DB doit être produit **en amont**.
- Il a déjà **tout le reste** : restic (dédup), `compressionMode off/auto/max` (**plain possible**), mirrors, remote-agents
  (WebSocket), `restic check`, **9 canaux de notif**.
- databasement (MIT) prouve les **commandes/flags corrects par moteur** — mais compresse/chiffre **toujours** (inadapté
  tel quel) → on **réimplémente en TS**, on ne fait **pas** tourner son binaire PHP.

## 2. Périmètre de la feature

Ajouter à zerobyte un **type de source « database »** qui, sur l'agent :
1. exécute un **dump cohérent** selon le moteur (subprocess) → fichier **plain** (jamais compressé/chiffré par la feature ;
   restic s'en charge, `compressionMode` du repo) ;
2. laisse restic snapshotter ce fichier (le reste du pipeline zerobyte est inchangé).

Moteurs prioritaires (nos besoins) : **PostgreSQL** (`pg_dump --clean --if-exists --no-owner --no-privileges
--quote-all-identifiers --format=custom`), **SQLite** (`sqlite3 <db> '.backup <out>'` — **WAL-safe**, jamais `cp` à chaud),
**Redis** (`redis-cli --rdb`). Extensible (MySQL/Mongo) plus tard.

Touche : **schéma Drizzle** (nouveau source type + champs `dbType/host/port/user` + réf secret), **runner par moteur**
(TS, sur l'agent), **gestion des creds DB** (où/comment zerobyte stocke un secret de connexion — à étudier dans son
modèle actuel), **UI** de config, **tests**. ⚠️ **Pas un micro-PR** : feature transverse.

## 3. Piège à ne pas refaire (issus de l'éval)

- **Sortie plain obligatoire** : ne jamais compresser/chiffrer dans la feature (sinon dédup restic cassée + double
  compression) — c'est l'erreur structurelle de databasement (`BaseCompressor.php:32-34`).
- **SQLite via SFTP = non atomique** : toujours `.backup` **local** côté source, jamais copie `main+wal+shm` à distance.
- **Redis** : databasement **ne restaure pas** Redis → notre restore-drill (H2, design v3) doit couvrir le cas.
- **Vérif non-vide/plancher** par artefact = le gate C1 du design v3 (à câbler côté source de toute façon).

## 4. Stratégie : UPSTREAM-FIRST, RFC AVANT code

Pour un **gros** feature (≠ Brique A/B micro), « PR-avec-code merge vite » ne s'applique plus : zerobyte sépare
**volontairement** dump/snapshot → une PR qui ajoute des dumps natifs **change le périmètre produit**.

1. **RFC/issue GitHub** proposant le *database source* : problème, design (schéma + runner + plain + creds), moteurs
   visés, offre de coder. **Convergée Codex, zéro secret, postée sous le compte opérateur.**
2. **Attendre l'alignement mainteneur** (gate externe). Réceptif → build + PR. Réservé/refus → décision **fork** (dette :
   re-sync à chaque release d'un app Bun/Effect/Drizzle — à assumer explicitement, contre « toujours latest »).
3. **Build + PR** (ou fork épinglé `zerobyte_version`).

## 5. Prérequis & ordonnancement

- **Prérequis dur** : le trou DR est fermé (piste A) **et** l'upgrade zerobyte v0.26→cible (design v3 P0-P2) est fait —
  on ne bâtit pas la feature sur v0.26.
- **Prérequis quota** : jauge hebdo < seuil (exécution différée, cf. statut).
- **Ordre** : (a) fermer trou DR [en cours] → (b) design v3 P0-P2 (upgrade) → (c) **RFC** [ce plan] → (d) alignement
  mainteneur → (e) build/PR/fork → (f) bascule Couche 1 hand-rollée vers la feature native → Couche 1 supprimée.

## 6. Gates humains

- **Alignement mainteneur** (réponse à la RFC) = gate externe, avant tout gros code.
- **Décision fork** (si refus) = gate opérateur (assume la dette).
- **Convergence Codex** de la RFC avant publication (règle 4) ; **aucun secret** dans la RFC (part chez OpenAI + public GitHub).
- Merge PR / bascule Couche 1 = gates séparés le moment venu.

## 7. Livrable immédiat de ce plan

Quand le quota le permet : produire la **RFC** (artefact texte convergé Codex) prête à poster. Ce document en est le
squelette. **Ne rien coder** avant la réponse mainteneur.
