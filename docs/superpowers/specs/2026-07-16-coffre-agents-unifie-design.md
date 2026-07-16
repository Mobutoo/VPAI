# Design unifié — Coffre agents (Vaultwarden) + migration secrets config

> **Date** : 2026-07-16
> **Statut** : design (spec) — approbation humaine requise avant tout plan d'exécution.
> **Base architecture** : `docs/plans/PLAN-COFFRE-AGENTS-2026-06-10.md` (Fable) — fact-check `docs/reference/VERIF-COFFRE-AGENTS-2026-06-10.md` (12 claims vérifiés).
> **Origine** : chantier P0-1 du lab Claude (`~/work/ops/claude-code-improvement-lab`) — fuite de secrets en clair, étendu par la demande « Vaultwarden comme coffre + accès quotidien Claude ».

---

## 1. Invariant gouvernant (non négociable)

> **La valeur d'un secret n'apparaît JAMAIS dans le contexte LLM** (prompt, tool result, transcript JSONL). **Le LLM décide, l'exécuteur détient.**

Décision humaine 2026-07-16 : « accès quotidien » = **utiliser sans jamais lire**. Claude lance `secret-run <ref> -- <cmd>` ; la valeur va dans l'env du process enfant, jamais en sortie. Lire le plaintext (`rbw get` → tool result) est **interdit** : ça re-crée exactement la fuite P0-1 qu'on répare. Montrer une valeur à l'humain = canal HITL explicite tracé (différable, Tier 2), jamais automatique.

## 2. Reframe P0-1 (établi cette session, preuves primaires)

La fuite JSONL n'est **pas** une exfiltration externe active — contrairement au cadrage initial du backlog :

