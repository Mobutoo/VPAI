# Phase 6: Building Blocks - Research

**Researched:** 2026-03-17
**Domain:** OpenClaw skill authoring (SKILL.md Jinja2 templates) + Remotion React compositions (TypeScript/React 9:16 video)
**Confidence:** HIGH

## Summary

Phase 6 has two independent workstreams: (1) creating the `content-director` OpenClaw skill with Telegram command routing, and (2) building 4 Remotion Instagram compositions. Both workstreams build on solid existing infrastructure from Phase 5 and the existing VPAI codebase.

The OpenClaw skill follows an established pattern: a Jinja2 `SKILL.md.j2` template deployed to `system/skills/<name>/SKILL.md`. The skill teaches the agent how to interpret Telegram commands and call external APIs (NocoDB for state, Qdrant for brand voice, Kitsu Zou API for tracking, n8n webhooks for delegation). The key challenge is designing a coherent state machine that maps `/content`, `/ok`, `/adjust`, `/back`, `/preview`, `/impact`, and gate commands to NocoDB CRUD operations and Kitsu status updates.

The Remotion workstream extends the existing render server (v4.0.259, ARM64/RPi5, Express API) with 4 new compositions. The server already has a working render queue, job management, and authentication. New compositions need to be registered in `Root.tsx`, added to `KNOWN_COMPOSITIONS` in `server/index.ts`, and their source files deployed via the Ansible role. All 4 compositions are 9:16 (1080x1920) Instagram Reels accepting `scenes[]`, `brand`, and `audio` props.

**Primary recommendation:** Treat the skill and Remotion as parallel workstreams. The skill is a single SKILL.md.j2 file + Ansible wiring. Remotion requires 4 composition React files + server/Root.tsx updates + Ansible task updates.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SKILL-01 | OpenClaw skill `content-director` created and loaded | Follows existing skill pattern: SKILL.md.j2 template + add to `openclaw_skills` list in defaults |
| SKILL-02 | Telegram topic 7 routed to content-director skill | Requires new topic entry in `openclaw_telegram_topics` + binding in openclaw.json.j2 |
| SKILL-03 | Command `/content <format> <brief>` creates new content | Skill instructions: create NocoDB row + Kitsu shot + set status step 1 |
| SKILL-04 | Command `/ok` validates current step, advances to next | Skill instructions: update NocoDB current_step + Kitsu task status |
| SKILL-05 | Command `/adjust <instruction>` modifies current step | Skill instructions: new version in NocoDB + Kitsu retake status |
| SKILL-06 | Command `/back <step>` returns to earlier step with impact analysis | Skill instructions: invalidation matrix logic + NocoDB cascade |
| SKILL-07 | Command `/preview` shows current project status | Skill instructions: read NocoDB content + format Telegram message |
| SKILL-08 | Command `/impact` shows what would be invalidated | Skill instructions: invalidation matrix calculation (read-only) |
| SKILL-09 | Gate commands `/lock-preprod`, `/lock-script`, `/ok-rough`, `/ok-final`, `/published` | Skill instructions: validate all steps done + lock NocoDB + Kitsu locked status |
| RMTN-01 | Composition `reel-motion-text` (9:16, 15-60s, animated text + gradients) | React component with spring animations, gradient backgrounds, text sequences |
| RMTN-02 | Composition `reel-meme-skit` (9:16, 15-30s, meme/skit format) | React component with image/video layers, text overlays, reaction zones |
| RMTN-03 | Composition `reel-feature-showcase` (9:16, 30-60s, product demo + overlays) | React component with screen capture frames, overlay animations, voiceover sync |
| RMTN-04 | Composition `reel-teaser` (9:16, 15s, hook + mystery + CTA) | React component with fast cuts, blur reveals, CTA text |
| RMTN-05 | All compositions accept `scenes[]`, `brand`, `audio` props | Shared TypeScript interfaces for SceneData, BrandProfile, AudioConfig |
</phase_requirements>

## Standard Stack

### Core (already deployed)

| Library | Version | Purpose | Location |
|---------|---------|---------|----------|
| Remotion | 4.0.259 | Video rendering framework | Waza RPi5 Docker |
| React | 18.3.x | Composition UI framework | Remotion container |
| Express | 4.21.x | Render server HTTP API | Remotion container |
| OpenClaw | v2026.3.x | AI agent gateway | Sese-AI Docker |
| Zod | 3.23.x | Request validation | Remotion server |

### Supporting (already deployed, used by skill)

