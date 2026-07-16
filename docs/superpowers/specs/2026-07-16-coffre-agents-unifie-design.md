# Design unifié — Coffre agents (Vaultwarden) + migration secrets config

> **Date** : 2026-07-16
> **Statut** : design (spec) — v2 post-revue adversariale (NEEDS-REWORK → corrigé). Approbation humaine requise avant tout plan d'exécution.
> **Base architecture** : `docs/plans/PLAN-COFFRE-AGENTS-2026-06-10.md` (Fable) — fact-check `docs/reference/VERIF-COFFRE-AGENTS-2026-06-10.md` (12 claims vérifiés).
> **Origine** : chantier P0-1 du lab Claude (`~/work/ops/claude-code-improvement-lab`) — fuite de secrets en clair, étendu par la demande « Vaultwarden comme coffre + accès quotidien Claude ».
> **Décisions humaines 2026-07-16** : (1) accès = *utiliser sans jamais lire* ; (2) invariant **dégradé assumé** pour les vars que Claude Code lit lui-même ; (3) creds PROD (pg/django) = **retirer les règles allow** (pas de tiering).

---

## 1. Invariants gouvernants (deux régimes — honnêteté requise)

La revue a établi qu'un invariant unique absolu est **infaisable** pour les secrets que Claude Code résout dans son propre process. Deux régimes distincts :

**A. Invariant FORT** (Tier 1 `secret-run` + Tier 2 résolveur) — *secrets utilisés dans des commandes* :
> La valeur n'apparaît **jamais** : ni sur disque en clair, ni dans argv (`ps`), ni dans le contexte LLM (prompt/tool result/transcript). Injectée dans l'env du process enfant uniquement, stdout filtré. Le LLM décide, l'exécuteur détient.

**B. Invariant DÉGRADÉ assumé** (vars lues par Claude Code / hooks **au démarrage**) — clés MCP (`mcp.json ${VAR}`), `TELEGRAM_BOT_TOKEN`/`AF_WEBHOOK_SECRET` des hooks :
> La valeur n'est **plus en clair sur disque** (sortie de Vaultwarden au unlock) MAIS **vit dans l'env de la session** (lisible `/proc/PID/environ` **même-user**). C'est une dégradation explicite : `secret-run` est **structurellement inapplicable** ici (Claude Code résout `${VAR}` au boot des serveurs MCP, avant tout wrapper per-commande). Gain réel = hors-disque + centralisé + rotable + ACL ; **résiduel assumé** = exposition env same-user, réservée aux **tokens renouvelables** (jamais un non-renouvelable).

Décision humaine : régime B accepté pour la sous-classe config, à condition d'étendre les guards (§P2.2) aux vecteurs env-dump.

## 2. Reframe P0-1 (établi cette session, preuves primaires)

La fuite JSONL n'est **pas** une exfiltration externe active :

| Maillon vérifié | Constat |
|---|---|
| `session-analyst.py` | dormant depuis 12 avr, **0 egress** (0 langfuse / 0 loki) dans `src/` — Track A jamais construit |
| n8n `session-complete` | forwarde chemin + métriques, **jamais le contenu** ; pas de nœud Langfuse ; `active:false` |
| spool `ai-memory-worker/index.py` | n'ingère que fichiers repo par `relative_path` ; payload `session_summary` jamais ingéré, `session_file` jamais lu |

⇒ P0-1 réel = **exposition disque locale en clair**. *« Local » ≠ bénin* : creds PROD, `Read(**)` global, subagents qui `cat`, near-miss vault S5. *Résidu R10* : revérifier le node-set live de `session-complete` sur mayi.

## 3. État des lieux (2026-07-16, vérifié)

- **Vaultwarden déjà déployé ET running sur Seko-VPN** : rôle `Seko-VPN/roles/vaultwarden/` complet, `vaultwarden_version: 1.35.1-alpine` **pinné**, `domain_vaultwarden: fongola.ewutelo.cloud`, Caddy `import vpn_only` + `vpn_error_page` (VPN-only confirmé), HSTS/nosniff/SAMEORIGIN. ⚠️ **P0 ne reconstruit PAS l'instance** — il ajoute backup/collections/comptes machine.
- **Backup Vaultwarden = absent** : grep restic/backup sur le rôle = 0 → offsite réellement à faire (P0.3 fondé).
- **Plan Fable jamais exécuté côté VPAI** : 0 rôle `secret-*`, pas de `RUNBOOK-COFFRE-AGENTS.md`, `rbw` absent de waza, absent de `versions.yml`.
- **Doctrine CLI** : `rbw` (Rust, hors npm) pour Tier 1 ; `bw serve` (npm pinné + checksum) uniquement dans le conteneur résolveur Tier 2 — réponse à la compromission `@bitwarden/cli` v2026.4.0 (22/04/2026).

