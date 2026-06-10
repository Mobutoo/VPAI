# PLAN — VPAI best-in-class (juin 2026)

> Exécutable par session Opus (orchestrateur) + subagents sonnet[1m] (R6 : chemins, pas contenu).
> Source : `docs/audits/2026-06-10-audit-strategique-vpai.md` (constats C1–C8, idées I1–I8).
> Règles : LOI R0–R11, checklist `docs/standards/ANSIBLE-ROLE-CHECKLIST.md`, lint avant deploy, atomic commits.
> Convention : chaque vague = 1 à 3 sessions, gate de sortie vérifiable avant la suivante. Gates humains marqués 🔒.

---

## V0 — Sécurité & quick wins (1 session, ~3h)

| # | Tâche | Fichiers | Done quand |
|---|---|---|---|
| 0.1 | Trancher budget IA : aligner $5 (ou documenter $10) | `inventory/group_vars/all/main.yml:201`, CLAUDE.md §Budget | valeurs identiques inventory/defaults/CLAUDE.md |
| 0.2 | `rotate-secrets.yml` : supprimer `debug` secrets clair → écriture fichier local `no_log: true` | `playbooks/ops/rotate-secrets.yml` (~l.66-83) | aucun secret dans stdout (`ansible-playbook --check` témoin) |
| 0.3 | Alerte Grafana budget LiteLLM (warn 70%, crit 90% sur `litellm_spend_*`) | `roles/monitoring/templates/grafana/provisioning/alerting.yaml.j2` | règle visible Grafana + test fire |
| 0.4 | Alertes : disk warn 75% Sese, RAM waza dédiée (filtre `instance`, seuil 75%) | idem | 2 règles provisionnées |
| 0.5 | Fix `:latest` opencut → var dans versions.yml | `roles/opencut/templates/docker-compose-opencut.yml.j2:48`, `inventory/group_vars/all/versions.yml` | grep `:latest` templates = 0 |
| 0.6 | Caddy waza 2.11.2→2.11.3 (CVE-2026-30851/52) | `versions.yml:83` | container waza sur 2.11.3 |
| 0.7 | Activer OOMScoreAdjust waza : restart conditionnel networkd/tailscaled (séquencé, ne pas couper SSH — restart tailscaled APRÈS networkd, via `systemd-run --on-active=5s` si besoin) | `roles/workstation-common/tasks/main.yml` (~l.264-342) | `systemctl show -p OOMScoreAdjust systemd-networkd` = -900 live |
| 0.8 | Pre-commit/CI guard : fail si `.vault_password`, `PRD.md` ou vault non chiffré staged | `.github/workflows/ci.yml` + hook pre-commit | test négatif passe |
| 0.9 | Reaper MCP orphelins au SessionStart (`pkill -f mcp_search.py` + sleep 1) | `~/.claude/hooks/memory-search-start.sh` | plus d'orphelin >1h (vérif `ps etime`) |
| 0.10 | Alerte durée worker : `duration_seconds` dans rapport webhook + règle n8n >2h → Telegram (R1 : validate_workflow avant import) | `roles/llamaindex-memory-worker/templates/run-and-report.sh.j2`, workflow n8n memory-run-report | alerte test reçue |

**Gate V0** : `make lint` vert, deploy ciblé (`make deploy-role ROLE=monitoring ENV=prod` + workstation), alertes visibles, commit atomiques.

---

## V1 — Hygiène repo & vérité documentaire (1 session, ~2h)

| # | Tâche | Done quand |
|---|---|---|
| 1.1 | Déplacer 53 binaires racine (PNG/xlsx/pdf/msg, fichier `200`) → `docs/evidence/2026-Q2/` ou suppression si jetables ; `.gitignore` racine pour `*.png *.xlsx *.pdf *.msg` | `ls` racine = code+docs seulement |
| 1.2 | 🔒 `FS/` (flash-studio) : proposer extraction vers `~/work/saas/` (MANIFESTE-CREATION-PROJET) — décision humaine | décision actée dans le commit msg |
| 1.3 | `scripts/` : séparer infra (`scripts/`) vs debug jetable (`.planning/scripts/` ou rm) | `ls scripts/` lisible, scripts infra seuls |
| 1.4 | README véridique : ce que le repo est vraiment (3 nœuds, 66 rôles, mémoire agentique), retirer "16 Molecule-tested", retirer réf `FIRST-DEPLOY.md` | zéro claim invérifiable |
| 1.5 | Écrire `docs/DOCTRINE.md` (1 page, I8) : VPN-first, frugal/burst, repo=cerveau, mesure avant croyance + règle de scope (tout nouveau rôle exige une entrée décommission ou une justification) | doc commitée, liée depuis README+CLAUDE.md |
| 1.6 | 🔒 Décommission : lister rôles jamais déployés (netbox, penpot, grapesjs, openpencil…) → proposer archive `attic/` branche dédiée — décision humaine | liste + décision actée |

