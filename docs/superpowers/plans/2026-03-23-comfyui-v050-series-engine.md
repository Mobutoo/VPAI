# ComfyUI Studio v0.5.0 — Series Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 modules (Style DNA, Scene Graph, Series Engine) + shared NocoDB client to ComfyUI Studio, exposed as 13 new MCP tools.

**Architecture:** NocoDB (source of truth, editable) syncs one-directionally to Qdrant (semantic search). A shared `NocoDBClient` is injected into all modules. MCP server on Waza accesses NocoDB via `hq.ewutelo.cloud` (Caddy VPN-only).

**Tech Stack:** Python 3.12, Qdrant (1536-dim cosine), NocoDB REST API v2, LiteLLM (embeddings + LLM), requests, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-comfyui-v050-series-engine-design.md`

**Codebase:** `/opt/workstation/comfyui-studio-repo/`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `comfyui_cli/nocodb.py` | Shared NocoDB REST client (CRUD + table discovery + ensure_tables) |
| `comfyui_cli/style_dna.py` | StyleDNA dataclass + StyleDNAManager (brand identity, prompt enrichment) |
| `comfyui_cli/scene_graph.py` | Entity dataclass + SceneGraph (entity registry, scene prompts) |
| `comfyui_cli/series_engine.py` | SeriesDefinition/Episode dataclasses + SeriesEngine (N episodes x M formats) |
| `tests/test_nocodb.py` | NocoDB client unit tests |
| `tests/test_style_dna.py` | Style DNA unit tests |
| `tests/test_scene_graph.py` | Scene Graph unit tests |
| `tests/test_series_engine.py` | Series Engine unit tests |

### Modified Files

| File | Change |
|------|--------|
| `comfyui_cli/config.py:14-47` | +2 DEFAULTS keys, +2 ENV_MAP entries |
| `comfyui_cli/__init__.py:2` | Version bump 0.4.0 -> 0.5.0 |
| `setup.py:5` | Version bump 0.4.0 -> 0.5.0 |
| `mcp/mcp_server.py:22-34` | +3 imports (NocoDBClient, StyleDNAManager, SceneGraph, SeriesEngine) |
| `mcp/mcp_server.py:47-54` | +4 lazy-init globals |
| `mcp/mcp_server.py:684-692` | +3 tool lists, update list_tools |
| `mcp/mcp_server.py:1114-1126` | +3 handler dispatch branches in call_tool |
| `tests/conftest.py` | +mock_nocodb fixture |

---

## Task 1: NocoDB Client + Config

**Files:**
- Create: `comfyui_cli/nocodb.py`
- Create: `tests/test_nocodb.py`
- Modify: `comfyui_cli/config.py:14-47`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write test for NocoDBClient auth header and list_rows**

```python
# tests/test_nocodb.py
"""Tests for NocoDB REST client."""
import json
import pytest
from unittest.mock import MagicMock, patch
from comfyui_cli.nocodb import NocoDBClient


@pytest.fixture
def nocodb():
    """NocoDBClient with mocked session (post-init)."""
    client = NocoDBClient("https://hq.ewutelo.cloud", "test-token")
    # Save the real header that was set during __init__
    real_headers = dict(client.session.headers)
    # Now replace session for CRUD method mocking
    client.session = MagicMock()
    client._real_headers = real_headers
    return client


class TestNocoDBClientInit:
    def test_auth_header_set(self, nocodb):
        assert nocodb._real_headers["xc-token"] == "test-token"

    def test_base_url_stripped(self):
        client = NocoDBClient("https://hq.ewutelo.cloud/", "tok")
        assert client.base_url == "https://hq.ewutelo.cloud"

    def test_empty_token_raises(self):
        with pytest.raises(ValueError, match="NOCODB_TOKEN"):
            NocoDBClient("https://hq.ewutelo.cloud", "")


class TestListRows:
    def test_list_rows_returns_list(self, nocodb):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"list": [{"Id": 1, "brand_name": "Taff"}]}
        mock_resp.raise_for_status = MagicMock()
        nocodb.session.get.return_value = mock_resp

        rows = nocodb.list_rows("tbl_abc123")
        assert rows == [{"Id": 1, "brand_name": "Taff"}]
        nocodb.session.get.assert_called_once()

    def test_list_rows_with_params(self, nocodb):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"list": []}
        mock_resp.raise_for_status = MagicMock()
        nocodb.session.get.return_value = mock_resp

        nocodb.list_rows("tbl_abc123", params={"where": "(brand_name,eq,Taff)"})
        call_kwargs = nocodb.session.get.call_args.kwargs
        assert "params" in call_kwargs


class TestCreateRow:
    def test_create_row_posts_data(self, nocodb):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"Id": 2, "brand_name": "NewBrand"}
        mock_resp.raise_for_status = MagicMock()
        nocodb.session.post.return_value = mock_resp

        result = nocodb.create_row("tbl_abc123", {"brand_name": "NewBrand"})
        assert result["brand_name"] == "NewBrand"


class TestUpdateRow:
    def test_update_row_patches_data(self, nocodb):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"Id": 1, "tone": "luxe"}
        mock_resp.raise_for_status = MagicMock()
        nocodb.session.patch.return_value = mock_resp

        result = nocodb.update_row("tbl_abc123", "1", {"tone": "luxe"})
        assert result["tone"] == "luxe"


class TestFindRow:
    def test_find_row_returns_match(self, nocodb):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"list": [{"Id": 1, "brand_name": "Taff"}]}
        mock_resp.raise_for_status = MagicMock()
        nocodb.session.get.return_value = mock_resp

        result = nocodb.find_row("tbl_abc123", "(brand_name,eq,Taff)")
        assert result["brand_name"] == "Taff"

    def test_find_row_returns_none_when_empty(self, nocodb):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"list": []}
        mock_resp.raise_for_status = MagicMock()
        nocodb.session.get.return_value = mock_resp

        result = nocodb.find_row("tbl_abc123", "(brand_name,eq,Missing)")
        assert result is None


class TestResolveTableId:
    def test_resolve_caches_result(self, nocodb):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"list": [
            {"id": "tbl_abc", "title": "brand_styles"},
            {"id": "tbl_def", "title": "scene_entities"},
        ]}
        mock_resp.raise_for_status = MagicMock()
        nocodb.session.get.return_value = mock_resp

        tid = nocodb.resolve_table_id("brand_styles")
        assert tid == "tbl_abc"
        # Second call should use cache, not hit API again
        tid2 = nocodb.resolve_table_id("brand_styles")
        assert tid2 == "tbl_abc"
        assert nocodb.session.get.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_nocodb.py -v`
Expected: `ModuleNotFoundError: No module named 'comfyui_cli.nocodb'`

- [ ] **Step 3: Implement NocoDBClient**

```python
# comfyui_cli/nocodb.py
"""NocoDB REST API client.

Thin wrapper for NocoDB REST API. Used by style_dna, scene_graph,
and series_engine modules for CRUD operations on NocoDB tables.
Accessed via hq.ewutelo.cloud (Caddy VPN-only).

NOTE: NocoDB v0.301.2 API paths. The data prefix depends on the instance
configuration. If paths fail at runtime, check the NocoDB Swagger UI at
/dashboard/#/nc/swagger to verify the correct prefix.
"""
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# NocoDB v0.301.2 data endpoint prefix
# Format: /api/v1/db/data/v1/{table_id} for data CRUD
# Format: /api/v2/meta/bases/{base_id}/tables for table meta
NOCODB_DATA_PREFIX = "/api/v1/db/data/v1"
NOCODB_META_PREFIX = "/api/v2/meta"


class NocoDBClient:
    """NocoDB REST API client with table ID caching."""

    def __init__(self, base_url: str, token: str):
        if not token:
            raise ValueError(
                "NocoDB token is required. Set NOCODB_TOKEN env var."
            )
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["xc-token"] = token
        self._table_cache: Dict[str, str] = {}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def list_rows(
        self, table_id: str, params: Optional[Dict] = None
    ) -> List[Dict]:
        """List rows from a table."""
        resp = self.session.get(
            self._url(f"{NOCODB_DATA_PREFIX}/{table_id}"),
            params=params or {},
        )
        resp.raise_for_status()
        return resp.json().get("list", [])

    def get_row(self, table_id: str, row_id: str) -> Dict:
        """Get a single row by ID."""
        resp = self.session.get(
            self._url(f"{NOCODB_DATA_PREFIX}/{table_id}/{row_id}"),
        )
        resp.raise_for_status()
        return resp.json()

    def create_row(self, table_id: str, data: Dict) -> Dict:
        """Create a new row."""
        resp = self.session.post(
            self._url(f"{NOCODB_DATA_PREFIX}/{table_id}"),
            json=data,
        )
        resp.raise_for_status()
        return resp.json()

    def update_row(self, table_id: str, row_id: str, data: Dict) -> Dict:
        """Update an existing row."""
        resp = self.session.patch(
            self._url(f"{NOCODB_DATA_PREFIX}/{table_id}/{row_id}"),
            json=data,
        )
        resp.raise_for_status()
        return resp.json()

    def find_row(
        self, table_id: str, where: str
    ) -> Optional[Dict]:
        """Find first row matching a where clause.

        where format: "(column,operator,value)" e.g. "(brand_name,eq,Taff)"
        """
        rows = self.list_rows(table_id, params={"where": where, "limit": 1})
        return rows[0] if rows else None

    def resolve_table_id(self, table_name: str, base_id: str = "") -> str:
        """Resolve table name to table ID via meta API. Cached.

        Args:
            table_name: Table name to resolve
            base_id: NocoDB base ID (required on first call if cache is empty)
        """
        if table_name in self._table_cache:
            return self._table_cache[table_name]

        if not base_id:
            raise ValueError(
                "base_id is required to resolve table names on first call"
            )

        resp = self.session.get(
            self._url(f"{NOCODB_META_PREFIX}/bases/{base_id}/tables")
        )
        resp.raise_for_status()
        for table in resp.json().get("list", []):
            self._table_cache[table["title"]] = table["id"]

        if table_name not in self._table_cache:
            raise ValueError(f"Table '{table_name}' not found in NocoDB")
        return self._table_cache[table_name]

    def ensure_tables(
        self, table_schemas: Dict[str, List[Dict]], base_id: str = ""
    ) -> List[str]:
        """Create tables if they don't exist (idempotent).

        Args:
            table_schemas: {table_name: [{title: str, uidt: str, ...}]}
            base_id: NocoDB base ID (required for creation)

        Returns:
            List of created table names (empty if all exist).
        """
        if not base_id:
            raise ValueError("base_id is required to ensure tables")

        # Refresh cache
        try:
            resp = self.session.get(
                self._url(f"{NOCODB_META_PREFIX}/bases/{base_id}/tables")
            )
            resp.raise_for_status()
            for table in resp.json().get("list", []):
                self._table_cache[table["title"]] = table["id"]
        except requests.RequestException:
            logger.warning("Could not fetch table list from NocoDB")

        created = []
        for table_name, columns in table_schemas.items():
            if table_name in self._table_cache:
                continue
            resp = self.session.post(
                self._url(f"{NOCODB_META_PREFIX}/bases/{base_id}/tables"),
                json={"title": table_name, "columns": columns},
            )
            resp.raise_for_status()
            table_data = resp.json()
            self._table_cache[table_name] = table_data["id"]
            created.append(table_name)
            logger.info("Created NocoDB table: %s", table_name)

        return created
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_nocodb.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Add config keys for NocoDB**