| Service | URL | Purpose |
|---------|-----|---------|
| NocoDB | https://hq.ewutelo.cloud | Content state (brands/contents/scenes tables) |
| Kitsu/Zou | https://boss.ewutelo.cloud | Production tracking API |
| Qdrant | http://qdrant:6333 | Brand voice semantic search |
| LiteLLM | http://litellm:4000 | Embedding generation + AI model proxy |
| n8n | http://n8n:5678 | Workflow delegation |

### No new dependencies required

All infrastructure is already deployed. Phase 6 creates configuration files (SKILL.md.j2) and React source files (compositions) that plug into existing systems.

## Architecture Patterns

### OpenClaw Skill Pattern (existing, proven)

```
roles/openclaw/templates/skills/<skill-name>/SKILL.md.j2
```

Every skill is a Jinja2 template that renders to a Markdown file containing:
1. YAML frontmatter (`name`, `description`, `metadata`)
2. When to use this skill (trigger conditions)
3. API endpoints and examples (how the agent calls external services)
4. Rules and constraints

The skill file is deployed to `system/skills/<name>/SKILL.md` on Sese-AI. OpenClaw reads all skills at startup and injects relevant ones into the agent's context when the agent invokes them.

**Registration:** Add skill name to `openclaw_skills` list in `roles/openclaw/defaults/main.yml`. The existing task loops handle directory creation and file deployment.

### Telegram Topic Routing Pattern (existing)

Topic routing is already enabled (`openclaw_telegram_topic_routing: true`). Topics map to agents via `openclaw_telegram_topics` dict in defaults. The content-director needs a **new agent or skill routing approach**.

**Critical design decision:** OpenClaw routes topics to **agents**, not skills. The content-director is a **skill**, not an agent. Two options:

1. **Route topic 7 to the concierge agent** — the concierge picks up the `content-director` skill when it sees `/content` commands. Simpler, but concierge handles everything.
2. **Create a dedicated `director` agent** — route topic 7 to this agent, which has `content-director` as its primary skill. More isolated, dedicated workspace.

**Recommendation:** Route topic 7 to the **marketer agent** (already exists, designed for content/campaigns). Add `content-director` as a skill the marketer agent loads. This avoids creating a new agent and leverages existing infrastructure. The marketer agent already has the explorer and writer in its swarm graph for research and content creation.

### Remotion Composition Pattern (existing)

```
roles/remotion/files/remotion/<CompositionName>/<CompositionName>.tsx
roles/remotion/files/remotion/Root.tsx   (register composition)
roles/remotion/files/server/index.ts     (add to KNOWN_COMPOSITIONS)
roles/remotion/tasks/main.yml            (add file copy tasks)
```

Each composition is a React component accepting typed props. Registered in Root.tsx with `<Composition>` tag specifying id, dimensions, fps, and default props.

**Instagram Reel dimensions:** 1080x1920 (9:16), 30fps standard.

### Shared Props Interface (new pattern for RMTN-05)

```typescript
// roles/remotion/files/remotion/types.ts
interface SceneData {
  scene_number: number;
  description: string;
  dialogue?: string;
  screen_text?: string;
  duration_sec: number;
  transition: string;
  visual_type: "motion_design" | "ai_generative" | "stock" | "meme";
  asset_url?: string;
}

interface BrandProfile {
  name: string;
  palette: { primary: string; accent: string; background?: string };
  typography: { heading: string; body: string };
  logo_url?: string;
}

interface AudioConfig {
  url?: string;
  startFrom?: number;
  volume?: number;
}

interface ReelProps {
  scenes: SceneData[];
  brand: BrandProfile;
  audio?: AudioConfig;
}
```

### Anti-Patterns to Avoid

- **Hardcoding composition durations:** Calculate from `scenes[].duration_sec` sum. Use `durationInFrames` as a function of total scene durations.
- **Monolithic SKILL.md:** The content-director skill will be large (many commands). Structure with clear sections per command, not one wall of text.
- **Duplicating API patterns:** Reference existing skills (delegate-n8n, search-content, generate-visual) for API call patterns rather than rewriting.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State machine for pipeline steps | Custom state tracker | NocoDB `current_step` field + Kitsu task status | Source of truth already exists |
| Invalidation cascade | Complex dependency graph | Static invalidation matrix in SKILL.md | 14 steps with known dependencies, matrix is deterministic |
| Video duration calculation | Manual frame math | `durationInFrames = Math.ceil(totalSeconds * fps)` | Remotion handles frame-level timing |
| Text animation | Custom CSS animation | Remotion `spring()` + `interpolate()` | Built-in, battle-tested, GPU-accelerated |
| Gradient backgrounds | Canvas API | CSS `linear-gradient` in `AbsoluteFill` | React rendering, simpler |
| Audio sync | Manual timing | Remotion `<Audio>` component with `startFrom` | Frame-accurate sync built-in |

