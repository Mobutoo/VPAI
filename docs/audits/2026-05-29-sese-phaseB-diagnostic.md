# Diagnostic Sese-AI — Pourquoi n8n / Grafana / LiteLLM / OpenClaw sont down

**Date** : 2026-05-29 (corrigé après vérification directe)
**Méthode** : lecture rôle `docker-stack` + investigation SSH read-only en direct (volumes, bind-mounts, journal docker, manifests registre).
**R0** : qdrant-find (docker-stack, CLAUDE.md Architecture Déploiement, CONCERNS).

---

## ⚠️ Correction d'un diagnostic initial erroné

Une première passe avait conclu « Phase B jamais déployée ». **C'est FAUX.** Erreur due à : (1) recherche limitée aux volumes nommés alors que les apps utilisent des **bind-mounts** `/opt/javisi/data/<app>` ; (2) `journalctl` borné à « depuis avril » ; (3) absence de conteneurs `Exited` interprétée comme « jamais lancé » au lieu de « `compose down` propre ».

**Réalité : n8n, OpenClaw, Grafana, Kitsu, etc. ont tourné pendant des mois, puis ont été arrêtés il y a ~20h.**

---

## 1. Réponse courte

Le **2026-05-29 vers 01:31**, un redéploiement avec **bumps de version** (postgres 18.3→18.4, redis, caddy, qdrant — cf. git log) a :
1. fait un pré-dump (`/opt/javisi/data/pg-dumpall-pre-18.4.sql.gz`, 63 Mo, 01:31) ;
2. recréé l'infra Phase A (succès) ;
3. comme le template compose avait changé, exécuté `docker compose -f docker-compose.yml down` → **arrêté toutes les apps Phase B** (n8n, openclaw, grafana…) ;
4. tenté `docker compose up` Phase B qui a **avorté à 01:33:54** sur un pull en échec :

```
May 29 01:33:54 sese dockerd: level=error msg="Not continuing with pull after error"
                              error="manifest unknown: manifest unknown"
```

`docker compose up` est **tout-ou-rien sur les pulls** : une seule image au tag mort interrompt tout le démarrage. **`failed_when: false`** (rôle docker-stack, tâche « Start Applications stack (Phase B) ») a **masqué l'échec** → le déploiement a rapporté un succès. Résultat : infra up, **0 app Phase B**, et Caddy qui route vers des backends inexistants → **502**.

---

## 2. Cause racine exacte — une image au manifest mort

| | |
|---|---|
| **Image fautive** | `minio/minio:RELEASE.2025-10-15T17-29-55Z` (dépendance de `plane-minio`) |
| **Test registre** | `docker manifest inspect` → **MANIFEST UNKNOWN** (tag purgé par MinIO) |
| **Pin** | `inventory/group_vars/all/versions.yml:30` → `plane_minio_image` |
| **Image locale (qui tournait)** | `minio/minio:RELEASE.2024-11-07T00-52-20Z` (présente) |
| **Tags valides vérifiés** | `RELEASE.2025-09-07T16-13-09Z` ✅, `RELEASE.2024-11-07T00-52-20Z` ✅ (déjà sur disque), `latest` ✅ |
| **Toutes les autres images Phase B** | testées au manifest → ✅ OK (litellm 1.83.7, firefly 6.6.1, n8n-enterprise 2.7.3, openclaw, plane×, etc.) |

> **Une seule ligne de `versions.yml` a mis à terre les 26 apps.** Ce n'est ni un crash applicatif, ni un manque de RAM, ni une erreur de config — c'est un tag d'image que le registre upstream a supprimé, combiné au comportement all-or-nothing de `compose up` et au masquage `failed_when: false`.

---

## 3. Preuves que Phase B a bien tourné

| Preuve | Détail |
|---|---|
| **Bind-mounts data** `/opt/javisi/data/` | dirs peuplés pour **n8n, openclaw, grafana** (UID 472), **loki, victoriametrics, nocodb, kitsu, plane, typebot, firefly, mealie, grocy, carbone, diun, palais, mop** — dates fév→avr 2026 |
| **Volumes nommés** | `javisi_kitsu_db`, `javisi_kitsu_previews` |
| **Sandboxes orphelines** | `openclaw-sbx-agent-builder-*`, `openclaw-sbx-agent-concierge-*` **Up 4 weeks** — spawnées PAR la gateway OpenClaw via le socket → la gateway a forcément tourné (elles survivent à son `down`) |
| **Réseaux** | `javisi_backend/frontend/monitoring/egress` présents |

---

## 4. Remédiation (la vraie, avant tout le reste)

