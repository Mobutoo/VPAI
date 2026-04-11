# Analyse Pipeline de Production vs Cinema Studio 2.0

> Date: 19 mars 2026 | Auteur: Claude Code session

## Pipeline de production en 14 étapes (Kitsu task types)

```
PRE-PRODUCTION                    PRODUCTION                      POST-PRODUCTION
┌──────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
│ 1. Brief             │  │ 7.  Image Gen            │  │ 10. Montage              │
│ 2. Recherche         │  │ 8.  Video Gen            │  │ 11. Sous-titres          │
│ 3. Script            │  │ 9.  Storyboard CF        │  │ 12. Color Grade          │
│ 4. Storyboard CF     │  │                          │  │ 13. Review               │
│ 5. Voice-over        │  │                          │  │ 14. Export / Publication  │
│ 6. Music             │  │                          │  │                          │
└──────────────────────┘  └──────────────────────────┘  └──────────────────────────┘
```

## Mapping outils existants par étape

| # | Étape | Outil actuel | Workflow | Status |
|---|-------|-------------|----------|--------|
| 1 | **Brief** | OpenClaw agent `artist` (Basquiat) + Telegram | Manuel via Telegram ou CLI | ✅ Opérationnel |
| 2 | **Recherche** | **VideoRef Engine** (`vref search`, `vref assets`) + MeTube | `vref analyze` → Kitsu assets + Qdrant search | ✅ **Nouveau (cette session)** |
| 3 | **Script** | OpenClaw agent `writer` (Thot) | Prompt → script structuré + NocoDB | ✅ Opérationnel |
| 4 | **Storyboard CF** | OpenClaw `artist` → n8n `creative-pipeline` → ComfyUI | Image gen locale (fal.ai, SDXL) | ✅ Opérationnel |
| 5 | **Voice-over** | ❌ Pas d'outil intégré | — | 🔴 **GAP** |
| 6 | **Music** | ❌ Pas d'outil intégré | — | 🔴 **GAP** |
| 7 | **Image Gen** | ComfyUI (local ARM64) + LiteLLM (Seedream/DALL-E cloud) | n8n `creative-pipeline.json.j2` | ✅ Opérationnel |
| 8 | **Video Gen** | BytePlus/Seedance (cloud) + Remotion (local) | n8n `video-generate.json` | ✅ Opérationnel |
| 9 | **Storyboard CF** | `vref remix` → ComfyUI workflow JSON | Templates Gitea (default/cinematic/anime) | ✅ **Nouveau (cette session)** |
| 10 | **Montage** | OpenCut (Docker, on-demand) | Manuel via `cut.ewutelo.cloud` | ⚠️ Manuel |
| 11 | **Sous-titres** | ❌ Pas d'outil intégré | — | 🔴 **GAP** |
| 12 | **Color Grade** | ❌ Pas d'outil intégré | — | 🔴 **GAP** |
| 13 | **Review** | Kitsu playlists + Review Room | Task status WFA → Done | ✅ Opérationnel |
| 14 | **Export/Publication** | ❌ Pas de pipeline auto | — | 🔴 **GAP** |

## Mapping outils de tracking

| Fonction | Outil | Status |
|----------|-------|--------|
| Production tracker | **Kitsu** (25+ shots, 6 assets, 5 metadata, previews) | ✅ |
| Asset provenance | n8n `asset-register.json` → PostgreSQL + Plane | ✅ |
| Semantic search | **Qdrant** (videoref_styles + kitsu-docs + vref-cli-docs) | ✅ **Nouveau** |
| Template versioning | **Gitea** (comfyui-templates, 3 templates) | ✅ **Nouveau** |
| Agent orchestration | OpenClaw (10 agents, skills, Telegram routing) | ✅ |
| Workflow automation | n8n (creative-pipeline, asset-register, video-generate) | ✅ |
| Monitoring | Grafana dashboard (creative-studio.json) | ✅ |
| Budget tracking | LiteLLM $5/jour global + n8n budget monitor | ✅ |

## Gaps vs Cinema Studio 2.0

### 🔴 Gaps critiques (manquants)