## 4. Architecture cible (reprise Fable)

```
waza (Pi5) — agent SANS secrets       Sese-AI — jobs/services        Seko-VPN — zone coffre (aucun shell agent)
  Claude Code / hooks : refs only        n8n (cred store natif)         Vaultwarden 1.35.1 (running, +backup)
  ├─ secret-run (Tier 1, rbw)            OpenClaw                        └─ RÉSOLVEUR (Tier 2, conteneur)
  ├─ deny-list + secret-guard hook       worker (user dédié)                bw serve 127.0.0.1 (pinné+checksum)
  └─ redactor PostToolUse                 secret-run (Tier 1)               politique.yaml · audit→Loki · actions only
```

| Tier | Secrets | Mécanisme | Régime invariant |
|---|---|---|---|
| **1-cmd** | tokens renouvelables utilisés en **commande** (HF, RUNPOD, PAT, Headscale) | `secret-run <ref> -- <cmd>` (env enfant, jamais argv) | **A (fort)** |
| **1-cfg** | vars lues par Claude Code/hooks au démarrage (clés MCP qdrant/plane/canva/n8n-docs, TELEGRAM_BOT/AF pour hooks) | bootstrap unlock → env de session (Vaultwarden via rbw) | **B (dégradé assumé)** |
| **2** | secrets forts, **non-renouvelables**, logins web | résolveur isolé Seko-VPN, actions only | **A (fort, frontière shell physique)** |
| n8n / LiteLLM | credentials workflows / clés providers | stores natifs (id / virtual keys) | déjà en place — ne rien changer |
| **RETIRÉS** | pwd Postgres PROD partagé, pwd admin Django | **suppression des règles allow** (re-prompt au besoin) | hors coffre — cf §5 |

## 5. Inventaire des secrets en clair sur waza (par secret unique — refait post-revue)

Valeurs **jamais** affichées. Sources vérifiées : `~/.claude/mcp.json`, `~/.claude/settings.json`, `VPAI/.claude/settings.local.json`, `~/.bashrc`, `~/.profile`.

| Secret unique | Emplacement(s) en clair | Destination | Régime |
|---|---|---|---|
| `QDRANT_API_KEY` | mcp.json (env) **+** .bashrc:131 **+** .profile:37 **+** settings.local allow | Vaultwarden `infra-agents` | 1-cfg |
| `TELEGRAM_BOT_TOKEN` | settings.json (env) **+** .bashrc:123 **+** .profile:33 | Vaultwarden `infra-agents` | 1-cfg |
| `STITCH_API_KEY` | mcp.json (env `${VAR}`) **valeur** dans .bashrc:157 | Vaultwarden `infra-agents` | 1-cfg |
| `AF_WEBHOOK_SECRET` | settings.json (env) + settings.json allow (2 règles webhook Telegram) | Vaultwarden `infra-agents` | 1-cfg |
| `NOCODB_TOKEN` | .bashrc:129 + .profile:45 | Vaultwarden `infra-agents` | 1-cmd |
| `MACGYVER_BOT_TOKEN` | .bashrc:132 | Vaultwarden `infra-agents` | 1-cmd |
| `HCLOUD_TOKEN` | .profile:40 | Vaultwarden `infra-agents` | 1-cmd |
| `NAMECHEAP_API_KEY` | .profile:44 | Vaultwarden `infra-agents` | 1-cmd |
| n8n-docs `Authorization` (Bearer) | mcp.json (headers) | Vaultwarden `infra-agents` | 1-cfg |
| canva-connect `x-api-key` | mcp.json (headers) | Vaultwarden `infra-agents` | 1-cfg |
| `PLANE_API_KEY` | mcp.json (env) | Vaultwarden `infra-agents` | 1-cfg |
| `LITELLM_API_KEY` (`sk-lm-…`) | settings.local allow (×3) | Vaultwarden `infra-agents` | 1-cmd (via secret-run env) |
| **pwd Postgres PROD partagé** | settings.local allow:99 | **RETIRÉ** (règles allow supprimées) | — |
| **pwd admin Django** (×2) | settings.local allow:104,106 | **RETIRÉ** (règles allow supprimées) | — |