## Common Pitfalls

### Pitfall 1: Remotion ARM64 Chromium Memory

**What goes wrong:** Chromium headless on RPi5 with 1080x1920 compositions can OOM at 512MB limit.
**Why it happens:** Each frame renders as a full Chromium page. 1080x1920 at 30fps is heavy.
**How to avoid:** Keep compositions CSS-based (no heavy canvas/WebGL). Consider bumping `remotion_memory_limit` to `1024M` if renders fail. Test with short (5s) compositions first.
**Warning signs:** Render jobs stuck at "in-progress" then "failed" with `SIGKILL`.

### Pitfall 2: KNOWN_COMPOSITIONS Allowlist

**What goes wrong:** New compositions render as "Unknown composition" 400 error.
**Why it happens:** `server/index.ts` has a hardcoded `KNOWN_COMPOSITIONS` Set that must list every valid composition ID.
**How to avoid:** Every new composition added to `Root.tsx` MUST also be added to the Set in `server/index.ts`.

### Pitfall 3: OpenClaw Skill Not Loading

**What goes wrong:** Skill deployed but agent does not use it.
**Why it happens:** Skill name not added to `openclaw_skills` list in `defaults/main.yml`, or skill directory not created by Ansible task loop.
**How to avoid:** Add to `openclaw_skills` list AND verify the Jinja2 template exists at the expected path.

### Pitfall 4: Telegram Topic Routing First-Match

**What goes wrong:** Content-director messages go to concierge instead of the intended agent.
**Why it happens:** OpenClaw uses first-match routing in bindings. The catch-all Telegram binding must come LAST.
**How to avoid:** Topic-specific bindings are already rendered FIRST in `openclaw.json.j2` (see the template comments). Just ensure the new topic entry is in `openclaw_telegram_topics`.

### Pitfall 5: NocoDB API Token

**What goes wrong:** OpenClaw agent cannot call NocoDB API.
**Why it happens:** The skill needs the NocoDB API token, but agents run in sandboxes without vault secrets.
**How to avoid:** The skill uses `web_fetch` tool to call NocoDB API. The token must be available as an environment variable in the agent's sandbox, OR the skill should instruct the agent to call NocoDB via n8n webhook (which already has the token).

### Pitfall 6: Kitsu Zou API Authentication

**What goes wrong:** API calls to Kitsu return 401.
**Why it happens:** Zou API requires JWT auth obtained via `/api/auth/login`.
**How to avoid:** The skill must document the auth flow: POST `/api/auth/login` with bot credentials, use returned JWT for subsequent calls. Bot Mobotoo credentials are in vault (`vault_kitsu_admin_email`, `vault_kitsu_admin_password`) but the skill should reference the n8n `kitsu-sync` workflow pattern for delegation.

### Pitfall 7: Ansible File Copy Loop

**What goes wrong:** New composition files not deployed to RPi5.
**Why it happens:** The `remotion/tasks/main.yml` has explicit file lists for copy tasks. New files must be added.
**How to avoid:** Add new composition directories and files to the existing copy loops in `tasks/main.yml`.

## Code Examples

### Example 1: SKILL.md.j2 Frontmatter Pattern

```yaml
---
name: content-director
description: Pilot the Content Factory pipeline — create content, validate steps, handle gates and invalidation via Telegram commands.
metadata: { "openclaw": { "emoji": "🎬", "always": false } }
---
```

### Example 2: Remotion Composition Registration (Root.tsx)

```tsx
// Source: existing pattern from roles/remotion/files/remotion/Root.tsx
import { Composition } from "remotion";
import { ReelMotionText } from "./ReelMotionText/ReelMotionText";

// In RemotionRoot component:
<Composition
  id="ReelMotionText"
  component={ReelMotionText}
  durationInFrames={900}  // 30s at 30fps, overridden by inputProps
  fps={30}
  width={1080}
  height={1920}
  defaultProps={{
    scenes: [],
    brand: { name: "Default", palette: { primary: "#FF6B35", accent: "#2EC4B6" }, typography: { heading: "sans-serif", body: "sans-serif" } },
  }}
/>
```