| Maillon vérifié | Constat |
|---|---|
| `session-analyst.py` (pipeline nommé dans la note d'avril) | dormant depuis le 12 avr, **0 egress** (0 import langfuse / 0 loki) dans `src/` — Track A Langfuse jamais construit |
| n8n `session-complete` | forwarde chemin + métriques, **jamais le contenu** ; pas de nœud Langfuse ; `active:false` |
| consommateur spool `ai-memory-worker/index.py` | n'ingère que fichiers repo par `relative_path` ; payload `session_summary` (sans `repo`) → jamais ingéré, `session_file` jamais lu |

⇒ P0-1 réel = **exposition disque locale en clair** : (S2) ~11 secrets dans les fichiers de config + (S1) 46 876 dans les transcripts JSONL. *« Local » ≠ bénin* : creds PROD (Postgres/LiteLLM/Qdrant), `Read(**)` global, subagents qui `cat`, near-miss vault S5 → tout agent qui dérive les relit et ça re-rentre dans un JSONL frais.
*Résidu R10 à revérifier* : node-set **live** de `session-complete` sur mayi (MCP n8n session expirée au moment de l'audit).

## 3. État des lieux (2026-07-16)

- **Vaultwarden tourne** sur Seko-VPN : `fongola.ewutelo.cloud`, VPN-only via Caddy (repo `~/work/infra/Seko-VPN`, pas VPAI). Déjà routé (headscale + telegram_bot).
- **Plan Fable = jamais exécuté** : 0 rôle `vaultwarden`/`secret-*` dans VPAI, pas de `RUNBOOK-COFFRE-AGENTS.md`, `rbw` absent de waza, absent de `versions.yml`.
- **Doctrine CLI** (VERIF §CLI) : `rbw` (Rust, hors npm) pour le chemin Tier 1 partout ; `bw serve` (npm pinné + checksum, jamais auto-update) uniquement dans le conteneur résolveur Tier 2 — réponse directe à la compromission `@bitwarden/cli` v2026.4.0 (22/04/2026).

## 4. Architecture cible (reprise Fable, condensée)

```
waza (Pi5) — agent SANS secrets       Sese-AI — jobs/services        Seko-VPN — zone coffre (aucun shell agent)
  Claude Code / hooks : refs only        n8n (cred store natif)         Vaultwarden (IaC, backup restic offsite)
  ├─ secret-run (Tier 1, rbw)            OpenClaw                        └─ RÉSOLVEUR (Tier 2, conteneur)
  ├─ deny-list + secret-guard hook       worker (user dédié)                bw serve 127.0.0.1 (pinné+checksum)
  └─ redactor PostToolUse                 secret-run (Tier 1)               politique.yaml · audit→Loki · actions only
```

| Tier | Secrets | Mécanisme | Garantie |
|---|---|---|---|
| **1** | tokens renouvelables quotidiens (HF, RUNPOD, QDRANT, PAT, Headscale, **+ les 11 secrets config ci-dessous**) | `secret-run` local (rbw) + politique + user séparé + redaction | non-accidentelle (rotation = filet) |
| **2** | secrets forts, logins web, non-renouvelables | résolveur isolé Seko-VPN, actions only | forte (frontière shell physique) |
| n8n / LiteLLM | credentials workflows / clés providers | stores natifs (référence par id / virtual keys) | déjà en place — ne rien changer |

## 5. Intégration du chantier (a) — migration des secrets config

Le chantier (a) du lab (sortir les littéraux des fichiers de config Claude Code) **est la première tranche concrète du Tier 1** de Fable (sa tâche P1.5 + P2.1). Périmètre inventorié (valeurs jamais affichées) :

| Fichier | Littéraux | Traitement (doc-vérifié Claude Code v2.1.x) |
|---|---|---|
| `~/.claude/mcp.json` | n8n-docs `Authorization`, canva `x-api-key`, plane `PLANE_API_KEY`, qdrant `QDRANT_API_KEY` (4) | → `${VAR}` **inline supporté** dans `headers`/`env`/`url`/`args`/`command` (`Bearer ${VAR}`, `${VAR:-def}`) |
| `~/.claude/settings.json` env (2) | `TELEGRAM_BOT_TOKEN`, `AF_WEBHOOK_SECRET` | ⚠️ le bloc `env` **n'interpole pas** `${VAR}` (littéral only) ET override le shell → **supprimer les clés** ; valeurs fournies par l'env shell (peuplé rbw) |
| `~/.claude/settings.json` allow (2) + VPAI `settings.local.json` allow (6) | webhook Telegram, postgres URL pwd, django ×3, telegram hex | `permissions.allow` = **match littéral** (substitution non documentée) → réécrire règle **+** commande en `$VAR` (match littéral `$VAR`↔`$VAR`), smoke-test chacun |

**Mécanique de peuplement de l'env** (résout la contrainte « pas de `.env` natif Claude Code ») : Claude Code hérite de l'env du shell interactif au lancement (prouvé : `STITCH_API_KEY` exporté depuis `~/.bashrc` = SET). Donc :
1. Bootstrap unlock humain (Fable P1.3) : `rbw-agent` déverrouillé au SSH/boot, timeout, jamais de master password sur disque.
2. `secret-run <ref> -- <cmd>` injecte la valeur dans l'env de l'enfant uniquement (jamais argv/`ps`), stdout/stderr filtrés en streaming.
3. Pour les vars que **Claude Code lui-même** doit voir (`${QDRANT_API_KEY}` dans mcp.json résolu au démarrage MCP) : au lieu d'un `secrets.env` statique, un bootstrap exporte depuis Vaultwarden (rbw) dans l'env de la session Claude au unlock. **Décision ouverte O1** ci-dessous.

## 6. Séquencement unifié (P0→P4 Fable, ancré sur le quotidien)

Reprend l'ordre strict de Fable — **le quotidien est sécurisé dès P2**. Détail des tâches = `PLAN-COFFRE-AGENTS-2026-06-10.md` §P0-P4 (inchangé sauf corrections §7).

| Phase | Contenu | Gate humain 🔒 | « (a) » dedans |
|---|---|---|---|
| **P0** | Fondations Vaultwarden : rôle IaC VPAI (image pinnée, VPN-only, backup restic offsite, healthcheck), organisation/collections (`infra-agents`/`strong-secrets`/`canary`), 3 comptes machine, sibling test rbw ARM64, item canary | P0.1 export préalable | — |
| **P1** | Tier 1 : rôle `secret-broker` (rbw + `secret-run` + `politique.yml`), bootstrap unlock, séparation user, **migration des 11 secrets config → refs Vaultwarden** puis rotation | P1.3 design unlock · P1.5 rotation | **cœur de (a)** |
| **P2** | Couches harness : deny-list `Read(.env*/secrets*/*.pem)`, hook `secret-guard.js` (bloque `rbw get`/`cat` secrets), `redactor.js` PostToolUse, scrubber JSONL (batch les 46 876 existants = chantier (b) différé du lab) | — | finalise (a) + (b) |
| **P3** | Tier 2 : résolveur isolé (`bw serve` pinné, token/agent, rate-limit type Cerberus, `politique.yaml` v2 anti-injection, `run_authenticated_call` en MCP, `secure_fill` web) | P3.2 politique HITL | — |
| **P4** | Exploitation : `rotate-secrets.yml` v2 (écrit dans Vaultwarden, `no_log`), alerte intégrité `bw serve`, mode dégradé documenté, test d'intrusion ami | P4.4 validation intrusion | — |

**Rotation** (décision humaine 2026-07-16) : le lab avait choisi « pas de rotation » pour la tranche (a) locale ; **mais** dès que les secrets passent en Vaultwarden (P1.5), Fable impose la rotation immédiate des anciennes valeurs (elles ont vécu en clair). À reconfirmer à P1.5 (gate 🔒).

## 7. Ce qui change vs le plan Fable du 2026-06-10

1. **Cible de (a) précisée** : les 11 secrets des fichiers config Claude Code entrent explicitement dans le périmètre P1.5 (le plan Fable listait pod-ingest/memory-worker/RUNPOD/PAT mais pas mcp.json/settings.json).
2. **Mécanique `${VAR}` doc-vérifiée** (v2.1.x) : settings.json `env` = littéral only (supprimer, pas `${VAR}`) ; `permissions.allow` = match littéral (réécrire les 2 côtés) ; mcp.json inline OK. À intégrer dans P1.5/P2.1.
3. **Urgence recalibrée par le reframe P0-1** : pas d'exfil externe → P0-1 n'est pas un incident actif, c'est de l'hygiène disque prioritaire. Ne change pas le contenu, informe l'ordonnancement (P0→P2 suffit pour clore le risque réel ; P3-P4 = durcissement).
4. **Résidu R10** : revérifier le workflow `session-complete` live (add-on à P2 scrubber).

## 8. Décisions ouvertes (à trancher dans le plan)

- **O1 — peuplement de l'env Claude Code** : (i) bootstrap au unlock qui exporte les N vars config depuis Vaultwarden dans la session (simple, mais les vars vivent en clair dans l'env du process shell le temps de la session) ; (ii) wrapper qui relance Claude Code sous `secret-run` multi-ref. Impact : (i) = env-exposure locale résiduelle (ps/environ same-user), mitigée user séparé + canary ; (ii) plus pur mais plus lourd. *Reco provisoire : (i) pour les refs Tier 1 renouvelables, cohérent avec le risque résiduel #1 assumé de Fable.*
- **O2 — ADR Ansible** (Fable P1.6) : statu quo `ansible-vault` (deploy) + Vaultwarden (runtime agents), un seul système par usage. À commiter en ADR.
- **O3 — rotation P1.5** : confirmer la rotation des 11 (creds PROD Postgres/LiteLLM/Qdrant) au moment du passage en Vaultwarden.

## 9. Validation & critères de succès

- **(a)/P1.5** : `grep -E '(token|secret|key|password)\s*[:=]\s*[A-Za-z0-9]{16,}'` sur mcp.json/settings.json/settings.local.json = **0** hors `${VAR}`/`$VAR` ; smoke : serveur MCP qdrant résout via rbw-bootstrap ; hook `session-memory-writer` voit `AF_WEBHOOK_SECRET`.
- **Invariant** : `grep` sur un transcript de session = **0** occurrence de valeur de secret (test avec secret planté).
- **P2** : secret planté dans une sortie simulée → `[REDACTED:type]` ; bypass `rbw get` tenté → bloqué + message « utilise secret-run ».
- **P3** : appel API authentifié bout-en-bout, grep transcript = 0 ; token A ne résout pas les refs de B.
- **P4** : test d'intrusion — chaque vecteur (env, ps, bypass wrapper) bloqué ou détecté (canary/audit).

## 10. Risques résiduels assumés (Fable + session)

1. **Tier 1 même-user** : agent shell déterminé sur waza peut viser le cache rbw de son user → mitigé user séparé + canary + rotation ; non-renouvelables interdits en Tier 1.
2. **Seko-VPN = coffre + backups (SPOF)** : compensé offsite S3 + mode dégradé (Tier 1 continue via cache rbw chiffré, Tier 2 fail-closed).
3. **Supply chain bw** : surface réduite au seul conteneur résolveur (pinné + checksum + alerte) ; rbw partout ailleurs.
4. **O1 (i) env-exposure** : les vars config vivent en clair dans l'env de la session le temps de son unlock — accepté pour les refs renouvelables Tier 1, à ne jamais utiliser pour des non-renouvelables.

## 11. Estimation

Fable : 6-7 sessions, ordre strict P0→P1→P2 (quotidien sécurisé dès P2), P3 après, P4 clôture. La tranche (a) est absorbée dans P1.5/P2.1 — pas de session supplémentaire.
