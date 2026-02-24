# Palais Phase 4 — Dependances & Timeline

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Systeme de dependances entre taches avec detection de cycles, blocage auto, chemin critique, et vue Gantt SVG interactive.

**Architecture:** Dependencies en DB avec validation DFS server-side. Chemin critique calcule via tri topologique + plus long chemin O(V+E). Timeline SVG avec d3-scale.

**Tech Stack:** SvelteKit 5, d3-scale, Custom SVG, Drizzle ORM

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 5 (Dependances + Chemin Critique)

---

## Task 1: Dependencies CRUD API

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/tasks/[id]/dependencies/+server.ts`

```bash
cd roles/palais/files/app && npm install d3-scale d3-time && npm install -D @types/d3-scale @types/d3-time
```

POST creates dependency, DELETE removes. GET lists dependencies for a task. Validate no self-reference.

Commit: `feat(palais): task dependencies CRUD API`

---

## Task 2: Cycle Detection (DFS)

**Files:**
- Create: `roles/palais/files/app/src/lib/server/utils/graph.ts`

```typescript
// src/lib/server/utils/graph.ts
import { db } from '$lib/server/db';
import { taskDependencies } from '$lib/server/db/schema';
import { eq } from 'drizzle-orm';

export async function hasCycle(taskId: number, dependsOnId: number): Promise<boolean> {
  // Build adjacency list from all deps in same project
  const allDeps = await db.select().from(taskDependencies);
  const adj = new Map<number, number[]>();

  for (const d of allDeps) {
    if (!adj.has(d.taskId)) adj.set(d.taskId, []);
    adj.get(d.taskId)!.push(d.dependsOnTaskId);
  }

  // Add the proposed edge
  if (!adj.has(taskId)) adj.set(taskId, []);
  adj.get(taskId)!.push(dependsOnId);

  // DFS cycle detection
  const visited = new Set<number>();
  const inStack = new Set<number>();

  function dfs(node: number): boolean {
    if (inStack.has(node)) return true; // cycle
    if (visited.has(node)) return false;
    visited.add(node);
    inStack.add(node);
    for (const neighbor of adj.get(node) || []) {
      if (dfs(neighbor)) return true;
    }
    inStack.delete(node);
    return false;
  }

  return dfs(taskId);
}
```

Integrate in POST dependencies route: reject with 400 if cycle detected.

Commit: `feat(palais): DFS cycle detection for task dependencies`

---

## Task 3: Auto-Blocking Logic

Add to task update logic: when updating a task status to `in-progress`, check if all dependencies are in a `done`/final column. If not, reject with 409.

Commit: `feat(palais): auto-blocking for unresolved dependencies`

---

## Task 4: Critical Path Algorithm

**Files:**
- Create: `roles/palais/files/app/src/lib/server/utils/critical-path.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/projects/[id]/critical-path/+server.ts`

```typescript
// src/lib/server/utils/critical-path.ts
type TaskNode = { id: number; duration: number; deps: number[] };

export function computeCriticalPath(taskNodes: TaskNode[]): number[] {
  const nodeMap = new Map(taskNodes.map(t => [t.id, t]));
  const adj = new Map<number, number[]>(); // task -> tasks that depend on it
  const inDegree = new Map<number, number>();

  for (const t of taskNodes) {
    inDegree.set(t.id, t.deps.length);
    for (const dep of t.deps) {
      if (!adj.has(dep)) adj.set(dep, []);
      adj.get(dep)!.push(t.id);
    }
  }

  // Topological sort + longest path
  const dist = new Map<number, number>();
  const prev = new Map<number, number>();
  const queue: number[] = [];

  for (const t of taskNodes) {
    dist.set(t.id, t.duration);
    if (t.deps.length === 0) queue.push(t.id);
  }

  while (queue.length > 0) {
    const u = queue.shift()!;
    for (const v of adj.get(u) || []) {
      const newDist = dist.get(u)! + nodeMap.get(v)!.duration;
      if (newDist > (dist.get(v) || 0)) {
        dist.set(v, newDist);
        prev.set(v, u);
      }
      inDegree.set(v, (inDegree.get(v) || 1) - 1);
      if (inDegree.get(v) === 0) queue.push(v);
    }
  }

  // Trace back from the node with max distance
  let maxNode = taskNodes[0]?.id;
  let maxDist = 0;
  for (const [id, d] of dist) {
    if (d > maxDist) { maxDist = d; maxNode = id; }
  }

  const path: number[] = [];
  let current: number | undefined = maxNode;
  while (current !== undefined) {
    path.unshift(current);
    current = prev.get(current);
  }

  return path;
}
```

API endpoint returns critical path task IDs.

Commit: `feat(palais): critical path algorithm O(V+E)`

---

## Task 5: Gantt/Timeline SVG View

**Files:**
- Create: `roles/palais/files/app/src/routes/projects/[id]/timeline/+page.svelte`
- Create: `roles/palais/files/app/src/lib/components/timeline/GanttChart.svelte`

GanttChart renders:
- Horizontal bars per task (gold fill on dark bg)
- Dependency arrows (cyan)
- Critical path tasks highlighted in red
- Time axis with d3-scaleTime (day/week/month zoom)
- Drag bars to update start/end dates (PATCH task API)

Commit: `feat(palais): Gantt timeline SVG with d3-scale`

---

## Task 6: Cascade Recalculation

When a critical-path task's end date changes, recalculate dependent tasks' start dates automatically.

Commit: `feat(palais): cascade date recalculation on timeline`

---

## Verification Checklist

- [ ] Dependencies can be created/deleted via API
- [ ] Cycle detection rejects circular dependencies (400)
- [ ] Tasks with unresolved deps cannot move to in-progress (409)
- [ ] `/projects/:id/critical-path` returns correct path
- [ ] `/projects/:id/timeline` renders Gantt with gold bars
- [ ] Dependency arrows in cyan, critical path in red
- [ ] Dragging dates updates task and cascades
