# ComfyUI Studio v0.5.0 — Series Engine Design Spec

> Date: 2026-03-23 | Status: Draft

## 1. Goal

Transform ComfyUI Studio from a "1 brief = 1 content" tool into a series production engine (N episodes x M formats) with brand coherence, narrative continuity, and cross-episode asset reuse.

## 2. Scope

### In Scope (v0.5.0)

| Module | File | MCP Tools |
|--------|------|-----------|
| Style DNA | `comfyui_cli/style_dna.py` | 4 |
| Scene Graph | `comfyui_cli/scene_graph.py` | 5 |
| Series Engine | `comfyui_cli/series_engine.py` | 4 |
| **Total** | 3 modules + 3 test files + mcp_server.py update | **13 new tools** |

### Out of Scope (deferred to v0.6.0)

- **Beat-Sync Montage** (`beat_sync.py`) — librosa/soundfile as optional extra (`extras_require["audio"]`), ARM64 compatibility risk on RPi5
- GPU-based generation (cloud APIs only)
- OpenClaw integration
- Feedback loops / performance metrics

## 3. Architecture

### 3.1 Data Flow

```
NocoDB (hq.ewutelo.cloud)          Qdrant (existing)
  source of truth                   semantic search
  editable via web UI               fast vector lookup
         |                                |
         |  sync (MCP tool call)          |
         +-----> style_dna.py -----> brand-dna collection
         +-----> scene_graph.py ---> scene-entities collection
         +-----> series_engine.py    (no Qdrant, CRUD only)
                      |
                      v
              LiteLLM (embeddings + LLM)
```

### 3.2 Execution Architecture

- **MCP server** stays on Waza (RPi5)
- **NocoDB API** accessed via `hq.ewutelo.cloud` (Caddy VPN-only, Tailscale)
- **Qdrant** accessed via existing `qdrant_url` config
- **LiteLLM** accessed via existing `litellm_url` config
- **Embeddings** via LiteLLM (same 1536-dim model as `rag.py`)

### 3.3 Config Additions

Two new keys in `comfyui_cli/config.py` (same DEFAULTS -> YAML -> ENV pattern):

| Key | Env Var | Default |
|-----|---------|---------|
| `nocodb_url` | `NOCODB_URL` | `https://hq.ewutelo.cloud` |
| `nocodb_token` | `NOCODB_TOKEN` | `""` |

Env var naming follows the existing convention: external services use their own prefix (`QDRANT_URL`, `KITSU_URL`, `PLANE_URL`), not `COMFYUI_`.

## 4. Module Designs

### 4.1 Style DNA (`comfyui_cli/style_dna.py`)

**Purpose:** Store and inject brand visual identity into generation prompts.

#### Data Model

```python
@dataclass
class StyleDNA:
    brand_name: str
    palette: Dict[str, str]         # {primary, secondary, accent, background}
    typography: Dict[str, str]      # {heading, body}
    tone: str                       # "professional", "playful", "luxe", "urban"
    visual_style: str               # "cinematic", "flat", "3d_render", "photorealistic"
    voice_profile: Dict[str, Any]   # {voice_id, speed, pitch}
    mood_keywords: List[str]
    reference_images: List[str]     # paths in asset cache
    description: str                # free-text for embedding

    def to_dict(self) -> Dict: ...
    @classmethod
    def from_dict(cls, data: Dict) -> "StyleDNA": ...
```

#### NocoDB Table: `brand_styles`

| Column | Type | Notes |
|--------|------|-------|
| `brand_name` | text (PK) | Unique identifier |
| `palette_primary` | text | Hex color |
| `palette_secondary` | text | Hex color |
| `palette_accent` | text | Hex color |
| `palette_background` | text | Hex color |
| `typography_heading` | text | Font name |
| `typography_body` | text | Font name |
| `tone` | text | Enum-like |
| `visual_style` | text | Enum-like |
| `voice_id` | text | ElevenLabs voice ID |
| `voice_speed` | number | 0.5-2.0 |
| `voice_pitch` | number | -20 to +20 |
| `mood_keywords` | json | `["energetic", "warm"]` |
| `reference_images` | json | `["path1.png", "path2.png"]` |
| `description` | text | Free-text for embedding |
| `updated_at` | datetime | Auto-updated |

#### Qdrant Collection: `brand-dna`

- Vector: `embed(description)` (1536-dim, same model as rag.py)
- Payload: full StyleDNA dict
- Point ID: `hash(brand_name)` (same pattern as rag.py `_text_to_point_id`)

#### Class: `StyleDNAManager`