1. **Corriger le tag MinIO** — `versions.yml:30` :
   ```yaml
   # mort : RELEASE.2025-10-15T17-29-55Z
   plane_minio_image: "minio/minio:RELEASE.2024-11-07T00-52-20Z"   # déjà sur disque, 0 risque migration, déblocage immédiat
   # ou un tag récent valide : RELEASE.2025-09-07T16-13-09Z (vérifier compat données Plane existantes)
   ```
   Recommandé pour déblocage immédiat : le **2024-11-07** (image déjà présente, exactement celle qui tournait → zéro risque de migration des données Plane). Bump vers un tag 2025 à traiter séparément (MinIO a des changements cassants console/fs entre 2024 et 2025).
2. **Pré-requis backup** : corriger d'abord le backup PG cassé (audit principal §1) — un pré-dump existe (`pg-dumpall-pre-18.4.sql.gz`) mais les dumps quotidiens sont vides.
3. **Relancer Phase B** : `make deploy-role ROLE=docker-stack ENV=prod` (rejoue Phase B), ou ciblé `cd /opt/javisi && docker compose -f docker-compose.yml up -d`. Caddy passera de 502 à 200 dès que les backends sont up.
4. **Surveiller la RAM** : 26 apps sur 11 Gi (déjà ~2.2 Gi pris). Mesurer pendant la montée ; OOM possible si tout démarre d'un coup (0 swap). Démarrer monitoring puis n8n/litellm/openclaw si besoin de séquencer.

---

## 5. Correctifs de fond (pour que ça ne se reproduise pas)

- 🔴 **Retirer `failed_when: false`** de la tâche « Start Applications stack (Phase B) » (`roles/docker-stack/tasks/main.yml:408`) — ou ajouter un check post-`up` qui compte les conteneurs attendus et FAIL si manquants. C'est l'angle mort qui a transformé un tag mort en panne invisible de 20h.
- 🟠 **Pré-pull / validation des manifests avant le `down`** : ne pas arrêter Phase B tant que toutes les images du nouveau compose ne sont pas confirmées tirables. Sinon un tag mort = downtime garanti.
- 🟠 **Pinner MinIO sur un tag stable et le faire suivre par DIUN** comme les autres (le tag actuel n'était visiblement pas surveillé/testé).
- 🟡 **Smoke-tests bloquants** (`smoke_test_strict: true`) post-deploy : mayi/tala/llm en 502 aurait dû faire échouer le déploiement.

---

## 6. Inventaire sese (27 conteneurs) — clarifié

| Catégorie | Conteneurs | Statut |
|---|---|---|
| **A — infra VPAI** (Phase A) | javisi_postgresql, _redis, _caddy, _qdrant, _socket_proxy | ✅ running (recréés 01:xx) |
| **B — apps VPAI** (Phase B) | n8n, litellm, grafana, openclaw, nocodb, kitsu, plane×6, typebot×2, carbone, gotenberg, msg2md, palais, zimboo, firefly, mailhog + monitoring (cadvisor/VM/loki/alloy/diun) | ❌ **DOWN depuis 01:33** (cause §2) — data préservée |
| **C — standalone VPAI** | javisi_dufs, _grapesjs, _pandoc_api, _vref_mock, workstation_metube (+ doublon `amazing_mclaren`) | ✅ running |
| **D — autres produits** | couchdb, fantrad_postgres, vps-app, flash-suite (×7), openclaw-sbx (×2 orphelines) | ✅ running |
| **infra-* (×4)** | **infra story-engine LOCALE** (workdir `/home/mobuone/projects/saas/story-engine/infra`) | ✅ running — **projet NON avorté** (le serveur Hetzner prod supprimé ≠ cette stack locale). À conserver. |

**Apps non-Docker** : aucune. Système natif uniquement : CrowdSec(+bouncer), Tailscale, exim4 (loopback), fail2ban, auditd.

---

## 7. Incohérences rôle ↔ compose (à traiter à part)

- **mealie / grocy** : rôles + configs + data-dirs présents, mais **absents du `docker-compose.yml`** (jamais ajoutés au YAML) → ne démarreront pas même après le fix MinIO.
- **koodia** : absent du compose javisi, tourne en doublon dans flash-suite.
- **metube** : doublon (`workstation_metube` + `amazing_mclaren`).
- Doublon mémoire-corrigée : 3 images du catalogue étaient signalées « manquantes localement » (litellm/firefly/minio) — en réalité litellm 1.83.7 et firefly 6.6.1 ont un manifest VALIDE (seront pull au prochain up) ; seul **minio** a un tag mort.

---

## 8. Synthèse en une ligne

Phase B tournait depuis des mois ; le redéploiement-bump du 2026-05-29 01:31 l'a arrêtée puis n'a pas pu la relancer car **`minio/minio:RELEASE.2025-10-15T17-29-55Z` (versions.yml:30) a un manifest supprimé** — `compose up` tout-ou-rien avorte, `failed_when: false` masque, Caddy renvoie 502. Fix = un tag MinIO valide + retirer le masquage d'erreur.