In `comfyui_cli/config.py`, add to `DEFAULTS` dict (after line 30, before the closing `}`):

```python
    "nocodb_url": "https://hq.ewutelo.cloud",
    "nocodb_token": "",
```

Add to `ENV_MAP` dict (after line 46, before the closing `}`):

```python
    "NOCODB_URL": "nocodb_url",
    "NOCODB_TOKEN": "nocodb_token",
```

- [ ] **Step 6: Add mock_nocodb fixture to conftest.py**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def mock_nocodb():
    """Mock NocoDB client."""
    client = MagicMock()
    client.find_row.return_value = None
    client.list_rows.return_value = []
    client.create_row.side_effect = lambda tid, data: {"Id": 1, **data}
    client.update_row.side_effect = lambda tid, rid, data: {"Id": rid, **data}
    client.resolve_table_id.side_effect = lambda name: f"tbl_{name}"
    return client
```

- [ ] **Step 7: Run full test suite to check no regressions**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/ -v --tb=short`
Expected: All existing tests + 9 new tests PASS

- [ ] **Step 8: Commit**

```bash
cd /opt/workstation/comfyui-studio-repo
git add comfyui_cli/nocodb.py comfyui_cli/config.py tests/test_nocodb.py tests/conftest.py
git commit -m "feat(nocodb): add NocoDB REST client + config keys

Shared client for style_dna, scene_graph, series_engine modules.
CRUD operations, table ID caching, idempotent ensure_tables.
Config: NOCODB_URL, NOCODB_TOKEN (same env var pattern as QDRANT_URL)."
```

---

## Task 2: Style DNA Module

**Files:**
- Create: `comfyui_cli/style_dna.py`
- Create: `tests/test_style_dna.py`

- [ ] **Step 1: Write tests for StyleDNA dataclass**

```python
# tests/test_style_dna.py
"""Tests for Style DNA module."""
import pytest
from unittest.mock import MagicMock, patch
from comfyui_cli.style_dna import StyleDNA, StyleDNAManager


SAMPLE_STYLE = StyleDNA(
    brand_name="Taff",
    palette={"primary": "#1B2A4A", "secondary": "#FFFFFF",
             "accent": "#D4A853", "background": "#F5F5F5"},
    typography={"heading": "Montserrat", "body": "Open Sans"},
    tone="professional",
    visual_style="cinematic",
    voice_profile={"voice_id": "abc123", "speed": 1.0, "pitch": 0},
    mood_keywords=["confident", "warm", "premium"],
    reference_images=["ref/taff-logo.png"],
    description="Premium professional brand with warm cinematic tones",
)


class TestStyleDNARoundtrip:
    def test_to_dict_from_dict(self):
        d = SAMPLE_STYLE.to_dict()
        assert d["brand_name"] == "Taff"
        assert d["palette"]["primary"] == "#1B2A4A"

        restored = StyleDNA.from_dict(d)
        assert restored.brand_name == SAMPLE_STYLE.brand_name
        assert restored.palette == SAMPLE_STYLE.palette
        assert restored.mood_keywords == SAMPLE_STYLE.mood_keywords

    def test_from_dict_handles_nocodb_flat_row(self):
        """NocoDB stores palette as flat columns, not nested dict."""
        row = {
            "brand_name": "Taff",
            "palette_primary": "#1B2A4A",
            "palette_secondary": "#FFFFFF",
            "palette_accent": "#D4A853",
            "palette_background": "#F5F5F5",
            "typography_heading": "Montserrat",
            "typography_body": "Open Sans",
            "tone": "professional",
            "visual_style": "cinematic",
            "voice_id": "abc123",
            "voice_speed": 1.0,
            "voice_pitch": 0,
            "mood_keywords": ["confident", "warm"],
            "reference_images": [],
            "description": "Test brand",
        }
        style = StyleDNA.from_nocodb_row(row)
        assert style.brand_name == "Taff"
        assert style.palette["primary"] == "#1B2A4A"
        assert style.voice_profile["voice_id"] == "abc123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_style_dna.py::TestStyleDNARoundtrip -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement StyleDNA dataclass**

```python
# comfyui_cli/style_dna.py
"""Style DNA — brand visual identity for consistent content generation.

Stores brand styles in NocoDB (editable source of truth) and syncs
to Qdrant (semantic search). Injects brand identity into prompts.
"""
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StyleDNA:
    """Brand visual identity."""

    brand_name: str
    palette: Dict[str, str]
    typography: Dict[str, str]
    tone: str
    visual_style: str
    voice_profile: Dict[str, Any]
    mood_keywords: List[str]
    reference_images: List[str]
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brand_name": self.brand_name,
            "palette": self.palette,
            "typography": self.typography,
            "tone": self.tone,
            "visual_style": self.visual_style,
            "voice_profile": self.voice_profile,
            "mood_keywords": self.mood_keywords,
            "reference_images": self.reference_images,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StyleDNA":
        return cls(
            brand_name=data["brand_name"],
            palette=data["palette"],
            typography=data["typography"],
            tone=data["tone"],
            visual_style=data["visual_style"],
            voice_profile=data["voice_profile"],
            mood_keywords=data.get("mood_keywords", []),
            reference_images=data.get("reference_images", []),
            description=data.get("description", ""),
        )

    @classmethod
    def from_nocodb_row(cls, row: Dict[str, Any]) -> "StyleDNA":
        """Build StyleDNA from flat NocoDB row columns."""
        return cls(
            brand_name=row["brand_name"],
            palette={
                "primary": row.get("palette_primary", ""),
                "secondary": row.get("palette_secondary", ""),
                "accent": row.get("palette_accent", ""),
                "background": row.get("palette_background", ""),
            },
            typography={
                "heading": row.get("typography_heading", ""),
                "body": row.get("typography_body", ""),
            },
            tone=row.get("tone", ""),
            visual_style=row.get("visual_style", ""),
            voice_profile={
                "voice_id": row.get("voice_id", ""),
                "speed": row.get("voice_speed", 1.0),
                "pitch": row.get("voice_pitch", 0),
            },
            mood_keywords=row.get("mood_keywords", []),
            reference_images=row.get("reference_images", []),
            description=row.get("description", ""),
        )

    def to_nocodb_row(self) -> Dict[str, Any]:
        """Flatten StyleDNA to NocoDB column format."""
        return {
            "brand_name": self.brand_name,
            "palette_primary": self.palette.get("primary", ""),
            "palette_secondary": self.palette.get("secondary", ""),
            "palette_accent": self.palette.get("accent", ""),
            "palette_background": self.palette.get("background", ""),
            "typography_heading": self.typography.get("heading", ""),
            "typography_body": self.typography.get("body", ""),
            "tone": self.tone,
            "visual_style": self.visual_style,
            "voice_id": self.voice_profile.get("voice_id", ""),
            "voice_speed": self.voice_profile.get("speed", 1.0),
            "voice_pitch": self.voice_profile.get("pitch", 0),
            "mood_keywords": self.mood_keywords,
            "reference_images": self.reference_images,
            "description": self.description,
        }
```

- [ ] **Step 4: Run dataclass tests to verify they pass**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_style_dna.py::TestStyleDNARoundtrip -v`
Expected: 2 tests PASS

- [ ] **Step 5: Write tests for StyleDNAManager**

Append to `tests/test_style_dna.py`:

```python
COLLECTION_BRAND_DNA = "brand-dna"


@pytest.fixture
def mock_rag():
    rag = MagicMock()
    rag.embed.return_value = [0.1] * 1536
    rag.ensure_collection.return_value = False
    return rag


@pytest.fixture
def manager(mock_rag, mock_nocodb):
    return StyleDNAManager(mock_rag, mock_nocodb)


class TestStyleDNAManagerGet:
    def test_get_from_nocodb(self, manager, mock_nocodb):
        mock_nocodb.find_row.return_value = {
            "Id": 1, "brand_name": "Taff", "palette_primary": "#1B2A4A",
            "palette_secondary": "#FFF", "palette_accent": "#D4A853",
            "palette_background": "#F5F5F5", "typography_heading": "Montserrat",
            "typography_body": "Open Sans", "tone": "professional",
            "visual_style": "cinematic", "voice_id": "", "voice_speed": 1.0,
            "voice_pitch": 0, "mood_keywords": [], "reference_images": [],
            "description": "test",
        }
        style = manager.get("Taff")
        assert style is not None
        assert style.brand_name == "Taff"

    def test_get_returns_none_for_unknown(self, manager, mock_nocodb):
        mock_nocodb.find_row.return_value = None
        assert manager.get("Unknown") is None


class TestStyleDNAManagerCreateOrUpdate:
    def test_create_new_style(self, manager, mock_nocodb):
        mock_nocodb.find_row.return_value = None
        result = manager.create_or_update(SAMPLE_STYLE)
        assert result.brand_name == "Taff"
        mock_nocodb.create_row.assert_called_once()

    def test_update_existing_style(self, manager, mock_nocodb):
        mock_nocodb.find_row.return_value = {"Id": 1, "brand_name": "Taff"}
        result = manager.create_or_update(SAMPLE_STYLE)
        assert result.brand_name == "Taff"
        mock_nocodb.update_row.assert_called_once()


class TestEnrichPrompt:
    def test_enrich_image_prompt(self, manager, mock_nocodb):
        mock_nocodb.find_row.return_value = {
            "Id": 1, "brand_name": "Taff", "palette_primary": "#1B2A4A",
            "palette_secondary": "#FFF", "palette_accent": "#D4A853",
            "palette_background": "#F5F5F5", "typography_heading": "M",
            "typography_body": "O", "tone": "professional",
            "visual_style": "cinematic", "voice_id": "", "voice_speed": 1.0,
            "voice_pitch": 0, "mood_keywords": ["confident", "warm"],
            "reference_images": [], "description": "Premium brand",
        }
        enriched = manager.enrich_prompt("A man in an office", "Taff", "image")
        assert "cinematic" in enriched
        assert "confident" in enriched

    def test_enrich_text_prompt(self, manager, mock_nocodb):
        mock_nocodb.find_row.return_value = {
            "Id": 1, "brand_name": "Taff", "palette_primary": "#1B2A4A",
            "palette_secondary": "#FFF", "palette_accent": "#D4A853",
            "palette_background": "#F5F5F5", "typography_heading": "M",
            "typography_body": "O", "tone": "professional",
            "visual_style": "cinematic", "voice_id": "", "voice_speed": 1.0,
            "voice_pitch": 0, "mood_keywords": [], "reference_images": [],
            "description": "Premium brand",
        }
        enriched = manager.enrich_prompt("Write a caption", "Taff", "text")
        assert "professional" in enriched

    def test_enrich_returns_original_if_brand_not_found(self, manager, mock_nocodb):
        mock_nocodb.find_row.return_value = None
        enriched = manager.enrich_prompt("A photo", "Missing", "image")
        assert enriched == "A photo"


class TestSyncFromNocodb:
    def test_sync_all_brands(self, manager, mock_nocodb, mock_rag):
        mock_nocodb.list_rows.return_value = [
            {"Id": 1, "brand_name": "A", "palette_primary": "#000",
             "palette_secondary": "#FFF", "palette_accent": "#F00",
             "palette_background": "#FFF", "typography_heading": "M",
             "typography_body": "O", "tone": "playful", "visual_style": "flat",
             "voice_id": "", "voice_speed": 1.0, "voice_pitch": 0,
             "mood_keywords": [], "reference_images": [], "description": "Brand A"},
            {"Id": 2, "brand_name": "B", "palette_primary": "#111",
             "palette_secondary": "#FFF", "palette_accent": "#0F0",
             "palette_background": "#FFF", "typography_heading": "M",
             "typography_body": "O", "tone": "luxe", "visual_style": "cinematic",
             "voice_id": "", "voice_speed": 1.0, "voice_pitch": 0,
             "mood_keywords": [], "reference_images": [], "description": "Brand B"},
        ]
        count = manager.sync_from_nocodb()
        assert count == 2


class TestCheckDrift:
    def test_check_drift_returns_float(self, manager, mock_nocodb, mock_rag):
        mock_nocodb.find_row.return_value = {
            "Id": 1, "brand_name": "Taff", "palette_primary": "#1B2A4A",
            "palette_secondary": "#FFF", "palette_accent": "#D4A853",
            "palette_background": "#F5F5F5", "typography_heading": "M",
            "typography_body": "O", "tone": "professional",
            "visual_style": "cinematic", "voice_id": "", "voice_speed": 1.0,
            "voice_pitch": 0, "mood_keywords": [], "reference_images": [],
            "description": "Premium brand",
        }
        mock_rag.embed.return_value = [0.1] * 1536
        drift = manager.check_drift("A dark moody scene", "Taff")
        assert isinstance(drift, float)
        assert 0.0 <= drift <= 1.0
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_style_dna.py -v -k "not Roundtrip"`
Expected: FAIL — `StyleDNAManager` not yet defined

- [ ] **Step 7: Implement StyleDNAManager**

Append to `comfyui_cli/style_dna.py`:

```python
from comfyui_cli.rag import RagEngine, EMBEDDING_DIM, _text_to_point_id

COLLECTION_BRAND_DNA = "brand-dna"

# Tone -> camera movement hint (for video prompts)
TONE_CAMERA_MAP = {
    "professional": "smooth dolly, steady",
    "playful": "handheld, dynamic pans",
    "luxe": "slow crane, elegant tracking",
    "urban": "FPV drone, fast cuts",
}

# Tone -> music energy (for audio prompts)
TONE_ENERGY_MAP = {
    "professional": "moderate, composed",
    "playful": "upbeat, energetic",
    "luxe": "slow, atmospheric",
    "urban": "high energy, bass-driven",
}


class StyleDNAManager:
    """Manage brand visual identities in NocoDB + Qdrant."""

    TABLE_NAME = "brand_styles"

    def __init__(self, rag_engine: RagEngine, nocodb):
        self.rag = rag_engine
        self.nocodb = nocodb
        self._table_id = None

    def _get_table_id(self) -> str:
        if self._table_id is None:
            self._table_id = self.nocodb.resolve_table_id(self.TABLE_NAME)
        return self._table_id

    def create_or_update(self, style: StyleDNA) -> StyleDNA:
        """Write style to NocoDB, then sync to Qdrant."""
        table_id = self._get_table_id()
        row_data = style.to_nocodb_row()

        existing = self.nocodb.find_row(
            table_id, f"(brand_name,eq,{style.brand_name})"
        )
        if existing:
            self.nocodb.update_row(table_id, str(existing["Id"]), row_data)
        else:
            self.nocodb.create_row(table_id, row_data)

        self._sync_to_qdrant(style)
        return style

    def get(self, brand_name: str) -> Optional[StyleDNA]:
        """Get style from NocoDB. Falls back to Qdrant if NocoDB unavailable."""
        table_id = self._get_table_id()
        try:
            row = self.nocodb.find_row(
                table_id, f"(brand_name,eq,{brand_name})"
            )
            if row:
                return StyleDNA.from_nocodb_row(row)
        except Exception:
            logger.warning("NocoDB unavailable, trying Qdrant for %s", brand_name)
            return self._get_from_qdrant(brand_name)
        return None

    def sync_from_nocodb(self, brand_name: Optional[str] = None) -> int:
        """Sync NocoDB -> Qdrant. Returns count of synced styles."""
        table_id = self._get_table_id()
        self.rag.ensure_collection(COLLECTION_BRAND_DNA)

        if brand_name:
            row = self.nocodb.find_row(
                table_id, f"(brand_name,eq,{brand_name})"
            )
            if row:
                self._sync_to_qdrant(StyleDNA.from_nocodb_row(row))
                return 1
            return 0

        rows = self.nocodb.list_rows(table_id)
        for row in rows:
            self._sync_to_qdrant(StyleDNA.from_nocodb_row(row))
        return len(rows)

    def enrich_prompt(
        self, prompt: str, brand_name: str, asset_type: str
    ) -> str:
        """Inject brand style into a generation prompt."""
        style = self.get(brand_name)
        if not style:
            logger.warning("Brand '%s' not found, returning original prompt", brand_name)
            return prompt

        if asset_type == "image":
            palette_str = ", ".join(f"{k}: {v}" for k, v in style.palette.items())
            mood_str = ", ".join(style.mood_keywords)
            return (
                f"{prompt}\n\nStyle: {style.visual_style}, "
                f"palette: {palette_str}, mood: {mood_str}. "
                f"{style.description}"
            )

        elif asset_type == "video":
            palette_str = ", ".join(f"{k}: {v}" for k, v in style.palette.items())
            mood_str = ", ".join(style.mood_keywords)
            camera = TONE_CAMERA_MAP.get(style.tone, "steady")
            return (
                f"{prompt}\n\nStyle: {style.visual_style}, "
                f"palette: {palette_str}, mood: {mood_str}. "
                f"Camera movement: {camera}. {style.description}"
            )

        elif asset_type == "audio_voice":
            vp = style.voice_profile
            return json.dumps({
                "text": prompt,
                "voice_id": vp.get("voice_id", ""),
                "speed": vp.get("speed", 1.0),
                "pitch": vp.get("pitch", 0),
            })

        elif asset_type == "audio_music":
            mood_str = ", ".join(style.mood_keywords)
            energy = TONE_ENERGY_MAP.get(style.tone, "moderate")
            return f"{prompt}\n\nGenre/mood: {mood_str}, energy: {energy}"

        elif asset_type == "text":
            return (
                f"Tone: {style.tone}. Writing style: {style.description}.\n\n"
                f"{prompt}"
            )

        return prompt

    def check_drift(self, prompt: str, brand_name: str) -> float:
        """Check how far a prompt drifts from brand style (0=on-brand, 1=off-brand)."""
        style = self.get(brand_name)
        if not style:
            return 1.0

        prompt_vec = self.rag.embed(prompt)
        style_vec = self.rag.embed(style.description)

        # Cosine similarity -> drift score
        dot = sum(a * b for a, b in zip(prompt_vec, style_vec))
        mag_a = sum(a * a for a in prompt_vec) ** 0.5
        mag_b = sum(b * b for b in style_vec) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 1.0
        similarity = dot / (mag_a * mag_b)
        return round(max(0.0, min(1.0, 1.0 - similarity)), 4)

    def _sync_to_qdrant(self, style: StyleDNA) -> None:
        """Upsert a single style to Qdrant."""
        self.rag.ensure_collection(COLLECTION_BRAND_DNA)
        self.rag.upsert_document(
            collection=COLLECTION_BRAND_DNA,
            doc_id=style.brand_name,
            text=style.description,
            title=style.brand_name,
            category="brand-style",
            extra_metadata=style.to_dict(),
        )

    def _get_from_qdrant(self, brand_name: str) -> Optional[StyleDNA]:
        """Fallback: search Qdrant for cached style."""
        results = self.rag.search(
            collection=COLLECTION_BRAND_DNA,
            query=brand_name,
            limit=1,
            score_threshold=0.8,
        )
        if results:
            meta = results[0].metadata
            if "brand_name" in meta:
                return StyleDNA.from_dict(meta)
        return None
```

