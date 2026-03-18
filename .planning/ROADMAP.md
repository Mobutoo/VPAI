# Roadmap: VPAI

## Milestones

- ✅ **v2026.3 Plane** - Phases 1-4 (shipped)
- 🚧 **v2026.3 Content Factory** - Phases 5-9 (in progress)

## Phases

<details>
<summary>✅ v2026.3 Plane (Phases 1-4) - SHIPPED</summary>

### Phase 1: Plane Deployment
**Goal**: Plane is accessible at `work.ewutelo.cloud`, connected to shared PostgreSQL and Redis, with admin accounts provisioned, monitoring active, and backup integrated
**Plans**: 3 plans (01-01, 01-02, 01-03)

### Phase 2: OpenClaw Upgrade
**Goal**: OpenClaw is running v2026.2.26 with all agents spawning correctly and security hardened
**Plans**: 2 plans (02-01, 02-02)

### Phase 3: Agent Integration
**Goal**: OpenClaw agents can discover tasks in Plane, update status/progress, and the Concierge can create and assign work through Plane API
**Plans**: 3 plans (03-01, 03-02, 03-03)

### Phase 4: Notifications & Orchestration
**Goal**: Plane events flow to Telegram in real-time, and the human can query project status via Telegram commands
**Plans**: 2 plans (04-01, 04-02)

</details>

### 🚧 v2026.3 Content Factory (In Progress)

**Milestone Goal:** Deploy the Content Factory pipeline -- Kitsu production tracking, NocoDB data model, Qdrant brand memory, OpenClaw content-director skill, n8n orchestration workflows, Remotion compositions, and Plane editorial calendar -- to produce Instagram content for Paul Taff.

