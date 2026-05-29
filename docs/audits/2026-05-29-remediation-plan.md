# Plan de remédiation unifié + améliorations — Sese-AI / waza / seko-vpn

**Date** : 2026-05-29
**Consolide** : `2026-05-29-infra-audit.md` (audit 3 hosts) + `2026-05-29-sese-phaseB-diagnostic.md` (cause racine Phase B).
**Cadrage usage (confirmé)** :
- **Critique = VPAI core uniquement** : n8n, OpenClaw, LiteLLM, Kitsu. Le reste (flash-suite, story-engine local, vps, fantrad) = **secondaire** mais co-hébergé sur le même host 11 Gi **sans `mem_limit`** → peut OOM le core (0 swap).
- **Priorité n°1 = Fiabilité / visibilité.** Les 2 incidents majeurs (backup PG cassé depuis mars, Phase B down 20h) étaient **invisibles** → c'est LE pattern à éliminer.

---

## 1. Principe directeur

> **Fenêtre de maintenance UNIQUE, fail-loud.** On prépare TOUT le code d'abord, on sécurise les données, puis UN seul déploiement orchestré — pour ne pas enchaîner des redéploiements qui recréent l'infra et re-tuent Phase B. Aucun redémarrage runtime tant que le backup n'est pas vérifié vert.

Graphe de dépendances (haut → bas = ordre obligatoire) :

```
P0 Filet données (backup PG réparé + vérifié, snapshot bind-mounts, dump Headscale)
        │  (rien ne redémarre avant que P0 soit VERT)
        ▼
P1 Correctifs CODE — RESTORE MINIMAL (change le moins possible)
   ├─ fix tag MinIO (débloque Phase B)               ← seul changement de version sur le chemin critique
   ├─ retirer failed_when:false + check post-up      ┐ doivent être en place
   ├─ smoke_test_strict: true                         ┘ AVANT le deploy P2
   └─ GATE pré-flight : manifest inspect de TOUS les tags changés (bloque P2 si un seul KO)
        │
        ▼
P2 Déploiement orchestré UNIQUE (lint→check→deploy docker-stack) → restaure le core, échoue bruyamment si KO
   └─ vérif liveness (200) ET intégrité données (workflows n8n, projets Kitsu, budget LiteLLM)
        │
        ▼
P3 Visibilité (priorité usage) : alerting Grafana→Telegram, Uptime Kuma externe, DIUN sur tags mutables
        │
        ▼  (parallélisables, hors fenêtre critique — chacun sibling-testé)
P4 Sécurité : Redis 8.4.x CVE (sibling-testé, tag à revérifier) · secrets+rotation · dufs · Redis ACL
P5 Protection core vs voisins (mem_limit) + hardening multi-host + SPOF Headscale
P6 Dette & hygiène
P7 Stratégique (voir §3 améliorations)
```

> ⚠️ **Leçon appliquée (R4 sibling-test)** : le bump Redis CVE est **retiré du restore critique**. Vérification empirique 2026-05-29 : `redis:8.4.3-bookworm` = **MANIFEST UNKNOWN** (tag inexistant — Redis a abandonné le suffixe `-bookworm` sur les patch releases, cf. `feedback_redis_8_8_setpriv_hardening`). Bundler ce bump aurait **re-détoné l'incident MinIO** sur le seul système critique. Redis 8.4.0 tourne depuis des mois, la CVE est post-auth → non urgente. Il passe en P4, sibling-testé, après revérification du tag exact au registre.

---

## 2. Plan unifié par phases

### P0 — Filet de données (BLOQUANT, avant tout redémarrage)
| # | Action | Fichier / cible | Dépend de |
|---|---|---|---|
| 0.1 | Ajouter `export PGPASSWORD='{{ postgresql_password }}'` au backup | `roles/backup-config/templates/pre-backup.sh.j2` | — |
| 0.2 | Lancer backup manuel + **vérifier dumps non vides** (n8n, litellm, nocodb, kitsu) | sese (postgres up) | 0.1 |
| 0.3 | Snapshot `tar` de `/opt/javisi/data/` (local) | sese | — |
| 0.4 | ⚠️ **Offsite bloqué** : la copie offsite passe par seko-vpn (Zerobyte) **actuellement injoignable** → le backup offsite « de protection » est peut-être déjà mort. Interim : pousser le dump directement vers **Hetzner S3 depuis sese**, sans attendre P5.4. | sese → S3 | — |

