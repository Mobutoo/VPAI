# Palais Phase 7 — Budget Intelligence

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Dashboard budget avec jauge journaliere, tracking double source (LiteLLM + providers directs), scheduling budget-aware, prediction burn rate.

**Architecture:** Cron server-side (setInterval) pour pull LiteLLM spend toutes les 15min et providers APIs toutes les 1h. Donnees stockees dans budget_snapshots. Forecast calcule en temps-reel.

**Tech Stack:** SvelteKit 5, LiteLLM API, OpenAI/OpenRouter/Anthropic Usage APIs, Drizzle ORM

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 8 (Budget Intelligence)

---

## Task 1: LiteLLM Spend Integration

**Files:** `src/lib/server/budget/litellm.ts`

Fetch `GET /global/spend/report` et `/spend/logs` depuis LiteLLM. Parser et stocker dans `budget_snapshots` (source: `litellm`).

Commit: `feat(palais): LiteLLM spend data fetching`

## Task 2: Direct Provider Tracking

**Files:** `src/lib/server/budget/providers.ts`

- OpenAI: `GET /v1/organization/usage/completions`
- OpenRouter: `GET /api/v1/auth/key` (credits restants)
- Anthropic: Usage API si disponible

Delta = cout provider - cout LiteLLM = appels directs. Stocker dans `budget_snapshots` (source: `*_direct`).

Commit: `feat(palais): direct provider usage tracking`

## Task 3: Budget Cron Jobs

**Files:** `src/lib/server/budget/cron.ts`

Sur startup serveur: `setInterval(fetchLiteLLMSpend, 15 * 60 * 1000)` et `setInterval(fetchProviderUsage, 60 * 60 * 1000)`. Initialiser dans hooks.server.ts.

Commit: `feat(palais): budget cron jobs (15min LiteLLM, 1h providers)`

## Task 4: Budget API Endpoints

- `GET /api/v1/budget/summary` — total today, by source, remaining
- `GET /api/v1/budget/by-agent` — spend per agent
- `GET /api/v1/budget/by-provider` — spend per provider
- `GET /api/v1/budget/forecast` — predicted exhaustion time

Commit: `feat(palais): budget REST API endpoints`

## Task 5: Budget Dashboard Page

**Files:** `src/routes/budget/+page.svelte`

- Jauge circulaire (arc SVG, remplissage dore, $spent/$5 daily limit)
- "Via LiteLLM: $X | Direct: $Y | Total: $Z"
- By-agent breakdown (bar chart)
- By-provider breakdown (pie/donut)
- 30-day history (line chart)
- Burn rate prediction ("Budget epuise a ~16:45")
- Eco mode toggle button (webhook n8n)

Commit: `feat(palais): budget dashboard with gauges and charts`

## Task 6: Budget-Aware Scheduler

**Files:** `src/routes/api/v1/budget/schedule/+server.ts`

POST: receives pending tasks list, returns prioritized order by ratio priorite/cout. Suggests which tasks to run now vs defer based on remaining budget.

Commit: `feat(palais): budget-aware task scheduler`

## Task 7: Cost Badges on Tasks

Add estimated_cost and actual_cost display on TaskCard component. Color: green if actual < estimated, red if over.

Commit: `feat(palais): cost badges on task cards`

---

## Verification Checklist

- [ ] LiteLLM spend data fetched and stored
- [ ] Provider direct costs fetched (at least OpenRouter)
- [ ] `/api/v1/budget/summary` returns correct totals
- [ ] Budget dashboard renders gauge + charts
- [ ] "Via LiteLLM / Direct / Total" display correct
- [ ] Burn rate prediction shown
- [ ] Eco mode toggle triggers n8n webhook
- [ ] Scheduler returns prioritized task list
