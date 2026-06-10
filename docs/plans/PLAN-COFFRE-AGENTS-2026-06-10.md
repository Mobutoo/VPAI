# PLAN D'IMPLÉMENTATION — Coffre agents VPAI (solution finale)

> Détaille VE.6/VE.7/VE.10 du `PLAN-2026-06-10-BEST-IN-CLASS.md`. Exécutable par session Opus + subagents (R6).
> Base vérifiée : `docs/reference/VERIF-COFFRE-AGENTS-2026-06-10.md` (fact-check 12 claims, 2026-06-10).
> Invariant : **la valeur d'un secret n'apparaît jamais dans le contexte LLM** (prompt, tool result, transcript). Le LLM décide, l'exécuteur détient.

---

## Architecture finale

```
waza (Pi5) ── agent shell ✗ secrets          Sese-AI ── jobs/services        Seko-VPN ── zone coffre (aucun agent n'y a de shell)
┌─────────────────────────────┐   ┌─────────────────────────┐   ┌──────────────────────────────────────┐
│ Claude Code / hooks          │   │ n8n (cred store natif)  │   │ Vaultwarden (IaC, backup restic)     │
│  refs seulement              │   │ OpenClaw                │   │ ┌──────────────────────────────────┐ │
│  ├─ secret-run (Tier 1, rbw) │   │ worker (user dédié)     │   │ │ RÉSOLVEUR (Tier 2, conteneur)    │ │
│  ├─ deny-list + hooks guard  │   │  secret-run (Tier 1)    │   │ │  bw serve 127.0.0.1 (pinné)      │ │
│  └─ redaction PostToolUse    │   │                         │   │ │  politique.yaml · audit → Loki   │ │
└──────────────┬──────────────┘   └────────────┬────────────┘   │ │  actions only — jamais de get    │ │
               └────────── Tailscale (token par agent) ─────────│ └──────────────────────────────────┘ │
                                                                 └──────────────────────────────────────┘
```

| Tier | Secrets | Mécanisme | Garantie |
|---|---|---|---|
| **1** | Tokens **renouvelables** quotidiens (HF, RUNPOD, QDRANT, PAT, Headscale) | `secret-run` local (rbw) + politique + user séparé + redaction | non-accidentelle (rotation = filet) |
| **2** | Secrets forts, logins web R2, toute donnée non renouvelable future | Résolveur isolé Seko-VPN, actions only | forte (frontière shell physique) |
| n8n | Credentials workflows | Store natif n8n (référence `credentialId`) | déjà en place — ne rien changer |
| LiteLLM | Clés providers IA | Virtual keys budgetées, injection proxy | déjà en place — modèle de référence |

---

## P0 — Fondations Vaultwarden (1 session) — gate 🔒