**Gate** : ne pas passer à P2 tant que 0.2 n'est pas vert. **Inversion de dépendance à acter** : « offsite vérifié » ne peut pas se clôturer tant que seko-vpn n'est pas diagnostiqué (P5.4) → soit remonter P5.4 avant P0, soit utiliser la cible S3 interim (0.4).

### P1 — Correctifs code, RESTORE MINIMAL (aucun runtime, change le moins possible)
| # | Action | Fichier:ligne |
|---|---|---|
| 1.1 | **Tag MinIO mort** → `RELEASE.2024-11-07T00-52-20Z` (sur disque, 0 migration, manifest ✅) | `versions.yml:30` |
| 1.2 | **Retirer `failed_when: false`** Phase B + task « compter conteneurs Phase B attendus vs réels, FAIL si manquants » | `roles/docker-stack/tasks/main.yml:408` |
| 1.3 | `smoke_test_strict: true` (smoke-tests bloquants) | `roles/smoke-tests` / group_vars |
| 1.4 | Vérifier que tous les `vault_*` consommés par Phase B existent dans `secrets.yml` (REX-62) | `secrets.yml` |
| 1.5 | **GATE pré-flight (DUR, bloque P2)** : `docker manifest inspect` de **chaque tag changé** + chaque image Phase A/B. **Aucun `up` tant qu'un seul est KO.** Résultats 2026-05-29 : MinIO 2024-11-07 ✅, redis 8.4.0 ✅ ; ⚠️ `redis:8.4.3-bookworm` **KO** → exclu du restore. | script |

> **Redis, redis:7→7.4.9, et tout autre bump : EXCLUS de P1.** Le restore critique ne change QUE le tag MinIO. Tout le reste est sibling-testé en P4. (R4)

### P2 — Déploiement orchestré unique (restore minimal)
1. `source .venv/bin/activate && make lint`
2. `ansible-playbook playbooks/stacks/site.yml --check --diff` (cible prod)
3. `make deploy-role ROLE=docker-stack ENV=prod` (rejoue Phase A inchangée + Phase B MinIO fixé)
4. **Vérifier liveness** : conteneurs Phase B up, `mayi/tala/llm/kitsu` → 200, LiteLLM healthy (1.2/1.3 → échec **bruyant** si un service manque).
5. **Vérifier INTÉGRITÉ DONNÉES** (200 ≠ données survécu, surtout après le bump PG 18.3→18.4 avec backups cassés) : `n8n` workflow count > 0, projets **Kitsu** présents, historique budget **LiteLLM** intact, `nocodb`/`plane` non vides. C'est la différence entre « c'est up » et « c'est réellement restauré ».

### P3 — Visibilité (priorité n°1)
| # | Action | Note |
|---|---|---|
| 3.1 | Configurer `notification_method` (Grafana → Telegram OU webhook n8n) | la stack grafana/VM/loki/alloy **revient avec Phase B (P2)** ; reste à brancher les notifs (actuellement vides) |
| 3.2 | Uptime Kuma externe (rôle `uptime-config`, sur **seko-vpn** = hors du host surveillé) sur mayi/tala/llm/kitsu | alerte si 502 → aurait détecté la panne de 20h |
| 3.3 | Alerte « backup PG > 24h sans succès » + « N conteneurs Phase B attendus ≠ réels » | métriques métier, pas juste CPU/RAM |
| 3.4 | DIUN surveille MinIO + images custom (tags mutables) | éviter le re-incident tag mort |

