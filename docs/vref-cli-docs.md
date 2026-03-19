# vref — VideoRef Engine CLI Documentation

> Version: 0.6.0 | API: https://cine.ewutelo.cloud | Source: roles/videoref-engine/files/vref

## Overview

`vref` is the command-line interface for the VideoRef creative pipeline. It allows humans and AI agents (OpenClaw, Claude Code, n8n) to:

- Download and analyze video references (MeTube → VideoRef Engine)
- Search visual references by style, mood, or semantic similarity
- Remix existing references with modifications (subject, style, mood, colors)
- Generate ComfyUI workflows ready for image generation

Zero dependencies — pure Python 3, calls the REST API. Works on Windows, Linux, macOS, RPi.

## Installation

```bash
# Copy to PATH
cp roles/videoref-engine/files/vref ~/.local/bin/vref
chmod +x ~/.local/bin/vref

# Or set VREF_URL if not using default
export VREF_URL=https://cine.ewutelo.cloud
```

## Commands

### vref health
Check service status and integrations.

```bash
$ vref health
✅ VideoRef Engine v0.6.0
  ✅ litellm
  ✅ kitsu
  ✅ qdrant
  ✅ gitea
```

### vref watch
List downloaded videos in the watch directory (MeTube downloads).

```bash
$ vref watch
📁 4 files in watch dir:

  📹 Video by santeanime.mp4
  📹 Video by evolving.ai.mp4
  📹 Video by logic_lens_3d [Logic_3d_video 20260314] DV3tQOejWn0.mp4
  📹 Video by radi_sastra_kusumah [Radi Sastra Kusumah 20260318] DWBm_YXE2pM.mp4
```

### vref jobs
List completed analyses.

```bash
$ vref jobs
📊 4 completed analyses:

  ✅ Video by santeanime.json
  ✅ Video by evolving.ai.json
  ✅ Video by logic_lens_3d [Logic_3d_video 20260314] DV3tQOejWn0.json
  ✅ Video by radi_sastra_kusumah [Radi Sastra Kusumah 20260318] DWBm_YXE2pM.json
```

### vref analyze <filename> [--template]
Analyze a video file. Detects scenes, extracts keyframes, runs Claude Vision analysis on each scene, creates shots + assets in Kitsu, indexes in Qdrant, versions in Gitea.

```bash
$ vref analyze "Video by santeanime.mp4" --template cinematic
🔍 Analyzing 'Video by santeanime.mp4' (template: cinematic)...
   This may take 1-5 minutes for Claude Vision analysis.

✅ Status: completed | Scenes: 8
   Kitsu: 8 shots, 8 assets, 8 previews
   Qdrant: ✅
   Gitea: ✅

──────────────────────────────────────────────────────────────────────
  Scene 1: 3D Animation                    | Cheerful and Playful
  Scene 2: Surrealistic cartoon            | Ironic, critical
  Scene 3: Cartoonish, 3D Animation        | Humorous, Surreal
  ...
```

Templates available: `default`, `cinematic`, `anime`

### vref assets [--style X] [--mood Y] [-q text] [--motion low|medium|high]
Search VideoRef assets in Kitsu. All filters are optional and combined with AND.

```bash
# All assets
$ vref assets

# Filter by style
$ vref assets --style 3D

# Filter by mood
$ vref assets --mood playful

# Free text search
$ vref assets -q "shoes animated"

# Combine filters
$ vref assets --style cartoon --mood humorous --motion low

# JSON output (for piping to jq or agents)
$ vref assets --style 3D --json
```

### vref get <asset_id>
Get full details of a specific asset including the complete AI prompt.

```bash
$ vref get 5b7c3339-df14-4858-9171-8d93286cad68
📦 Video by santeanime
   ID:      5b7c3339-df14-4858-9171-8d93286cad68
   Style:   3D animation, cartoonish, playful
   Mood:    humorous, whimsical, lively
   Colors:  #d1c8b4, #3b312e, #6d6a66, #bb4430, #160f10
   Motion:  low
   Created: 2026-03-19T09:04:13

──────────────────────────────────────────────────────────────────────
AI Prompt:
Create a playful and cartoonish 3D animation scene featuring
anthropomorphic shoes with expressive faces in various comical
situations, such as at the beach and in industrial settings...
```

### vref prompt <asset_id>
Print only the AI prompt — designed for piping.

```bash
# Copy prompt to clipboard (macOS)
$ vref prompt abc123 | pbcopy

# Pipe to another tool
$ vref prompt abc123 | xargs -I{} comfyui-api generate --prompt "{}"

# Use in a script
PROMPT=$(vref prompt abc123)
echo "Generating with: $PROMPT"
```