| # | Tâche | Done quand |
|---|---|---|
| P0.1 | 🔒 **Export préalable** du Vaultwarden existant (Seko-VPN) — humain, hors bande | export chiffré confirmé par l'humain |
| P0.2 | Rôle Ansible `vaultwarden` : image pinnée `versions.yml`, volume, HTTPS VPN-only, log rotation, healthcheck — checklist `docs/standards/ANSIBLE-ROLE-CHECKLIST.md` complète | redéploiement Seko-VPN reconstruit l'instance, données intactes |
| P0.3 | Backup : data Vaultwarden dans le périmètre Restic→Hetzner S3 (attention : Zerobyte tourne sur le MÊME hôte — l'offsite est obligatoire, cf PLAN V3.1) | restore testé sur conteneur éphémère |
| P0.4 | Organisation + collections : `infra-agents` (Tier 1), `strong-secrets` (Tier 2), `canary` ; comptes machine : `agent-waza`, `agent-sese`, `resolver` (API keys distinctes) | 3 comptes, ACL par collection vérifiées (agent-* ne voit PAS strong-secrets) |
| P0.5 | R8 vérifs préalables : `rbw` dispo ARM64 (apt Debian/cargo) + compat Vaultwarden (test login/get sur item de test) ; checksum `@bitwarden/cli` version pinnée (post-compromission 2026.4.0) | sibling test R4 : 1 secret de test lu par rbw depuis waza |
| P0.6 | Item **canary** : fausse "clé API" = URL webhook n8n d'alerte (tout usage → Telegram immédiat) | déclenchement test reçu |

---

## P1 — Tier 1 : `secret-run` (1-2 sessions)

| # | Tâche | Done quand |
|---|---|---|
| P1.1 | Rôle `secret-broker` (waza + Sese) : installe rbw pinné, config par machine (compte machine dédié), déploie `secret-run` + `politique.yml` | idempotent, 2e run changed=0 |
| P1.2 | **`secret-run <ref> -- <cmd>`** : (1) vérifie politique `ref → {commandes, hôtes} autorisés` → refus sinon ; (2) `rbw get` → **env du process enfant uniquement** (jamais argv — visible `ps`) ; (3) stdout/stderr **filtrés en streaming** des occurrences de la valeur ; (4) exit≠0 si ref absente ; (5) audit JSON (ts, ref, cmd, exit — jamais la valeur) → journald → Alloy/Loki | tests : secret jamais dans ps/argv/stdout ; commande hors politique refusée |
| P1.3 | Bootstrap session : `rbw-agent` déverrouillé par l'humain (au boot/SSH), timeout configurable ; jamais de master password sur disque | reboot → agents bloqués proprement jusqu'à unlock humain |
| P1.4 | Séparation user : jobs à secrets sous le user du worker (déjà distinct) via unités systemd dédiées — l'agent **déclenche** (`systemctl --user start x.service`), n'instrumente pas ; `/proc/PID/environ` illisible cross-user | lecture environ depuis le user agent = EACCES |
| P1.5 | Migration : `pod-ingest.env`, secrets de `memory-worker.env`, `RUNPOD_API_KEY` (fantrad/.env), GITHUB_PAT → refs Vaultwarden ; puis 🔒 **rotation immédiate** des anciennes valeurs (elles ont vécu en clair) | grep secrets en clair sur waza/Sese = 0 (hors stores natifs n8n/LiteLLM) |
| P1.6 | Ansible : lookups vault → option Vaultwarden (`community.general.bitwarden_secrets` non — Secrets Manager incompatible ; utiliser lookup `community.general.bitwarden` via bw CLI du résolveur OU garder ansible-vault pour le déploiement, Vaultwarden pour le **runtime**) — trancher par ADR : **recommandé = statu quo ansible-vault (deploy) + Vaultwarden (runtime agents)**, un seul système par usage | ADR commitée |

---

## P2 — Couches harness (1 session)

| # | Tâche | Done quand |
|---|---|---|
| P2.1 | Deny-list `settings.json` (waza, global) : `Read(.env*)`, `Read(**/secrets*.yml)`, `Read(.vault_password)`, `Read(**/*.pem)` | lecture directe refusée |
| P2.2 | Hook PreToolUse `secret-guard.js` (pattern `loi-op-enforcer`) : exit 2 sur `rbw get`, `bw get`, `cat/less/grep` sur fichiers à secrets, `ansible-vault view`, `curl -v` avec header auth → message "utilise secret-run" | bypass tenté = bloqué + message |
| P2.3 | Hook PostToolUse `redactor.js` : regex types (`sk-`, `ghp_`, `hf_`, `eyJ`, `AKIA`, `tskey-`, `rpa_`) + **valeurs exactes du canary** → `[REDACTED:type]` avant entrée en contexte | secret planté dans une sortie simulée → caviardé |
| P2.4 | Scrubber JSONL (lien PLAN 4.4) : mêmes regex + Presidio `encrypt` en moteur candidat — **prérequis Phase 10** inchangé | test secrets plantés → 100% scrubés |

---

## P3 — Tier 2 : résolveur isolé (2 sessions)

| # | Tâche | Done quand |
|---|---|---|
| P3.1 | Rôle `secret-resolver` (Seko-VPN) : conteneur dédié — `bw serve` 127.0.0.1 interne (npm pinné + checksum, auto-update interdit) + app résolveur ; durcissement `cap_drop: ALL`, `no-new-privileges`, `read_only` (sauf tmpfs), réseau : Tailscale uniquement | conteneur up, aucun port public, scan depuis waza = seul l'endpoint actions répond |
| P3.2 | Auth : token par agent (waza, sese-n8n, openclaw) + rate-limit (s'inspirer Cerberus : 3/min, 20/h par item) + HITL Telegram optionnel par ref | token A ne résout pas les refs de B |
| P3.3 | `politique.yaml` v2 : `ref → {domaines, endpoints, champs}` ; vérification de l'URL/domaine effective **côté résolveur** avant injection (pare-feu anti prompt-injection) | ref demandée hors domaine = refus + audit |
| P3.4 | Action 1 : `run_authenticated_call(ref, method, url, body)` — le résolveur injecte le header, relaie la réponse **caviardée** ; exposée en MCP (bridge stdio waza → HTTP résolveur) | appel API authentifié bout-en-bout, grep transcript = 0 occurrence |
| P3.5 | Action 2 (différable) : `secure_fill(ref, steps)` — Playwright headless **dans le conteneur résolveur** (modèle Cerberus : l'agent envoie les steps, ne voit que statut + snapshot re-tokenisé) ; pour les logins web R2 | login web test sans la valeur dans aucun tool result |
| P3.6 | Audit complet → Loki + dashboard Grafana (usage par ref/agent/jour) | dashboard visible |

---

## P4 — Exploitation & durcissement (1 session)

| # | Tâche | Done quand |
|---|---|---|
| P4.1 | `rotate-secrets.yml` v2 : écrit les nouvelles valeurs **dans Vaultwarden** (`no_log`), plus jamais en stdout ; étendu aux tokens providers IA | rotation test sans fuite log |
| P4.2 | Alerte intégrité : version `bw serve` ≠ pinnée → alerte ; checksum au déploiement | test version mutée → alerte |
| P4.3 | Mode dégradé documenté : Seko-VPN down → Tier 1 continue (rbw cache local chiffré), Tier 2 indisponible (fail-closed) | runbook `docs/runbooks/RUNBOOK-COFFRE-AGENTS.md` commité + ingéré mémoire |
| P4.4 | Test d'intrusion ami : session Claude dédiée qui TENTE d'exfiltrer (lecture env, ps, bypass wrapper) → chaque vecteur bloqué ou détecté (canary/audit) | rapport REX commité |

---

## Gates humains 🔒 récapitulatif
P0.1 (export avant IaC) · P1.3 (design unlock) · P1.5 (rotation post-migration) · P3.2 (politique HITL par ref) · P4.4 (validation du test d'intrusion).

## Risques résiduels assumés
1. **Tier 1 même-user** : un agent shell déterminé sur waza peut viser le cache rbw de son propre user → mitigé par user séparé (P1.4) + canary + rotation. Les non-renouvelables sont interdits en Tier 1.
2. **Seko-VPN concentre coffre + backups** : SPOF assumé, compensé par offsite S3 (P0.3) + mode dégradé (P4.3). Réévaluer si NAS arrive (3-2-1 complet).
3. **Supply chain bw** : surface réduite au seul conteneur résolveur, pinné + checksum + alerte (P4.2) ; rbw (hors npm) partout ailleurs.

## Estimation
6-7 sessions. Ordre strict P0→P1→P2 (le quotidien est sécurisé dès P2) ; P3 peut suivre V-ECO SSO ; P4 clôture. S'insère dans V-ECO : P0=VE.6, P1+P2=VE.7, P3=VE.10.
