# Design: Pipeline Creatif E2E — Correctif Complet

**Date**: 2026-03-20
**Statut**: Approuve
**Impact**: `roles/videoref-engine/files/app.py` (~250 lignes)

## Probleme racine

Le pipeline a 2 chemins pour les scenes :
1. **Avec video MeTube** : `run_analysis()` → ffmpeg scene detect → keyframes → Claude Vision → `scene_analyses[]` riche
2. **Sans video / video pas trouvee** : cree 1 seule scene synthetique vague → 1 plan storyboard → 0 videos

Le job "Superman vs Ninjas" avait une URL MeTube mais le fichier n'etait pas dans `WATCH_DIR` ("File not in watch dir"). Le research a cree 1 scene synthetique → tout le pipeline n'a produit qu'un seul plan. De plus, meme quand `run_analysis()` fonctionne, elle detecte 1 seule scene sur 15s (seuil ffmpeg trop permissif).

Cote Kitsu : seul le projet + 1 concept vide (ecran noir) + 1 shot overview existent. Pas d'assets, pas de shots par scene, pas de previews sur les shots.

## Correctifs

### 1. `_step_research()` — Download MeTube + fallback LLM

**1a. Telecharger la video depuis MeTube**
Si `job["url"]` contient `tube.ewutelo.cloud`, telecharger le fichier dans `WATCH_DIR` via HTTP GET avant d'appeler `run_analysis()`. Timeout 120s, max 500MB.

**1b. Ameliorer la detection de scenes**
Si ffmpeg ne detecte qu'1 scene sur une video > 5s, reduire le seuil (0.3 → 0.2 → 0.15) ou decouper uniformement tous les 3-5s comme fallback.

**1c. Fallback LLM quand pas de video**
Si aucune video disponible (brief textuel pur), appeler LiteLLM pour decomposer le brief en `num_scenes` scenes structurees (JSON) au lieu de creer 1 scene vague.

Prompt LLM :
```
Tu es un directeur artistique. Decompose ce brief en {num_scenes} scenes cinematographiques.
Brief: {description}
Style de reference: {ref_style}, Mood: {ref_mood}, Couleurs: {ref_colors}

Retourne un JSON array. Pour chaque scene:
{{
  "scene_index": 0,
  "description": "Description narrative de la scene",
  "visual_prompt": "Prompt detaille pour generation image/video",
  "camera_movement": "pan left / dolly in / static / ...",
  "mood": "intense / calm / ...",
  "duration_seconds": 5
}}
```

**1d. Concept preview fiable**
S'assurer que le mood board est uploade comme preview du Concept dans Kitsu. Logger + retry si l'upload echoue. Verifier que `concept_id` est present dans le job.

### 2. `_step_script()` — LLM Scene Splitter + enrichissement

**2a. Detection scene_analyses pauvres**
Si `scene_analyses` contient <=1 item ou que le seul item est synthetique (pas de `keyframe`, pas de `analysis.suggested_prompt` substantiel), declencher le LLM Scene Splitter.

**2b. LLM Scene Splitter**
`num_scenes` parametrable via `params["num_scenes"]` (defaut : 5). Appeler LiteLLM avec le prompt ci-dessus. Parser le JSON retourne comme `scene_analyses` et continuer le flow normal.

**2c. Enrichissement des prompts**
Injecter les metadonnees de la reference (`ref_style`, `ref_mood`, `ref_colors` depuis Qdrant ou l'analyse video) dans chaque `visual_prompt` de scene.

### 3. `_step_script()` — Kitsu conforme (doc officielle)

Ref: `kitsu-docs` collection Qdrant (98 points), sections 5.5, 5.7, 1.16, 1.17.

**3a. Assets par personnage/decor (pas par scene)**
Analyser le brief via LLM pour extraire les entites (personnages, decors, props). Creer 1 asset Kitsu par entite avec le bon `asset_type` (Characters, Environment, Props).

Prompt LLM :
```
Extrais les entites visuelles de ce brief. Retourne un JSON:
{{"characters": ["Superman", "Ninja Leader"], "environments": ["Forest", "Temple"], "props": ["Sword"]}}
```

**3b. Shots par scene**
1 shot par scene (`SH0010`, `SH0020`, ...) sous la sequence. Chaque shot a :
- `description` : le visual_prompt de la scene
- `data` : `{"prompt": ..., "scene_index": ..., "duration": ..., "camera": ...}`
- `nb_frames` : calcule depuis duration * fps

**3c. Breakdown/Casting**
Pour chaque shot, determiner quels assets y apparaissent (via LLM ou analyse du prompt). Cast chaque asset dans le shot via `PUT /entities/{shot_id}/casting`.

**3d. Tasks sur chaque shot**
Les task types du pipeline (Storyboard, Video Gen, etc.) sont automatiquement crees par Kitsu quand le shot est cree. Verifier que c'est bien le cas.

### 4. `_step_storyboard()` — Preview sur chaque shot

**4a. Upload preview par shot**
Pour chaque frame generee, uploader comme preview sur la task "Storyboard CF" du shot correspondant (pas juste sur le shot overview).

**4b. Statut WFA par shot**
Chaque task storyboard → status WFA pour validation individuelle.

### 5. `_step_videogen()` — Failsafe + preview Kitsu

**5a. Failsafe scene_prompts vide**
Si `scene_prompts` est vide, construire des prompts depuis la description du job (comme le storyboard fait deja en fallback). Ne jamais retourner 0 videos sans erreur.

**5b. Preview upload par shot**
Uploader la video generee comme preview sur la task "Video Gen" de chaque shot dans Kitsu.

**5c. Telegram video**
Envoyer le lien streaming fal.ai dans Telegram (deja implemente).

### 6. `_step_brief()` — production_type

`production_type: "tvshow"` (inchange). Le type `short` avait des limitations dans Kitsu auto-heberge (assets/concepts). Documente dans le code ligne 576.

## Decisions de design

| Decision | Choix | Raison |
|----------|-------|--------|
| production_type | `tvshow` | Valide par REX — `short` avait des bugs |
| Assets | Par personnage/decor | Conforme doc Kitsu — pas par scene |
| Nombre de scenes | Parametrable (defaut 5) | `params["num_scenes"]` |
| Fallback video | LLM decomposition | Quand MeTube indisponible |
| Scene detection | Seuil adaptatif | 0.3 → 0.2 → 0.15 si trop peu de scenes |
| Previews | Sur task du shot | Conforme doc Kitsu (preview → comment → task) |

## Fichiers impactes

| Fichier | Fonctions modifiees |
|---------|-------------------|
| `roles/videoref-engine/files/app.py` | `_step_research()`, `_step_script()`, `_step_storyboard()`, `_step_videogen()`, `_step_brief()` |

## Estimation

~250 lignes modifiees/ajoutees dans `app.py`. Pas de nouveau fichier.
