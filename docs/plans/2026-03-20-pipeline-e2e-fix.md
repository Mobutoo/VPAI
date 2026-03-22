# Pipeline Creatif E2E Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Corriger le pipeline creatif pour qu'il genere des scenes multiples, remplisse Kitsu correctement (assets, shots, breakdown, previews), et produise des videos de bout en bout.

**Architecture:** Le videoref-engine (`app.py`) orchestre 14 steps. Les corrections ciblent `_step_research()` (download MeTube + fallback LLM), `_step_script()` (LLM scene splitter + assets Kitsu), `_step_storyboard()` (preview par shot), et `_step_videogen()` (failsafe + preview Kitsu).

**Tech Stack:** Python 3.12, aiohttp, LiteLLM (Claude/GPT), Kitsu/Zou REST API, fal.ai, Qdrant, Telegram Bot API

**Design doc:** `docs/plans/2026-03-20-pipeline-e2e-fix-design.md`

**Fichier principal:** `roles/videoref-engine/files/app.py`

**Deploiement:** `ansible-playbook playbooks/workstation.yml --tags videoref-engine -e "workstation_pi_ip=100.64.0.1"` puis rebuild Docker.

**Test E2E:** `docker exec openclaw-sbx-agent-director-402731dc python3 /workspace/vref --json produce-start --title "TestE2E" ...` puis `produce-step` pour chaque etape.

**Audit Kitsu:** `scripts/audit_kitsu.py` (execute dans le container videoref).

---

## Task 1: `_step_research()` — Download video MeTube

**Files:**
- Modify: `roles/videoref-engine/files/app.py` — fonction `_step_research()` (lignes ~2976-3112)

**Step 1: Ajouter la fonction `_download_metube_video()`**

Ajouter avant `_step_research()` :

```python
async def _download_metube_video(url: str, watch_dir: Path) -> Path | None:
    """Download video from MeTube (tube.ewutelo.cloud) into watch_dir.

    Returns local path if successful, None otherwise.
    """
    if "tube." not in url and "metube" not in url.lower():
        return None

    # Extract filename from URL (URL-decoded)
    from urllib.parse import unquote
    filename = unquote(url.split("/")[-1])
    if not filename:
        return None

    local_path = watch_dir / filename
    if local_path.exists() and local_path.stat().st_size > 0:
        print(f"[research] MeTube video already in watch: {local_path.name}", flush=True)
        return local_path

    print(f"[research] Downloading MeTube video: {filename}...", flush=True)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    print(f"[research] MeTube download failed: {resp.status}", flush=True)
                    return None
                content = await resp.read()
                if len(content) > 500 * 1024 * 1024:  # 500MB limit
                    print(f"[research] Video too large: {len(content)} bytes", flush=True)
                    return None
                local_path.write_bytes(content)
                print(f"[research] Downloaded {len(content)} bytes -> {local_path.name}", flush=True)
                return local_path
    except Exception as exc:
        print(f"[research] MeTube download error: {exc}", flush=True)
        return None
```

**Step 2: Modifier `_step_research()` pour tenter le download MeTube**

Dans `_step_research()`, avant le bloc qui verifie `WATCH_DIR`, ajouter :

```python
# Try to download video from MeTube if URL provided
video_url = job.get("url", "")
if video_url and ("tube." in video_url or "download" in video_url):
    downloaded = await _download_metube_video(video_url, WATCH_DIR)
    if downloaded:
        # Re-check watch dir — file should now be there
        print(f"[research] MeTube video ready: {downloaded.name}", flush=True)
```

**Step 3: Syntax check**

Run: `python3 -c "import ast; ast.parse(open('roles/videoref-engine/files/app.py').read()); print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add roles/videoref-engine/files/app.py
git commit -m "feat(videoref): download MeTube video in _step_research before analysis"
```

---

## Task 2: `_step_research()` — Fallback LLM scene decomposition