```python
class StyleDNAManager:
    def __init__(self, rag_engine: RagEngine, nocodb: NocoDBClient): ...

    def create_or_update(self, style: StyleDNA) -> StyleDNA
    def get(self, brand_name: str) -> Optional[StyleDNA]
    def sync_from_nocodb(self, brand_name: Optional[str] = None) -> int
    def enrich_prompt(self, prompt: str, brand_name: str, asset_type: str) -> str
    def check_drift(self, prompt: str, brand_name: str) -> float
```

`check_drift` is internal-only (not exposed as MCP tool). Used for logging/diagnostics.

**Sync flow:** NocoDB -> StyleDNA dataclass -> Qdrant upsert (one-directional). `create_or_update` writes to NocoDB first, then syncs to Qdrant.

#### Prompt Enrichment by Asset Type

| Type | Injection |
|------|-----------|
| `image` | `"Style: {visual_style}, palette: {palette}, mood: {mood_keywords}. {description}"` |
| `video` | Same as image + `"Camera movement: {tone_to_camera_map}"` |
| `audio_voice` | Select `voice_id` + `speed/pitch` params |
| `audio_music` | `"Genre/mood: {mood_keywords}, energy: {tone_to_energy_map}"` |
| `text` | System prompt: `"Tone: {tone}. Writing style: {description}"` |

#### MCP Tools (4)

| Tool | Input | Output |
|------|-------|--------|
| `style_dna_create` | StyleDNA fields | Created/updated StyleDNA |
| `style_dna_get` | `brand_name` | StyleDNA or null |
| `style_dna_enrich_prompt` | `prompt`, `brand_name`, `asset_type` | Enriched prompt string |
| `style_dna_sync` | `brand_name` (optional) | Count of synced styles |

### 4.2 Scene Graph (`comfyui_cli/scene_graph.py`)

**Purpose:** Persistent entity registry (characters, products, locations) for visual continuity across contents.

#### Data Model

```python
@dataclass
class Entity:
    entity_id: str
    entity_type: str              # "character", "product", "location", "prop"
    name: str
    brand_name: str               # FK to StyleDNA
    visual_description: str       # detailed description for prompts (~100 words)
    reference_images: List[str]   # paths in asset cache
    attributes: Dict[str, Any]    # flexible: hair_color, height, material...
    appearance_count: int              # incremented on each use
    last_seen_content: str             # last content name

    def to_dict(self) -> Dict: ...
    @classmethod
    def from_dict(cls, data: Dict) -> "Entity": ...
```

#### NocoDB Table: `scene_entities`

| Column | Type | Notes |
|--------|------|-------|
| `entity_id` | text (PK) | UUID or slug |
| `entity_type` | text | character/product/location/prop |
| `name` | text | Display name |
| `brand_name` | text | FK to brand_styles |
| `visual_description` | text | Detailed prompt-ready description |
| `reference_images` | json | `["path1.png"]` |
| `attributes` | json | Flexible key-value |
| `appearance_count` | number | Incremented on each use |
| `last_seen_content` | text | Content name |
| `updated_at` | datetime | Auto-updated |

#### Qdrant Collection: `scene-entities`

- Vector: `embed(visual_description)` (1536-dim)
- Payload: full Entity dict
- Point ID: `hash(entity_id)`

#### Class: `SceneGraph`

```python
class SceneGraph:
    def __init__(self, rag_engine: RagEngine, nocodb: NocoDBClient): ...

    def register_entity(self, entity: Entity) -> Entity
    def get_entity(self, name: str, brand: str) -> Optional[Entity]
    def find_similar(self, description: str, entity_type: str = "", limit: int = 5) -> List[Entity]
    def build_scene_prompt(self, entity_names: List[str], brand: str) -> str
    def record_appearance(self, entity_name: str, brand: str, content_name: str, step: str) -> None
    def sync_from_nocodb(self, brand_name: Optional[str] = None) -> int
```

**Visual continuity strategy (no GPU):**
1. Structured descriptions (~100 words) with precise physical attributes
2. Reference images passed as `image_url` to cloud APIs (fal.ai FLUX img2img)
3. Seed fixing when API supports it
4. Standardized prompt format for LLM generation

#### MCP Tools (5)

| Tool | Input | Output |
|------|-------|--------|
| `scene_entity_register` | Entity fields | Created/updated Entity |
| `scene_entity_get` | `name`, `brand` | Entity or null |
| `scene_entity_search` | `description`, `entity_type`, `limit` | List of similar entities |
| `scene_build_prompt` | `entity_names[]`, `brand` | Scene prompt string |
| `scene_entity_sync` | `brand_name` (optional) | Count of synced entities |