### Example 3: Basic Reel Composition Structure

```tsx
// Source: Remotion docs pattern + existing HelloWorld
import React from "react";
import { AbsoluteFill, Sequence, spring, useCurrentFrame, useVideoConfig, Audio } from "remotion";

interface ReelMotionTextProps {
  scenes: SceneData[];
  brand: BrandProfile;
  audio?: AudioConfig;
}

export const ReelMotionText: React.FC<ReelMotionTextProps> = ({ scenes, brand, audio }) => {
  const { fps } = useVideoConfig();

  // Calculate frame offsets per scene
  let frameOffset = 0;
  const sceneFrames = scenes.map((scene) => {
    const start = frameOffset;
    const duration = Math.ceil(scene.duration_sec * fps);
    frameOffset += duration;
    return { ...scene, startFrame: start, durationFrames: duration };
  });

  return (
    <AbsoluteFill style={{ backgroundColor: brand.palette.primary }}>
      {audio?.url && <Audio src={audio.url} startFrom={audio.startFrom ?? 0} volume={audio.volume ?? 1} />}
      {sceneFrames.map((scene, i) => (
        <Sequence key={i} from={scene.startFrame} durationInFrames={scene.durationFrames}>
          {/* Scene content rendered here */}
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
```

### Example 4: NocoDB API Call Pattern (for SKILL.md)

```
POST https://hq.ewutelo.cloud/api/v2/meta/bases/<base-id>/tables/<table-id>/records
Headers:
  Content-Type: application/json
  xc-token: ${NOCODB_API_TOKEN}
Body:
  {
    "title": "<content title>",
    "format": "reel",
    "status": "brief",
    "current_phase": 1,
    "current_step": 1,
    "brand_id": "<brand row id>"
  }
```

### Example 5: Kitsu Zou API Pattern (for SKILL.md)