- [ ] **Step 8: Run all style_dna tests**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_style_dna.py -v`
Expected: All 10 tests PASS

- [ ] **Step 9: Commit**

```bash
cd /opt/workstation/comfyui-studio-repo
git add comfyui_cli/style_dna.py tests/test_style_dna.py
git commit -m "feat(style-dna): add StyleDNA module for brand visual identity

StyleDNA dataclass + StyleDNAManager with NocoDB CRUD, Qdrant sync,
prompt enrichment per asset type (image/video/voice/music/text),
and style drift detection."
```

---

## Task 3: Scene Graph Module

**Files:**
- Create: `comfyui_cli/scene_graph.py`
- Create: `tests/test_scene_graph.py`

- [ ] **Step 1: Write tests for Entity dataclass and SceneGraph**

```python
# tests/test_scene_graph.py
"""Tests for Scene Graph module."""
import pytest
from unittest.mock import MagicMock
from comfyui_cli.scene_graph import Entity, SceneGraph


SAMPLE_ENTITY = Entity(
    entity_id="paul-taff",
    entity_type="character",
    name="Paul Taff",
    brand_name="Taff",
    visual_description=(
        "Homme 35 ans, barbe courte soignee, cheveux chatains, "
        "chemise bleue marine, montre en or. Expression: confiant."
    ),
    reference_images=["ref/paul-taff-001.png"],
    attributes={"hair": "chatain", "age": 35, "outfit": "chemise bleue"},
    appearance_count=0,
    last_seen_content="",
)


class TestEntityRoundtrip:
    def test_to_dict_from_dict(self):
        d = SAMPLE_ENTITY.to_dict()
        assert d["entity_id"] == "paul-taff"
        restored = Entity.from_dict(d)
        assert restored.name == "Paul Taff"
        assert restored.attributes["hair"] == "chatain"

    def test_from_nocodb_row(self):
        row = {
            "entity_id": "paul-taff", "entity_type": "character",
            "name": "Paul Taff", "brand_name": "Taff",
            "visual_description": "Homme 35 ans",
            "reference_images": ["ref.png"], "attributes": {"hair": "brun"},
            "appearance_count": 3, "last_seen_content": "Episode 2",
        }
        entity = Entity.from_nocodb_row(row)
        assert entity.appearance_count == 3
        assert entity.last_seen_content == "Episode 2"


@pytest.fixture
def mock_rag():
    rag = MagicMock()
    rag.embed.return_value = [0.1] * 1536
    rag.ensure_collection.return_value = False
    return rag


@pytest.fixture
def graph(mock_rag, mock_nocodb):
    return SceneGraph(mock_rag, mock_nocodb)


class TestSceneGraphRegister:
    def test_register_new_entity(self, graph, mock_nocodb):
        mock_nocodb.find_row.return_value = None
        result = graph.register_entity(SAMPLE_ENTITY)
        assert result.entity_id == "paul-taff"
        mock_nocodb.create_row.assert_called_once()

    def test_register_updates_existing(self, graph, mock_nocodb):
        mock_nocodb.find_row.return_value = {"Id": 1, "entity_id": "paul-taff"}
        result = graph.register_entity(SAMPLE_ENTITY)
        mock_nocodb.update_row.assert_called_once()


class TestSceneGraphGet:
    def test_get_entity(self, graph, mock_nocodb):
        mock_nocodb.find_row.return_value = {
            "Id": 1, "entity_id": "paul-taff", "entity_type": "character",
            "name": "Paul Taff", "brand_name": "Taff",
            "visual_description": "Homme 35 ans",
            "reference_images": [], "attributes": {},
            "appearance_count": 0, "last_seen_content": "",
        }
        entity = graph.get_entity("Paul Taff", "Taff")
        assert entity is not None
        assert entity.entity_type == "character"

    def test_get_returns_none(self, graph, mock_nocodb):
        mock_nocodb.find_row.return_value = None
        assert graph.get_entity("Missing", "Taff") is None


class TestBuildScenePrompt:
    def test_build_with_two_entities(self, graph, mock_nocodb):
        mock_nocodb.find_row.side_effect = [
            {"Id": 1, "entity_id": "paul", "entity_type": "character",
             "name": "Paul Taff", "brand_name": "Taff",
             "visual_description": "Homme 35 ans, barbe courte",
             "reference_images": ["ref.png"], "attributes": {},
             "appearance_count": 2, "last_seen_content": "Ep1"},
            {"Id": 2, "entity_id": "bureau", "entity_type": "location",
             "name": "Bureau TAFF", "brand_name": "Taff",
             "visual_description": "Open space moderne, murs blancs",
             "reference_images": [], "attributes": {},
             "appearance_count": 1, "last_seen_content": "Ep1"},
        ]
        prompt = graph.build_scene_prompt(["Paul Taff", "Bureau TAFF"], "Taff")
        assert "Paul Taff" in prompt
        assert "Bureau TAFF" in prompt
        assert "Homme 35 ans" in prompt
        assert "Open space" in prompt


class TestRecordAppearance:
    def test_increments_count(self, graph, mock_nocodb):
        mock_nocodb.find_row.return_value = {
            "Id": 1, "entity_id": "paul", "entity_type": "character",
            "name": "Paul Taff", "brand_name": "Taff",
            "visual_description": "Homme", "reference_images": [],
            "attributes": {}, "appearance_count": 2,
            "last_seen_content": "Ep1",
        }
        graph.record_appearance("Paul Taff", "Taff", "Ep3", "Image Gen")
        mock_nocodb.update_row.assert_called_once()
        update_data = mock_nocodb.update_row.call_args[0][2]
        assert update_data["appearance_count"] == 3
        assert update_data["last_seen_content"] == "Ep3"


class TestSyncFromNocodb:
    def test_sync_all(self, graph, mock_nocodb, mock_rag):
        mock_nocodb.list_rows.return_value = [
            {"Id": 1, "entity_id": "e1", "entity_type": "character",
             "name": "A", "brand_name": "B", "visual_description": "desc",
             "reference_images": [], "attributes": {},
             "appearance_count": 0, "last_seen_content": ""},
        ]
        count = graph.sync_from_nocodb()
        assert count == 1


class TestFindSimilar:
    def test_find_similar_returns_entities(self, graph, mock_rag):
        from comfyui_cli.rag import SearchResult
        mock_rag.search.return_value = [
            SearchResult(
                score=0.95, title="Paul Taff", text="desc",
                collection="scene-entities",
                metadata={"entity_id": "paul", "entity_type": "character",
                          "name": "Paul Taff", "brand_name": "Taff",
                          "visual_description": "Homme",
                          "reference_images": [], "attributes": {},
                          "appearance_count": 1, "last_seen_content": "Ep1"},
            ),
        ]
        results = graph.find_similar("young man professional")
        assert len(results) == 1
        assert results[0].name == "Paul Taff"
        mock_rag.search.assert_called_once()

    def test_find_similar_filters_by_type(self, graph, mock_rag):
        from comfyui_cli.rag import SearchResult
        mock_rag.search.return_value = [
            SearchResult(
                score=0.9, title="Bureau", text="office",
                collection="scene-entities",
                metadata={"entity_id": "bureau", "entity_type": "location",
                          "name": "Bureau", "brand_name": "Taff",
                          "visual_description": "Office",
                          "reference_images": [], "attributes": {},
                          "appearance_count": 1, "last_seen_content": "Ep1"},
            ),
        ]
        results = graph.find_similar("office", entity_type="character")
        assert len(results) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_scene_graph.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement SceneGraph module**

