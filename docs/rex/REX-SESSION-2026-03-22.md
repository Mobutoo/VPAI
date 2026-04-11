# REX Session 19 — Pipeline E2E + Kitsu Sync (2026-03-22)

## Objectif

Reprendre la construction du pipeline video E2E et rendre chaque step visible dans Kitsu.

## Ce qui a ete fait

### Remotion (montage video)

| Fix | Commit | Detail |
|-----|--------|--------|
| VideoUrl localhost → Docker hostname | `dd8b90f` | Remotion retourne `localhost:3200` dans les URLs de rendu, mais videoref est dans un autre container. Rewrite vers `workstation_remotion:3200` |
| Cap render a 720p | `17b2f37` | Chromium OOM a 1080p sur ARM64 (Pi 16GB). 720p render en ~2.5 min |
| Stall detection | `17b2f37` | Si le progress stagne 60s, cancel + fallback ffmpeg. Evite les renders bloques a 70% qui bloquent toute la queue |
| Timeout reduit 600s → 300s | `17b2f37` | 60 polls × 5s au lieu de 120 |

**Etat** : Remotion render OK en 720p (~2.5 min pour 2 scenes de 5s). Le test isole passe. En E2E, le render peut encore stagner si le Pi est charge (fallback ffmpeg sans audio dans ce cas).

### Kitsu (production tracker)

| Fix | Commit | Detail |
|-----|--------|--------|
| DB tables manquantes | `fddad7a` | `zou init-db` n'etait pas dans les tasks Ansible. Ajout de la tache idempotente |
| Reference data manquante | `5f41717` | `zou init-data` necessaire pour creer les task statuses (Todo, WIP, Done, WFA) et task types (Storyboard, Layout, etc.) |
| Memory 512M → 768M | `fddad7a` | Gunicorn OOM au demarrage (449/512 MB = 88%) → workers SIGKILL. 768M OK (50% usage) |
| `production_style` invalide | `5f41717` | Champ pas supporte par l'API Zou. Deplace vers `data.style` |
| Noms projets uniques | `f5266ab` | Kitsu enforce unique project names. Ajout du `job_id[:8]` en suffixe |
| Auto-refresh token | `924c8cf` | Le JWT expire apres 7 jours. Auto-login dans `_kitsu_api()` sur 401/422 |
| Task type `for_entity` | `924c8cf` | Les task types custom (Brief, Script, etc.) doivent etre `for_entity=Shot` |

**Etat actuel** : Le projet Kitsu est cree, le login fonctionne, le token est auto-refresh. **MAIS** les tasks echouent encore avec `"Task type of the task does not match entity type"`.

### Pipeline video

| Fix | Commit | Detail |
|-----|--------|--------|
| Keyframes obligatoires | `782e746` | Ne jamais skip imagegen — les keyframes sont l'ancrage visuel pour img2vid |
| Voiceover auto-narration | `421e026` | Si pas de texte, generer la narration depuis les scene_prompts |
| ffmpeg audio mix | `421e026` | Fallback ffmpeg avec voiceover + music (amix, volume control) |
| Prompt anchoring | `421e026` | Injecter le prompt de la scene 0 dans les scenes suivantes pour coherence |
| Kokoro voice param | `efbf56b` | Kokoro TTS requiert le param `voice` (default `af_heart`) |

**Etat** : Le pipeline genere des keyframes → img2vid → montage. Le voiceover Kokoro est lent sur ARM64 (timeout curl). L'audio n'est pas dans le montage final car le voiceover n'a pas fini avant le montage.

## Probleme bloquant — Task types Kitsu

### Symptome

```
Kitsu POST /data/tasks: 400
{"error":true,"message":"Task type of the task does not match entity type."}
```

### Cause racine

Les task types custom (Brief, Script, Image Gen, Video Gen, Montage, etc.) ont ete crees **sans `for_entity`** lors des sessions precedentes. Zou leur assigne `for_entity=Asset` par defaut. Quand le pipeline essaie de creer un task de type "Brief" sur un **Shot**, Zou refuse car le type est pour Asset.

Le fix `for_entity=Shot` dans `_kitsu_get_task_type_id` ne s'applique qu'aux **nouveaux** types. Les types existants dans la DB Kitsu ont toujours `for_entity=Asset`.

### Solution a implementer

1. **Option A** : `_kitsu_get_task_type_id` doit verifier `for_entity` du type existant et faire un PUT pour le corriger si necessaire
2. **Option B** : Supprimer les task types incorrects et les recreer avec `for_entity=Shot`
3. **Option C** : Script de provisioning Kitsu qui cree tous les task types du pipeline avec les bons `for_entity`

**Recommandation** : Option A (auto-correction dans le code) car elle est idempotente et ne necessite pas d'intervention manuelle.

## Architecture validee

```
Director scene_prompts → ImageGen (keyframes coherents via ComfyUI)
                       → VideoGen img2vid (depuis les keyframes, Seedance/Veo/Kling)
                       → Montage Remotion 720p (ou ffmpeg fallback)
                       → Telegram notification
```

Chaque step doit remonter dans Kitsu :
- Projet cree au Brief (tvshow, nom unique avec job_id)
- Sequence + Shot overview pour les tasks pipeline
- Tasks par step (Brief, Script, Image Gen, etc.) avec status (Done, WFA)
- Previews attachees aux comments sur tasks (pas directement aux entites)

## Fichiers critiques

| Fichier | Lignes | Role |
|---------|--------|------|
| `roles/videoref-engine/files/app.py` | 496-527 | `_kitsu_api` — helper HTTP avec auto-refresh |
| `roles/videoref-engine/files/app.py` | 682-697 | `_kitsu_get_task_type_id` — get/create task type |
| `roles/videoref-engine/files/app.py` | 3323-3450 | `_step_brief` — cree projet Kitsu |
| `roles/videoref-engine/files/app.py` | 5840-5900 | `_kitsu_step_task` — cree task sur shot |
| `roles/kitsu/tasks/main.yml` | 72-95 | `zou init-db` + `init-data` + `create-admin` |
| `roles/kitsu/defaults/main.yml` | 7-8 | Memory 768M |

## Prochaines etapes

1. **Fixer les task types `for_entity`** dans `_kitsu_get_task_type_id` (verifier + corriger)
2. **Tester chaque step** individuellement avec verification Kitsu
3. **Run E2E complet** avec montage Remotion + audio + Kitsu sync
4. **Push klingCreator Docker** sur GitHub (repo a creer)
5. **Handler Ansible `docker compose build`** quand les sources changent