**Phase Numbering:**
- Integer phases (5, 6, 7): Planned milestone work
- Decimal phases (5.1, 5.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 5: Foundation** - Kitsu deploy, data model (NocoDB + Qdrant + Kitsu structure), Fal.ai integration, monitoring, backup
- [x] **Phase 6: Building Blocks** - OpenClaw content-director skill with all Telegram commands + Remotion Instagram compositions (completed 2026-03-17)
- [x] **Phase 7: Orchestration** - n8n production workflows, Kitsu webhook integration, Plane editorial calendar (completed 2026-03-17)
- [ ] **Phase 8: Data Layer Glue** - 4 NocoDB CRUD webhooks + Kitsu project structure provisioning (gap closure)
- [x] **Phase 9: Integration Fixes** - Ansible variable fix, Remotion API mismatches, env vars, tech debt (gap closure) (completed 2026-03-18)

## Phase Details

### Phase 5: Foundation
**Goal**: All infrastructure and data layers are deployed and populated -- Kitsu running, NocoDB tables created, Qdrant brand-voice collection active, brand profile seeded -- ready for skills and workflows to build on
**Depends on**: Phase 4 (Plane milestone complete)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06
**Success Criteria** (what must be TRUE):
  1. Kitsu UI is accessible at `boss.ewutelo.cloud` via VPN, showing a project structure with Production/Episode/Sequence/Shot/Task hierarchy mapped to brand/drop/phase/content/step
  2. NocoDB tables `brands`, `contents`, `scenes` exist at `hq.ewutelo.cloud` with the Paul Taff brand profile populated (Flash-Studio colors, sarcastic tone, Instagram platform)
  3. Qdrant collection `brand-voice` accepts and returns semantic search queries for brand tone and style references
  4. Fal.ai API key is available in n8n environment and a test API call to a Fal.ai model succeeds
  5. Kitsu healthcheck appears green in Grafana and `kitsu_production` database is included in daily Zerobyte backup
**Plans**: 3 plans

Plans:
- [ ] 05-01-PLAN.md — Kitsu Ansible role + infra config (Docker Compose, Caddy, PostgreSQL, backup, Fal.ai, monitoring)
- [ ] 05-02-PLAN.md — NocoDB data model provisioning (brands/contents/scenes tables, Paul Taff brand, Qdrant brand-voice)
- [ ] 05-03-PLAN.md — Kitsu provisioning (Zou DB init, admin, project structure with 14 task types)

### Phase 6: Building Blocks
**Goal**: The content-director skill responds to all Telegram commands and Remotion renders all 4 Instagram composition formats from structured scene data
**Depends on**: Phase 5
**Requirements**: SKILL-01, SKILL-02, SKILL-03, SKILL-04, SKILL-05, SKILL-06, SKILL-07, SKILL-08, SKILL-09, RMTN-01, RMTN-02, RMTN-03, RMTN-04, RMTN-05
**Success Criteria** (what must be TRUE):
  1. User sends `/content reel-motion-text "Flash Studio launch"` in Telegram topic 7 and receives a structured concept response from OpenClaw content-director
  2. User sends `/ok`, `/adjust`, `/back`, `/preview`, `/impact` commands and each returns the correct pipeline state or modification
  3. Gate commands (`/lock-preprod`, `/lock-script`, `/ok-rough`, `/ok-final`, `/published`) advance content through the 4 production gates with appropriate validation
  4. Each Remotion composition (`reel-motion-text`, `reel-meme-skit`, `reel-feature-showcase`, `reel-teaser`) renders a 9:16 video on Waza, accepting `scenes[]`, `brand`, `audio` props
**Plans**: 3 plans

Plans:
- [ ] 06-01-PLAN.md — Remotion shared types + 4 Instagram Reel compositions (ReelMotionText, ReelMemeSkit, ReelFeatureShowcase, ReelTeaser) + Root.tsx + server registration + Ansible tasks
- [ ] 06-02-PLAN.md — OpenClaw content-director SKILL.md.j2 (9 Telegram commands, invalidation matrix, n8n delegation) + skill registration + topic 7 routing
- [ ] 06-03-PLAN.md — Deploy and verify (Ansible deploy to Sese-AI + Waza, smoke tests, human verification)

### Phase 7: Orchestration
**Goal**: The full 14-step production pipeline works end-to-end from Telegram brief to rendered video with scene-level invalidation, Kitsu sync, and editorial calendar in Plane
**Depends on**: Phase 6
**Requirements**: FLOW-01, FLOW-02, FLOW-03, FLOW-04, FLOW-05, FLOW-06, FLOW-07, CAL-01, CAL-02, CAL-03
**Success Criteria** (what must be TRUE):
  1. User creates content via `/content` and the `brief-to-concept` workflow automatically executes steps 1-5 (brief, research, moodboard, concept, casting), producing a validated concept stored in NocoDB
  2. `script-to-storyboard` generates a scene-by-scene storyboard, `generate-assets` dispatches each scene to the correct provider (ComfyUI/Remotion local first, Fal.ai cloud fallback), and `rough-cut` assembles the final video via Remotion
  3. Modifying a scene at step N triggers `invalidation-engine` to invalidate only downstream dependents (not full rebuild), visible via `/impact` before confirmation
  4. Kitsu webhooks fire on task status changes and preview uploads, keeping the Kitsu board in sync with pipeline state via `kitsu-sync` workflow
  5. Editorial calendar is visible in Plane with contents as work items (with publish dates) and drops organized as cycles, auto-created from NocoDB content entries via n8n
**Plans**: 5 plans

Plans:
- [ ] 07-01-PLAN.md — Pipeline core: brief-to-concept + script-to-storyboard LLM chain workflows
- [ ] 07-02-PLAN.md — Asset generation: generate-assets provider dispatch + rough-cut Remotion assembly
- [ ] 07-03-PLAN.md — Feedback loops: invalidation-engine + kitsu-sync + kitsu-inbound event handler
- [ ] 07-04-PLAN.md — Calendar sync + Ansible registration: Plane editorial calendar + register all 8 workflows in deploy pipeline
- [ ] 07-05-PLAN.md — Deploy + smoke test: Ansible deploy to Sese-AI + human verification of all endpoints

### Phase 8: Data Layer Glue
**Goal**: The 4 NocoDB CRUD webhook workflows exist and handle all content/scene CRUD operations, and Kitsu project structure is provisioned with 14 task types -- closing the data layer gap that blocks the entire pipeline
**Depends on**: Phase 7
**Requirements**: DATA-06
**Gap Closure**: Closes BLOCKER from v2026.3 audit (4 missing webhooks + unsatisfied DATA-06)
**Success Criteria** (what must be TRUE):
  1. `cf-create-content` webhook creates a row in NocoDB `contents` table and returns the new content ID
  2. `cf-update-content` webhook updates content fields (status, step, data) by content ID with action routing
  3. `cf-read-content` webhook reads content by ID or filters and returns full record
  4. `cf-scene` webhook handles scene CRUD (create, list, update, invalidate) by content ID
  5. Kitsu project "Paul Taff" has Production/Episode/Sequence hierarchy with 14 task types mapped to pipeline steps
**Plans**: 2 plans

Plans:
- [ ] 08-01-PLAN.md — 4 NocoDB CRUD webhook JSON files + NocoDB schema column additions + table ID env vars
- [ ] 08-02-PLAN.md — Ansible registration in deploy loops + deploy to Sese-AI + DATA-06 verification

### Phase 9: Integration Fixes
**Goal**: All cross-phase integration issues are fixed -- Kitsu events reach n8n, Remotion renders succeed, env vars are complete -- and the 3 E2E flows pass
**Depends on**: Phase 8
**Requirements**: (none new -- fixes existing FLOW-02, FLOW-05, FLOW-07 runtime behavior)
**Gap Closure**: Closes 2 BLOCKERs + 4 tech debt items from v2026.3 audit
**Success Criteria** (what must be TRUE):
  1. `event_handler.py.j2` uses correct variable `n8n_webhook_secret` and Kitsu events reach `cf-kitsu-inbound`
  2. `creative-pipeline.json.j2` calls `/renders` with `compositionId` field and reads `jobId` from response
  3. `n8n.env.j2` includes `REMOTION_API_KEY` and `BYTEPLUS_API_KEY`
  4. `cf-rough-cut` sends `action` field in `cf-update-content` call
  5. `cf-kitsu-sync` STATUS_MAP includes `locked` mapping
  6. Kitsu bot account (`javisi.bot@gmail.com`) exists in Zou and can authenticate via API
  7. Kitsu project "Paul Taff" created with Production/Episode/Sequence hierarchy (DATA-06 runtime)
  8. Vault credentials for Kitsu admin updated to match actual server (`seko.mobutoo@gmail.com`)
**Plans**: 2 plans

Plans:
- [ ] 09-01-PLAN.md — Template/workflow fixes (event_handler variable, Remotion API fields, env vars, rough-cut action, STATUS_MAP locked) + vault credential update
- [ ] 09-02-PLAN.md — Bot account provisioning + deploy to Sese-AI + E2E verification

## Progress

**Execution Order:**
Phases execute in numeric order: 5 -> 6 -> 7 -> 8 -> 9

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 5. Foundation | 2/3 | In Progress |  | - |
| 6. Building Blocks | 3/3 | Complete | 2026-03-17 | - |
| 7. Orchestration | 5/5 | Complete | 2026-03-17 | - |
| 8. Data Layer Glue | 1/2 | In Progress|  | - |
| 9. Integration Fixes | 2/2 | Complete   | 2026-03-18 | - |