**Files:**
- Modify: `roles/videoref-engine/files/app.py` — fonction `_step_research()` (lignes ~3001-3044)

**Step 1: Ajouter `_llm_decompose_scenes()`**

Ajouter avant `_step_research()` :

```python
async def _llm_decompose_scenes(
    description: str,
    num_scenes: int = 5,
    style: str = "",
    mood: str = "",
    colors: str = "",
) -> list[dict[str, Any]]:
    """Use LLM to decompose a text brief into structured scenes.

    Returns list of scene dicts compatible with scene_analyses format.
    Called when no video reference is available.
    """
    if not LITELLM_URL or not LITELLM_API_KEY:
        return []

    style_ctx = ""
    if style or mood or colors:
        style_ctx = f"\nStyle de reference: {style}\nMood: {mood}\nCouleurs: {colors}"

    prompt = f"""Tu es un directeur artistique pour des videos courtes (reels/shorts).
Decompose ce brief en exactement {num_scenes} scenes cinematographiques.{style_ctx}

Brief: {description}

Retourne UNIQUEMENT un JSON array valide. Pour chaque scene:
[{{
  "scene_index": 0,
  "description": "Description narrative de la scene (1-2 phrases)",
  "visual_prompt": "Prompt detaille pour generation image/video en anglais, incluant sujet, action, eclairage, ambiance, cadrage",
  "camera_movement": "static | pan left | pan right | dolly in | dolly out | tracking | crane up | handheld",
  "mood": "mot-cle ambiance",
  "duration_seconds": 5
}}]"""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LITELLM_URL}/v1/chat/completions",
                json={
                    "model": "fast",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 3000,
                },
                headers={
                    "Authorization": f"Bearer {LITELLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]

                # Extract JSON from response (handle markdown code blocks)
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                content = content.strip()

                scenes_raw = json.loads(content)

                # Convert to scene_analyses format
                scenes = []
                for i, s in enumerate(scenes_raw):
                    scenes.append({
                        "scene_index": i,
                        "start_time": i * s.get("duration_seconds", 5),
                        "end_time": (i + 1) * s.get("duration_seconds", 5),
                        "duration": s.get("duration_seconds", 5),
                        "analysis": {
                            "style": style or "cinematic",
                            "mood": s.get("mood", mood or "dramatic"),
                            "colors": colors or "",
                            "description": s.get("description", ""),
                            "suggested_prompt": s.get("visual_prompt", s.get("description", "")),
                            "camera_movement": s.get("camera_movement", "static"),
                            "negative_prompt": "blurry, low quality, distorted",
                        },
                        "llm_generated": True,
                    })
                print(f"[research] LLM decomposed brief into {len(scenes)} scenes", flush=True)
                return scenes
    except Exception as exc:
        print(f"[research] LLM decomposition error: {exc}", flush=True)
        return []
```

**Step 2: Modifier le fallback dans `_step_research()`**

Remplacer le bloc qui cree 1 scene synthetique (lignes ~3031-3040) par :

```python
# Instead of 1 synthetic scene, decompose via LLM
num_scenes = int(params.get("num_scenes", 5))
llm_scenes = await _llm_decompose_scenes(
    description=job.get("description", job.get("title", "")),
    num_scenes=num_scenes,
    style=extras.get("ref_style", ""),
    mood=extras.get("ref_mood", ""),
    colors=extras.get("ref_colors", ""),
)
if llm_scenes:
    extras["scene_analyses"] = llm_scenes
else:
    # Ultimate fallback: single scene from description
    extras["scene_analyses"] = [{
        "scene_index": 0,
        "start_time": 0, "end_time": 5, "duration": 5,
        "analysis": {
            "style": extras.get("ref_style", "cinematic"),
            "mood": extras.get("ref_mood", "dramatic"),
            "colors": extras.get("ref_colors", ""),
            "description": job.get("description", ""),
            "suggested_prompt": job.get("description", ""),
            "negative_prompt": "blurry, low quality",
        },
    }]
```

