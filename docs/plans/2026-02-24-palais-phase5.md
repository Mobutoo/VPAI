# Palais Phase 5 — Boite a Idees + Mission Launcher

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Pipeline d'ideation (Draft→Approved→Dispatched) avec versioning, et flow co-planning humain+IA (brainstorming LiteLLM, co-editing inline, dispatch auto).

**Architecture:** Ideas avec versions snapshots en JSONB. Missions avec chat LiteLLM streaming. Co-editing via formulaire inline (pas juste approve/reject). Dispatch cree projet + taches + notifie agents.

**Tech Stack:** SvelteKit 5, LiteLLM API, Drizzle ORM, TipTap

**PRD Reference:** `docs/PRD-PALAIS.md` — Modules 3 (Boite a Idees) + 4 (Mission Launcher)

---

## Task 1: Ideas CRUD API

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/ideas/+server.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/ideas/[id]/+server.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/ideas/[id]/versions/+server.ts`

GET/POST ideas. PUT to update status/content. POST versions to create new snapshot. GET versions to list history.

Commit: `feat(palais): ideas + versions CRUD API`

---

## Task 2: Ideas Pipeline Page

**Files:**
- Create: `roles/palais/files/app/src/routes/ideas/+page.svelte`
- Create: `roles/palais/files/app/src/routes/ideas/+page.server.ts`

Visual pipeline: columns for each status (Draft, Brainstorming, Planned, Approved, Dispatched, Archived). Cards draggable between columns. Gold accents.

Commit: `feat(palais): ideas pipeline visual page`

---

## Task 3: Idea Detail + Version History

**Files:**
- Create: `roles/palais/files/app/src/routes/ideas/[id]/+page.svelte`

Show idea with TipTap editor, tags, priority. Version timeline on the right. Click version to view snapshot. Diff button between any two versions (simple JSON diff display).

Commit: `feat(palais): idea detail with version history + diff`

---

## Task 4: Mission Creation Flow

**Files:**
- Create: `roles/palais/files/app/src/routes/missions/+page.server.ts`
- Create: `roles/palais/files/app/src/routes/missions/+page.svelte`
- Create: `roles/palais/files/app/src/routes/missions/new/+page.svelte`
- Create: `roles/palais/files/app/src/routes/api/v1/missions/+server.ts`

New mission: text brief or select from approved idea. Creates mission in DB with status `briefing`.

Commit: `feat(palais): mission creation flow`

---

## Task 5: Brainstorming Chat (LiteLLM)

**Files:**
- Create: `roles/palais/files/app/src/routes/missions/[id]/+page.svelte`
- Create: `roles/palais/files/app/src/routes/api/v1/missions/[id]/chat/+server.ts`
- Create: `roles/palais/files/app/src/lib/server/llm/client.ts`

LLM client:
```typescript
// src/lib/server/llm/client.ts
import { env } from '$env/dynamic/private';

export async function chatCompletion(messages: { role: string; content: string }[]) {
  const res = await fetch(`${env.LITELLM_URL}/v1/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.LITELLM_KEY}`
    },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      messages,
      max_tokens: 1000
    })
  });
  return res.json();
}
```

Chat endpoint: POST with user message, append to mission_conversations, call LiteLLM, store response. System prompt: "Tu es un planificateur. Pose 1 question a la fois pour comprendre le besoin."

UI: chat interface with message bubbles (gold for user, surface for AI). Auto-save conversation.

Commit: `feat(palais): brainstorming chat with LiteLLM integration`

---

## Task 6: Co-Editing Plan

After brainstorming, mission moves to `planning` → LLM generates task breakdown (stored in `plan_snapshot` JSONB). Then `co_editing`: user sees editable table of tasks. Can:
- Reorder tasks (drag)
- Change assigned agent (dropdown)
- Edit cost estimates (inline)
- Add/remove dependencies
- Add/remove tasks

All changes saved to mission `plan_snapshot`.

Commit: `feat(palais): co-editing plan with inline modifications`

---

## Task 7: Dispatch (Approved → Project + Tasks)

When user clicks "Dispatch":
1. Create project from mission title
2. Create default columns
3. Create tasks from plan_snapshot
4. Set dependencies
5. Update mission status to `executing`
6. (Future: notify agents via OpenClaw)

Commit: `feat(palais): mission dispatch — auto-create project + tasks`

---

## Verification Checklist

- [ ] Ideas CRUD works (create, edit, status transitions)
- [ ] Version snapshots saved on status change
- [ ] Version diff displays changes
- [ ] Mission created from brief or idea
- [ ] Brainstorming chat works (LiteLLM responds, conversation saved)
- [ ] Co-editing allows inline plan modification
- [ ] Dispatch creates project + tasks + dependencies
- [ ] Mission status flow: briefing → brainstorming → planning → co_editing → approved → executing