```python
# comfyui_cli/scene_graph.py
"""Scene Graph — persistent entity registry for visual continuity.

Characters, products, locations persist across contents.
Stored in NocoDB (editable) and synced to Qdrant (semantic search).
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from comfyui_cli.rag import RagEngine, _text_to_point_id

logger = logging.getLogger(__name__)

COLLECTION_SCENE_ENTITIES = "scene-entities"


@dataclass
class Entity:
    """A persistent entity (character, product, location, prop)."""

    entity_id: str
    entity_type: str
    name: str
    brand_name: str
    visual_description: str
    reference_images: List[str]
    attributes: Dict[str, Any]
    appearance_count: int = 0
    last_seen_content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "brand_name": self.brand_name,
            "visual_description": self.visual_description,
            "reference_images": self.reference_images,
            "attributes": self.attributes,
            "appearance_count": self.appearance_count,
            "last_seen_content": self.last_seen_content,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        return cls(
            entity_id=data["entity_id"],
            entity_type=data["entity_type"],
            name=data["name"],
            brand_name=data["brand_name"],
            visual_description=data.get("visual_description", ""),
            reference_images=data.get("reference_images", []),
            attributes=data.get("attributes", {}),
            appearance_count=data.get("appearance_count", 0),
            last_seen_content=data.get("last_seen_content", ""),
        )

    @classmethod
    def from_nocodb_row(cls, row: Dict[str, Any]) -> "Entity":
        return cls.from_dict(row)

    def to_nocodb_row(self) -> Dict[str, Any]:
        return self.to_dict()


class SceneGraph:
    """Entity registry with NocoDB persistence and Qdrant search."""

    TABLE_NAME = "scene_entities"

    def __init__(self, rag_engine: RagEngine, nocodb):
        self.rag = rag_engine
        self.nocodb = nocodb
        self._table_id = None

    def _get_table_id(self) -> str:
        if self._table_id is None:
            self._table_id = self.nocodb.resolve_table_id(self.TABLE_NAME)
        return self._table_id

    def register_entity(self, entity: Entity) -> Entity:
        """Register or update an entity in NocoDB + Qdrant."""
        table_id = self._get_table_id()
        row_data = entity.to_nocodb_row()

        existing = self.nocodb.find_row(
            table_id, f"(entity_id,eq,{entity.entity_id})"
        )
        if existing:
            self.nocodb.update_row(table_id, str(existing["Id"]), row_data)
        else:
            self.nocodb.create_row(table_id, row_data)

        self._sync_to_qdrant(entity)
        return entity

    def get_entity(self, name: str, brand: str) -> Optional[Entity]:
        """Get entity by name + brand from NocoDB."""
        table_id = self._get_table_id()
        row = self.nocodb.find_row(
            table_id, f"(name,eq,{name})~and(brand_name,eq,{brand})"
        )
        if row:
            return Entity.from_nocodb_row(row)
        return None

    def find_similar(
        self, description: str, entity_type: str = "", limit: int = 5
    ) -> List[Entity]:
        """Semantic search for similar entities in Qdrant."""
        self.rag.ensure_collection(COLLECTION_SCENE_ENTITIES)
        results = self.rag.search(
            collection=COLLECTION_SCENE_ENTITIES,
            query=description,
            limit=limit,
        )
        entities = []
        for r in results:
            meta = r.metadata
            if entity_type and meta.get("entity_type") != entity_type:
                continue
            if "entity_id" in meta:
                entities.append(Entity.from_dict(meta))
        return entities

    def build_scene_prompt(
        self, entity_names: List[str], brand: str
    ) -> str:
        """Build a structured scene prompt from multiple entities."""
        characters = []
        locations = []
        props = []

        for name in entity_names:
            entity = self.get_entity(name, brand)
            if not entity:
                logger.warning("Entity '%s' not found for brand '%s'", name, brand)
                continue

            block = f"- {entity.name}: {entity.visual_description}"
            if entity.reference_images:
                refs = ", ".join(entity.reference_images)
                block += f"\n  [ref: {refs}]"

            if entity.entity_type == "character":
                characters.append(block)
            elif entity.entity_type == "location":
                locations.append(block)
            else:
                props.append(block)

        sections = []
        if characters:
            sections.append("Characters present:\n" + "\n".join(characters))
        if locations:
            sections.append("Location:\n" + "\n".join(locations))
        if props:
            sections.append("Props:\n" + "\n".join(props))

        return "\n\n".join(sections)

    def record_appearance(
        self, entity_name: str, brand: str, content_name: str, step: str
    ) -> None:
        """Record that an entity appeared in a content."""
        table_id = self._get_table_id()
        row = self.nocodb.find_row(
            table_id, f"(name,eq,{entity_name})~and(brand_name,eq,{brand})"
        )
        if not row:
            logger.warning("Entity '%s' not found for appearance tracking", entity_name)
            return

        self.nocodb.update_row(table_id, str(row["Id"]), {
            "appearance_count": row.get("appearance_count", 0) + 1,
            "last_seen_content": content_name,
        })

    def sync_from_nocodb(self, brand_name: Optional[str] = None) -> int:
        """Sync entities from NocoDB to Qdrant."""
        table_id = self._get_table_id()
        self.rag.ensure_collection(COLLECTION_SCENE_ENTITIES)

        if brand_name:
            rows = self.nocodb.list_rows(
                table_id, params={"where": f"(brand_name,eq,{brand_name})"}
            )
        else:
            rows = self.nocodb.list_rows(table_id)

        for row in rows:
            self._sync_to_qdrant(Entity.from_nocodb_row(row))
        return len(rows)

    def _sync_to_qdrant(self, entity: Entity) -> None:
        """Upsert entity to Qdrant."""
        self.rag.ensure_collection(COLLECTION_SCENE_ENTITIES)
        self.rag.upsert_document(
            collection=COLLECTION_SCENE_ENTITIES,
            doc_id=entity.entity_id,
            text=entity.visual_description,
            title=entity.name,
            category=entity.entity_type,
            extra_metadata=entity.to_dict(),
        )
```

- [ ] **Step 4: Run all scene_graph tests**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_scene_graph.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /opt/workstation/comfyui-studio-repo
git add comfyui_cli/scene_graph.py tests/test_scene_graph.py
git commit -m "feat(scene-graph): add entity registry for visual continuity

Entity dataclass + SceneGraph with NocoDB CRUD, Qdrant sync,
semantic entity search, scene prompt builder, appearance tracking."
```

---

## Task 4: Series Engine Module

**Files:**
- Create: `comfyui_cli/series_engine.py`
- Create: `tests/test_series_engine.py`

- [ ] **Step 1: Write tests for SeriesDefinition/Episode dataclasses and SeriesEngine**

```python
# tests/test_series_engine.py
"""Tests for Series Engine module."""
import json
import time
import pytest
from unittest.mock import MagicMock, patch
from comfyui_cli.series_engine import (
    SeriesDefinition, Episode, SeriesEngine,
)


SAMPLE_SERIES = SeriesDefinition(
    series_id="ser-001",
    brand_name="Taff",
    title="Behind the Craft",
    concept="5-episode series showing the artisan process",
    n_episodes=3,
    narrative_arc="build-up",
    recurring_entities=["paul-taff", "bureau-taff"],
    formats=["reel_9_16", "post_4_5"],
    episode_briefs=[],
    created_at=time.time(),
    status="draft",
)


class TestSeriesDefinitionRoundtrip:
    def test_to_dict_from_dict(self):
        d = SAMPLE_SERIES.to_dict()
        assert d["series_id"] == "ser-001"
        restored = SeriesDefinition.from_dict(d)
        assert restored.title == "Behind the Craft"
        assert restored.n_episodes == 3


class TestEpisodeRoundtrip:
    def test_to_dict_from_dict(self):
        ep = Episode(
            episode_number=1, series_id="ser-001", title="The Vision",
            brief={"hook": "It all started with..."}, status="planned",
            assets=[], reused_assets=[], kitsu_task_id="", cost_usd=0.0,
        )
        d = ep.to_dict()
        restored = Episode.from_dict(d)
        assert restored.episode_number == 1
        assert restored.brief["hook"] == "It all started with..."


@pytest.fixture
def mock_style_dna():
    mgr = MagicMock()
    mgr.get.return_value = MagicMock(
        brand_name="Taff", description="Premium professional brand",
        to_dict=lambda: {"brand_name": "Taff", "description": "Premium"},
    )
    return mgr


@pytest.fixture
def mock_scene_graph():
    sg = MagicMock()
    sg.get_entity.return_value = MagicMock(
        name="Paul Taff", visual_description="Homme 35 ans",
        to_dict=lambda: {"name": "Paul Taff"},
    )
    return sg


@pytest.fixture
def mock_asset_cache():
    cache = MagicMock()
    cache.find_similar.return_value = []
    return cache


@pytest.fixture
def mock_rag():
    rag = MagicMock()
    return rag


@pytest.fixture
def engine(mock_style_dna, mock_scene_graph, mock_asset_cache, mock_nocodb, mock_rag):
    return SeriesEngine(
        mock_style_dna, mock_scene_graph, mock_asset_cache, mock_nocodb, mock_rag,
    )


LLM_RESPONSE = json.dumps([
    {"title": "The Vision", "hook": "It starts...", "entities": ["paul-taff"],
     "scene": "Bureau", "emotion": "confident", "callback": None,
     "cliffhanger": "But what about..."},
    {"title": "The Process", "hook": "Day by day...", "entities": ["paul-taff"],
     "scene": "Atelier", "emotion": "focused", "callback": "Ep1 vision",
     "cliffhanger": "The deadline approaches"},
    {"title": "The Result", "hook": "Finally...", "entities": ["paul-taff", "bureau-taff"],
     "scene": "Bureau", "emotion": "triumphant", "callback": "Ep2 deadline",
     "cliffhanger": None},
])


class TestCreateSeries:
    def test_creates_n_episode_briefs(self, engine, mock_nocodb, mock_rag):
        mock_rag._get_openai.return_value.chat.completions.create.return_value = \
            MagicMock(choices=[MagicMock(message=MagicMock(content=LLM_RESPONSE))])

        series = engine.create_series(
            concept="Artisan process", n_episodes=3,
            brand_name="Taff", formats=["reel_9_16"],
        )
        assert series.n_episodes == 3
        assert len(series.episode_briefs) == 3
        assert series.status == "draft"
        mock_nocodb.create_row.assert_called()

    def test_stores_series_in_nocodb(self, engine, mock_nocodb, mock_rag):
        mock_rag._get_openai.return_value.chat.completions.create.return_value = \
            MagicMock(choices=[MagicMock(message=MagicMock(content=LLM_RESPONSE))])

        engine.create_series(
            concept="Test", n_episodes=3,
            brand_name="Taff", formats=["reel_9_16"],
        )
        # Should create 1 series row + 3 episode rows = 4 creates
        assert mock_nocodb.create_row.call_count == 4