> **Note attribution (corrige v1)** : le `settings.json` **global** ne contient PAS le pwd Postgres en clair — il le récupère dynamiquement via `docker exec … printenv`. Le pwd PROD littéral est uniquement dans `settings.local.json` (règles allow). Les « 2 » du global = les 2 occurrences du hex webhook Telegram (`AF_WEBHOOK_SECRET`).
> `TELEGRAM_CHAT_ID` (settings.json:9) + canva `connected_account_id` = faible sensibilité, **ignorés volontairement**.

### Mécanique de migration (doc-vérifiée, source citée)

Source : agent `claude-code-guide` sur docs `code.claude.com/docs/en/{mcp,settings,env-vars}.md` (v2.1.x, confidence HIGH sauf où noté).

| Cible | Traitement |
|---|---|
| **mcp.json** (4 littéraux) | → `${VAR}` **inline** (documenté : `headers`/`env`/`url`/`args`/`command`, ex. `Bearer ${VAR}`, `${VAR:-def}`). Var résolue depuis l'env de session (régime 1-cfg). |
| **settings.json** `env` (2) | le bloc `env` **n'interpole PAS** `${VAR}` (littéral only, MEDIUM confidence — à reconfirmer) et **override le shell** → **supprimer les clés** ; valeurs fournies par l'env de session. |
| **settings.json allow** (2) + **settings.local allow** avec secrets | **NE PAS** réécrire en `$VAR` inline (mettrait la valeur en **argv**, visible `ps` — viole l'invariant fort). → soit **retirer** la règle (pg/django : décision humaine), soit router la commande via `secret-run <ref> -- <cmd>` (injection env). Jamais `$VAR` dans une règle allow. |
| **.bashrc / .profile** (7 exports secrets) | **retirer les exports en clair** ; remplacés par le bootstrap unlock (rbw → env de session). Sinon la migration des configs est **cosmétique** pour les 3 valeurs dupliquées (QDRANT/TELEGRAM/STITCH). |

## 6. Séquencement unifié

Ordre strict Fable. Détail des tâches = `PLAN-COFFRE-AGENTS-2026-06-10.md` §P0-P4 (corrigé §7).

| Phase | Contenu | Gate 🔒 |
|---|---|---|
| **P0** | Vaultwarden : **backup restic offsite** (l'instance existe déjà), organisation/collections (`infra-agents`/`strong-secrets`/`canary`), 3 comptes machine, sibling test `rbw` ARM64, item canary. **NE reconstruit PAS l'instance.** | P0.1 export préalable |
| **P1** | Tier 1 : rôle `secret-broker` (rbw + `secret-run` + politique + bootstrap unlock + user séparé) ; **migration** des secrets config + `.bashrc`/`.profile` → refs Vaultwarden ; **suppression** des règles allow pg/django ; puis rotation | P1.3 unlock · P1.5 rotation |
| **P2** | Harness : deny-list `Read(.env*/secrets*/*.pem)`, hook `secret-guard.js` **étendu env-dump** (`env`/`printenv`/`set`/`cat /proc/*/environ` en plus de `rbw get`/`cat` secrets), `redactor.js` PostToolUse, scrubber JSONL batch (chantier (b), les 46 876 existants). **Fin de P2 = set config sécurisé** (les non-renouvelables sont retirés, pas reportés en P3). | — |
| **P3** | Tier 2 : résolveur isolé (`bw serve` pinné, token/agent, rate-limit type Cerberus, politique v2 anti-injection, `run_authenticated_call` MCP, `secure_fill` web) — pour **futurs** secrets forts/logins web | P3.2 politique HITL |
| **P4** | `rotate-secrets.yml` v2 (écrit dans Vaultwarden, `no_log`), alerte intégrité `bw serve`, mode dégradé, test d'intrusion ami (**doit inclure les vecteurs env-dump du régime B**) | P4.4 intrusion |

> **Correction v1** : « quotidien sécurisé dès P2 » ne tient QUE parce que les non-renouvelables (pg/django) sont **retirés** (pas tierés en P3). Sans cette décision, P2 n'aurait pas suffi.

## 7. Ce qui change vs Fable 2026-06-10 (+ post-revue)

1. **Deux régimes d'invariant** (fort / dégradé) au lieu d'un absolu — régime B = admission honnête que `secret-run` n'atteint pas les vars de démarrage Claude Code.
2. **Re-tiering** : pg PROD + django (non-renouvelables) **retirés** (règles allow supprimées), pas mis en Tier 1.
3. **Scope élargi** : `.bashrc`/`.profile` (7 secrets, dont 3 dupliqués config) entrent dans P1.5 — sinon migration cosmétique.
4. **Guards étendus** (P2.2) aux vecteurs env-dump ; le **canary ne couvre PAS** l'env-dump → à documenter.
5. **Anti-argv** : migration allow via `secret-run` env, jamais `$VAR` inline.
6. **Mécanique `${VAR}` doc-sourcée** (claude-code-guide) ; env-block-literal à reconfirmer (MEDIUM).
7. **P0 = backup/collections/comptes**, pas rebuild (instance Seko-VPN existe).
8. **Urgence recalibrée** par le reframe P0-1 (hygiène disque prioritaire, pas incident actif).

## 8. Décisions ouvertes restantes (au plan)

- **O2 — ADR Ansible** (Fable P1.6) : statu quo `ansible-vault` (deploy) + Vaultwarden (runtime agents). À commiter.
- **O3 — rotation P1.5** : les creds passant en Vaultwarden (QDRANT/LITELLM/NOCODB/PAT…) ont vécu en clair → rotation immédiate (Fable P1.5). Note : les creds PROD pg/django ne sont pas concernés (retirés, pas migrés) — leur exposition cesse par suppression des règles.

## 9. Validation & critères de succès (renforcés post-revue)

- **Migration** : `grep -E '(token|secret|key|password)\s*[:=]\s*[A-Za-z0-9]{16,}'` sur **les 5 fichiers** (`mcp.json`, `settings.json`, `settings.local.json`, `.bashrc`, `.profile`) = **0** hors `${VAR}`. *(v1 ne ciblait que 3 fichiers → pouvait passer vert avec .bashrc encore en clair.)*
- **Régime A (fort)** : secret planté → `grep` transcript = **0** occurrence de valeur ; commande hors politique refusée ; jamais dans `ps`/argv.
- **Régime B (dégradé)** : la valeur N'est PAS sur disque en clair ; guard bloque `env`/`printenv`/`set`/`/proc/*/environ` (test : tentative de dump → exit 2 + message). *Assumé* : la valeur reste dans l'env de session — non testable comme « absente ».
- **Guards P2** : bypass `rbw get`/env-dump tenté → bloqué ; secret planté en sortie → `[REDACTED:type]`.
- **P3/P4** : appel authentifié bout-en-bout grep=0 ; test d'intrusion — chaque vecteur (env-dump inclus) bloqué ou détecté.

## 10. Risques résiduels assumés

1. **Régime B env-dump** : un agent shell déterminé same-user peut dumper l'env de session (mitigé : guards P2.2 + user séparé pour les jobs, MAIS la session Claude elle-même porte les vars 1-cfg). **Réservé aux renouvelables** ; rotation = filet. Jamais un non-renouvelable en 1-cfg.
2. **Tier 1 même-user** (cache rbw) : mitigé user séparé + canary + rotation.
3. **Seko-VPN = coffre + backups (SPOF)** : offsite S3 + mode dégradé (Tier 1 continue via cache rbw, Tier 2 fail-closed).
4. **Supply chain bw** : surface = seul conteneur résolveur (pinné + checksum + alerte) ; rbw ailleurs.
5. **Canary aveugle à l'env-dump** : documenté ; ne pas s'en remettre au canary pour le régime B.

## 11. Estimation

Fable : 6-7 sessions, P0→P2 = quotidien sécurisé (grâce au retrait pg/django), P3-P4 = durcissement + futurs secrets forts. Scope (a)+`.bashrc`/`.profile` absorbé dans P1.5/P2 — **possible léger dépassement** vu l'ajout `.bashrc`/`.profile` + extension guards (revu à la hausse vs « pas de session supplémentaire » de v1).
