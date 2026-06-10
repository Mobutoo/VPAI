# Audit stratégique VPAI — 2026-06-10

> Méthode : 4 subagents d'audit (vision, qualité Ansible, couche IA/mémoire, ops/sécu) + 1 benchmark état de l'art juin 2026 (web, sources citées). Constats vérifiés par lecture directe quand critiques.
> Audits précédents : `docs/audits/2026-04-09-vpai-repo-audit.md`, `2026-04-11-vpai-repo-audit-v2.md`, `2026-05-29-infra-audit.md`.

---

## 1. Verdict exécutif

| Dimension | Score | Tendance |
|---|---|---|
| Couche IA/mémoire (RAG v3, R0 continu, LOI) | **9/10** | ↑ état de l'art self-hosted |
| Qualité Ansible (FQCN, idempotence, CI integration) | 8/10 | → solide, dette ciblée |
| Hardening prod (VPN-only, CVE pinning, CrowdSec) | 8/10 | → très bon |
| Monitoring infra | 7/10 | → bon mais réactif |
| Backups | **4/10** | ⚠ Zerobyte non-IaC, drill jamais fait |
| Observabilité LLM / éval continue | **3/10** | ⚠ Phase 10 planifiée depuis avril, 0 déployé |
| Gouvernance repo (scope, hygiène, README) | **3/10** | ⚠ 4/5 recos audit avril non faites |
| Résilience (SPOF) | 5/10 | → fixes incidents déployés, SPOF structurels restent |

**Position** : la couche mémoire agentique (hybrid BM25+RRF mesuré par éval golden, hooks R0 continu, LOI 12 règles, REX systématiques) est **déjà au niveau ou au-dessus de l'état de l'art self-hosted juin 2026** — c'est l'actif différenciant du projet. Ce qui empêche VPAI d'être "meilleur de sa catégorie" : (a) la boucle de mesure n'est pas fermée (zéro trace LLM, zéro éval continue en prod), (b) l'opérationnel ne tient pas la promesse (backups non testés, Zerobyte manuel), (c) le repo croît sans gouvernance (66 rôles, 53 binaires racine, README mensonger).

---

## 2. But & philosophie (constatés)

**But** : infrastructure IA personnelle souveraine, 3 nœuds (Sese-AI OVH = brain, Seko-VPN Ionos = hub/backup, Waza Pi5 = workstation+mémoire), pilotable et opérée par agents IA, VPN-only, à coût plancher.

Principes directeurs réellement appliqués :
- **VPN-first** : zéro service public (exception assumée : CouchDB Obsidian).
- **Tout-Ansible** : idempotence vérifiée en CI (2e run changed=0).
- **Frugal au repos, éphémère au burst** : VPS 8GB + RunPod GPU à la demande + budget LiteLLM. *Jamais formalisé comme doctrine — devrait l'être.*
- **Le repo est le cerveau exécutif** : REX, STATE.md, LOI, mémoire RAG. L'IA est citoyenne du système, pas un outil externe.
- **Mesure avant croyance** (récent) : harness éval golden 76 q, gates de parité bf16/fp32.

---

## 3. Constats critiques (vérifiés)

### C1 — Budget IA : cap effectif $10/jour, pas $5
`inventory/group_vars/all/main.yml:201` = `10.00` override `roles/litellm/defaults/main.yml:27` = `5.00`. Le CLAUDE.md annonce $5. Aucune alerte Grafana sur `litellm_spend_*` (dashboards seulement).

### C2 — Secrets
- `playbooks/ops/rotate-secrets.yml` (~l.66-83) : `debug` affiche tous les nouveaux secrets en clair (logs CI inclus), sans `no_log`.
- Tokens providers IA (anthropic, openai, openrouter, gemini) hors périmètre du playbook de rotation.
- Restes mémoire : HF/QDRANT/RUNPOD tokens + Headscale/PAT à roter (gate humain, jamais fait).
- `PRD.md` et `.vault_password` : **gitignorés, non trackés** (vérifié `git check-ignore`) — credentials en clair sur disque uniquement. Risque résiduel local acceptable, mais aucun garde-fou pre-commit/CI ne l'atteste.

