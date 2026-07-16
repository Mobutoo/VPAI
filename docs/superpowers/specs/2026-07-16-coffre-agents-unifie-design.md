# Design unifié — Coffre agents (Vaultwarden) + migration secrets config

> **Date** : 2026-07-16 · **Statut** : design v3 (2 passes de revue adversariale foldées). Approbation humaine requise avant tout plan d'exécution.
> **Base** : `docs/plans/PLAN-COFFRE-AGENTS-2026-06-10.md` (Fable) + fact-check `docs/reference/VERIF-COFFRE-AGENTS-2026-06-10.md`.
> **Origine** : chantier P0-1 du lab Claude — fuite de secrets en clair, étendu par « Vaultwarden coffre + accès quotidien ».
> **Détecteur de validation prouvé** : `scripts/secrets-migration-check.sh` (self-test = 19 violations sur l'état actuel = non-aveugle).
>
> **Décisions humaines 2026-07-16** : (1) accès = *utiliser sans jamais lire* ; (2) **split par classe** de secret (pas par coffre) ; (3) creds PROD pg/django = **retirer les règles allow** ; (4) contrôle du régime dégradé = **redacteur en sortie**, pas blocklist.

---

## 1. Principe directeur — split par CLASSE de secret

Le discriminant (établi par revue) : **ce secret peut-il être injecté par-commande, ou doit-il persister dans l'env de session pour la durée de vie d'un serveur ?**

| Classe | Contrainte physique | Store | Garantie |
|---|---|---|---|
| **A — secret de commande** (renouvelable, utilisé dans une commande discrète) | injectable dans l'env d'un **process enfant transitoire** (jamais session, jamais argv, jamais contexte) | **Vaultwarden** via `secret-run <ref> -- <cmd>` | **FORTE** — « utiliser sans lire » réellement atteignable |
| **B — var de démarrage** (clés MCP `${VAR}`, env des hooks) | **doit persister dans l'env de la session** pour que les serveurs MCP bootent et restent authentifiés → **dumpable same-user** (`echo $VAR`) *quel que soit le coffre* | **`.env` 600 local** (headless-safe), refs `${VAR}` dans les configs | **DÉGRADÉE assumée** — hors-disque-clair + centralisé, MAIS valeur en env de session ; contrôle réel = **redacteur en sortie** (pas un guard) |
| **C — secret fort / non-renouvelable** (futurs logins web, secrets non rotables) | résolveur hors-machine, actions only | **Vaultwarden Tier 2** (Seko-VPN) | **FORTE** (frontière shell physique) |
| **RETIRÉS** | pwd Postgres PROD partagé, pwd admin Django | **suppression des règles allow** | exposition cesse par retrait |

> **Pourquoi Vaultwarden n'aide PAS la classe B** : Claude Code résout `${VAR}` **au boot des serveurs MCP, depuis l'env hérité au lancement de `claude`** — avant tout unlock/wrapper. Un unlock non-interactif exigerait un secret bootstrap en clair (600) = on échange N clairs contre 1 + coffre, **sans gain** pour la classe B (toujours dumpable same-user). De plus le CLAUDE.md tourne en **mode autonome headless** : pas d'humain pour `rbw unlock` par session. Donc classe B = `.env` 600 local, sourcé **avant** `claude` (bashrc interactif / `EnvironmentFile=` systemd). **Vaultwarden reste le coffre quotidien** des secrets que Claude *utilise* (classes A et C).

## 2. Reframe P0-1 (preuves primaires, cette session)

Pas d'exfiltration externe active : `session-analyst.py` dormant + 0 egress ; n8n `session-complete` forwarde chemin+métriques jamais le contenu ; spool `index.py` n'ingère que fichiers repo par `relative_path`. ⇒ P0-1 = **exposition disque locale en clair**. *Résidu R10* : revérifier `session-complete` live sur mayi.

## 3. État des lieux (vérifié)

- **Vaultwarden déployé + running Seko-VPN** : `roles/vaultwarden/`, `1.35.1-alpine` pinné, `fongola.ewutelo.cloud`, Caddy VPN-only. **P0 ne reconstruit PAS l'instance** (backup/collections/comptes seulement). Backup restic = **absent** (à faire).
- **Plan Fable jamais exécuté** côté VPAI (0 rôle `secret-*`, `rbw` absent, pas dans `versions.yml`).
- **Doctrine CLI** : `rbw` (Rust) pour Tier 1 ; `bw serve` (pinné+checksum) uniquement conteneur résolveur Tier 2 (compromission `@bitwarden/cli` 22/04/2026).

## 4. Inventaire des secrets en clair sur waza (par secret unique, vérifié)

Valeurs **jamais** affichées. 5 fichiers scannés. *(dups corrigés post-revue : dups shell↔shell réels = TELEGRAM/QDRANT/NOCODB ; STITCH = dépendance config→shell `mcp.json ${STITCH}` ← `.bashrc:157`.)*

| Secret | Emplacement(s) clair | Classe → Destination |
|---|---|---|
| `QDRANT_API_KEY` | mcp.json env + .bashrc:131 + .profile:37 + settings.local allow | **B** → `.env` 600 + `${VAR}` mcp.json (le serveur MCP qdrant en a besoin au boot) |
| `TELEGRAM_BOT_TOKEN` | settings.json env + .bashrc:123 + .profile:33 | **B** → `.env` 600 (hooks) ; supprimé du bloc settings.json.env |
| `AF_WEBHOOK_SECRET` | settings.json env + settings.json allow (×2) | **B** → `.env` 600 (hook session-memory-writer) |
| `STITCH_API_KEY` | valeur dans .bashrc:157 (mcp.json déjà `${VAR}`) | **B** → `.env` 600 |
| n8n-docs `Authorization` | mcp.json headers | **B** → `${VAR}` mcp.json + `.env` 600 |
| canva-connect `x-api-key` | mcp.json headers | **B** → `${VAR}` mcp.json + `.env` 600 |
| `PLANE_API_KEY` | mcp.json env | **B** → `${VAR}` mcp.json + `.env` 600 |
| `NOCODB_TOKEN` | .bashrc:129 + .profile:45 | **A** → Vaultwarden, `secret-run` (usage commande) |
| `MACGYVER_BOT_TOKEN` | .bashrc:132 | **A** → Vaultwarden, `secret-run` |
| `HCLOUD_TOKEN` | .profile:40 | **A** → Vaultwarden, `secret-run` |
| `NAMECHEAP_API_KEY` | .profile:44 | **A** → Vaultwarden, `secret-run` |
| `LITELLM_API_KEY` (`sk-lm-…`) | settings.local allow (×3) | **A** → Vaultwarden, `secret-run` env (jamais `$VAR` argv) |
| **pwd Postgres PROD** | settings.local allow:99 | **RETIRÉ** (règle supprimée) |
| **pwd admin Django** (×2) | settings.local allow:104,106 | **RETIRÉ** (règles supprimées) |

> **Attribution** : `settings.json` **global** ne contient AUCUN littéral pg — il le récupère via `docker exec … printenv`. Le pg littéral est uniquement dans `settings.local.json:99`.

### Mécanique de migration (doc-sourcée : agent `claude-code-guide` sur `code.claude.com/docs`, v2.1.x)

- **mcp.json** : `${VAR}` **inline supporté** (headers/env/url/args/command, ex. `Bearer ${VAR}`). Résolu depuis l'env de session (classe B).
- **settings.json `env`** : n'interpole PAS `${VAR}` (littéral only, MEDIUM confidence — à reconfirmer) + override le shell → **supprimer les clés** ; valeurs via env de session.
- **allow rules à secret** : **jamais** `$VAR` inline (→ argv, `ps`, viole l'invariant fort) → **retirer** (pg/django) ou router via `secret-run` (LITELLM).
- **.bashrc/.profile** : retirer les exports en clair ; classe B rapatriée dans `~/.config/claude/secrets.env` (600) sourcé `set -a; . …; set +a` **avant** `claude` ; classe A supprimée (passe par `secret-run`).

## 5. Contrôle du régime B (dégradé) — redacteur, pas guard

Décision humaine : une blocklist de commandes (`env`/`printenv`/`echo $VAR`/`python -c os.environ`/`declare -p`…) est **contournable à l'infini** (même classe de faiblesse que le bug bash-lint). Donc :
- **Contrôle réel = `redactor.js` PostToolUse** : attrape la **valeur** (regex types + valeurs exactes chargées depuis le `.env` 600) dans TOUTE sortie d'outil → `[REDACTED:type]` avant entrée en contexte, quel que soit le vecteur de dump.
- **Guard `secret-guard.js` = ralentisseur anti-accident** seulement (bloque `cat` de fichiers secrets, `rbw get`) — explicitement PAS un rempart contre un agent same-user déterminé.
- **Résiduel honnête** : la valeur classe B vit dans l'env de session ; un agent same-user déterminé peut la dumper — mitigé par redacteur (sortie) + rotation, **pas** par le guard. Réservé aux **renouvelables**.

## 6. Séquencement unifié

| Phase | Contenu | Gate 🔒 |
|---|---|---|
| **P0** | Vaultwarden : **backup restic offsite** (instance existe), collections (`infra-agents`/`strong-secrets`/`canary`), comptes machine, sibling test `rbw` ARM64, canary. NE reconstruit PAS. | P0.1 export |
| **P1a (classe B, quotidien)** | `~/.config/claude/secrets.env` 600 ; sourcing avant `claude` (bashrc + `EnvironmentFile=` si systemd) ; migrer mcp.json→`${VAR}`, supprimer clés settings.json.env, retirer exports .bashrc/.profile classe B, **retirer** allow pg/django ; gate `secrets-migration-check.sh` = 0 violation | — |
| **P1b (classe A)** | rôle `secret-broker` (rbw + `secret-run` + politique + user séparé) ; migrer NOCODB/MACGYVER/HCLOUD/NAMECHEAP/LITELLM → Vaultwarden ; rotation des migrés | P1.3 unlock · P1.5 rotation |
| **P2** | `redactor.js` (contrôle régime B) + `secret-guard.js` (ralentisseur) + deny-list `Read(.env*/secrets*/*.pem)` + scrubber JSONL batch (chantier (b), 46 876 existants) | — |
| **P3** | Tier 2 (classe C) : résolveur isolé `bw serve` pinné, token/agent, rate-limit type Cerberus, politique v2 anti-injection, `run_authenticated_call` MCP, `secure_fill` web | P3.2 HITL |
| **P4** | `rotate-secrets.yml` v2 (écrit Vaultwarden, `no_log`), alerte intégrité, mode dégradé, test d'intrusion (**inclut vecteurs env-dump régime B → doit être attrapé par le redacteur, pas le guard**) | P4.4 intrusion |

> **« Quotidien sécurisé »** : atteint à **P1a+P2** (classe B hors-clair + redacteur) et P1b (classe A dans le coffre). Les non-renouvelables sont **retirés** (pas reportés en P3).

## 7. Ce qui change vs Fable + vs v1/v2

1. **Split par classe** (A/B/C) — B ne va PAS dans Vaultwarden (headless + inapplicabilité secret-run), va en `.env` 600.
2. **pg/django retirés** (règles allow supprimées), pas tierés.
3. **Scope .bashrc/.profile** (7 secrets, dups TELEGRAM/QDRANT/NOCODB) dans P1.
4. **Détecteur redésigné + prouvé** (`secrets-migration-check.sh`, self-test 19 violations) — remplace le grep §9 non-fonctionnel des v1/v2.
5. **Redacteur = contrôle régime B** ; guard rétrogradé en ralentisseur ; canary aveugle à l'env-dump documenté.
6. **Ordre résolu** : classe B sourcée avant `claude` (bashrc/`EnvironmentFile`), pas d'unlock par session ; Vaultwarden unlock concerne uniquement classes A/C.
7. **P0 = backup/collections/comptes**, pas rebuild (instance Seko-VPN existe).

## 8. Décisions ouvertes (au plan)

- **O2 — ADR Ansible** : `ansible-vault` (deploy) + Vaultwarden (runtime agents A/C). À commiter.
- **O3 — rotation** : classe A migrée en Vaultwarden a vécu en clair → rotation (P1.5). Classe B : rotation optionnelle (reste local ; a aussi vécu en clair — recommandé de roter QDRANT/TELEGRAM au passage).
- **O4 — sourcing headless** : confirmer le mode de lancement réel de `claude` (interactif bashrc vs systemd `EnvironmentFile`) pour câbler le sourcing du `.env` 600 avant boot MCP.

## 9. Validation & critères de succès (renforcés + prouvés)

- **Migration** : `scripts/secrets-migration-check.sh` → **0 violation** (allowlist + assert `${VAR}`/absent). **Contrôle positif** : `--self-test` doit trouver ≥1 violation sur l'état pré-migration (prouvé : 19). *(Remplace le grep de forme v1/v2 qui passait faux-vert sur l'état 100% en clair.)*
- **Classe A (fort)** : secret planté → `grep` transcript = 0 ; jamais dans `ps`/argv ; commande hors politique refusée.
- **Classe B (dégradé)** : `.env` 600 (perms vérifiées) ; **redacteur** attrape la valeur dans une sortie plantée (test : `echo $VAR` simulé → `[REDACTED]`) — c'est LE critère, pas l'absence en env (non atteignable).
- **P3/P4** : appel authentifié bout-en-bout grep=0 ; intrusion — chaque vecteur (env-dump inclus) attrapé (redacteur) ou détecté (audit).

## 10. Risques résiduels assumés

1. **Classe B env-dump same-user** : valeur en env de session, dumpable ; mitigé **redacteur (sortie) + rotation**, PAS guard. Renouvelables uniquement.
2. **`.env` 600 = exposition locale mono-fichier** : mieux que N secrets éparpillés + hors git, mais tout process same-user le lit. Assumé pour la classe B.
3. **Tier 1 rbw même-user** (classe A) : user séparé + canary + rotation.
4. **Seko-VPN coffre+backups (SPOF)** : offsite S3 + mode dégradé.
5. **Supply chain bw** : conteneur résolveur seul (pinné+checksum) ; rbw ailleurs.
6. **Canary aveugle env-dump** : documenté.

## 11. Estimation

6-7 sessions. P1a+P2 = classe B sécurisée (quotidien) ; P1b = classe A au coffre ; P3-P4 = durcissement + classe C future. Le scope `.bashrc`/`.profile` + redacteur peut ajouter ~½ session vs Fable.
