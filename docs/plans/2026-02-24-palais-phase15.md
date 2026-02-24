# Palais Phase 15 — War Room

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Vue immersive War Room pour les missions complexes — layout split VPS/Pi, timeline live, budget decompte, feed agrege multi-noeud, boutons d'action rapide.

**Architecture:** Activable sur les missions avec 5+ taches paralleles. Combine SSE (events agents) + polling (ComfyUI, health) dans une vue unifiee. Pas de nouveau backend — aggrege les APIs existantes.

**Tech Stack:** SvelteKit 5, SSE, Custom SVG timeline, Drizzle ORM

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 14 (War Room)

---

## Task 1: War Room Route + Layout

**Files:**
- Create: `roles/palais/files/app/src/routes/missions/[id]/warroom/+page.svelte`
- Create: `roles/palais/files/app/src/routes/missions/[id]/warroom/+page.server.ts`

Layout split en 4 zones (CSS Grid) :

```
┌──────────────┬──────────────────────────┐
│  AGENTS VPS  │  OUTILS PI               │
│  (zone 1)    │  (zone 2)                │
├──────────────┴──────────────────────────┤
│  TIMELINE LIVE (zone 3)                  │
├──────────────────────────────────────────┤
│  FEED TEMPS-REEL (zone 4)               │
└──────────────────────────────────────────┘
```

Server load : charger la mission + taches + agents assignes + budget du jour.

```css
.warroom-grid {
  display: grid;
  grid-template-columns: 1fr 2fr;
  grid-template-rows: 1fr 80px auto;
  height: 100vh;
  background: var(--palais-bg);
}
```

Commit: `feat(palais): War Room layout with 4-zone grid`

## Task 2: Zone 1 — Agents VPS

**Files:**
- Modify: `roles/palais/files/app/src/routes/missions/[id]/warroom/+page.svelte`

Colonne gauche : liste des agents VPS assignes a la mission.

Chaque agent :
- Avatar + nom
- Barre de progression (tokens consommes / estimation)
- Status : `idle` (gris), `busy` (pulse or), `error` (rouge)
- Tache en cours (titre tronque)

Connecte au SSE pour update live des statuts.

```svelte
{#each vpsAgents as agent}
  <div class="agent-card" class:busy={agent.status === 'busy'} class:error={agent.status === 'error'}>
    <img src={agent.avatarUrl} alt={agent.name} class="avatar" />
    <div class="agent-info">
      <span class="name">{agent.name}</span>
      <div class="progress-bar">
        <div class="fill" style="width: {agent.progressPercent}%"></div>
      </div>
      <span class="task-name">{agent.currentTaskTitle ?? 'idle'}</span>
    </div>
  </div>
{/each}
```

Commit: `feat(palais): War Room zone 1 — VPS agents live status`

## Task 3: Zone 2 — Outils Pi

**Files:**
- Modify: `roles/palais/files/app/src/routes/missions/[id]/warroom/+page.svelte`

Colonne droite : status des outils sur le Pi.

- **ComfyUI** : nombre d'images en queue/completees, preview derniere image
- **Remotion** : status rendering (idle/rendering/done), progression si en cours
- **Claude Code** : session active ou idle, derniere action

Polling toutes les 10s vers les APIs respectives (via Palais backend qui proxy).

Commit: `feat(palais): War Room zone 2 — Pi tools status`

## Task 4: Zone 3 — Timeline Live Mission

**Files:**
- Modify: `roles/palais/files/app/src/routes/missions/[id]/warroom/+page.svelte`

Barre de progression horizontale :
- Barre doree remplie selon % taches completees
- Texte : `XX% complete | Budget: $X.XX/$5.00`
- Par-tache mini-barres en dessous (chaque tache = segment colore selon status)
- Budget live : se met a jour via SSE quand un agent consomme des tokens

```svelte
<div class="timeline-bar">
  <div class="progress" style="width: {mission.progressPercent}%"></div>
  <span class="label">
    {mission.progressPercent}% complete | Budget: ${budgetSpent.toFixed(2)}/${budgetLimit.toFixed(2)}
  </span>
</div>
<div class="task-segments">
  {#each missionTasks as task}
    <div class="segment" class:done={task.status === 'done'} class:active={task.status === 'in-progress'}
         style="width: {100 / missionTasks.length}%">
    </div>
  {/each}
</div>
```

Commit: `feat(palais): War Room zone 3 — live timeline + budget`

## Task 5: Zone 4 — Feed Temps-Reel

**Files:**
- Modify: `roles/palais/files/app/src/routes/missions/[id]/warroom/+page.svelte`

Feed scrollable d'evenements en temps-reel, filtre par la mission :
- Chaque event : timestamp + agent avatar + action + lien preview
- Sources : SSE events (agent activity) + polling (ComfyUI completions)
- Auto-scroll vers le bas, pause si l'utilisateur scroll up

```svelte
<div class="feed" bind:this={feedContainer}>
  {#each events as event}
    <div class="event-row">
      <time>{formatTime(event.timestamp)}</time>
      <img src={event.agentAvatar} class="mini-avatar" />
      <span class="action">{event.description}</span>
      {#if event.previewUrl}
        <a href={event.previewUrl} class="preview-link">[preview]</a>
      {/if}
    </div>
  {/each}
</div>
```

Commit: `feat(palais): War Room zone 4 — real-time activity feed`

## Task 6: Boutons d'Action Rapide

**Files:**
- Modify: `roles/palais/files/app/src/routes/missions/[id]/warroom/+page.svelte`

Barre d'actions en haut a droite :

- **[Pause Mission]** : met toutes les taches `in-progress` en `paused`, notifie agents
- **[Reassigner]** : ouvre un modal pour reassigner une tache stuck a un autre agent
- **[Eco Mode]** : toggle eco mode via webhook n8n `budget-control`
- **[Escalader]** : cree un insight `critical` + notification Telegram

Chaque bouton appelle l'API Palais correspondante.

```svelte
<div class="action-bar">
  <button class="btn-war" onclick={() => pauseMission()}>Pause Mission</button>
  <button class="btn-war" onclick={() => showReassignModal = true}>Reassigner</button>
  <button class="btn-war" class:active={ecoMode} onclick={() => toggleEcoMode()}>
    Eco Mode {ecoMode ? 'ON' : 'OFF'}
  </button>
  <button class="btn-war btn-danger" onclick={() => escalate()}>Escalader</button>
</div>
```

Commit: `feat(palais): War Room action buttons (pause, reassign, eco, escalate)`

## Task 7: Declenchement Automatique War Room

**Files:**
- Modify: `roles/palais/files/app/src/routes/missions/[id]/+page.svelte`

Quand une mission a 5+ taches paralleles (taches `in-progress` simultanees) :
- Afficher un banner : "Mission complexe detectee — [Ouvrir War Room]"
- Le bouton navigue vers `/missions/:id/warroom`

Detection cote server dans le load function :
```typescript
const parallelTasks = missionTasks.filter(t => t.status === 'in-progress');
const suggestWarRoom = parallelTasks.length >= 5;
```

Commit: `feat(palais): auto-suggest War Room on complex missions`

---

## Verification Checklist

- [ ] Layout War Room 4 zones responsive
- [ ] Agents VPS avec status live (SSE)
- [ ] Outils Pi avec status (polling)
- [ ] Timeline live avec % progression + budget
- [ ] Feed temps-reel avec auto-scroll
- [ ] Bouton Pause met les taches en pause
- [ ] Bouton Eco Mode toggle via webhook
- [ ] Bouton Escalader cree insight + Telegram
- [ ] Suggestion War Room quand 5+ taches paralleles