### C3 — Backups non prouvés
- Zerobyte (orchestrateur Restic) configuré **manuellement** sur Seko-VPN — perte Seko-VPN = reconstruction backup à la main.
- Restore drill prescrit mensuel dans `docs/DISASTER-RECOVERY.md`, **jamais attesté**, playbook interactif non automatisable tel quel.
- 3-2-1 incomplet : NAS absent (2 copies). Heartbeat conditionnel silencieux si URL absente du vault.
- Précédent : pg_dumps vides ~3 mois (audit 2026-05-29) — exactement le scénario qu'un drill aurait détecté.

### C4 — Observabilité LLM = 0 déployé
Phase 10 AI Ops (Langfuse, juge LLM, traces sessions) : planifiée complète depuis 2026-04-12 (`.planning/phases/10-ai-ops/`), **zéro déploiement**. Conséquence : aucune trace, aucun coût par session, aucune éval continue — la qualité du RAG v3 n'est mesurée que manuellement. Prérequis sécurité : scrubber credentials JSONL (`.planning/notes/security-jsonl-credentials-leak.md`) **avant** toute ingestion.

### C5 — Gouvernance repo en échec
Audit 2026-04-09 : 5 recommandations, **1 réalisée** (STRUCTURE.md). Depuis : 66 rôles (16 prévus au PRD), 53 binaires à la racine (PNG/xlsx/msg/pdf, repo 862M), `FS/` hors-sujet, `scripts/` mélange infra et debug jetable, `README.md` annonce "16 Molecule-tested roles" + référence `docs/FIRST-DEPLOY.md` inexistant. Aucun mécanisme de décommission.

### C6 — Conformité aux propres règles CLAUDE.md (quantifié)
| Règle | État |
|---|---|
| FQCN | ✅ 0 violation / 66 rôles |
| `changed_when` | 2 violations (`llamaindex-memory-worker`, `penpot`) |
| `set -euo pipefail` | 10 rôles en violation (15 blocs/58) — dont `hardening` |
| Tags `[role, phaseN]` dans tasks | 38 rôles sans tag (fonctionnel via site.yml — règle à amender ou appliquer) |
| Images pinnées | 1 `:latest` prod : `roles/opencut/templates/docker-compose-opencut.yml.j2:48` ; CI `check-no-latest` ne scanne pas les templates |
| Log rotation | 3 templates sans (`docker-stack` infra, `penpot`, `story-engine`) |
| `state: restarted` interdit | 1 violation (`roles/penpot/tasks/main.yml:208`) |

### C7 — Résilience
- SPOF assumés : Sese-AI (tout le brain), Seko-VPN (backup+supervision externe), Waza (toute la couche mémoire : worker, MCP search, éval).
- Fixes incidents déployés (disk-guard, OOM-shield, net-watchdog) MAIS `OOMScoreAdjust=-900` **inactif jusqu'au restart** de networkd/tailscaled sur waza.
- Caddy waza `2.11.2` ≠ prod `2.11.3` → CVE-2026-30851/30852 non patchées côté Pi (`versions.yml:83`).
- Orphelins MCP `mcp_search.py` non reapés (REX 2026-06-07) ; run worker 30h passé inaperçu (REX 2026-06-10) — pas d'alerte durée.
- Alerting réactif : disk à 90% (= seuil HARD disk-guard, trop tard), pas d'alerte RAM dédiée waza (l'incident OOM du 06-05 serait passé sous le radar).

### C8 — Couche IA : 4 chantiers prêts mais dormants
| Chantier | État | Gain attendu |
|---|---|---|
| Reranker bge-reranker-v2-m3 ONNX int8 | code prêt (`scripts/memory/rerank.py`), modèle absent du cache HF → no-op | +5–10 pts recall@1, effort 30 min |
| `--boost-usage` (use_count × récence) | codé, off — données s'accumulent depuis le 06-10 | activer ~J+14 |
| Graphe de connaissances (varflow Ansible, multi-hop) | spec complète `docs/superpowers/specs/2026-06-07-memory-graph-layer-design.md`, **0 ligne de code** | analyse d'impact var→rôle→service |
| Topics portables cross-projet (Phase 6a/6b) | spec `2026-06-08-topics-portables-cross-projet.md` — **P6 livré le 06-08** selon mémoire projet ; vérifier périmètre restant 6b golden-set vivant | R0 partout |

