# Palais Phase 8 — Knowledge Graph

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Memoire persistante — noeuds episodiques/semantiques dans PostgreSQL, embeddings dans Qdrant, recherche semantique, graphe visuel interactif, enrichissement retroactif.

**Architecture:** Pattern hybride Zep + A-MEM. Events → noeuds episodiques → extraction LLM → noeuds semantiques + aretes. Embeddings via LiteLLM (text-embedding-3-small, 1536 dims) stockes dans Qdrant collection `palais_memory`.

**Tech Stack:** SvelteKit 5, Qdrant HTTP API, LiteLLM Embeddings, d3-force (graphe), Drizzle ORM

**PRD Reference:** `docs/PRD-PALAIS.md` — Module 2 (Knowledge Graph Temporel)

---

## Task 1: Qdrant Collection Init

**Files:** `src/lib/server/memory/qdrant.ts`

Sur startup: verifier si collection `palais_memory` existe, sinon creer (1536 dims, cosine distance). Client HTTP vers `QDRANT_URL`.

Commit: `feat(palais): Qdrant collection initialization`

## Task 2: Embedding Generation

**Files:** `src/lib/server/memory/embeddings.ts`

```typescript
export async function generateEmbedding(text: string): Promise<number[]> {
  const res = await fetch(`${LITELLM_URL}/v1/embeddings`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${LITELLM_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'text-embedding-3-small', input: text })
  });
  const data = await res.json();
  return data.data[0].embedding;
}
```

Commit: `feat(palais): embedding generation via LiteLLM`

## Task 3: Memory Node CRUD API

- `POST /api/v1/memory/nodes` — create node, generate embedding, upsert in Qdrant
- `GET /api/v1/memory/nodes/:id` — get node with edges
- `POST /api/v1/memory/search` — embed query, search Qdrant top-K, return matching nodes

Commit: `feat(palais): memory nodes CRUD + semantic search API`

## Task 4: Auto-Ingestion from Activity Log

Hook dans `logActivity()` : pour les evenements importants (task completed, error, deployment), creer automatiquement un noeud episodique.

Commit: `feat(palais): auto-ingest activity events as memory nodes`

## Task 5: Semantic Extraction (LLM Triplets)

**Files:** `src/lib/server/memory/extract.ts`

Appeler LiteLLM pour extraire triplets (sujet, relation, objet) d'un noeud episodique. Creer noeuds semantiques + aretes. Prompt: "Extrais les faits cles de cet evenement sous forme de triplets."

Commit: `feat(palais): LLM semantic extraction (triplets)`

## Task 6: Graph Sub-Query API

`GET /api/v1/memory/graph/:entityId` — a partir d'un noeud, traverser les aretes (profondeur 2), retourner sous-graphe.

Commit: `feat(palais): graph traversal API`

## Task 7: Memory UI Page

**Files:** `src/routes/memory/+page.svelte`

```bash
npm install d3-force
```

- Barre de recherche semantique (input → POST /memory/search → resultats)
- Graphe visuel interactif (d3-force : noeuds or, aretes cyan, hover = details)
- Timeline d'evenements (liste chronologique des noeuds episodiques)
- Clic noeud → detail panel avec contenu, relations, metadata

Commit: `feat(palais): memory page with semantic search + visual graph`

## Task 8: Retroactive Enrichment

Quand un nouveau noeud est ajoute : chercher les 5 noeuds les plus similaires dans Qdrant, creer des aretes `related_to` si score > 0.8.

Commit: `feat(palais): retroactive enrichment (A-MEM pattern)`

---

## Verification Checklist

- [ ] Qdrant collection `palais_memory` creee au demarrage
- [ ] Embeddings generes via LiteLLM
- [ ] POST /memory/nodes cree noeud + embedding Qdrant
- [ ] POST /memory/search retourne resultats semantiques
- [ ] Auto-ingestion des events (task completed, errors)
- [ ] Extraction triplets fonctionne
- [ ] `/memory` affiche graphe visuel interactif
- [ ] Enrichissement retroactif cree des aretes automatiques
