# Vérification — note flash-studio "Coffre-fort credentials agents IA" → application VPAI

> Date : 2026-06-10. Source évaluée : note d'architecture flash-studio/infra v1.0 (coffre + injection edge).
> Fact-check web (subagent, 12 claims). Décisions d'adaptation VPAI en §3. Alimente PLAN V-ECO (VE.7/VE.10).

## 1. Verdicts fact-check

| # | Claim | Verdict | Source |
|---|---|---|---|
| 1 | Cerberus KeyRouter (DemoJacob, AGPL-3.0, Vaultwarden+CDP, rate-limit 3/min 20/h, HITL 50s, `{{totp}}`) | ✅ vérifié (nuance : "MCP Streamable HTTP" non confirmé dans le README) | github.com/DemoJacob/cerberus-keyrouter |
| 2 | Vaultwarden n'implémente pas Secrets Manager (licence Bitwarden) | ✅ vérifié — BlackDex : "This feature is Bitwarden licensed" | vaultwarden issues #3368, #5702 |
| 3 | `bw` + `bw serve` OK contre Vaultwarden (API key + unlock → BW_SESSION, login/note/carte/identité) | ✅ vérifié | bitwarden.com/help/cli + discourse vaultwarden |
| 4 | MCP Bitwarden officiel, adossé CLI → compatible Vaultwarden | ✅ vérifié (compat via `BW_API_BASE_URL`, non revendiquée explicitement) | github.com/bitwarden/mcp-server |
| 5 | Bitwarden Agent Access SDK alpha (2026-03-24) | ✅ vérifié — produit **séparé** de Secrets Manager (pas "rattaché") | businesswire 2026-03-24 |
| 6 | **`@bitwarden/cli` compromis npm** | ✅ vérifié — v2026.4.0, 22/04/2026, ~1h30, preinstall `bwsetup.js`, via checkmarx/ast-github-action (TeamPCP) | thehackernews.com 2026-04 |
| 7 | Infisical Agent Vault (proxy Go, preview, header Authorization) | ⚠ partiel — proxy confirmé ; "HTTP/2 désactivé" et "isolation Claude-only" **non confirmés** | infisical.com/blog/agent-vault |
| 8 | Browser Use `sensitive_data` + `allowed_domains` + `use_vision=False` | ✅ vérifié — MAIS masquage des pages de confirmation **non garanti** par la doc | docs.browser-use.com |
| 9 | npm `agent-secrets-vault` (Axis, keychain OS) | ✅ vérifié | libraries.io/npm/agent-secrets-vault |
| 10 | passwd-mcp `exec --inject` (env subprocess, stdout masqué) | ✅ vérifié | passwd.team/blog |
| 11 | Presidio : seul `encrypt` réversible | ✅ vérifié | microsoft.github.io/presidio/anonymizer |
| 12 | 1Password Secure Agentic Autofill | ✅ vérifié (early access oct. 2025) | developer.1password.com/docs/agentic-autofill |

## 2. Ce que la note a de juste et de transposable (validé)

1. **"Le facteur déterminant n'est pas le coffre mais l'isolation du résolveur"** (frontière shell) — s'applique à VPAI au maximum : Claude Code **a un shell sur waza**. Un résolveur local waza = garantie "non-accidentelle" seulement.
2. **Table de politique secret→cible** (épinglage domaine/commande) = pare-feu anti prompt-injection. Converge avec OPA (PLAN V5.1) — un seul moteur de politique à terme.
3. **Pattern `exec --inject` + stdout masking** (passwd-mcp, vérifié) = validation état-de-l'art du wrapper `secret-run` VE.7. Le **masking stdout** (filtrer les occurrences du secret dans la sortie) est à ajouter au design initial.
4. **Caviardage du chemin retour** — chez VPAI : hook PostToolUse redaction sur TOUS les tool results, y compris `browser_snapshot` Playwright MCP post-fill (la page de confirmation est le canal de fuite, et Browser Use ne le garantit pas — claim 8).
5. **Règle de décision** injection-par-référence (défaut) vs sandwich tokenisation (seulement si la valeur doit apparaître dans le texte). Sandwich VPAI = Presidio `encrypt` → candidat moteur du scrubber JSONL (PLAN 4.4) — réutilisation, pas de double outil.
6. **Renouvelable vs non-renouvelable** : VPAI aujourd'hui = quasi exclusivement des tokens **renouvelables** (HF, RunPod, Qdrant, PAT, Headscale) → la rotation reste le filet principal, le tiering peut être pragmatique. Cartes/PII = hors scope actuel (futur OpenClaw assistant → cartes virtuelles obligatoires, jamais la réelle).

## 3. Décisions d'adaptation VPAI (deltas vs la note)

| Sujet | Note flash-studio | Adaptation VPAI |
|---|---|---|
| Surface principale | Navigateur (login, paiement, NIR) | **Shell/API d'abord** (Bash Claude Code, jobs worker, n8n) ; navigateur = R2 Playwright, second temps |
| Résolveur | Hôte isolé générique | **Seko-VPN** (déjà hôte de Vaultwarden, aucun agent n'y a de shell) — conteneur dédié, `bw serve` 127.0.0.1, exposé en MCP/HTTP actions-only via Tailscale, token par agent |
| Tiering | Non tiéré | **Tier 1** (tokens renouvelables, usage quotidien) : `secret-run` local waza + deny-list + redaction + rotation — pragmatique. **Tier 2** (secrets forts, web login, futur PII) : résolveur isolé Seko-VPN, l'agent n'a que des actions |
| Isolation locale waza | "garantie nulle si shell" | Atténuation réelle : **user systemd séparé** — les jobs à secrets tournent sous le user du worker (déjà le cas), `/proc/PID/environ` illisible cross-user ; l'agent *déclenche* le job, ne l'instrumente pas |
| CLI Bitwarden | "pinner et vérifier" | Doctrine versions.yml + **préférer `rbw` (Rust, hors npm)** pour le chemin wrapper Tier 1 ; `bw serve` (npm pinné + checksum, jamais auto-update) uniquement dans le conteneur résolveur Tier 2 — réponse directe à la compromission vérifiée du 22/04/2026 |
| Cerberus | Route A (fork) possible | Usage perso → AGPL OK, mais projet jeune : **s'inspirer des 6 couches**, ne pas en faire un socle. Le besoin login-web VPAI passe par un outil MCP maison `secure_fill` côté résolveur (Tier 2) |
| Infisical / Agent Access SDK | Options | **Écartés** : preview avec claims non confirmés / alpha ligne Secrets Manager (incompatible Vaultwarden probable). À revoir dans 6 mois |
| MCP Bitwarden officiel | "à envelopper" | Confirmé : `get` rend le clair → **jamais exposé à l'agent** ; utilisable uniquement comme lib interne du résolveur |
| Ce que la note n'a pas | — | Contrôles harness déjà en place chez VPAI (deny-list Read, hooks exit 2 type loi-op-enforcer, audit → Loki) + **canary token** Vaultwarden |

## 4. Risque résiduel honnête

Tier 1 (waza) : un agent shell déterminé peut contourner (lecture cross-process si même user, timing). Acceptable pour tokens renouvelables + rotation + canary. Toute donnée **non renouvelable** (identité, carte réelle) est interdite en Tier 1 — Tier 2 uniquement, et carte réelle jamais (virtuelle plafonnée).