class TestGetEpisodeBrief:
    def test_includes_previous_context(self, engine, mock_nocodb):
        mock_nocodb.find_row.side_effect = [
            # Series row
            {"Id": 1, "series_id": "ser-001", "brand_name": "Taff",
             "title": "Test", "concept": "Test concept", "n_episodes": 3,
             "narrative_arc": "build-up", "recurring_entities": [],
             "formats": ["reel_9_16"], "status": "draft",
             "created_at": "2026-01-01"},
        ]
        mock_nocodb.list_rows.return_value = [
            {"episode_id": "ep-1", "series_id": "ser-001", "episode_number": 1,
             "title": "Ep 1", "brief": {"hook": "First"},
             "status": "done", "assets": [], "reused_assets": [],
             "kitsu_task_id": "", "cost_usd": 1.0},
            {"episode_id": "ep-2", "series_id": "ser-001", "episode_number": 2,
             "title": "Ep 2", "brief": {"hook": "Second"},
             "status": "planned", "assets": [], "reused_assets": [],
             "kitsu_task_id": "", "cost_usd": 0.0},
        ]

        brief = engine.get_episode_brief("ser-001", 2)
        assert "previous_episodes" in brief
        assert brief["episode_number"] == 2


class TestFindReusableAssets:
    def test_returns_empty_for_first_episode(self, engine, mock_nocodb, mock_asset_cache):
        mock_nocodb.find_row.return_value = {
            "Id": 1, "series_id": "ser-001", "brand_name": "Taff",
            "title": "T", "concept": "C", "n_episodes": 3,
            "narrative_arc": "build-up", "recurring_entities": ["paul"],
            "formats": [], "status": "draft", "created_at": "2026-01-01",
        }
        mock_nocodb.list_rows.return_value = []

        assets = engine.find_reusable_assets("ser-001", 1)
        assert assets == []


class TestSeriesStats:
    def test_stats_calculation(self, engine, mock_nocodb):
        mock_nocodb.find_row.return_value = {
            "Id": 1, "series_id": "ser-001", "brand_name": "Taff",
            "title": "T", "concept": "C", "n_episodes": 3,
            "narrative_arc": "build-up", "recurring_entities": [],
            "formats": ["reel_9_16"], "status": "in_production",
            "created_at": "2026-01-01",
        }
        mock_nocodb.list_rows.return_value = [
            {"episode_id": "e1", "series_id": "ser-001", "episode_number": 1,
             "title": "E1", "brief": {}, "status": "done",
             "assets": ["a1", "a2"], "reused_assets": ["a1"],
             "kitsu_task_id": "", "cost_usd": 2.5},
            {"episode_id": "e2", "series_id": "ser-001", "episode_number": 2,
             "title": "E2", "brief": {}, "status": "in_production",
             "assets": ["a3"], "reused_assets": [],
             "kitsu_task_id": "", "cost_usd": 1.0},
        ]

        stats = engine.series_stats("ser-001")
        assert stats["total_episodes"] == 3
        assert stats["completed_episodes"] == 1
        assert stats["total_cost_usd"] == 3.5
        assert stats["reuse_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_series_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement SeriesEngine module**

```python
# comfyui_cli/series_engine.py
"""Series Engine — N episodes x M formats with continuity and asset reuse.

Orchestrates Style DNA + Scene Graph + Asset Cache to produce
coherent content series with narrative continuity.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TABLE_SERIES = "series"
TABLE_EPISODES = "episodes"

SERIES_PROMPT_TEMPLATE = """Tu es un directeur artistique de serie video.

CONCEPT: {concept}
MARQUE: {brand_name}
STYLE: {style_description}
ENTITES EXISTANTES: {entities_list}
ARC NARRATIF: {narrative_arc}
NOMBRE D'EPISODES: {n_episodes}

Genere {n_episodes} briefs d'episodes avec:
1. Titre accrocheur
2. Hook (premiere phrase du script)
3. Entites presentes (existantes ou nouvelles a creer)
4. Scene principale
5. Emotion/energie de l'episode
6. Callback vers episodes precedents (sauf ep. 1)
7. Cliffhanger ou transition vers episode suivant (sauf dernier)

Reponds en JSON uniquement: [{{"title": "...", "hook": "...", "entities": [...], "scene": "...", "emotion": "...", "callback": "...", "cliffhanger": "..."}}]"""


@dataclass
class SeriesDefinition:
    """A content series definition."""

    series_id: str
    brand_name: str
    title: str
    concept: str
    n_episodes: int
    narrative_arc: str
    recurring_entities: List[str]
    formats: List[str]
    episode_briefs: List[Dict]
    created_at: float
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "series_id": self.series_id,
            "brand_name": self.brand_name,
            "title": self.title,
            "concept": self.concept,
            "n_episodes": self.n_episodes,
            "narrative_arc": self.narrative_arc,
            "recurring_entities": self.recurring_entities,
            "formats": self.formats,
            "episode_briefs": self.episode_briefs,
            "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SeriesDefinition":
        return cls(
            series_id=data["series_id"],
            brand_name=data["brand_name"],
            title=data["title"],
            concept=data["concept"],
            n_episodes=data["n_episodes"],
            narrative_arc=data["narrative_arc"],
            recurring_entities=data.get("recurring_entities", []),
            formats=data.get("formats", []),
            episode_briefs=data.get("episode_briefs", []),
            created_at=data.get("created_at", 0),
            status=data.get("status", "draft"),
        )

    @classmethod
    def from_nocodb_row(cls, row: Dict[str, Any]) -> "SeriesDefinition":
        # NocoDB may include extra fields (Id, updated_at as string, etc.)
        known_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in row.items() if k in known_keys}
        return cls.from_dict(filtered)


@dataclass
class Episode:
    """A single episode in a series."""

    episode_id: str
    episode_number: int
    series_id: str
    title: str
    brief: Dict
    status: str
    assets: List[str]
    reused_assets: List[str]
    kitsu_task_id: str
    cost_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "episode_number": self.episode_number,
            "series_id": self.series_id,
            "title": self.title,
            "brief": self.brief,
            "status": self.status,
            "assets": self.assets,
            "reused_assets": self.reused_assets,
            "kitsu_task_id": self.kitsu_task_id,
            "cost_usd": self.cost_usd,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Episode":
        return cls(
            episode_id=data.get("episode_id", ""),
            episode_number=data["episode_number"],
            series_id=data["series_id"],
            title=data["title"],
            brief=data.get("brief", {}),
            status=data.get("status", "planned"),
            assets=data.get("assets", []),
            reused_assets=data.get("reused_assets", []),
            kitsu_task_id=data.get("kitsu_task_id", ""),
            cost_usd=data.get("cost_usd", 0.0),
        )

    @classmethod
    def from_nocodb_row(cls, row: Dict[str, Any]) -> "Episode":
        # NocoDB may include extra fields (Id, created_at, etc.) — ignore them
        known_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in row.items() if k in known_keys}
        return cls.from_dict(filtered)


class SeriesEngine:
    """Orchestrate series production across episodes and formats."""

    def __init__(self, style_dna_mgr, scene_graph, asset_cache, nocodb, rag_engine):
        self.style_dna = style_dna_mgr
        self.scene_graph = scene_graph
        self.asset_cache = asset_cache
        self.nocodb = nocodb
        self.rag = rag_engine
        self._series_table_id = None
        self._episodes_table_id = None

    def _get_series_table_id(self) -> str:
        if self._series_table_id is None:
            self._series_table_id = self.nocodb.resolve_table_id(TABLE_SERIES)
        return self._series_table_id

    def _get_episodes_table_id(self) -> str:
        if self._episodes_table_id is None:
            self._episodes_table_id = self.nocodb.resolve_table_id(TABLE_EPISODES)
        return self._episodes_table_id

    def create_series(
        self,
        concept: str,
        n_episodes: int,
        brand_name: str,
        formats: List[str],
        narrative_arc: str = "build-up",
    ) -> SeriesDefinition:
        """Decompose a concept into N episode briefs via LLM."""
        # Gather context
        style = self.style_dna.get(brand_name)
        style_desc = style.description if style else ""

        # Build LLM prompt
        prompt = SERIES_PROMPT_TEMPLATE.format(
            concept=concept,
            brand_name=brand_name,
            style_description=style_desc,
            entities_list="(none yet)",
            narrative_arc=narrative_arc,
            n_episodes=n_episodes,
        )

        # Call LLM via RagEngine's OpenAI client
        client = self.rag._get_openai()
        resp = client.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        raw = resp.choices[0].message.content
        briefs = json.loads(raw)

        # Build series
        series_id = f"ser-{uuid.uuid4().hex[:8]}"
        series = SeriesDefinition(
            series_id=series_id,
            brand_name=brand_name,
            title=briefs[0].get("title", concept[:50]) if briefs else concept[:50],
            concept=concept,
            n_episodes=n_episodes,
            narrative_arc=narrative_arc,
            recurring_entities=[],
            formats=formats,
            episode_briefs=briefs,
            created_at=time.time(),
            status="draft",
        )

        # Store in NocoDB
        series_tid = self._get_series_table_id()
        episodes_tid = self._get_episodes_table_id()

        self.nocodb.create_row(series_tid, {
            "series_id": series.series_id,
            "brand_name": brand_name,
            "title": series.title,
            "concept": concept,
            "n_episodes": n_episodes,
            "narrative_arc": narrative_arc,
            "recurring_entities": [],
            "formats": formats,
            "status": "draft",
        })

        for i, brief in enumerate(briefs):
            self.nocodb.create_row(episodes_tid, {
                "episode_id": f"ep-{uuid.uuid4().hex[:8]}",
                "series_id": series_id,
                "episode_number": i + 1,
                "title": brief.get("title", f"Episode {i+1}"),
                "brief": brief,
                "status": "planned",
                "assets": [],
                "reused_assets": [],
                "kitsu_task_id": "",
                "cost_usd": 0.0,
            })

        return series

    def get_episode_brief(self, series_id: str, episode_num: int) -> Dict:
        """Get enriched episode brief with context from previous episodes."""
        series_tid = self._get_series_table_id()
        episodes_tid = self._get_episodes_table_id()

        series_row = self.nocodb.find_row(
            series_tid, f"(series_id,eq,{series_id})"
        )
        if not series_row:
            raise ValueError(f"Series '{series_id}' not found")

        episodes = self.nocodb.list_rows(
            episodes_tid, params={"where": f"(series_id,eq,{series_id})"}
        )
        episodes.sort(key=lambda e: e.get("episode_number", 0))

        target = None
        previous = []
        for ep in episodes:
            if ep.get("episode_number") == episode_num:
                target = ep
            elif ep.get("episode_number", 0) < episode_num:
                previous.append({
                    "episode_number": ep["episode_number"],
                    "title": ep.get("title", ""),
                    "status": ep.get("status", ""),
                    "brief_summary": ep.get("brief", {}).get("hook", ""),
                })

        if not target:
            raise ValueError(f"Episode {episode_num} not found in series '{series_id}'")

        return {
            "episode_number": episode_num,
            "title": target.get("title", ""),
            "brief": target.get("brief", {}),
            "status": target.get("status", ""),
            "series_title": series_row.get("title", ""),
            "brand_name": series_row.get("brand_name", ""),
            "previous_episodes": previous,
        }

    def find_reusable_assets(self, series_id: str, episode_num: int) -> list:
        """Find assets from previous episodes that can be reused."""
        episodes_tid = self._get_episodes_table_id()

        episodes = self.nocodb.list_rows(
            episodes_tid, params={"where": f"(series_id,eq,{series_id})"}
        )

        previous_assets = []
        for ep in episodes:
            if ep.get("episode_number", 0) < episode_num:
                for asset_id in ep.get("assets", []):
                    previous_assets.append(asset_id)

        if not previous_assets:
            return []

        reusable = []
        for asset_id in previous_assets:
            found = self.asset_cache.find_similar(asset_id, limit=1)
            reusable.extend(found)
        return reusable

    def series_stats(self, series_id: str) -> Dict:
        """Get series statistics."""
        series_tid = self._get_series_table_id()
        episodes_tid = self._get_episodes_table_id()

        series_row = self.nocodb.find_row(
            series_tid, f"(series_id,eq,{series_id})"
        )
        if not series_row:
            raise ValueError(f"Series '{series_id}' not found")

        episodes = self.nocodb.list_rows(
            episodes_tid, params={"where": f"(series_id,eq,{series_id})"}
        )

        completed = sum(1 for e in episodes if e.get("status") == "done")
        total_cost = sum(e.get("cost_usd", 0) for e in episodes)
        total_assets = sum(len(e.get("assets", [])) for e in episodes)
        reuse_count = sum(len(e.get("reused_assets", [])) for e in episodes)

        return {
            "series_id": series_id,
            "title": series_row.get("title", ""),
            "total_episodes": series_row.get("n_episodes", 0),
            "completed_episodes": completed,
            "in_production": sum(1 for e in episodes if e.get("status") == "in_production"),
            "total_cost_usd": total_cost,
            "total_assets": total_assets,
            "reuse_count": reuse_count,
            "reuse_rate": round(reuse_count / max(total_assets, 1), 2),
            "status": series_row.get("status", ""),
        }
```

- [ ] **Step 4: Run all series_engine tests**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/test_series_engine.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /opt/workstation/comfyui-studio-repo
git add comfyui_cli/series_engine.py tests/test_series_engine.py
git commit -m "feat(series-engine): add N episodes x M formats orchestration

SeriesDefinition/Episode dataclasses + SeriesEngine with LLM-powered
episode decomposition, cross-episode context, asset reuse detection,
and cost tracking."
```

---

## Task 5: MCP Server Integration + Version Bump

**Files:**
- Modify: `mcp/mcp_server.py:9-34,47-54,684-692,1114-1134`
- Modify: `comfyui_cli/config.py` (already done in Task 1)
- Modify: `setup.py:5`
- Modify: `comfyui_cli/__init__.py:2`

- [ ] **Step 1: Add imports to mcp_server.py**

After line 34 (after the `from comfyui_cli.rag import ...` block), add:

```python
from comfyui_cli.nocodb import NocoDBClient
from comfyui_cli.scene_graph import SceneGraph
from comfyui_cli.series_engine import SeriesEngine
from comfyui_cli.style_dna import StyleDNAManager
```

- [ ] **Step 2: Add lazy-init globals and functions**

After line 54 (`_config = None`), add:

```python
_nocodb: NocoDBClient = None
_style_dna: StyleDNAManager = None
_scene_graph: SceneGraph = None
_series: SeriesEngine = None
```

After the existing `_get_asset_cache()` function, add:

```python
def _get_nocodb():
    global _nocodb
    if _nocodb is None:
        cfg = _get_config()
        if not cfg.get("nocodb_token"):
            raise ValueError(
                "NocoDB token not configured. Set NOCODB_TOKEN env var."
            )
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
            _get_asset_cache(), _get_nocodb(), _get_rag(),
        )
    return _series
