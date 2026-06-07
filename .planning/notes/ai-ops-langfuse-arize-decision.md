---
title: Décision architecture AI Ops — Langfuse + Arize Phoenix
date: 2026-04-12
context: Exploration session — amélioration continue des prompts Claude Code
---

## Décision

Ajouter Langfuse et Arize Phoenix au cycle d'amélioration continue des prompts.
Ces outils transforment l'audit ponctuel (session-analyst) en observabilité **en continu**.

## Contexte existant

### Ce qui tourne déjà

| Composant | Rôle | Localisation |
|---|---|---|
| `ai-memory-worker` | Indexe les repos git dans Qdrant (mémoire sémantique) | Waza (local) |
| Qdrant `memory_v1` | Stockage vecteurs — REX, configs, codebase | Sese-AI |
| `session-analyst` | Audit ponctuel des sessions JSONL Claude Code | Waza (scripts Python) |
| Hook memory search (R0) | Recherche Qdrant automatique au SessionStart | Waza (hooks CC) |
| ULTIMATE-CONFIG couches 0–5 | Hooks préprocesseur, bash-lint, error-escalator… | En cours d'implémentation |

### Ce qui manque : observabilité continue

L'audit ponctuel (2,240 sessions → 77M tokens perdus) est réactif.
Langfuse + Arize rendent le cycle **proactif** : chaque session devient une trace exploitable.

## Rôle de chaque outil

### Langfuse
- **Traces** : chaque session Claude Code → span Langfuse avec tokens, coût, latence
- **Prompt versioning** : comparer les effets de chaque changement CLAUDE.md / hooks
- **Datasets** : ingérer les sessions JSONL comme datasets d'évaluation annotés
- **Evals** : mesurer la qualité des réponses dans le temps (avant/après un hook)

### Arize Phoenix
- **RAG eval** : évaluer la qualité de ce que Qdrant retourne (pertinence mémoire)
- **Embedding viz** : visualiser les clusters dans `memory_v1` — voir si la mémoire est bien organisée
- **LLM eval** : hallucination detection, faithfulness, relevance sur les traces

### Intégration dans le mesh Tailscale
- Langfuse + Arize sur nouveau serveur CX32 (`ai-ops.ewutelo.cloud` ou similaire)
- Qdrant reste sur Sese-AI — Arize s'y connecte via VPN Tailscale
- Prompts et CLAUDE.md sur Waza — traces envoyées au CX32 via VPN

## Serveur cible

**Nouveau CX32 permanent** (pas l'actuel app-prod éphémère).

Ce serveur cumule deux rôles :
1. **AI Ops** (permanent) : Langfuse + Arize Phoenix + leurs dépendances (ClickHouse, PostgreSQL, Redis)
2. **Bac à sable recette** (semi-permanent) : remplace l'actuel app-prod éphémère pour la recette des applications

Sizing minimum recommandé : **CX32 (4 vCPU / 8 GB RAM)** — ClickHouse seul consomme ~2 GB sous charge.
Budget estimé : ~10–13 €/mois (Hetzner).

## Stack technique Langfuse (self-hosted)

- Langfuse server (Docker)
- ClickHouse (backend analytics — heavy CPU mais episodique)
- PostgreSQL (metadata — peut partager l'instance du bac à sable si isolée)
- Redis (queue)

## Next step

Voir seed `langfuse-arize-new-server.md` pour la phase Ansible associée.