**Step 3: Syntax check + commit**

```bash
python3 -c "import ast; ast.parse(open('roles/videoref-engine/files/app.py').read()); print('OK')"
git add roles/videoref-engine/files/app.py
git commit -m "feat(videoref): LLM scene decomposition fallback when no video reference"
```

---

## Task 3: `_step_research()` — Concept preview fiable

**Files:**
- Modify: `roles/videoref-engine/files/app.py` — `_step_research()` bloc mood board (lignes ~3051-3101)

**Step 1: Ajouter logging + retry pour concept preview upload**

Apres l'upload du mood board, verifier le resultat :

```python
# Upload mood board to Concept
concept_id = job.get("concept_id", "")
if concept_id and mood_bytes:
    upload_ok = await _kitsu_upload_concept_preview(
        session, concept_id, mood_bytes, job.get("kitsu_project_id", ""),
    )
    if upload_ok:
        print(f"[research] Concept preview uploaded OK", flush=True)
    else:
        print(f"[research] WARNING: Concept preview upload failed, retrying...", flush=True)
        # Retry once
        upload_ok = await _kitsu_upload_concept_preview(
            session, concept_id, mood_bytes, job.get("kitsu_project_id", ""),
        )
        if not upload_ok:
            print(f"[research] ERROR: Concept preview upload failed after retry", flush=True)
```

**Step 2: Syntax check + commit**

```bash
python3 -c "import ast; ast.parse(open('roles/videoref-engine/files/app.py').read()); print('OK')"
git add roles/videoref-engine/files/app.py
git commit -m "fix(videoref): concept preview upload with retry and logging"
```

---

## Task 4: `_step_script()` — LLM scene splitter pour scenes pauvres

**Files:**
- Modify: `roles/videoref-engine/files/app.py` — `_step_script()` (lignes ~3115-3241)

**Step 1: Detecter les scene_analyses pauvres et enrichir**

Au debut de `_step_script()`, avant l'iteration sur scene_analyses, ajouter :

```python
scene_analyses = job.get("scene_analyses", job.get("scenes", []))

# Detect poor/synthetic scene data → enrich via LLM
is_poor = (
    len(scene_analyses) <= 1
    or all(sa.get("llm_generated") for sa in scene_analyses)
    or not any(
        sa.get("analysis", {}).get("suggested_prompt", "")
        for sa in scene_analyses
    )
)

if is_poor:
    num_scenes = int(params.get("num_scenes", 5))
    print(f"[script] Scene data poor ({len(scene_analyses)} scenes), enriching via LLM to {num_scenes} scenes", flush=True)
    llm_scenes = await _llm_decompose_scenes(
        description=job.get("description", job.get("title", "")),
        num_scenes=num_scenes,
        style=job.get("ref_style", ""),
        mood=job.get("ref_mood", ""),
        colors=job.get("ref_colors", ""),
    )
    if llm_scenes:
        scene_analyses = llm_scenes
```

**Step 2: Syntax check + commit**

```bash
python3 -c "import ast; ast.parse(open('roles/videoref-engine/files/app.py').read()); print('OK')"
git add roles/videoref-engine/files/app.py
git commit -m "feat(videoref): LLM scene splitter in _step_script when scenes are poor"
```

---

## Task 5: `_step_script()` — Assets Kitsu par personnage/decor

**Files:**
- Modify: `roles/videoref-engine/files/app.py` — `_step_script()` section Kitsu (lignes ~3172-3230)

**Step 1: Ajouter `_llm_extract_entities()`**