### 4.3 Series Engine (`comfyui_cli/series_engine.py`)

**Purpose:** Orchestrate N episodes x M formats with narrative continuity, asset reuse, and cost tracking.

#### Data Model

```python
@dataclass
class SeriesDefinition:
    series_id: str
    brand_name: str
    title: str
    concept: str                   # series pitch
    n_episodes: int
    narrative_arc: str             # "build-up", "episodic", "cliffhanger", "documentary"
    recurring_entities: List[str]  # entity_ids from SceneGraph
    formats: List[str]             # ["reel_9_16", "story_9_16"]
    episode_briefs: List[Dict]     # LLM-generated per episode
    created_at: float
    status: str                    # "draft", "in_production", "done"

    def to_dict(self) -> Dict: ...
    @classmethod
    def from_dict(cls, data: Dict) -> "SeriesDefinition": ...

@dataclass
class Episode:
    episode_number: int
    series_id: str
    title: str
    brief: Dict                    # full episode brief
    status: str                    # "planned", "in_production", "done"
    assets: List[str]              # asset_ids from cache
    reused_assets: List[str]       # reused asset_ids from previous episodes
    kitsu_task_id: str
    cost_usd: float

    def to_dict(self) -> Dict: ...
    @classmethod
    def from_dict(cls, data: Dict) -> "Episode": ...
```

#### NocoDB Tables

**Table: `series`**

| Column | Type | Notes |
|--------|------|-------|
| `series_id` | text (PK) | UUID |
| `brand_name` | text | FK to brand_styles |
| `title` | text | Series title |
| `concept` | text | Series pitch |
| `n_episodes` | number | Episode count |
| `narrative_arc` | text | Arc type |
| `recurring_entities` | json | `["entity_id_1", ...]` |
| `formats` | json | `["reel_9_16", ...]` |
| `status` | text | draft/in_production/done |
| `created_at` | datetime | Creation timestamp |

**Table: `episodes`**

| Column | Type | Notes |
|--------|------|-------|
| `episode_id` | text (PK) | UUID |
| `series_id` | text | FK to series |
| `episode_number` | number | 1-indexed |
| `title` | text | Episode title |
| `brief` | json | Full brief dict |
| `status` | text | planned/in_production/done |
| `assets` | json | `["asset_id_1", ...]` |
| `reused_assets` | json | `["asset_id_1", ...]` |
| `kitsu_task_id` | text | Kitsu task reference |
| `cost_usd` | number | Generation cost |

#### Class: `SeriesEngine`

```python
class SeriesEngine:
    def __init__(self, style_dna_mgr: StyleDNAManager, scene_graph: SceneGraph,
                 asset_cache: AssetCache, nocodb: NocoDBClient,
                 rag_engine: RagEngine): ...

    def create_series(self, concept: str, n_episodes: int, brand_name: str,
                      formats: List[str], narrative_arc: str = "build-up") -> SeriesDefinition
    def get_episode_brief(self, series_id: str, episode_num: int) -> Dict
    def find_reusable_assets(self, series_id: str, episode_num: int) -> List[CachedAsset]
    def series_stats(self, series_id: str) -> Dict
```

**LLM decomposition:** `create_series` calls LiteLLM to decompose a concept into N episode briefs. The prompt includes the StyleDNA, existing SceneGraph entities, and narrative arc type. Output is structured JSON with title, hook, entities, scene, emotion, callbacks per episode.

**Cross-episode asset reuse:** `find_reusable_assets` searches the asset cache for assets from previous episodes in the same series that match recurring entities (characters, locations, music).

**Estimated savings:** 30-40% cost reduction on a 5-episode series vs 5 independent contents.

#### MCP Tools (4)

| Tool | Input | Output |
|------|-------|--------|
| `series_create` | `concept`, `n_episodes`, `brand_name`, `formats`, `narrative_arc` | SeriesDefinition with episode briefs |
| `series_get_brief` | `series_id`, `episode_num` | Enriched episode brief (with context from previous episodes) |
| `series_reuse_assets` | `series_id`, `episode_num` | List of reusable CachedAssets |
| `series_stats` | `series_id` | Stats dict (cost, progress, reuse rate) |

## 5. NocoDB Integration Pattern

All three modules share the same NocoDB access pattern:

```python
class NocoDBClient:
    """Thin wrapper for NocoDB REST API v2.

    NocoDB v0.301.2 uses the v2 API. Endpoints:
    - Data: /api/v2/meta/bases/{base_id}/tables, /api/v1/db/data/v1/{table_id}
    - Meta: /api/v2/meta/tables/{table_id}
    The exact paths must be validated against the running instance.
    """

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["xc-token"] = token
        self._table_cache: Dict[str, str] = {}  # {table_name -> table_id}

    def ensure_tables(self, table_schemas: Dict[str, List[Dict]]) -> None:
        """Create tables if they don't exist (idempotent).
        Similar to RagEngine.ensure_collection() pattern.
        table_schemas: {table_name: [{title, uidt, ...}]}"""

    def list_rows(self, table_id: str, params: dict = None) -> List[Dict]: ...
    def get_row(self, table_id: str, row_id: str) -> Dict: ...
    def create_row(self, table_id: str, data: dict) -> Dict: ...
    def update_row(self, table_id: str, row_id: str, data: dict) -> Dict: ...
    def find_row(self, table_id: str, where: str) -> Optional[Dict]: ...
    def resolve_table_id(self, table_name: str) -> str: ...
```

This shared client lives in `comfyui_cli/nocodb.py`. A **single instance** is created in the MCP server via `_get_nocodb()` and injected into all three modules as a constructor argument. This avoids duplicate sessions and table discovery calls (same pattern as `_get_kitsu()` being injected into `PipelineEngine`).

**Table creation:** `ensure_tables()` is called once at init, creating any missing tables idempotently (similar to `RagEngine.ensure_collection()`). Table schemas are defined as constants in each module.

**Table ID resolution:** Table IDs are discovered via the NocoDB meta API and cached in `_table_cache`. `resolve_table_id(name)` is used instead of hardcoded IDs.

## 6. MCP Server Changes

### Tool Registration

Follow the existing manual registration pattern in `mcp/mcp_server.py`:

```python
STYLE_DNA_TOOLS = [
    Tool(name="style_dna_create", description="...", inputSchema={...}),
    Tool(name="style_dna_get", ...),
    Tool(name="style_dna_enrich_prompt", ...),
    Tool(name="style_dna_sync", ...),
]

SCENE_GRAPH_TOOLS = [...]  # 5 tools
SERIES_ENGINE_TOOLS = [...]  # 4 tools

# Added to existing list_tools lambda
server.list_tools = lambda: (
    COMFYUI_TOOLS + PIPELINE_TOOLS + ORCHESTRATOR_TOOLS +
    RAG_TOOLS + ASSET_CACHE_TOOLS +
    STYLE_DNA_TOOLS + SCENE_GRAPH_TOOLS + SERIES_ENGINE_TOOLS
)
```

### Handler Dispatch

New handler functions per category, added to the existing `call_tool` dispatcher:

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name.startswith("style_dna_"):
        output = await _handle_style_dna_tool(name, arguments)
    elif name.startswith("scene_entity_") or name == "scene_build_prompt":
        output = await _handle_scene_graph_tool(name, arguments)
    elif name.startswith("series_"):
        output = await _handle_series_tool(name, arguments)
    elif name in ORCHESTRATOR_TOOL_NAMES:
        # ... existing handlers
```

### Lazy Init (existing pattern)

```python
_nocodb = None
_style_dna = None
_scene_graph = None
_series = None

def _get_nocodb():
    global _nocodb
    if _nocodb is None:
        cfg = _get_config()
        _nocodb = NocoDBClient(cfg["nocodb_url"], cfg["nocodb_token"])
    return _nocodb

def _get_style_dna():
    global _style_dna
    if _style_dna is None:
        _style_dna = StyleDNAManager(_get_rag(), _get_nocodb())
    return _style_dna

def _get_scene_graph():
    global _scene_graph
    if _scene_graph is None:
        _scene_graph = SceneGraph(_get_rag(), _get_nocodb())
    return _scene_graph

def _get_series():
    global _series
    if _series is None:
        _series = SeriesEngine(
            _get_style_dna(), _get_scene_graph(),
            _get_asset_cache(), _get_nocodb(), _get_rag()
        )
    return _series