```
# Step 1: Authenticate
POST https://boss.ewutelo.cloud/api/auth/login
Body: { "email": "<bot_email>", "password": "<bot_password>" }
Response: { "access_token": "jwt..." }

# Step 2: Create shot (content)
POST https://boss.ewutelo.cloud/api/data/projects/<project-id>/shots
Headers: Authorization: Bearer <jwt>
Body: { "name": "<content-title>", "sequence_id": "<sequence-id>" }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat skill .md files | Skill directories with SKILL.md | Already in place | Skills deployed as `skills/<name>/SKILL.md` |
| Single HelloWorld composition | Multiple registered compositions | This phase | Must update `KNOWN_COMPOSITIONS` Set and `Root.tsx` |
| Manual Telegram routing | Topic-based agent routing | Already in place (v2026.3.7) | Content-director gets its own topic (7) |

## Open Questions

1. **Topic 7 agent assignment**
   - What we know: Topic 7 is designated for content-director per STATE.md decisions. Topic routing maps to agents, not skills.
   - What's unclear: Which existing agent should handle topic 7 (marketer vs. new agent vs. concierge).
   - Recommendation: Use the marketer agent. Add topic 7 to `openclaw_telegram_topics` mapping to marketer. The marketer agent already has writer and artist in its swarm graph.

2. **NocoDB API token access from agent sandbox**
   - What we know: Agents run in sandboxes. NocoDB API requires `xc-token` header.
   - What's unclear: Whether to inject the token as sandbox env var or delegate all NocoDB calls through n8n.
   - Recommendation: Delegate via n8n webhook (consistent with delegate-n8n pattern). The SKILL.md instructs the agent to use n8n for CRUD operations, keeping secrets out of agent sandboxes.

3. **Remotion memory for 1080x1920 compositions**
   - What we know: Current limit is 512MB. HelloWorld is 1920x1080 (landscape). New compositions are 1080x1920 (portrait, same pixel count).
   - What's unclear: Whether 512MB is sufficient for multi-scene compositions with images.
   - Recommendation: Test with 512MB first. Document that `remotion_memory_limit` may need bumping to `1024M`.

4. **Dynamic durationInFrames**
   - What we know: Remotion requires `durationInFrames` at registration time. Scene durations are dynamic (from inputProps).
   - What's unclear: How to handle variable-length compositions.
   - Recommendation: Use `calculateMetadata` callback in Remotion 4.x to compute duration from props at render time. This is the official pattern for dynamic durations.

## Validation Architecture

> `workflow.nyquist_validation` not explicitly set to false in config.json -- including validation section.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Ansible + manual smoke tests |
| Config file | `roles/openclaw/molecule/default/molecule.yml` (existing) |
| Quick run command | `make lint` (YAML/Ansible linting) |
| Full suite command | `make deploy-role ROLE=openclaw ENV=prod --check --diff` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SKILL-01 | Skill file created and Ansible deploys it | smoke | `ansible-playbook playbooks/site.yml --tags openclaw --check --diff` | Wave 0 |
| SKILL-02 | Topic 7 routing configured | smoke | `grep content-director` on rendered openclaw.json | Wave 0 |
| SKILL-03 | `/content` command documented in skill | manual-only | Send `/content reel test` in Telegram topic 7 | N/A |
| SKILL-04 | `/ok` command documented in skill | manual-only | Send `/ok` in Telegram topic 7 | N/A |
| SKILL-05 | `/adjust` command documented in skill | manual-only | Send `/adjust tone more sarcastic` in Telegram topic 7 | N/A |
| SKILL-06 | `/back` command documented in skill | manual-only | Send `/back 3` in Telegram topic 7 | N/A |
| SKILL-07 | `/preview` command documented in skill | manual-only | Send `/preview` in Telegram topic 7 | N/A |
| SKILL-08 | `/impact` command documented in skill | manual-only | Send `/impact` in Telegram topic 7 | N/A |
| SKILL-09 | Gate commands documented in skill | manual-only | Send gate commands in Telegram topic 7 | N/A |
| RMTN-01 | ReelMotionText composition renders | smoke | `curl -X POST localhost:3200/renders -d '{"compositionId":"ReelMotionText",...}'` | Wave 0 |
| RMTN-02 | ReelMemeSkit composition renders | smoke | `curl -X POST localhost:3200/renders -d '{"compositionId":"ReelMemeSkit",...}'` | Wave 0 |
| RMTN-03 | ReelFeatureShowcase composition renders | smoke | `curl -X POST localhost:3200/renders -d '{"compositionId":"ReelFeatureShowcase",...}'` | Wave 0 |
| RMTN-04 | ReelTeaser composition renders | smoke | `curl -X POST localhost:3200/renders -d '{"compositionId":"ReelTeaser",...}'` | Wave 0 |
| RMTN-05 | All compositions accept shared props | unit | TypeScript compilation check (`npx tsc --noEmit`) | Wave 0 |

### Sampling Rate
- **Per task commit:** `make lint`
- **Per wave merge:** `make deploy-role ROLE=openclaw ENV=prod --check --diff`
- **Phase gate:** Full deploy + Telegram smoke test + Remotion render test

### Wave 0 Gaps
- [ ] `roles/remotion/files/remotion/types.ts` -- shared TypeScript interfaces for RMTN-05
- [ ] Composition test renders via curl (smoke scripts)
- [ ] Skill template at `roles/openclaw/templates/skills/content-director/SKILL.md.j2`

## Sources

### Primary (HIGH confidence)
- Codebase: `roles/openclaw/defaults/main.yml` -- skill registration pattern, agent config, topic routing
- Codebase: `roles/openclaw/tasks/main.yml` -- skill deployment task loop
- Codebase: `roles/openclaw/templates/openclaw.json.j2` -- full OpenClaw config with bindings, topic routing
- Codebase: `roles/remotion/files/` -- existing server, composition, Dockerfile patterns
- Codebase: `roles/remotion/tasks/main.yml` -- Ansible deployment pattern for compositions
- Codebase: `roles/openclaw/templates/skills/*/SKILL.md.j2` -- 5 existing skills examined for pattern

### Secondary (MEDIUM confidence)
- PRD: `docs/PRD-CONTENT-FACTORY.md` -- pipeline design, commands, compositions, invalidation matrix
- STATE.md: Phase 5 decisions, Kitsu IDs, bot credentials

### Tertiary (LOW confidence)
- Remotion 4.0.259 `calculateMetadata` API for dynamic duration -- based on training data, verify with Remotion docs before implementation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all infrastructure exists and was verified from codebase
- Architecture: HIGH -- follows proven existing patterns (skills, compositions, Ansible roles)
- Pitfalls: HIGH -- derived from actual codebase constraints (KNOWN_COMPOSITIONS, topic routing order, sandbox env)
- Remotion dynamic duration: MEDIUM -- `calculateMetadata` is standard Remotion 4.x but not yet used in this project

**Research date:** 2026-03-17
**Valid until:** 2026-04-17 (stable infrastructure, no fast-moving dependencies)