```python
async def _llm_extract_entities(description: str) -> dict[str, list[str]]:
    """Extract characters, environments, props from a brief via LLM.

    Returns {"characters": [...], "environments": [...], "props": [...]}.
    """
    if not LITELLM_URL or not LITELLM_API_KEY:
        return {"characters": [], "environments": [], "props": []}

    prompt = f"""Extrais les entites visuelles de ce brief de video.
Retourne UNIQUEMENT un JSON valide avec ces 3 cles:
{{"characters": ["nom1", "nom2"], "environments": ["lieu1"], "props": ["objet1"]}}

Brief: {description}"""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LITELLM_URL}/v1/chat/completions",
                json={
                    "model": "fast",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
                headers={
                    "Authorization": f"Bearer {LITELLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return {"characters": [], "environments": [], "props": []}
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                if "```" in content:
                    content = content.split("```json")[-1].split("```")[0] if "```json" in content else content.split("```")[1].split("```")[0]
                return json.loads(content.strip())
    except Exception as exc:
        print(f"[script] Entity extraction error: {exc}", flush=True)
        return {"characters": [], "environments": [], "props": []}
```

**Step 2: Creer les assets Kitsu par entite (pas par scene)**

Remplacer la creation d'assets (1 par scene) par :

```python
# Extract entities from brief for Kitsu assets
entities = await _llm_extract_entities(job.get("description", job.get("title", "")))
print(f"[script] Entities: {len(entities.get('characters',[]))} chars, {len(entities.get('environments',[]))} envs, {len(entities.get('props',[]))} props", flush=True)

# Map entity type name -> Kitsu asset_type_id
asset_type_map = {}  # populated below
for at in asset_types:
    name_lower = at.get("name", "").lower()
    if "character" in name_lower:
        asset_type_map["characters"] = at["id"]
    elif "environment" in name_lower:
        asset_type_map["environments"] = at["id"]
    elif "prop" in name_lower:
        asset_type_map["props"] = at["id"]

# Create assets
asset_ids = []
for category, names in entities.items():
    type_id = asset_type_map.get(category)
    if not type_id:
        continue
    for name in names:
        asset = await _kitsu_create_asset(
            session, project_id, type_id,
            name=name,
            description=f"{category.title()}: {name}",
            data={
                "ai_prompt": f"{name}, {job.get('ref_style', 'cinematic')} style",
                "style": job.get("ref_style", ""),
                "mood": job.get("ref_mood", ""),
            },
        )
        if asset and "id" in asset:
            asset_ids.append(asset["id"])
            print(f"[script] Created asset: {name} ({category})", flush=True)
```

**Step 3: Creer les shots avec frame info**

```python
# Create shots — 1 per scene
shot_ids = []
fps = int(job.get("fps", 24))
for sp in scene_prompts:
    idx = sp.get("scene_index", 0)
    duration = sp.get("duration_seconds", 5)
    frame_in = idx * duration * fps + 1
    frame_out = (idx + 1) * duration * fps

    shot = await _kitsu_create_shot(
        session, project_id, sequence_id,
        name=f"SH{(idx + 1) * 10:04d}",
        data={
            "prompt": sp.get("enriched", sp.get("original", ""))[:300],
            "scene_index": idx,
            "duration": duration,
            "camera_movement": sp.get("camera_movement", ""),
            "frame_in": frame_in,
            "frame_out": frame_out,
        },
        description=sp.get("enriched", "")[:500],
    )
    if shot and "id" in shot:
        shot_ids.append(shot["id"])
```

**Step 4: Breakdown/Casting — lier assets aux shots**

```python
# Cast all assets into all shots (simplified — each asset appears in all scenes)
# A more advanced version would use LLM to determine which assets per scene
for shot_id in shot_ids:
    for asset_id in asset_ids:
        await _kitsu_cast_asset_to_shot(session, project_id, shot_id, asset_id)