**Gate V1** : repo < 100M hors .git (ou justifié), README honnête, doctrine commitée.

---

## V2 — Conformité Ansible (1-2 sessions)

| # | Tâche | Cibles | Done quand |
|---|---|---|---|
| 2.1 | `set -euo pipefail` sur 15 blocs restants (prio `hardening`, `docker-stack`) | content-factory-provision, docker-stack×3, hardening, obsidian, plane-provision, headscale-node, openclaw, app-factory-provision, kitsu-provision | grep audit = 0 violation |
| 2.2 | `changed_when` manquants | `roles/llamaindex-memory-worker/tasks/main.yml`, `roles/penpot/tasks/main.yml` | 0 violation |
| 2.3 | `penpot` : `state: restarted` → `present` + `recreate: always` | `roles/penpot/tasks/main.yml:208` | conforme |
| 2.4 | Log rotation 3 templates | `docker-stack/templates/docker-compose-infra.yml.j2`, `penpot/...`, `story-engine/...` | grep logging = présent |
| 2.5 | CI `check-no-latest` étendu à `roles/*/templates/**/*.j2` | `.github/workflows/ci.yml` | CI rouge si `:latest` template |
| 2.6 | Pinner images Molecule (`geerlingguy/...:latest` → tag fixe) | 16 `molecule.yml` | 0 `:latest` molecule |
| 2.7 | Trancher règle tags : soit amender CLAUDE.md ("tags au niveau site.yml suffisent"), soit script d'ajout sur 38 rôles | CLAUDE.md ou roles/* | règle et réalité alignées |
| 2.8 | `meta/main.yml` minimal sur 24 rôles (script généré) | roles/* | 0 manquant |

**Gate V2** : `make lint` vert, CI integration dimanche verte (idempotence 2e run), 2e run local changed=0 sur rôles touchés.

---

## V3 — Backups & résilience prouvés (2 sessions)

| # | Tâche | Done quand |
|---|---|---|
| 3.1 | Zerobyte → IaC : exporter jobs/schedules/creds S3 dans vault + rôle `zerobyte` (ou bootstrap API) sur Seko-VPN | redéploiement Seko-VPN restaure les jobs sans UI |
| 3.2 | Restore drill automatisé : variante non-interactive de `backup-restore.yml` (`--extra-vars`) → restore vers container éphémère → vérif row counts pg + collections Qdrant → rapport | drill exécuté avec succès, rapport dans `docs/evidence/` |
| 3.3 | Drill mensuel planifié : workflow GitHub Actions cron (pattern `integration.yml`, CX22 éphémère) ou timer Seko-VPN | 1er run planifié vert |
| 3.4 | Heartbeat backup obligatoire : fail explicite si `backup_heartbeat_url` absent (plus de `default('')` silencieux) + moniteur Kuma | backup raté = alerte <24h |
| 3.5 | Uptime Kuma idempotent via API depuis `roles/uptime-config` | moniteurs recréés par playbook |
| 3.6 | Snapshot Qdrant robuste : parse JSON (`python3 -c`/`jq`) au lieu de grep, fail si vide | snapshot vérifié dans pre-backup |
| 3.7 | 🔒 Rotation tokens : HF, QDRANT, RUNPOD, Headscale, GITHUB_PAT + étendre `rotate-secrets.yml` aux providers IA | rotation faite + playbook couvre providers |
| 3.8 | Test parité config worker : `test_memory_core.py` vérifie `defaults/main.yml` ≡ constantes `memory_core.py` (CHUNK_SIZE etc.) | test en CI |

**Gate V3** : un restore complet prouvé par drill, backup silencieusement raté impossible, Seko-VPN reconstructible par playbook.

---

## V4 — Fermer la boucle de mesure IA (3-4 sessions) — **le levier best-in-class**

| # | Tâche | Done quand |
|---|---|---|
| 4.1 | Reranker : exporter bge-reranker-v2-m3 ONNX int8 → `HF_HOME` waza ; éval golden avant/après | delta recall@1 mesuré ; si ≥ +3 pts → `--rerank` défaut |
| 4.2 | Éval continue : timer hebdo harness golden → push métriques (r@1, r@5, MRR) VictoriaMetrics → alerte Grafana si r@1 régresse >2 pts | métriques visibles, alerte testée |
| 4.3 | Golden set vivant : exploiter `~/.claude/r0-golden-candidates.jsonl` → revue semi-auto → enrichir `scripts/memory/eval/golden.yml` (cible 150+ q dont code/config/cross-repo) | golden ≥150 q, pipeline documenté |
| 4.4 | 🔒 Scrubber credentials JSONL (préalable absolu à 4.5) — spec `.planning/notes/security-jsonl-credentials-leak.md` | test : JSONL avec secrets plantés → 100% scrubés |
| 4.5 | Phase 10 Track A : Langfuse self-hosted (compose Sese, rôle Ansible, MIT) OU OpenLLMetry→Alloy (option zéro-service, trancher via sibling test R4) ; instrumenter LiteLLM | traces + coût/session visibles dashboard |
| 4.6 | Activer `--boost-usage` (≥ J+14 après 2026-06-10, use_count accumulé) + éval avant/après | delta mesuré, décision actée |
| 4.7 | Graphe P1 : `scripts/memory/graph/` varflow Ansible (var→rôle→service) + `graph_query.py` — spec `docs/superpowers/specs/2026-06-07-memory-graph-layer-design.md` ; gate P4 (−50% tokens sur questions d'impact) avant d'investir plus | requête multi-hop répond juste sur 10 cas tests |
| 4.8 | Consolidation REX cross-repo : `consolidate_rex.py` lit `docs/rex/` des 20 repos découverts | synthèses cross-repo générées |
| 4.9 | `valid_to` + decay : invalidation des docs obsolètes au ranking (mémoire temporelle légère, I4 option A) | docs expirés démotés, éval sans régression |

**Gate V4** : régression RAG détectable automatiquement <7j ; coût et qualité par session visibles ; reranker statué chiffres à l'appui.

---

## V5 — Agentique avancée (2-3 sessions, après V4)

| # | Tâche | Done quand |
|---|---|---|
| 5.1 | OPA policy engine (ARM64/VPS) : actions destructives n8n/OpenClaw (restart, delete, deploy) → `deny unless approval_token` + audit JSON → Loki. La LOI devient exécutable serveur. | action non approuvée bloquée + tracée |
| 5.2 | Auto-remédiation gardée : alerte Grafana → n8n → LLM (LiteLLM) classe {restart, alert, rien} → exécution si confiance >0.85 ET policy OPA OK → REX auto. Périmètre initial : container crash-loop uniquement. (R1 validate avant import) | 1 incident simulé auto-remédié + audité |
| 5.3 | Whisper.cpp waza : notes vocales → transcription → `~/work/.../notes/` → ingestion mémoire auto | note vocale retrouvable via R0 <1h |
| 5.4 | OTEL spans `mcp.*`/`gen_ai.*` sur n8n-mcp → Alloy/Grafana | latence/erreurs par outil MCP visibles |
| 5.5 | Agent Card A2A : `/.well-known/agent.json` statique derrière Caddy (VPN-only) | curl VPN renvoie la card |
| 5.6 | 🔒 Évaluer Graphiti/Zep vs graphe maison APRÈS gate 4.7 P4 — ne pas doubler | décision écrite (ADR) |

**Gate V5** : 1 boucle auto-remédiation complète prouvée, zéro action destructive non auditée.

---

## Modèle d'exécution (pour la session Opus)

1. **Par vague** : R0 topics concernés → `TaskCreate` par tâche → exécuter via subagents sonnet[1m] (chemins, pas contenu) → vérif Opus → commits atomiques → gate.
2. **Jamais** : deploy sans `make lint` ; import n8n sans `validate_workflow` (R1) ; 2 tâches d'infra prod en parallèle sur le même hôte.
3. **Gates humains 🔒** : 1.2, 1.6, 3.7, 4.4 (validation scrubber), 5.6 — bloquer et demander.
4. **Compaction** : fin de chaque vague = écrire état dans `.planning/STATE.md` + `/compact`.
5. **Mesure** : toute modif RAG passe par le harness éval avant/après (baseline `.planning/eval/`).
6. **Estimation totale** : 10-15 sessions. V0+V1 immédiat ; V2 mécanique ; V3 avant tout nouveau service ; V4 = différenciation ; V5 = couronnement.
