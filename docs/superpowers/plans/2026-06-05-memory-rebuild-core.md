# Memory System Rebuild — Core (Plan A) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a coherent `memory_v2` Qdrant collection (single 768d model, payload taxonomy wing/room/doc_kind, payload indexes) ingested via an on-demand GPU pod, queryable scoped+capped from Waza — and make the Waza worker OOM-safe first.

**Architecture:** Deploy the already-validated fix B (memory caps + net-resilience) to make Waza safe, then wipe the fragmented memory collections (snapshot first), create `memory_v2` with payload indexes, assign `wing`/`room` per source in `sources.yml`, embed the corpus on a transient RunPod GPU pod that joins Headscale via an ephemeral key and upserts directly into `qd.ewutelo.cloud` over VPN, then upgrade `search_memory.py` to scope by wing/doc_kind by default. Repos stay at current paths (reorg = Plan B; payloads are path-independent).

**Tech Stack:** Ansible, systemd-user, Qdrant (qdrant-client), `google/embeddinggemma-300m` (fastembed/llama-index), RunPod on-demand GPU pod, Headscale ephemeral pre-auth key, Python 3.

**Spec:** `docs/superpowers/specs/2026-06-05-memory-system-rebuild-design.md` (D1–D14)

**Pre-done this session (safety):** uncapped worker run killed (PID 58161, ~3.16G RSS) + `llamaindex-memory-worker.timer` `disable --now`. This is volatile — Task 1 makes it durable.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `playbooks/hosts/workstation.yml` | Deploy entrypoint (fix B tags) | run |
| `roles/workstation-common/` (fix B) | net-resilience + OOM-protect drop-ins | deploy (no edit) |
| `roles/llamaindex-memory-worker/defaults/main.yml` | sources + caps + embedding vars; add `wing`/`room` per source | modify |
| `roles/llamaindex-memory-worker/templates/index.py.j2` | payload schema: add `wing`,`room`,`valid_from`,`valid_to` | modify |
| `roles/llamaindex-memory-worker/templates/search_memory.py.j2` | v2 scoped+capped retrieval, `--wing`/`--room` filters | modify |
| `scripts/memory/qdrant_rebuild.py` | snapshot → wipe(memory-only) → create memory_v2 → 6 indexes | create |
| `scripts/memory/gpu_ingest/` | RunPod on-demand batch: embed embeddinggemma + direct upsert | create |
| `scripts/memory/parity_check.py` | GPU↔CPU cosine ≈ 1.0 gate | create |

---

## Task 1: Deploy fix B — make Waza OOM-safe (durable)

**Files:**
- Run: `playbooks/hosts/workstation.yml` (tags `net_resilience`, `llamaindex-memory-worker`)
- No source edits (role already validated, commit `45015bb`)

- [ ] **Step 1: Lint**

Run: `source .venv/bin/activate && ansible-lint roles/workstation-common roles/llamaindex-memory-worker`
Expected: 0 failure.

- [ ] **Step 2: Dry-run (check + diff)**

Run: `source .venv/bin/activate && ansible-playbook playbooks/hosts/workstation.yml --tags "net_resilience,llamaindex-memory-worker" --check --diff`
Expected: failed=0; diff shows MemoryMax/MemoryHigh/OOMScoreAdjust on the worker unit, OOM-protect drop-ins on systemd-networkd + tailscaled, net-watchdog units created.

- [ ] **Step 3: Deploy**

Run: `source .venv/bin/activate && ansible-playbook playbooks/hosts/workstation.yml --tags "net_resilience,llamaindex-memory-worker" --diff`
Expected: changed>0, failed=0.

- [ ] **Step 4: Verify caps live (evidence before done)**

Run:
```bash
systemctl --user daemon-reload
systemctl --user show llamaindex-memory-worker.service -p MemoryMax -p MemoryHigh -p OOMScoreAdjust
systemctl show systemd-networkd tailscaled -p OOMScoreAdjust
systemctl status net-watchdog.timer --no-pager | head -5
```
Expected: worker `MemoryMax=4G`/`MemoryHigh=3G`/`OOMScoreAdjust=1000`; networkd+tailscaled `OOMScoreAdjust=-900`; `net-watchdog.timer` active.

- [ ] **Step 5: Keep the worker timer DISABLED until M3 is done**