```

**Step 5: Syntax check + commit**

```bash
python3 -c "import ast; ast.parse(open('roles/videoref-engine/files/app.py').read()); print('OK')"
git add roles/videoref-engine/files/app.py
git commit -m "feat(videoref): Kitsu assets by entity + shots with frames + breakdown casting"
```

---

## Task 6: `_step_storyboard()` — Preview sur chaque shot

**Files:**
- Modify: `roles/videoref-engine/files/app.py` — `_step_storyboard()` section Kitsu upload (lignes ~3334-3365)

**Step 1: Uploader le preview sur la task du bon shot**

Verifier que le code existant utilise `kitsu_shot_ids[scene_idx]` (pas `scene_idx + 1`) pour cibler le bon shot. Si l'overview shot est `shot_ids[0]`, les shots par scene commencent a `shot_ids[1]` — valider l'indexation.

```python
# Get the correct shot for this scene
if scene_idx < len(job.get("kitsu_shot_ids", [])):
    target_shot_id = job["kitsu_shot_ids"][scene_idx]
else:
    target_shot_id = job.get("kitsu_overview_shot_id", "")

if target_shot_id and image_bytes:
    # Get or create Storyboard task on this shot
    task = await _kitsu_get_or_create_task(
        session, target_shot_id, storyboard_type_id, project_id,
    )
    if task:
        comment = await _kitsu_post_comment(
            session, task["id"], wfa_status_id,
            f"Storyboard S{scene_idx} — {model_name}\n{prompt[:200]}",
        )
        if comment and image_bytes:
            preview_id = await _kitsu_upload_preview(
                session, comment, image_bytes, project_id,
            )
            scene_result["kitsu_preview_id"] = preview_id or ""
            scene_result["kitsu_shot_id"] = target_shot_id
```

**Step 2: Syntax check + commit**

```bash
python3 -c "import ast; ast.parse(open('roles/videoref-engine/files/app.py').read()); print('OK')"
git add roles/videoref-engine/files/app.py
git commit -m "fix(videoref): storyboard preview uploaded to correct shot task"
```

---

## Task 7: `_step_videogen()` — Failsafe + preview Kitsu

**Files:**
- Modify: `roles/videoref-engine/files/app.py` — `_step_videogen()` (lignes ~3617-3737)

**Step 1: Failsafe quand scene_prompts est vide**

Au debut de `_step_videogen()`, avant la boucle :

```python
scene_prompts = job.get("scene_prompts", [])

# Failsafe: if scene_prompts empty, build from description
if not scene_prompts:
    print("[videogen] WARNING: scene_prompts empty, building from description", flush=True)
    desc = job.get("description", job.get("title", ""))
    if desc:
        scene_prompts = [{
            "scene_index": 0,
            "original": desc,
            "enriched": _inject_camera_tokens(
                desc, job.get("camera", ""), job.get("lens", ""),
            ),
        }]
```

**Step 2: Upload video preview sur le shot Kitsu**

Apres le download video reussi, uploader comme preview sur la task "Video Gen" du shot :

```python
if video_bytes and scene_result.get("video_path"):
    # Upload video to Kitsu shot task
    shot_ids = job.get("kitsu_shot_ids", [])
    scene_idx = sp.get("scene_index", 0)
    if scene_idx < len(shot_ids):
        target_shot_id = shot_ids[scene_idx]
        try:
            async with aiohttp.ClientSession() as ks:
                task = await _kitsu_get_or_create_task(
                    ks, target_shot_id, videogen_type_id,
                    job.get("kitsu_project_id", ""),
                )
                if task:
                    comment = await _kitsu_post_comment(
                        ks, task["id"], wfa_status_id,
                        f"Video S{scene_idx} — {model_name}, {duration}s",
                    )
                    # Note: Kitsu accepts video previews (mp4)
                    if comment:
                        await _kitsu_upload_preview(
                            ks, comment, video_bytes,
                            job.get("kitsu_project_id", ""),
                        )
                        print(f"[videogen] Uploaded video preview to Kitsu shot {target_shot_id[:8]}", flush=True)
        except Exception as ke:
            print(f"[videogen] Kitsu preview upload error: {ke}", flush=True)