### vref search <query>
Semantic search across all analyzed videos via Qdrant embeddings. Finds visually similar references by meaning, not just keywords.

```bash
$ vref search dramatic dark cinematic
🔎 'dramatic dark cinematic' — 4 results:

  [███████░░░░░░░░░░░░░] 0.385
    Style: 3D Animation with Cartoon Elements | Mood: Whimsical
    Prompt: Create a whimsical 3D animated story...

  [██████░░░░░░░░░░░░░░] 0.353
    Style: 3D Animation with Cartoon Elements | Mood: Whimsical
    Prompt: Create a whimsical 3D animated story...

$ vref search "watercolor landscape sunset" --limit 3
$ vref search "anime fight scene neon" --json
```

### vref remix <asset_id> [options]
Remix an existing VideoRef asset by modifying elements. Claude LLM rewrites the prompt with your changes applied, then generates a ComfyUI workflow.

```bash
# Change subject
$ vref remix abc123 --subject "cats instead of shoes"

# Change style
$ vref remix abc123 --style "watercolor painting"

# Change mood
$ vref remix abc123 --mood "melancholic"

# Change colors
$ vref remix abc123 --colors "#1a1a2e, #16213e, #0f3460"

# Add elements
$ vref remix abc123 --extra "add rain, twilight sky, neon signs"

# Combine all modifications
$ vref remix abc123 \
  --subject "dragons" \
  --style "oil painting" \
  --mood "epic" \
  --extra "medieval castle, fire breathing" \
  --template cinematic \
  --output dragon-epic-v1

# Remix from a raw prompt (no asset needed)
$ vref remix --source-prompt "A cat sitting on a windowsill" \
  --style "pixel art" --mood "cozy" --output pixel-cat-v1
```

Output:
```
🎨 Remixing with: {'subject': 'dragons', 'style': 'oil painting', 'mood': 'epic'}
   Template: cinematic

✅ Remix complete!
──────────────────────────────────────────────────────────────────────
Original:  Create a playful 3D animation scene with anthropomorphic shoes...
──────────────────────────────────────────────────────────────────────
Remixed:   Create an epic oil painting depicting majestic dragons with
           expressive features soaring over a medieval castle, breathing
           fire against a dramatic sky...
──────────────────────────────────────────────────────────────────────
Style:     oil painting
Mood:      epic
Workflow:   /comfyui-workflows/dragon-epic-v1_workflow.json
```

## JSON Output

All commands support `--json` for machine-readable output:

```bash
$ vref assets --style 3D --json | jq '.assets[0].ai_prompt'
$ vref get abc123 --json | jq '{style, mood, prompt: .ai_prompt}'
$ vref remix abc123 --style watercolor --json | jq '.workflow'
```

## Agent Integration

### OpenClaw Agent Example
```python
import subprocess, json

# Search for references
result = subprocess.run(["vref", "assets", "--style", "3D", "--json"],
                       capture_output=True, text=True)
assets = json.loads(result.stdout)["assets"]

# Get the best match
asset_id = assets[0]["id"]
detail = subprocess.run(["vref", "get", asset_id, "--json"],
                       capture_output=True, text=True)
prompt = json.loads(detail.stdout)["ai_prompt"]

# Remix it
remix = subprocess.run(
    ["vref", "remix", asset_id,
     "--subject", "robots",
     "--style", "cyberpunk",
     "--json"],
    capture_output=True, text=True)
workflow = json.loads(remix.stdout)["workflow"]
```

### n8n Workflow
Use the Execute Command node with:
- Command: `vref assets --mood playful --json`
- Parse JSON output for downstream nodes

### Claude Code
```bash
# In Claude Code terminal
vref search "anime magical girl transformation"
vref get <id_from_results>
vref remix <id> --style "studio ghibli" --mood "nostalgic"
```

## Architecture

```
MeTube (download) → VideoRef Engine (analyze) → Kitsu (track) + Qdrant (search) + Gitea (version)
                                               ↓
                                          vref CLI ← Agent (OpenClaw/Claude Code/n8n)
                                               ↓
                                          ComfyUI (generate images)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| VREF_URL | https://cine.ewutelo.cloud | VideoRef Engine API base URL |

## REST API Reference

The CLI calls these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| /health | GET | Service health |
| /api/watch | GET | List watch dir files |
| /api/jobs | GET | List completed analyses |
| /api/analyze | POST | Analyze video (body: {filename, template}) |
| /api/assets | GET | Search assets (?style=X&mood=Y&q=Z) |
| /api/assets/{id} | GET | Get asset details |
| /api/search | GET | Semantic search (?q=query&limit=5) |
| /api/remix | POST | Remix asset (body: {asset_id, modifications, template}) |
| /api/webhook/metube | POST | MeTube download webhook (auto-trigger) |