```

- [ ] **Step 3: Add tool definitions**

Before the `@server.list_tools()` decorator (line 687), add the 13 new tool definitions:

```python
STYLE_DNA_TOOLS = [
    Tool(
        name="style_dna_create",
        description="Create or update a brand's visual identity (Style DNA). Writes to NocoDB and syncs to Qdrant.",
        inputSchema={
            "type": "object",
            "properties": {
                "brand_name": {"type": "string", "description": "Unique brand identifier"},
                "palette": {"type": "object", "description": "Color palette {primary, secondary, accent, background}"},
                "typography": {"type": "object", "description": "Typography {heading, body}"},
                "tone": {"type": "string", "description": "Brand tone: professional, playful, luxe, urban"},
                "visual_style": {"type": "string", "description": "Visual style: cinematic, flat, 3d_render, photorealistic"},
                "voice_profile": {"type": "object", "description": "Voice settings {voice_id, speed, pitch}"},
                "mood_keywords": {"type": "array", "items": {"type": "string"}, "description": "Mood keywords"},
                "reference_images": {"type": "array", "items": {"type": "string"}, "description": "Reference image paths"},
                "description": {"type": "string", "description": "Free-text brand description for semantic search"},
            },
            "required": ["brand_name"],
        },
    ),
    Tool(
        name="style_dna_get",
        description="Get a brand's Style DNA by name.",
        inputSchema={
            "type": "object",
            "properties": {"brand_name": {"type": "string"}},
            "required": ["brand_name"],
        },
    ),
    Tool(
        name="style_dna_enrich_prompt",
        description="Enrich a generation prompt with brand style. Injects palette, tone, visual style based on asset type.",
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Original generation prompt"},
                "brand_name": {"type": "string", "description": "Brand to apply"},
                "asset_type": {"type": "string", "description": "Asset type: image, video, audio_voice, audio_music, text"},
            },
            "required": ["prompt", "brand_name", "asset_type"],
        },
    ),
    Tool(
        name="style_dna_sync",
        description="Sync brand styles from NocoDB to Qdrant. Omit brand_name to sync all.",
        inputSchema={
            "type": "object",
            "properties": {"brand_name": {"type": "string"}},
            "required": [],
        },
    ),
]

SCENE_GRAPH_TOOLS = [
    Tool(
        name="scene_entity_register",
        description="Register or update a persistent entity (character, product, location, prop).",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Unique entity ID (slug)"},
                "entity_type": {"type": "string", "description": "character, product, location, prop"},
                "name": {"type": "string", "description": "Display name"},
                "brand_name": {"type": "string", "description": "Brand this entity belongs to"},
                "visual_description": {"type": "string", "description": "Detailed visual description for prompts"},
                "reference_images": {"type": "array", "items": {"type": "string"}},
                "attributes": {"type": "object", "description": "Flexible attributes (hair, age, material...)"},
            },
            "required": ["entity_id", "entity_type", "name", "brand_name", "visual_description"],
        },
    ),
    Tool(
        name="scene_entity_get",
        description="Get an entity by name and brand.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "brand": {"type": "string"},
            },
            "required": ["name", "brand"],
        },
    ),
    Tool(
        name="scene_entity_search",
        description="Semantic search for similar entities.",
        inputSchema={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Description to search for"},
                "entity_type": {"type": "string", "description": "Filter by type (optional)"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["description"],
        },
    ),
    Tool(
        name="scene_build_prompt",
        description="Build a structured scene prompt from multiple entities.",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_names": {"type": "array", "items": {"type": "string"}, "description": "Entity names to include"},
                "brand": {"type": "string"},
            },
            "required": ["entity_names", "brand"],
        },
    ),
    Tool(
        name="scene_entity_sync",
        description="Sync entities from NocoDB to Qdrant. Omit brand_name to sync all.",
        inputSchema={
            "type": "object",
            "properties": {"brand_name": {"type": "string"}},
            "required": [],
        },
    ),
]