### P4 — Sécurité (parallèle, hors fenêtre, chaque item sibling-testé)
| # | Action | Cible |
|---|---|---|
| 4.1 | **Redis CVE bump (découplé de P2)** : revérifier le tag exact au registre (`8.4.3-bookworm` = KO ; tester `8.4.3` sans suffixe / `8.4.x` valide), sibling-tester en isolation (REX 8.8 setpriv), PUIS bump `versions.yml:14` + redeploy infra seul | `versions.yml:14`, `roles/redis` |
| 4.2 | Pin `redis:7-alpine` → tag fixe valide (revérifier manifest) — secondaires | `roles/flash-suite/.../docker-compose.yml.j2:43` |
| 4.3 | Credentials hardcodés → vault + **ROTATION** (présents dans l'historique git) | `scripts/setup-kitsu-*.py`, `kitsu-create-shot.py`, `immo-finder-gif-yvette.json` |
| 4.4 | dufs : `--auth` ou `import vpn_only` | `roles/dufs`, Caddyfile |
| 4.5 | Redis durcissement : ACL + `protected-mode` + bind interne (post-bump 4.1) | `roles/redis` |

> Caddy `2.10-alpine` story-engine : **caduc en runtime** (prod Hetzner supprimée). À corriger AVANT tout futur redéploiement story-engine.

### P5 — Protéger le core des voisins + hardening (adapté criticité)
| # | Action | Pourquoi (usage) |
|---|---|---|
| 5.1 | **`mem_limit` sur flash-suite (×7), dufs, grapesjs, story-engine local** | empêcher un service **secondaire** d'OOM le **core critique** (0 swap). Priorité haute vu la réponse criticité. |
| 5.2 | Étendre hardening : waza (confirmer sshd key-only, ufw, **reboot pending**) + seko-vpn | hosts actuellement nus |
| 5.3 | Handlers `state: restarted` → `present` + `recreate: always` (×4) | `roles/{postgresql,qdrant,caddy,docker}/handlers/main.yml` |
| 5.4 | Diagnostiquer **seko-vpn injoignable** (console Ionos) | SPOF Headscale = mesh entier |

### P6 — Dette & hygiène
- mealie / grocy : **absents du compose** (configs rendues mais service jamais dans le YAML) → ajouter au compose **ou** retirer rôles/configs orphelins.
- Doublons : `metube` (workstation_metube + amazing_mclaren), `koodia` (flash-suite vs catalogue).
- ~40 violations `changed_when`/`failed_when` ; `set -euo pipefail` manquant `webhook-relay`.
- CouchDB 3.3.3 → 3.5.1 (hors fenêtre de patch).
- waza : 60 paquets apt + reboot post-update.
- CI : ajouter un vrai test d'intégration (compose up) — Molecule est en mode stub.

### P7 — Stratégique → voir §3.

---

## 3. Améliorations adaptées à TON usage (solo-op, fiabilité-first, VPAI core critique)

Classées par rapport impact/effort, pensées pour quelqu'un qui **ne surveille pas en continu** et dont la **vraie valeur = les données du core** (workflows n8n, projets/assets Kitsu, budget LiteLLM, agents OpenClaw).

### 🥇 A — « Fail-loud » comme règle d'or
Le pattern qui t'a coûté 2 pannes invisibles, c'est le **masquage d'erreur**. Bannir `failed_when: false` sur toute tâche de démarrage. Règle : **un déploiement qui laisse un service attendu down doit ÉCHOUER**. C'est le plus gros gain fiabilité pour un effort minime. → généralise 1.4 à tous les rôles app.

### 🥈 B — Observabilité « qui te ping » (pas un dashboard que tu ne regardes pas)
Pour un solo, un Grafana qu'on ne consulte pas ne sert à rien. Ce qui compte = **alertes push** :
- Grafana → **Telegram/n8n** sur : service core down, CPU/RAM/disk, budget LiteLLM proche du cap $5.
- **Uptime Kuma sur seko-vpn** (host externe) qui teste mayi/tala/llm/kitsu de l'extérieur — le seul moyen de détecter un 502 quand le host lui-même ment.
- 2 métriques métier qui auraient tout changé : **« âge du dernier backup réussi »** et **« conteneurs Phase B attendus vs réels »**.

### 🥉 C — Pinning par **digest** pour les tags mutables
Le tag MinIO purgé = 20h down. Un `image@sha256:…` ne peut pas disparaître. À appliquer au moins à **MinIO + images custom ghcr (n8n-enterprise, zimboo, grapesjs, vps)**. DIUN continue de proposer les bumps, tu valides. Coût quasi nul, supprime une classe entière de pannes.

### D — Cloisonner le blast-radius (core vs secondaires)
Ton core critique partage 11 Gi sans limites avec 4 produits secondaires. Deux niveaux :
1. **Immédiat (P5.1)** : `mem_limit` partout → un voisin ne peut plus OOM le core.
2. **Moyen terme** : comme seul VPAI core est critique, envisager de **sortir flash-suite/story-engine/vps sur un 2e petit VPS** (ou les éteindre quand inutilisés). Tu protèges le core ET tu récupères de la RAM/du budget. Sobriété + fiabilité d'un coup.

### E — Backups « juste ce qu'il faut » (ne pas sur-ingénierer)
Pour un solo, **WAL/PITR (Barman) est sur-dimensionné**. Le bon niveau :
- `pg_dump` quotidien **réparé + VÉRIFIÉ** (P0) + **chiffré** (age) + **offsite** (seko-vpn/Hetzner S3).
- **Restore test automatique hebdo** sur un conteneur jetable → un backup non testé n'est pas un backup.
- Inclure les bind-mounts Kitsu (assets) et la DB Headscale.
C'est l'effort minimal qui rend tes données réellement récupérables.

### F — Réduire la surface Phase B au strict utile
26 apps = 26 sources de panne. Beaucoup sont probablement peu utilisées (grocy, mealie, firefly perso, mailhog, carbone, gotenberg). Proposer un **profil `core`** (n8n, openclaw, litellm, kitsu, nocodb, monitoring) déployé/surveillé sérieusement, vs des **`extras`** activables à la demande. Moins de RAM, moins de blast-radius, moins de budget — aligné fiabilité + sobriété.

### G — Pré-flight déploiement
Vu la fréquence de tes bumps (git log ≈ bumps quasi quotidiens), un `make preflight` avant tout deploy : (1) valide que **tous les manifests sont tirables**, (2) vérifie les `vault_*`, (3) déclenche le backup. Transforme « deploy qui casse en silence » en « deploy qui refuse de partir si risqué ».

### H — Cadence de versions maîtrisée
Bumper en **batch planifié** plutôt qu'en continu, et **séparer infra critique** (rare, testée : pg/redis/caddy/qdrant) des **apps** (DIUN propose, tu valides). Chaque bump non testé est un mini-risque (cf. MinIO).

### I — Runbook de reprise (DR) du core
Un solo n'a pas de mémoire d'équipe. Une page par service core : « comment je le restaure depuis zéro » (volumes, DB, env). Surtout Headscale (SPOF mesh) et Postgres (DB partagée de tout le core).

---

## 4. Ce qui change vs l'audit initial (à acter)
- ❌ « Phase B jamais déployée » → **FAUX**. Tournait des mois ; tuée par le redeploy du 01:31 sur un tag MinIO mort.
- ⚠️ **DRIFT confirmé — flash-suite / vps / fantrad / story-engine tournent sur SESE alors que leur cible est un serveur dev Hetzner (supprimé, redéployable).** Preuve runtime 2026-05-29 : working_dirs locaux (`/opt/flash-suite`, `/home/mobuone/projects/saas/{vps,fantrad,story-engine/infra}`), up 4 sem–2 mois, sur host `sese` (IPv6 OVH). **13 conteneurs secondaires squattent le host du core critique, sans `mem_limit`.**
  - → **Action recommandée (quick-win fiabilité + RAM)** : les évacuer de sese (redéployer sur le Hetzner dev quand nécessaire, éteindre sur sese sinon). Aligné avec « VPAI core seul critique » : on retire le blast-radius secondaire du host critique au lieu de juste le cloisonner. Rend P5.1 (`mem_limit`) secondaire si évacuation faite.
- ✅ Risque OOM 8GB → infirmé (11 Gi). Mais **0 swap + 13 voisins non-intentionnels sans mem_limit** = vrai risque résiduel sur le core.
- ✅ Le vrai fil rouge = **invisibilité des pannes** → confirmé comme priorité n°1.

---

## 6. Architecture cible — 3 tiers (downgrade OVH + Hetzner éphémère + NAS/IA local)

**Objectif** : réduire Sese-AI au strict core VPAI pour **redescendre en gamme OVH** (coût), sortir le dev en éphémère, et rapatrier backups + fallback IA sur un NAS local.

### Tier 1 — Sese-AI OVH (permanent, minimal)
Garde **uniquement le core critique** + son infra :
- Infra : postgresql, redis, qdrant, caddy, socket-proxy.
- Apps core : n8n, litellm, openclaw, kitsu, nocodb.
- Observabilité **légère** (Beszel ~50 Mo au lieu de la stack Grafana ~600 Mo).
- Tout le reste (plane×6, typebot, firefly, mealie, grocy, carbone, gotenberg, mailhog, zimboo, grapesjs, dufs, metube, couchdb) → **désactivé/évacué** sauf besoin réel (profil `extras`).

**Dimensionnement** (mesure idle + estimation Phase B core) :
| Poste | ~RAM |
|---|---|
| OS + Docker | ~0.5 Go |
| Infra (qdrant domine à 0.8) | ~1.0 Go |
| Apps core (n8n+litellm+openclaw+kitsu+nocodb) une fois up | ~2–3 Go |
| **Total core** | **~3.5–4.5 Go** |

→ Cible **OVH 8 Go + swap 4 Go** (de 11→8 : déjà un downgrade net, marge sûre). **4 Go faisable** seulement en tunant qdrant (mmap/quantization), openclaw on-demand, Beszel — risqué sans swap. **Mesurer le core réel en P2** avant de choisir la gamme. **Ajouter du swap est non-négociable** sur une petite gamme (actuellement 0 B).

### Tier 2 — Hetzner éphémère (dev à la demande)
flash-suite, story-engine, vps, fantrad → **redéployés sur un VPS Hetzner créé pour la session de dev, détruit après**. Le repo le permet déjà (groupes `app_prod`/`story_engine`/inventaire). À industrialiser : cloud-init + `make deploy` one-shot + snapshot avant destruction. Coût ≈ heures d'usage seulement.

### Tier 3 — NAS + IA local (P6X58D-E, ce week-end)
- **Stockage** : 8×8 To → **ZFS RAIDZ2** (~48 To utile, tolère 2 disques HS). TrueNAS Scale (déjà anticipé dans `docs/BACKUP-STRATEGY.md` §11). ⚠️ Carte desktop = **pas d'ECC** → activer **scrubs ZFS réguliers** (mitigation bitrot). **Attendre les 48 Go DDR3 (dimanche)** : 6 Go est trop juste pour ZFS ARC + IA.
- **Backups offsite → ce NAS** (remplace le offsite seko-vpn/Zerobyte défaillant) : **restic** depuis sese vers un dataset ZFS, via le **mesh Tailscale** (le NAS rejoint Headscale). Dedup + chiffré + snapshots. Schéma **3-2-1** : copie locale sese + copie NAS + (option froide Hetzner S3).
- **IA fallback local** : modèle **quantized GGUF** (Gemma 3/4, Qwen/Phi 7–12B en Q4) via Ollama/llama.cpp, exposé en endpoint OpenAI-compat → **LiteLLM route dessus en eco-mode** quand le budget $5/j est atteint ou OVH indispo. Vraie résilience + coût nul.
  - ⚠️ **Perf réaliste** : X58 (Nehalem/Westmere ~2010) + DDR3 = bande passante limitée → **quelques tok/s** sur petits modèles. Bon pour *fallback*, pas pour usage principal. Pas de GPU mentionné = CPU-only. « DeepSeek V4 Flash » (MoE, gros) sera probablement trop lent en CPU sur cette plateforme — viser des modèles ≤12B.
  - ⚠️ **Conso élec** : X58 ~150–250 W. Pour NAS 24/7 + IA à la demande, ok ; sinon Wake-on-LAN pour l'IA. À chiffrer vs économie OVH.

### Impact sur ce plan
- **P5.1 (`mem_limit` voisins)** → remplacé par **évacuation** (Tier 2). Plus de squat sur le host critique.
- **P0.4 / P3 backup offsite** → cible définitive = **NAS Tier 3** (dès dimanche) au lieu de S3 interim.
- **P3 monitoring** → Beszel (Tier 1 léger) cohérent avec le downgrade, plutôt que la stack Grafana lourde.

---

## 5. TL;DR — par où commencer
1. **P0.1+0.2** : réparer + vérifier le backup PG (ne rien redémarrer avant) ; pousser une copie offsite S3 (seko-vpn KO).
2. **P1** : corriger le **seul** tag MinIO (`versions.yml:30`) + retirer `failed_when:false` + GATE manifest. **Ne PAS bundler le bump Redis** (`8.4.3-bookworm` est mort → re-casserait tout).
3. **P2** : un seul `make deploy-role ROLE=docker-stack` → core de retour, 502→200 ; vérifier **données** (workflows n8n, projets Kitsu), pas juste le 200.
4. **P3** : brancher l'alerting (Telegram) + Uptime Kuma externe → ne plus jamais subir une panne invisible.
5. **P4+** : Redis CVE (sibling-testé, tag revérifié), secrets, mem_limit, hardening, dette, stratégique — parallélisable.
