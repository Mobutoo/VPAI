# Palais Phase 9 — Observabilite LLM

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Traces d'execution LLM depliables (arbre de spans), score de confiance, badges presence agent sur Kanban. Inspire Langfuse.

**Architecture:** Spans ingeres depuis sessions OpenClaw (via WS events ou polling). Arbre parent-child dans `agent_spans`. Confiance calculee depuis metriques spans.

**Tech Stack:** SvelteKit 5, Drizzle ORM, Custom SVG tree

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 1 (agent_spans) + Module 9

---

## Task 1: Span Ingestion

Enrichir le WebSocket handler (`src/lib/server/ws/openclaw.ts`) pour capturer les events `span.*` et inserer dans `agent_spans` table. Chaque span a un `parent_span_id` pour construire l'arbre.

Commit: `feat(palais): span ingestion from OpenClaw sessions`

## Task 2: Spans API

`GET /api/v1/agents/:id/sessions/:sid/spans` — retourne arbre de spans pour une session. Format: array plat avec parent_span_id, le client reconstruit l'arbre.

Commit: `feat(palais): spans tree API endpoint`

## Task 3: Trace Detail Page

**Files:** `src/routes/agents/[id]/traces/[sid]/+page.svelte`

Arbre depliable: chaque span montre type (icone), name, model, tokens_in/out, cost, duration_ms. Couleurs: llm_call = cyan, tool_call = gold, decision = ambre, delegation = green. Erreurs en rouge.

Style holographique: fond sombre, lignes de connexion en dashed cyan, glow sur le span selectionne.

Commit: `feat(palais): trace detail page with collapsible span tree`

## Task 4: Confidence Score Calculation

Apres session completee: calculer score depuis metriques (ratio erreurs, tokens utilises vs estimation, nombre retries). Stocker dans `agent_sessions.confidence_score` et propager vers `tasks.confidence_score`.

Commit: `feat(palais): confidence score calculation`

## Task 5: Confidence + Presence Badges on Kanban

Enrichir `TaskCard.svelte`:
- Badge confiance: cercle colore (vert > 0.8, orange 0.5-0.8, rouge < 0.5)
- Presence: si un agent travaille activement (session running), afficher indicateur pulse

Commit: `feat(palais): confidence + presence badges on Kanban cards`

## Task 6: Agent Performance Metrics

Enrichir la page agent detail: ajouter section metriques — tokens/$ par tache (moyenne), modeles utilises (breakdown), qualite moyenne, tendance 30j.

Commit: `feat(palais): agent performance metrics section`

---

## Verification Checklist

- [ ] Spans inseres dans DB depuis events WS
- [ ] API retourne arbre de spans pour une session
- [ ] `/agents/:id/traces/:sid` affiche arbre depliable
- [ ] Chaque span montre model, tokens, cost, duration
- [ ] Confidence score calcule et affiche
- [ ] Badge confiance visible sur Kanban cards
- [ ] Presence agent visible quand session running