| Feature Cinema Studio | Ce qui manque | Effort estimé |
|----------------------|---------------|---------------|
| **Camera simulation** (RED, ARRI, IMAX, Panavision) | Tokens de prompt simulant les optiques physiques dans les templates ComfyUI | 1 jour — adapter l'approche Open-Higgsfield (virtual lenses → prompt tokens) |
| **Lens simulation** (Anamorphic, Macro, Prime 85mm, 35mm) | Mapping focal length → tokens bokeh/DOF/compression dans les templates | 1 jour — même approche |
| **Aperture control** (f/1.4 → f/11, DOF) | Tokens de profondeur de champ dans les prompts | Inclus avec lenses |
| **Camera motion** (dolly, pan, crane, FPV) | Pour image: tokens de mouvement. Pour vidéo: paramètres BytePlus/Kling | 2 jours |
| **Character consistency** (Soul Cast) | LoRA training + IP-Adapter dans ComfyUI, ou service dédié | 3-5 jours |
| **Voice cloning + Lip sync** | API externe (ElevenLabs, Coqui) + workflow n8n | 2 jours |
| **Sous-titres auto** | Whisper (local ou API) → SRT → Remotion | 1 jour |
| **Color grading auto** | LUT application dans ffmpeg ou ComfyUI post-processing | 1 jour |
| **Grid Mode** (16 variations) | ComfyUI batch_size + vref CLI `--variations 16` | 0.5 jour |
| **Multi-model routing** (Kling 3.0, Veo 3.1, Sora 2, WAN 2.5) | Ajouter ces modèles dans LiteLLM config + routing dans creative-pipeline | 1 jour config |

### 🟡 Gaps mineurs

| Feature | Status |
|---------|--------|
| Music generation | Peut utiliser Suno/Udio via API cloud |
| Export pipeline auto | n8n workflow export → S3 → publication |
| Storyboard from script | OpenClaw `artist` fait déjà image gen from script |

### ✅ Avantages de notre stack vs Cinema Studio

| Feature | Notre stack | Cinema Studio |
|---------|-------------|---------------|
| **Self-hosted** | 100% auto-hébergé, zéro SaaS | Cloud-only ($9-119/mois) |
| **Production tracking** | Kitsu (shots, séquences, tasks, previews, reviews) | ❌ Aucun tracker intégré |
| **Semantic search** | Qdrant (recherche par similarité visuelle) | ❌ Pas de recherche sémantique |
| **Asset library** | Kitsu + Qdrant (réutilisable cross-productions) | Basique |
| **Agent automation** | OpenClaw 10 agents + n8n orchestration | ❌ Manuel seulement |
| **Remix API** | `vref remix` + Claude LLM prompt rewrite | ❌ Pas de remix programmatique |
| **Budget control** | LiteLLM hard cap $5/jour, alertes Telegram | ❌ Crédits agressifs, cher |
| **CLI/API** | `vref` CLI universel pour agents | ❌ UI only |
| **Versioning** | Gitea (templates + analyses versionnées) | ❌ Pas de versioning |
| **Video analysis** | ffmpeg scene detection + Claude Vision | ❌ Pas d'analyse |

## Plan pour combler les gaps prioritaires

### Phase 1 : Camera Presets (1 jour)
Ajouter dans les templates Gitea + `vref remix --camera RED --lens anamorphic --focal 35mm --aperture f2.8`

### Phase 2 : Multi-model video (1 jour)
Ajouter Kling 3.0, Veo 3.1, WAN 2.5 dans LiteLLM config. Router via n8n creative-pipeline.

### Phase 3 : Voice + Subtitles (2 jours)
Whisper pour transcription/sous-titres. ElevenLabs/Coqui pour voice-over. Workflow n8n.

### Phase 4 : Character Consistency (3 jours)
IP-Adapter dans ComfyUI + LoRA training pipeline.

## Architecture cible

```
BRIEF                    RECHERCHE               GENERATION              POST-PROD
┌──────────┐  ┌──────────────────┐  ┌──────────────────────┐  ┌──────────────────┐
│ OpenClaw │  │ MeTube (download)│  │ ComfyUI (image, local)│  │ OpenCut (montage)│
│ + Telegram│→│ VideoRef (analyze)│→│ + camera presets       │→│ Whisper (sous-t) │
│           │  │ vref search/remix│  │ Seedance (video,cloud)│  │ ffmpeg (color)   │
│           │  │ Qdrant (semantic)│  │ Kling/Veo/WAN (video) │  │ Remotion (render)│
│           │  │ Kitsu (assets)   │  │ ElevenLabs (voice)    │  │ Kitsu (review)   │
└──────────┘  └──────────────────┘  └──────────────────────┘  └──────────────────┘
      ↕               ↕                       ↕                       ↕
   Telegram       vref CLI              n8n creative-pipeline     n8n export
                  OpenClaw                  LiteLLM routing        S3 → publish
```
