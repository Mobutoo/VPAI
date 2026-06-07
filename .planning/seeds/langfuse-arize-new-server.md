---
title: Nouveau serveur CX32 — AI Ops (Langfuse + Arize) + bac à sable recette
trigger_condition: Milestone v2026.4 ou décision de démarrer l'observabilité continue
planted_date: 2026-04-12
---

## Idée

Provisionner un **nouveau serveur Hetzner CX32 permanent** qui cumule :
1. **Langfuse** — traces LLM, prompt versioning, datasets, evals
2. **Arize Phoenix** — RAG eval, embedding viz, LLM eval
3. **Bac à sable recette** — accueil des applications en phase de recette (remplace app-prod éphémère)

## Pourquoi ce serveur existe

Le CX32 répond à deux contraintes simultanées :
- Sese-AI (8 GB) est déjà saturé — Langfuse + ClickHouse = surcharge CPU garantie
- L'actuel app-prod (CX22 éphémère) ne peut pas héberger des services permanents

## Ce que ça implique dans le VPAI

### Nouveau groupe d'inventaire

```yaml
# inventory/hosts.yml — nouveau groupe
ai_ops:
  hosts:
    ai-ops-prod:
      ansible_host: "{{ ai_ops_ip }}"
      ansible_port: 804
      ansible_user: "{{ prod_user }}"
```

### Nouveaux rôles Ansible à créer

| Rôle | Description |
|---|---|
| `langfuse` | Langfuse server + ClickHouse + Redis (compose) |
| `arize-phoenix` | Phoenix server + PostgreSQL (compose) |
| `ai-ops-caddy` | Reverse proxy VPN-only pour les deux UIs |

### Nouveau playbook

`playbooks/hosts/ai-ops.yml` — déploiement sur le serveur AI Ops

### Intégration Tailscale

- Serveur rejoint le mesh Tailscale (rôle `headscale-node` existant)
- Arize Phoenix → se connecte au Qdrant de Sese-AI via `100.64.x.x`
- Waza → envoie les traces Langfuse via `ai-ops.ewutelo.cloud` (VPN only)

## Sizing

| Ressource | Minimum | Recommandé |
|---|---|---|
| vCPU | 4 (CX32) | 4–8 |
| RAM | 8 GB | 8 GB (ClickHouse ~2 GB idle) |
| Stockage | 40 GB | 80 GB (traces + ClickHouse data) |
| Coût Hetzner | ~10 €/mois | ~13 €/mois (CX32 + volume) |

## Dépendances

- Langfuse v3+ supporte self-hosted avec ClickHouse
- Arize Phoenix >= 4.x (open source, MIT)
- Qdrant sur Sese-AI accessible via Tailscale (déjà en place)
- `headscale-node` role déployable sur le nouveau serveur (existe déjà)

## Références

- Note complète : `.planning/notes/ai-ops-langfuse-arize-decision.md`
- Langfuse self-hosted docs : https://langfuse.com/docs/deployment/self-host
- Arize Phoenix : https://github.com/Arize-ai/phoenix
