# Palais Phase 3 — Project Board Kanban

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Vue Kanban drag & drop complete avec CRUD taches, commentaires TipTap, labels, filtres, et vue liste. Style Kuba headers + accents or.

**Architecture:** Kanban client-side avec drag natif HTML5 (ou @dnd-kit/svelte), API REST pour persistence, TipTap pour rich text.

**Tech Stack:** SvelteKit 5, TipTap, HTML5 Drag & Drop, Drizzle ORM

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 5 (Project Board)

**Prerequis:** Phase 1-2 completes

---

## Task 1: Install TipTap + Drag Dependencies

```bash
cd roles/palais/files/app
npm install @tiptap/core @tiptap/starter-kit @tiptap/pm @tiptap/extension-placeholder svelte-dnd-action
```

Commit: `chore(palais): add TipTap + svelte-dnd-action dependencies`

---

## Task 2: Projects List Page

**Files:**
- Create: `roles/palais/files/app/src/routes/projects/+page.server.ts`
- Create: `roles/palais/files/app/src/routes/projects/+page.svelte`

**Step 1: Server load**

```typescript
// src/routes/projects/+page.server.ts
import { db } from '$lib/server/db';
import { projects } from '$lib/server/db/schema';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
  const all = await db.select().from(projects).orderBy(projects.updatedAt);
  return { projects: all };
};
```

**Step 2: Projects page with create form**

Render list of projects as cards (gold border, Kuba pattern bg), with a "New Project" button that opens a modal. Each card links to `/projects/[id]`.

Commit: `feat(palais): projects list page`

---

## Task 3: Kanban Board Page

**Files:**
- Create: `roles/palais/files/app/src/routes/projects/[id]/+page.server.ts`
- Create: `roles/palais/files/app/src/routes/projects/[id]/+page.svelte`
- Create: `roles/palais/files/app/src/lib/components/kanban/KanbanBoard.svelte`
- Create: `roles/palais/files/app/src/lib/components/kanban/KanbanColumn.svelte`
- Create: `roles/palais/files/app/src/lib/components/kanban/TaskCard.svelte`

**Step 1: Load project with columns and tasks**

```typescript
// src/routes/projects/[id]/+page.server.ts
import { db } from '$lib/server/db';
import { projects, columns, tasks } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { error } from '@sveltejs/kit';

export const load = async ({ params }) => {
  const projectId = parseInt(params.id);
  const [project] = await db.select().from(projects).where(eq(projects.id, projectId));
  if (!project) throw error(404, 'Project not found');

  const cols = await db.select().from(columns)
    .where(eq(columns.projectId, projectId))
    .orderBy(asc(columns.position));

  const allTasks = await db.select().from(tasks)
    .where(eq(tasks.projectId, projectId))
    .orderBy(asc(tasks.position));

  return { project, columns: cols, tasks: allTasks };
};
```

**Step 2: KanbanBoard component**

Uses `svelte-dnd-action` for drag & drop. Columns rendered horizontally with scroll. Each column has Kuba-pattern header. Cards show title, priority accent (gold left border), confidence badge, cost badge.

On drop: `PUT /api/v1/tasks/:id` with new `columnId` and `position`.

**Step 3: TaskCard component**

Shows: title, priority color bar (left), agent avatar, confidence badge (green/orange/red circle), cost (estimated vs actual). Click opens detail panel.

Commit: `feat(palais): Kanban board with drag & drop`

---

## Task 4: Task Detail Panel

**Files:**
- Create: `roles/palais/files/app/src/lib/components/kanban/TaskDetail.svelte`
- Create: `roles/palais/files/app/src/lib/components/editor/RichTextEditor.svelte`

**Step 1: TipTap Rich Text Editor wrapper**