SERIES_ENGINE_TOOLS = [
    Tool(
        name="series_create",
        description="Create a content series: decompose a concept into N episode briefs via LLM.",
        inputSchema={
            "type": "object",
            "properties": {
                "concept": {"type": "string", "description": "Series concept/pitch"},
                "n_episodes": {"type": "integer", "description": "Number of episodes"},
                "brand_name": {"type": "string", "description": "Brand for style consistency"},
                "formats": {"type": "array", "items": {"type": "string"}, "description": "Output formats (reel_9_16, story_9_16, etc.)"},
                "narrative_arc": {"type": "string", "default": "build-up", "description": "Arc type: build-up, episodic, cliffhanger, documentary"},
            },
            "required": ["concept", "n_episodes", "brand_name", "formats"],
        },
    ),
    Tool(
        name="series_get_brief",
        description="Get enriched episode brief with context from previous episodes.",
        inputSchema={
            "type": "object",
            "properties": {
                "series_id": {"type": "string"},
                "episode_num": {"type": "integer"},
            },
            "required": ["series_id", "episode_num"],
        },
    ),
    Tool(
        name="series_reuse_assets",
        description="Find reusable assets from previous episodes in the same series.",
        inputSchema={
            "type": "object",
            "properties": {
                "series_id": {"type": "string"},
                "episode_num": {"type": "integer"},
            },
            "required": ["series_id", "episode_num"],
        },
    ),
    Tool(
        name="series_stats",
        description="Get series statistics: cost, progress, reuse rate.",
        inputSchema={
            "type": "object",
            "properties": {"series_id": {"type": "string"}},
            "required": ["series_id"],
        },
    ),
]

STYLE_DNA_TOOL_NAMES = {t.name for t in STYLE_DNA_TOOLS}
SCENE_GRAPH_TOOL_NAMES = {t.name for t in SCENE_GRAPH_TOOLS}
SERIES_ENGINE_TOOL_NAMES = {t.name for t in SERIES_ENGINE_TOOLS}
```

- [ ] **Step 4: Update list_tools to include new tools**

Replace the `list_tools` function body (line 689-692):

```python
@server.list_tools()
async def list_tools():
    return (
        COMFYUI_TOOLS + PIPELINE_TOOLS + ORCHESTRATOR_TOOLS
        + RAG_TOOLS + ASSET_CACHE_TOOLS
        + STYLE_DNA_TOOLS + SCENE_GRAPH_TOOLS + SERIES_ENGINE_TOOLS
    )
```

- [ ] **Step 5: Add handler functions**

Before `call_tool` (line 1114), add:

```python
async def _handle_style_dna_tool(name: str, arguments: dict) -> str:
    """Handle Style DNA MCP tools."""
    mgr = _get_style_dna()

    if name == "style_dna_create":
        from comfyui_cli.style_dna import StyleDNA
        style = StyleDNA(
            brand_name=arguments["brand_name"],
            palette=arguments.get("palette", {}),
            typography=arguments.get("typography", {}),
            tone=arguments.get("tone", ""),
            visual_style=arguments.get("visual_style", ""),
            voice_profile=arguments.get("voice_profile", {}),
            mood_keywords=arguments.get("mood_keywords", []),
            reference_images=arguments.get("reference_images", []),
            description=arguments.get("description", ""),
        )
        result = mgr.create_or_update(style)
        return json.dumps(result.to_dict())

    elif name == "style_dna_get":
        result = mgr.get(arguments["brand_name"])
        return json.dumps(result.to_dict() if result else None)

    elif name == "style_dna_enrich_prompt":
        enriched = mgr.enrich_prompt(
            arguments["prompt"], arguments["brand_name"], arguments["asset_type"],
        )
        return json.dumps({"enriched_prompt": enriched})

    elif name == "style_dna_sync":
        count = mgr.sync_from_nocodb(arguments.get("brand_name"))
        return json.dumps({"synced": count})

    return json.dumps({"error": f"Unknown style_dna tool: {name}"})


async def _handle_scene_graph_tool(name: str, arguments: dict) -> str:
    """Handle Scene Graph MCP tools."""
    sg = _get_scene_graph()

    if name == "scene_entity_register":
        from comfyui_cli.scene_graph import Entity
        entity = Entity(
            entity_id=arguments["entity_id"],
            entity_type=arguments["entity_type"],
            name=arguments["name"],
            brand_name=arguments["brand_name"],
            visual_description=arguments["visual_description"],
            reference_images=arguments.get("reference_images", []),
            attributes=arguments.get("attributes", {}),
        )
        result = sg.register_entity(entity)
        return json.dumps(result.to_dict())

    elif name == "scene_entity_get":
        result = sg.get_entity(arguments["name"], arguments["brand"])
        return json.dumps(result.to_dict() if result else None)

    elif name == "scene_entity_search":
        results = sg.find_similar(
            arguments["description"],
            entity_type=arguments.get("entity_type", ""),
            limit=arguments.get("limit", 5),
        )
        return json.dumps([e.to_dict() for e in results])

    elif name == "scene_build_prompt":
        prompt = sg.build_scene_prompt(arguments["entity_names"], arguments["brand"])
        return json.dumps({"scene_prompt": prompt})

    elif name == "scene_entity_sync":
        count = sg.sync_from_nocodb(arguments.get("brand_name"))
        return json.dumps({"synced": count})

    return json.dumps({"error": f"Unknown scene_graph tool: {name}"})


async def _handle_series_tool(name: str, arguments: dict) -> str:
    """Handle Series Engine MCP tools."""
    eng = _get_series()

    if name == "series_create":
        result = eng.create_series(
            concept=arguments["concept"],
            n_episodes=arguments["n_episodes"],
            brand_name=arguments["brand_name"],
            formats=arguments["formats"],
            narrative_arc=arguments.get("narrative_arc", "build-up"),
        )
        return json.dumps(result.to_dict())

    elif name == "series_get_brief":
        result = eng.get_episode_brief(arguments["series_id"], arguments["episode_num"])
        return json.dumps(result)

    elif name == "series_reuse_assets":
        assets = eng.find_reusable_assets(arguments["series_id"], arguments["episode_num"])
        return json.dumps([a.to_dict() if hasattr(a, 'to_dict') else str(a) for a in assets])

    elif name == "series_stats":
        result = eng.series_stats(arguments["series_id"])
        return json.dumps(result)

    return json.dumps({"error": f"Unknown series tool: {name}"})
```

- [ ] **Step 6: Update call_tool dispatcher**

In `call_tool` (line 1114-1134), add 3 new branches after the `try:` and before `if name in ORCHESTRATOR_TOOL_NAMES`:

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        if name in STYLE_DNA_TOOL_NAMES:
            output = await _handle_style_dna_tool(name, arguments)
        elif name in SCENE_GRAPH_TOOL_NAMES:
            output = await _handle_scene_graph_tool(name, arguments)
        elif name in SERIES_ENGINE_TOOL_NAMES:
            output = await _handle_series_tool(name, arguments)
        elif name in ORCHESTRATOR_TOOL_NAMES:
            output = await _handle_orchestrator_tool(name, arguments)
        elif name in RAG_TOOL_NAMES:
            output = await _handle_rag_tool(name, arguments)
        elif name in ASSET_CACHE_TOOL_NAMES:
            output = await _handle_asset_cache_tool(name, arguments)
        elif name.startswith("pipeline_"):
            output = await _handle_pipeline_tool(name, arguments)
        else:
            output = await _handle_comfyui_tool(name, arguments)
    except subprocess.TimeoutExpired:
        output = json.dumps({"error": f"Tool '{name}' timed out after 300s"})
    except ValueError as e:
        output = json.dumps({"error": str(e)})
    except Exception as e:
        output = json.dumps({"error": f"{type(e).__name__}: {str(e)}"})

    return [TextContent(type="text", text=output)]
```

- [ ] **Step 7: Version bump**

In `setup.py` line 5: change `version="0.4.0"` to `version="0.5.0"`

In `comfyui_cli/__init__.py` line 2: change `__version__ = "0.4.0"` to `__version__ = "0.5.0"`

- [ ] **Step 8: Run full test suite**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS (existing 80+ tests + 37 new tests)

- [ ] **Step 9: Commit**

```bash
cd /opt/workstation/comfyui-studio-repo
git add mcp/mcp_server.py setup.py comfyui_cli/__init__.py
git commit -m "feat(mcp): add 13 MCP tools for Style DNA, Scene Graph, Series Engine

style_dna_create/get/enrich_prompt/sync (4 tools)
scene_entity_register/get/search + scene_build_prompt + scene_entity_sync (5 tools)
series_create/get_brief/reuse_assets/stats (4 tools)
Version bump 0.4.0 -> 0.5.0"
```

---

## Task 6: Full Integration Test

**Files:**
- No new files — verification only

- [ ] **Step 1: Run complete test suite**

Run: `cd /opt/workstation/comfyui-studio-repo && python -m pytest tests/ -v --tb=long 2>&1 | tail -30`
Expected: All tests PASS, 0 failures

- [ ] **Step 2: Verify import chain works**

Run: `cd /opt/workstation/comfyui-studio-repo && python -c "from comfyui_cli.style_dna import StyleDNA, StyleDNAManager; from comfyui_cli.scene_graph import Entity, SceneGraph; from comfyui_cli.series_engine import SeriesDefinition, Episode, SeriesEngine; from comfyui_cli.nocodb import NocoDBClient; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Verify MCP server starts without errors**

Run: `cd /opt/workstation/comfyui-studio-repo && timeout 5 python -c "from mcp.server import Server; from mcp.types import Tool; import mcp.mcp_server; print(f'Tools: {len(mcp.mcp_server.COMFYUI_TOOLS) + len(mcp.mcp_server.PIPELINE_TOOLS) + len(mcp.mcp_server.ORCHESTRATOR_TOOLS) + len(mcp.mcp_server.RAG_TOOLS) + len(mcp.mcp_server.ASSET_CACHE_TOOLS) + len(mcp.mcp_server.STYLE_DNA_TOOLS) + len(mcp.mcp_server.SCENE_GRAPH_TOOLS) + len(mcp.mcp_server.SERIES_ENGINE_TOOLS)}')" 2>&1 || echo "Import check done"`
Expected: `Tools: 49` (36 existing + 13 new)

- [ ] **Step 4: Verify version**

Run: `cd /opt/workstation/comfyui-studio-repo && python -c "from comfyui_cli import __version__; print(f'v{__version__}')"`
Expected: `v0.5.0`