The rebuild uses the GPU pod, not the Waza worker. Confirm: `systemctl --user is-enabled llamaindex-memory-worker.timer` → `disabled`. (Re-enabled at end of M3 only if incremental Waza runs are wanted — capped now.)

- [ ] **Step 6: Commit (state note only — no code change)**

No code change in this task; record the deploy in the session note/memory. Skip git commit.

---

## Task 2: M2 — Qdrant snapshot → wipe (memory-only) → memory_v2 → 6 indexes

**Files:**
- Create: `scripts/memory/qdrant_rebuild.py`
- Test: `scripts/memory/test_qdrant_rebuild.py`

Qdrant: `qd.ewutelo.cloud:443` (VPN + API key from `vault_qdrant_api_key`). Reach over Tailscale from Waza.

- [ ] **Step 1: Inventory + classify collections (read-only)**

Write `qdrant_rebuild.py --inventory` that lists all collections with point counts and dimension, classified MEMORY (wipe) vs APP (spare) vs CACHE.
- MEMORY (wipe): `memory_v1`, `mop_kb`, `vpai_rex`, `operational-rex`, `rex_lessons`, `dev-knowledge`, `content_index`, all `*-docs` fragmentées.
- CACHE (wipe, regenerates): `semantic_cache`.
- APP (SPARE — never touch): `jarvis-*`, `flash-*`, `zimboo`, `macgyver`, `app-factory`.

Run: `python scripts/memory/qdrant_rebuild.py --inventory`
Expected: prints the 3 buckets; the SPARE list matches live app collections exactly.

- [ ] **Step 2: Disk pre-check on Sese (snapshot room)**

Sese had a 100%→66% disk incident (`project_sese_disk_containerd_leases`). Before snapshot, confirm free space.
Run: `ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 'df -h / && du -sh /var/lib/docker/volumes/*qdrant* 2>/dev/null'`
Expected: free space > 2× total size of memory collections to snapshot.

- [ ] **Step 3: LiteLLM survives semantic_cache drop — pre-check**

Verify dropping `semantic_cache` doesn't crash LiteLLM before it recreates the collection. Check LiteLLM config handles a missing cache collection gracefully (it recreates on next request).
Run: inspect `roles/litellm/` cache config + a smoke test plan; if uncertain, drop `semantic_cache` LAST and immediately curl LiteLLM `/health`.
Expected: documented decision — safe to drop, recreates on demand.

- [ ] **Step 4: Snapshot MEMORY collections only (mandatory rollback)**

Write `qdrant_rebuild.py --snapshot` → calls Qdrant snapshot API for each MEMORY collection (skip CACHE/APP). Download snapshots to a dated dir on Waza (capped disk) or leave on Sese if room (Step 2).
Run: `python scripts/memory/qdrant_rebuild.py --snapshot --out ~/qdrant-snapshots/2026-06-05/`
Expected: one snapshot per MEMORY collection, sizes > 0, manifest written.

- [ ] **Step 5: Wipe MEMORY + CACHE collections**

Run: `python scripts/memory/qdrant_rebuild.py --wipe --confirm`
Expected: MEMORY + `semantic_cache` deleted; APP collections still present (re-run `--inventory` to confirm SPARE intact).

- [ ] **Step 6: LiteLLM health after cache drop**

Run: `curl -sf https://llm.ewutelo.cloud/health/liveliness` (or LiteLLM health route)
Expected: 200 / healthy. If not → restore is recreating; confirm within 1 min.

- [ ] **Step 7: Create memory_v2 + 6 payload indexes**

Write `qdrant_rebuild.py --create` → create `memory_v2` (768d, cosine) and payload indexes on `wing`, `room`, `doc_kind`, `repo`, `topic`, `tags`.
Run: `python scripts/memory/qdrant_rebuild.py --create`
Expected: collection exists; `client.get_collection('memory_v2')` shows the 6 payload schema fields indexed.

- [ ] **Step 8: Commit**

```bash
git add scripts/memory/qdrant_rebuild.py scripts/memory/test_qdrant_rebuild.py
git commit -m "feat(memory): M2 qdrant rebuild — snapshot/wipe(memory-only)/memory_v2 + 6 indexes"
```

---

## Task 3: M3 — sources taxonomy + GPU ingestion

