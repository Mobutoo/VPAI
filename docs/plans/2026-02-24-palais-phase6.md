# Palais Phase 6 — Time Tracking & Livrables

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Timer auto/manuel sur les taches, compteur d'iterations, analytics projet (post-mortem), upload livrables avec liens de telechargement.

**Architecture:** Timers geres server-side (time_entries table). Iterations detectees au changement de statut. Livrables stockes dans `/data/deliverables/` avec token UUID pour download public.

**Tech Stack:** SvelteKit 5, Drizzle ORM, multipart upload, crypto.randomUUID

**PRD Reference:** `docs/PRD-PALAIS.md` — Modules 6 (Time Tracking) + 7 (Livrables)

---

## Task 1: Auto Timer (start on in-progress, stop on done)

Hook dans la route `PUT /api/v1/tasks/:id` : quand `status` change vers `in-progress`, creer `time_entry` (type auto). Quand status → `review`/`done`, fermer le time_entry ouvert.

Commit: `feat(palais): auto timer on task status change`

## Task 2: Manual Timer API

- `POST /api/v1/tasks/:id/timer/start` — cree time_entry manual
- `POST /api/v1/tasks/:id/timer/stop` — ferme time_entry, calcule duration
- `GET /api/v1/tasks/:id/time-entries` — liste entries

Commit: `feat(palais): manual timer API`

## Task 3: Timer UI Component

Bouton start/stop/pause sur les cartes tache. Affiche duree en cours (compteur live cote client).

Commit: `feat(palais): timer UI component on task cards`

## Task 4: Iteration Counter

Detecter dans `PUT /api/v1/tasks/:id` quand une tache passe de `done` → `in-progress`. Creer `task_iteration` avec numero incremente.

Commit: `feat(palais): iteration counter on task reopen`

## Task 5: Project Analytics Page

**Files:** `src/routes/projects/[id]/analytics/+page.svelte`

Affiche: temps total, temps par phase (duree dans chaque colonne), nombre iterations, cout total, graphique estime vs reel, top 3 taches couteuses, ratio cout/iteration.

Commit: `feat(palais): project analytics page`

## Task 6: Post-Mortem Auto

Quand projet passe en `Done` : generer rapport via LiteLLM (resume, stats, lecons), stocker comme noeud memoire Knowledge Graph, envoyer webhook n8n pour Telegram.

Commit: `feat(palais): auto post-mortem on project completion`

## Task 7: Deliverables Upload API

- `POST /api/v1/tasks/:id/deliverables` — multipart file upload
- `GET /api/v1/tasks/:id/deliverables` — list
- `GET /api/v1/projects/:id/deliverables` — list all for project

Stockage: `/data/deliverables/projects/<slug>/<task_id>/<filename>`. Token UUID genere pour chaque fichier.

Commit: `feat(palais): deliverables upload API (multipart)`

## Task 8: Download Endpoint

`GET /dl/:token` — lookup deliverable by download_token, stream file. Pas d'auth requise (token = auth).

Commit: `feat(palais): deliverable download endpoint /dl/:token`

## Task 9: Deliverables Gallery Page

`src/routes/projects/[id]/deliverables/+page.svelte` — galerie avec preview inline (images, PDF embed, markdown render). Drag & drop upload zone.

Commit: `feat(palais): deliverables gallery with inline preview`

---

## Verification Checklist

- [ ] Timer auto demarre quand tache → in-progress
- [ ] Timer auto s'arrete quand tache → done
- [ ] Timer manuel start/stop fonctionne
- [ ] Iteration incrementee quand tache done → in-progress
- [ ] `/projects/:id/analytics` affiche stats completes
- [ ] Upload fichier via API fonctionne
- [ ] `/dl/:token` telecharge le fichier
- [ ] Galerie affiche previews images/PDF