```svelte
<!-- src/lib/components/editor/RichTextEditor.svelte -->
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { Editor } from '@tiptap/core';
  import StarterKit from '@tiptap/starter-kit';
  import Placeholder from '@tiptap/extension-placeholder';

  let { content = '', onUpdate }: { content?: string; onUpdate?: (html: string) => void } = $props();
  let element: HTMLDivElement;
  let editor: Editor;

  onMount(() => {
    editor = new Editor({
      element,
      extensions: [
        StarterKit,
        Placeholder.configure({ placeholder: 'Ecrivez ici...' })
      ],
      content,
      onUpdate: ({ editor }) => {
        onUpdate?.(editor.getHTML());
      }
    });
  });

  onDestroy(() => editor?.destroy());
</script>

<div bind:this={element} class="prose prose-invert max-w-none min-h-[100px] p-3 rounded-md"
  style="background: var(--palais-bg); border: 1px solid var(--palais-border);"></div>
```

**Step 2: TaskDetail panel**

Slide-out panel from right. Shows: title (editable), description (TipTap), status, priority dropdown, agent assignment, dates, cost, comments list, add comment form.

Commit: `feat(palais): task detail panel with TipTap editor`

---

## Task 5: Comments API + UI

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/tasks/[id]/comments/+server.ts`

```typescript
// GET: list comments, POST: create comment
import { db } from '$lib/server/db';
import { comments } from '$lib/server/db/schema';
import { eq, asc } from 'drizzle-orm';
import { json } from '@sveltejs/kit';

export const GET = async ({ params }) => {
  const taskId = parseInt(params.id);
  const result = await db.select().from(comments)
    .where(eq(comments.taskId, taskId))
    .orderBy(asc(comments.createdAt));
  return json(result);
};

export const POST = async ({ params, request }) => {
  const taskId = parseInt(params.id);
  const body = await request.json();
  const [comment] = await db.insert(comments).values({
    taskId,
    content: body.content,
    authorType: body.authorType || 'user',
    authorAgentId: body.authorAgentId
  }).returning();
  return json(comment, { status: 201 });
};
```

Commit: `feat(palais): comments CRUD API + UI in task detail`

---

## Task 6: Activity Log Middleware

**Files:**
- Create: `roles/palais/files/app/src/lib/server/activity.ts`

```typescript
import { db } from '$lib/server/db';
import { activityLog } from '$lib/server/db/schema';

export async function logActivity(params: {
  entityType: string;
  entityId: number;
  action: string;
  actorType?: 'user' | 'agent' | 'system';
  actorAgentId?: string;
  oldValue?: string;
  newValue?: string;
}) {
  await db.insert(activityLog).values({
    entityType: params.entityType,
    entityId: params.entityId,
    action: params.action,
    actorType: (params.actorType || 'system') as any,
    actorAgentId: params.actorAgentId,
    oldValue: params.oldValue,
    newValue: params.newValue
  });
}
```

Integrate in task update and comment creation routes.

Commit: `feat(palais): activity log recording`

---

## Task 7: Labels CRUD

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/labels/+server.ts`

CRUD for labels. Associate labels to tasks via `task_labels` table.

Commit: `feat(palais): labels CRUD + task-label association`

---

## Task 8: List View

**Files:**
- Create: `roles/palais/files/app/src/routes/projects/[id]/list/+page.svelte`

Filterable/sortable table. Columns: title, status, priority, agent, confidence, cost, dates. Filters: agent dropdown, status checkboxes, priority, labels. Bulk select + actions.

Commit: `feat(palais): project list view with filters`

---

## Verification Checklist

- [ ] `/projects` lists all projects
- [ ] `/projects/:id` shows Kanban with drag & drop
- [ ] Task cards show priority accent, confidence badge, cost
- [ ] Click task opens detail panel with TipTap editor
- [ ] Comments can be added and listed
- [ ] Activity log records task changes
- [ ] Labels can be created and assigned
- [ ] `/projects/:id/list` shows filterable table
- [ ] Kuba pattern visible on column headers