```

**Step 3: Syntax check + commit**

```bash
python3 -c "import ast; ast.parse(open('roles/videoref-engine/files/app.py').read()); print('OK')"
git add roles/videoref-engine/files/app.py
git commit -m "feat(videoref): videogen failsafe + video preview upload to Kitsu shots"
```

---

## Task 8: Deploy + E2E Test

**Step 1: Deploy**

```bash
cd /home/asus/seko/VPAI && source .venv/bin/activate
ansible-playbook playbooks/workstation.yml --tags videoref-engine -e "workstation_pi_ip=100.64.0.1"
ssh mobuone@100.64.0.1 "cd /opt/workstation && docker compose -f docker-compose-creative.yml build --no-cache videoref-engine && docker compose -f docker-compose-creative.yml up -d videoref-engine"
```

**Step 2: E2E test — brief textuel (pas de video)**

```bash
SLUG=$(docker exec openclaw-sbx-agent-director-402731dc python3 /workspace/vref --json produce-start --title "Dragon vs Knight" --camera RED --lens anamorphic 2>&1 | grep slug | cut -d'"' -f4)
docker exec ... python3 /workspace/vref produce-step $SLUG brief --description "A fire dragon attacks a medieval castle. A lone knight stands against it. Epic battle with dramatic lighting."
docker exec ... python3 /workspace/vref produce-step $SLUG research
docker exec ... python3 /workspace/vref produce-step $SLUG script
```

**Expected:** `scene_prompts` contient 5 scenes. Kitsu a 5 shots + assets (Dragon, Knight, Castle).

**Step 3: Audit Kitsu**

```bash
cat scripts/audit_kitsu.py | ssh ... "docker exec -i workstation_videoref python3 -u -"
```

**Expected:**
- Sequences: 1
- Shots: 6 (SH0000 overview + SH0010-SH0050)
- Assets: 3+ (Dragon, Knight, Castle)
- Concept: preview != NONE

**Step 4: Continue pipeline**

```bash
docker exec ... python3 /workspace/vref produce-step $SLUG storyboard
docker exec ... python3 /workspace/vref produce-step $SLUG voiceover --skip
docker exec ... python3 /workspace/vref produce-step $SLUG music --skip
docker exec ... python3 /workspace/vref produce-step $SLUG imagegen --skip
docker exec ... python3 /workspace/vref produce-step $SLUG videogen
```

**Expected:**
- Storyboard: 5 frames generes, chacun uploade sur son shot Kitsu
- Videogen: 5 clips video generes via Seedance, chacun uploade sur son shot Kitsu
- Telegram: preview video dans le topic 173 Studio

**Step 5: Final Kitsu audit**

Verifier que chaque shot a :
- Task "Storyboard CF" avec preview image
- Task "Video Gen" avec preview video
- Assets castes (breakdown)

**Step 6: Commit final**

```bash
git add -A
git commit -m "feat(videoref): pipeline E2E fix — multi-scene, Kitsu assets, previews"
```

---

## Resume des changements

| Task | Fonction | Changement |
|------|----------|------------|
| 1 | `_download_metube_video()` | Nouvelle fonction — download MeTube → WATCH_DIR |
| 2 | `_llm_decompose_scenes()` | Nouvelle fonction — LLM scene splitter |
| 2 | `_step_research()` | Fallback LLM au lieu de 1 scene synthetique |
| 3 | `_step_research()` | Concept preview upload avec retry |
| 4 | `_step_script()` | Detection scenes pauvres → enrichissement LLM |
| 5 | `_llm_extract_entities()` | Nouvelle fonction — extraction personnages/decors |
| 5 | `_step_script()` | Assets par entite + shots avec frames + casting |
| 6 | `_step_storyboard()` | Preview sur la task du bon shot |
| 7 | `_step_videogen()` | Failsafe scene_prompts vide + preview Kitsu |
| 8 | — | Deploy + E2E test complet |