**Files:**
- Modify: `roles/llamaindex-memory-worker/defaults/main.yml` (add `wing`/`room` per source)
- Modify: `roles/llamaindex-memory-worker/templates/index.py.j2` (payload: `wing`,`room`,`valid_from`,`valid_to`)
- Create: `scripts/memory/gpu_ingest/` (RunPod batch + Dockerfile/handler)
- Create: `scripts/memory/parity_check.py`

> **Critical (plan-review finding):** Today `wing`/`room` have ZERO plumbing. `merge_source_roots` (`index.py.j2:617`) discards everything except `root`; `to_text_nodes` (`index.py.j2:524`) has no wing/room params; `repo=repo_root.name` (basename, stable across parent move) and `doc_kind=classify_doc_kind(path)` are path-derived. During Plan A the Waza worker timer stays DISABLED, so **the GPU batch (Step 4) is the path that actually writes `memory_v2`** — it MUST build the `root→{wing,room}` mapping and set the fields, or every point gets `wing=null` and M4 scoping is dead. The worker (`index.py.j2`) and the GPU batch MUST share ONE payload-building path (batch imports the worker's chunk/payload functions) + ONE `root→{wing,room}` lookup.

- [ ] **Step 1: RESEARCH gate (R0/R8) — RunPod on-demand + Headscale ephemeral key**

Before any code: cite official docs for (a) RunPod on-demand GPU pod lifecycle + network-volume mount + outbound networking, (b) Headscale ephemeral pre-auth key creation + node ACL + revocation. Reuse `roles/headscale-node/` patterns where possible.
Output: short `scripts/memory/gpu_ingest/RESEARCH.md` with cited commands. Do NOT proceed to Step 4 until done.

- [ ] **Step 2: Confirm D8 + assign wing/room per source in sources.yml**

Confirm (already verified): `memory_worker_embedding_model: google/embeddinggemma-300m`, `memory_worker_embedding_dim: 768` in `defaults/main.yml:56-57` → zero migration, parity-continuity valid.
Add `wing:` and `room:` to each entry in `memory_worker_sources` (defaults/main.yml). Map: VPAI→wing `infra`; saas repos (fantrad/story-engine/podpilot/hawkeye/riposte/flash-studio)→wing `saas`, room per concern; DOCS/typebot-docs→wing `refdocs`. Keep `name:` and `root:` (current paths) unchanged.

- [ ] **Step 3: Plumb wing/room through BOTH the worker and a shared lookup (the load-bearing fix)**

1. In `sources.yml.j2`: emit `wing`/`room` for each source (currently only `root`/`name`/`tags`).
2. In `index.py.j2`: change `merge_source_roots` (`:617`) to preserve the full source dict (or return a `root → {wing, room}` lookup alongside the roots list); thread `wing`/`room` into `to_text_nodes` (`:524`) and into the metadata dict (near `:545`) — add `wing`, `room`, `valid_from`, `valid_to: null`. Match `root` to source by resolved path. Keep `repo`/`namespace`/`relative_path`/`doc_kind` as-is.
3. Expose a reusable function (e.g. `load_wing_room_lookup(sources_path) -> dict[resolved_root, {wing, room}]`) the GPU batch can import. Resolve keys canonically (`Path(root).expanduser().resolve()`) on BOTH the build side and the match side.
4. Confirm chunking constants (1600/200) are module-level importable (not buried in a function) so the GPU batch reuses them.

Test (`scripts/memory/test_payload_plumbing.py`): given a sample source dict + a file under its root, `to_text_nodes` output carries the correct `wing`/`room`. Run; expect PASS.

- [ ] **Step 4: Build GPU batch ingest — REUSING the worker payload path + lookup**

`scripts/memory/gpu_ingest/`: stage corpus from current `~/` paths to `/runpod-volume`; pod joins Headscale (ephemeral key); for each file reuse the worker's chunking + `to_text_nodes`/`load_wing_room_lookup` (import, do NOT reimplement) so payloads carry `wing`/`room`/`doc_kind`/`repo`/`relative_path`/`topic`/`tags`; embed chunks with `embeddinggemma-300m` on GPU; **direct upsert** into `memory_v2` over VPN.
**Staged-path trap:** `sources.yml` roots use `~/` but the pod reads from `/runpod-volume`. The `load_wing_room_lookup` keys must be the **staged paths on the pod**, not the `~/` source paths — build a `~/source-root → /runpod-volume/<repo>` remap so the canonical-resolved lookup keys align, else reuse silently returns null `wing`/`room` on the pod. Chunking config reused from worker (md-section/llama-sentence, 1600/200).
Verify on a 1-repo dry-run: upserted points have non-null `wing`/`room`.

- [ ] **Step 5: Parity gate — GPU↔CPU cosine (R4 protects D6)** *(harness from Step 4 now exists)*

`parity_check.py`: embed a fixed sample text with `embeddinggemma-300m` on the pod GPU and on Waza CPU, compare cosine.
Expected: cosine ≥ 0.9999. **Fallback:** force fp32 on the pod; last resort capped CPU embed on Waza.
**Gate:** do not run full bulk ingest (Step 6) until parity passes.

- [ ] **Step 6: Run bulk ingest**

Launch pod, run batch on full corpus, monitor.
Expected: point count in `memory_v2` ≈ expected chunk count; per-wing counts sane; **spot-check: zero points with null `wing`/`room`**.

- [ ] **Step 7: Teardown — terminate pod + revoke key**

Terminate the RunPod pod; revoke/confirm-removed the Headscale ephemeral node.
Expected: pod gone (no further billing); `headscale nodes list` shows the pod node removed.

- [ ] **Step 8: Commit**

```bash
git add roles/llamaindex-memory-worker/defaults/main.yml roles/llamaindex-memory-worker/templates/index.py.j2 scripts/memory/gpu_ingest scripts/memory/parity_check.py
git commit -m "feat(memory): M3 wing/room taxonomy + GPU on-demand ingestion (Headscale ephemeral, direct upsert)"
```

---

## Task 4: M4 — search_memory.py v2 (scoped + capped)

**Files:**
- Modify: `roles/llamaindex-memory-worker/templates/search_memory.py.j2`
- Test: `roles/llamaindex-memory-worker/templates/` sibling test or `scripts/memory/test_search_v2.py`

- [ ] **Step 1: Write failing test — scoped query excludes refdocs by default**

Test that a query without `--wing` does NOT return `wing=refdocs` chunks unless asked, and that `--wing infra --doc-kind rex` filters correctly.

- [ ] **Step 2: Point search at memory_v2 + add filters**

Update collection name to `memory_v2`; add `--wing`, `--room` args; default scoping (exclude refdocs unless requested or query clearly doc-seeking).

- [ ] **Step 3: Embedding = embeddinggemma CPU (D6/D8)**

Confirm query embeds with the SAME model on Waza CPU. No LiteLLM/network for the query embed.

- [ ] **Step 4: Cap the retrieval process (D14)**

Ensure `search_memory.py` / `mcp_search.py` runs under a memory cap (systemd-user slice or explicit limit). The two live `mcp_search.py` (~1.5G each) must not be able to OOM the Pi.

- [ ] **Step 5: Run tests + live scoped query**

Run the test + a real query (e.g. `--wing infra --doc-kind rex "caddy vpn"`).
Expected: relevant results, no refdocs drowning, latency acceptable on CPU.

- [ ] **Step 6: Commit**

```bash
git add roles/llamaindex-memory-worker/templates/search_memory.py.j2 scripts/memory/test_search_v2.py
git commit -m "feat(memory): M4 search v2 — memory_v2 scoped+capped retrieval (wing/doc_kind defaults)"
```

---

## Acceptance Gates (Plan A done)

1. Worker `MemoryMax=4G`, net-watchdog active, networkd/tailscaled OOM-protected (Task 1 Step 4).
2. `memory_v2` + 6 indexes exist; APP collections intact; LiteLLM healthy after cache drop (Task 2).
3. Parity GPU↔CPU cosine ≥ 0.9999 (Task 3 Step 5).
4. Bulk ingest complete; per-wing counts sane; pod terminated + key revoked (Task 3).
5. Scoped query returns relevant results without refdocs drowning; query embed on Waza CPU; retrieval capped (Task 4).

## Notes / Risks (from spec §8 + D14)

- Snapshot before wipe is **mandatory** (irreversible "repartir à 0").
- Headscale ephemeral key: revoke after batch; restrict node ACL.
- M3 internals gated on Step 1 research — adapt during execution if RunPod/Headscale specifics differ.
- Reorg (M1) + manifest (M5) = **Plan B**, executed after Plan A (terminal VPAI move + Claude Code restart).