```

## 7. Files Changed

### New Files

| File | Purpose |
|------|---------|
| `comfyui_cli/nocodb.py` | Shared NocoDB REST client |
| `comfyui_cli/style_dna.py` | Style DNA module |
| `comfyui_cli/scene_graph.py` | Scene Graph module |
| `comfyui_cli/series_engine.py` | Series Engine module |
| `tests/test_nocodb.py` | NocoDB client tests |
| `tests/test_style_dna.py` | Style DNA tests |
| `tests/test_scene_graph.py` | Scene Graph tests |
| `tests/test_series_engine.py` | Series Engine tests |

### Modified Files

| File | Change |
|------|--------|
| `mcp/mcp_server.py` | +13 MCP tools (4 style + 5 scene + 4 series), 3 handler functions, 4 lazy-init functions |
| `comfyui_cli/config.py` | +2 config keys (`nocodb_url`, `nocodb_token`) |
| `setup.py` | Version bump 0.4.0 -> 0.5.0, no new required deps (requests already present) |
| `comfyui_cli/__init__.py` | Version bump |

### New Qdrant Collections

| Collection | Content | Vector |
|------------|---------|--------|
| `brand-dna` | StyleDNA per brand | embed(description), 1536-dim |
| `scene-entities` | Entities (characters, locations, products) | embed(visual_description), 1536-dim |

### New NocoDB Tables (4)

| Table | Purpose | Sync Target |
|-------|---------|-------------|
| `brand_styles` | Editable brand visual identity | Qdrant `brand-dna` |
| `scene_entities` | Editable entity registry | Qdrant `scene-entities` |
| `series` | Series definitions | None (CRUD only) |
| `episodes` | Episode briefs and tracking | None (CRUD only) |

## 8. Error Handling

### NocoDB Unavailability

NocoDB is behind Caddy VPN-only. If unreachable:

| Operation | Behavior |
|-----------|----------|
| `create_or_update` | Raise `ConnectionError` with clear message (write path must not silently fail) |
| `get` | Fall back to Qdrant payload if available, log warning |
| `sync_from_nocodb` | Raise `ConnectionError` (explicit sync must report failure) |
| `enrich_prompt` | Fall back to Qdrant-cached style, log warning |
| MCP tool handlers | Catch exceptions, return `{"error": "NocoDB unreachable: ..."}` (existing pattern) |

### Dependency Requirements

The new modules depend on `qdrant-client` and `openai` (via `RagEngine`), which are in `extras_require["rag"]`. Since these extras are already required for the existing MCP server to function (RAG tools, asset cache), no new extras group is needed. The `rag` extra is a de facto requirement for any MCP server deployment.

## 9. Implementation Order

```
Wave 1: nocodb.py + config changes + style_dna.py + tests + MCP tools
         (foundation - everything else depends on NocoDB client and style)
         |
Wave 2: scene_graph.py + tests + MCP tools
         (depends on style_dna for brand_name FK pattern)
         |
Wave 3: series_engine.py + tests + MCP tools + version bump
         (orchestrates style_dna + scene_graph + asset_cache)
```

## 10. Testing Strategy

Follow existing patterns from `tests/`:

- **Unit tests** with mocked dependencies (NocoDB, Qdrant, LiteLLM)
- **Mock NocoDB** via `NocoDBClient` mock (requests.Session patched)
- **Mock Qdrant** via direct `engine._qdrant = mock_qdrant` injection
- **Mock LiteLLM** for embeddings: return fixed 1536-dim vectors
- **Mock LLM** for series decomposition: return pre-built episode briefs
- **Fixture-based** setup with `@pytest.fixture`
- **Dataclass roundtrip** tests: `to_dict()` / `from_dict()`

### Test Coverage Per Module

| Module | Key Tests |
|--------|-----------|
| `nocodb.py` | list/get/create/update/find rows, table ID discovery, auth header |
| `style_dna.py` | create/get, enrich_prompt per asset type, sync_from_nocodb, check_drift returns 0-1, get returns None for unknown |
| `scene_graph.py` | register/get, find_similar with mock Qdrant, build_scene_prompt with 2+ entities, record_appearance increments counter, sync |
| `series_engine.py` | create_series generates N briefs with mock LLM, get_episode_brief includes previous episode context, find_reusable_assets, series_stats |

## 11. Constraints

| Constraint | Impact |
|------------|--------|
| Zero GPU local | Cloud APIs only (fal.ai, Replicate, BytePlus). ComfyUI local = composition/overlay. |
| Zero OpenClaw | Orchestration via MCP tools + n8n + PipelineEngine |
| Zero feedback loop | Style drift = logging only (check_drift returns float, no auto-correction) |
| RPi5 16GB (Waza) | All Python runs on CPU. Qdrant and NocoDB on Sese-AI. |
| NocoDB via Caddy | API calls go through `hq.ewutelo.cloud` (VPN-only), not Docker network |
| Beat-Sync deferred | librosa/soundfile ARM64 risk, moved to v0.6.0 as optional extra |
