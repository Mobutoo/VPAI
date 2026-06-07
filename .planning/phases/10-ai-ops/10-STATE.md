# Phase 10: AI Ops — État de planification

**Date:** 2026-04-12
**Statut:** Spec Track B complète — prête pour `/gsd-plan-phase 10 --skip-research`
**Artefact clé :** `.planning/phases/10-ai-ops/10-TRACK-B-SPEC.md` (destinations 1-7, scrubber sécurité, 3 plans B1/B2/B3)

---

## Architecture finale — Deux tracks parallèles, zéro nouveau serveur obligatoire

```
SessionStop hook (ULTIMATE-CONFIG Couche 5)
  → session-analyst.py (enhanced)
      ├── Track A → Langfuse Python SDK → Langfuse Cloud (free, 50k traces/mois)
      ├── Track B → NocoDB table claude_sessions (rétention long terme)
      ├── Track B → VictoriaMetrics remote write → Grafana dashboard
      ├── Track B → Loki HTTP push (logs structurés) → Grafana Explore
      ├── Track B → OTLP → Alloy → Tempo (Sese-AI monitoring stack) → Grafana trace viewer
      ├── Track B → Qdrant sessions_v1 → recherche sémantique sessions
      └── Track B → n8n webhook → LiteLLM juge qualité → score → NocoDB + Telegram

Gitea webhook (push CLAUDE.md/hooks) → n8n → sha → NocoDB + Langfuse metadata
OpenClaw skill session-stats → query NocoDB/VictoriaMetrics → réponse Telegram
```

**Track C (optionnel)** : Langfuse self-hosted sur CX32/Oracle — déclenché uniquement si rétention 30j bloquante ou confidentialité problématique. Décision après 4 semaines de données réelles.

---

## Décisions validées (immuables pour le planning)

| Décision | Validé par |
|----------|-----------|
| SessionStop hook = déclencheur unique (pas inotify, pas cron) | Advisor ULTRATHINK |
| Langfuse Cloud free tier d'abord (0€, 50k traces/mois) | Advisor ULTRATHINK |
| Loki (déjà en stack) pour timeline — pas Tempo | Analyse stack existante |
| LiteLLM = juge qualité (pas capturer les appels) | Advisor ULTRATHINK |
| Arize Phoenix = hors scope Phase 10 | Research + Advisor |
| Nouveau serveur = optionnel (Track C seulement) | Advisor ULTRATHINK |
| NocoDB pour stockage long terme (remplace rétention 30j Cloud) | Architecture session |
| git sha CLAUDE.md injecté comme metadata Langfuse | Advisor ULTRATHINK |
| Périmètre sessions = 8 projets Waza (pas seulement VPAI) | Spec Track B 2026-04-12 |
| `git_sha_hooks` = git log local sur `~/.claude` — pas de webhook Gitea | Spec Track B 2026-04-12 |
| Repo `claude-config` sur Gitea (privé) — CLAUDE.md + hooks + skills + workers | Spec Track B 2026-04-12 |
| Token Gitea : UI `git.ewutelo.cloud` ou `docker exec gitea` sur Seko-VPN | Spec Track B 2026-04-12 |
| Scrubber sécurité obligatoire avant toute ingestion texte libre | `.planning/notes/security-jsonl-credentials-leak.md` |

---

## Artefacts à jour

| Fichier | Statut |
|---------|--------|
| `.planning/REQUIREMENTS.md` — AIOPS-01 à AIOPS-09 réécrits | ✅ À jour |
| `.planning/ROADMAP.md` — Phase 10 goal révisé | ✅ À jour |
| `.planning/phases/10-ai-ops/10-CONTEXT.md` | ⚠️ À mettre à jour (reflète l'ancienne archi CX32) |
| `.planning/phases/10-ai-ops/10-RESEARCH.md` | ⚠️ Garde-fous actifs (voir ci-dessous) |

---

## Garde-fous RESEARCH.md (inchangés)

1. **Langfuse SDK version** — `langfuse==4.2.0` / "API v4 OpenTelemetry" potentiellement confabulé (knowledge cutoff août 2025). Vérifier via `pip index versions langfuse` au moment de l'implémentation.
2. **ClickHouse low-memory tuning** — source blog 2024 (`jamesoclaire.com`). Vérifier via doc officielle ClickHouse si Track C se déclenche.
3. **Versions images Docker** — `3.68.0`, `24.3` ClickHouse — confirmer sur Docker Hub au déploiement.

> Ces garde-fous s'appliquent uniquement si Track C (self-hosted) se déclenche. Pour Track A+B, le SDK version est la seule donnée critique à vérifier.

---

## Décisions architecture supplémentaires (2026-04-12 session 2)

| Décision | Valeur |
|----------|--------|
| SessionStop stdin | À vérifier via hook debug avant code (test 2min) |
| Score qualité | Option A local (axes 1-3, 0-10) pendant 30j, puis hybride LLM |
| Coach mode | Option C semi-auto : génération async + smoke test 14j + activation si précision > 70% |
| Méta-qualité coach | 3 dimensions : cohérence immédiate + validité J+7 + human_rating Telegram |
| Table `coach_log` | 10 champs dont `baseline_rate`, `outcome_delta`, `human_rating` |
| Qdrant `prompt_patterns_v1` | Séparé de `sessions_v1` — activé après 50 paires, pas au Plan 10-B1 |
| Cache refresh `team-patterns.json` | Option C async (thread daemon) + cron @reboot fallback |
| Token Gitea | À créer manuellement — nom: `waza-session-analyst`, scope: `read:repository` |
| Repo `claude-config` | À créer sur Gitea (privé) — contenu: ~/.claude/ (CLAUDE.md, hooks/, skills/) |

## Infra à créer avant déploiement

- [ ] Token Gitea `waza-session-analyst` (user: créer via UI git.ewutelo.cloud)
- [ ] Repo Gitea `claude-config` (privé, init avec ~/.claude/)
- [ ] NocoDB table `claude_sessions` (TABLE_ID requis dans config)
- [ ] NocoDB table `prompt_improvements` (TABLE_ID requis dans config)
- [ ] NocoDB table `coach_log` (TABLE_ID requis dans config)

## Pour reprendre

```bash
# Prérequis : token Gitea + TABLE_IDs NocoDB (pas bloquants pour le planning)
# 1. Mettre à jour CONTEXT.md (nouvelle archi Track A+B/C)
# 2. Lancer le planner
#    /gsd-plan-phase 10 --skip-research
#
# Le planner produit 3 plans :
#   10-01 : session-analyst enhanced + scrubber + score local axes 1-3
#   10-02 : NocoDB + VictoriaMetrics + Loki push (Track B stockage/métriques)
#   10-03 : n8n coach quality + Grafana dashboard + alertes Telegram + coach_log
```