---

## 4. Ce qui manque pour être le meilleur de la catégorie (juin 2026)

Benchmark (sources vérifiées : OTEL GenAI semconv, Langfuse MIT, Zep/Graphiti 63.8% LongMemEval, OWASP LLM Top 10 2025, MCP sous Linux Foundation) :

### I1 — Fermer la boucle de mesure (le gap #1)
Le meilleur projet de la catégorie **mesure tout** : traces LLM par session, coût par requête, éval RAG continue avec alerte sur régression. VPAI a déjà le harness golden et Grafana — il manque le branchement.
→ Langfuse self-hosted (MIT, ~300MB RAM) ou OpenLLMetry → Alloy/Grafana existant (zéro nouveau service, spans `gen_ai.*`/`mcp.*`). Éval golden en cron hebdo → métriques VictoriaMetrics → alerte si r@1 régresse > 2 pts.

### I2 — Policy engine pour agents (OWASP "Excessive Agency")
Les agents (n8n, OpenClaw, sessions autonomes) exécutent des actions destructives sans couche décisionnelle. Pattern 2026 : plan-then-execute + policy engine.
→ OPA minimal (ARM64 OK) : actions à risque (restart, delete, deploy) passent par une règle `deny unless approval_token`, audit trail JSON structuré dans Loki (déjà déployé). C'est l'extension naturelle de la LOI : **la LOI devient exécutable côté serveur**, pas seulement côté hooks Claude.

### I3 — Auto-remédiation gardée
Alerte Grafana → workflow n8n → LLM analyse le log → action parmi {restart, alert, rien} si confiance haute → trace auditée. MTTR mesuré. Les briques existent toutes (Grafana, n8n, LiteLLM, Telegram) — c'est un assemblage, pas un développement.

### I4 — Mémoire temporelle / épisodique
memory_v3 est sémantique pur, append-only, `valid_to` jamais renseigné. Les faits à durée de vie ("LiteLLM rollback jusqu'à X", "budget épuisé J+3") polluent ou manquent.
→ Option légère : renseigner `valid_to` + decay au ranking. Option lourde : Graphiti (Zep OSS) par-dessus Postgres existant — à évaluer seulement après la couche graphe maison (spec déjà écrite, ne pas doubler).

### I5 — Golden set vivant
76 questions statiques → enrichissement automatique depuis les requêtes R0 réelles (`r0-golden-candidates.jsonl` déjà prévu par `r0-marker.js`, non exploité). Transforme l'éval en capteur de dérive réel.

### I6 — Entrées multimodales zéro coût
Whisper.cpp sur Pi (ARM64 natif) : notes vocales → transcription locale → ingestion mémoire. Différenciant, coût nul.

### I7 — Future-proof protocoles
Agent Card A2A (`/.well-known/agent.json` derrière Caddy, fichier statique) + spans OTEL `mcp.*` sur n8n-mcp. Effort quasi nul, positionne la stack sur les standards qui gagnent.

### I8 — Doctrine écrite
Formaliser en 1 page la philosophie constatée (§2) : "frugal au repos / éphémère au burst", "le repo est le cerveau", "mesure avant croyance", "VPN-first". C'est le contrat qui gouverne les arbitrages de scope — son absence est la cause racine de C5.

---

## 5. Plan

Plan exécutable détaillé (vagues, tâches, fichiers, critères de done, modèle d'exécution Opus) : **`docs/plans/PLAN-2026-06-10-BEST-IN-CLASS.md`**.

Séquence : V0 sécurité/quick-wins → V1 hygiène repo → V2 conformité Ansible → V3 backups/résilience prouvés → V4 boucle de mesure IA → V5 innovations agentiques. V0–V2 sont des préalables de crédibilité ; V4 est le levier "meilleur de la catégorie".
