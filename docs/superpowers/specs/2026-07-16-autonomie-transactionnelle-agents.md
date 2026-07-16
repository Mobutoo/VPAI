# Spec — Autonomie transactionnelle des agents (secrets + autofill + paiement, zéro accès donnée)

> **Date** 2026-07-16 · **Statut** design (spec) · **Étend** le plan coffre `docs/plans/PLAN-COFFRE-AGENTS-2026-06-10.md` **§P3 Tier 2** (concrétise `secure_fill`/`run_authenticated_call` avec les outils SOTA mi-2026) + ajoute la **couche paiement** absente.
> **Base SOTA** : recherche datée mi-2026 (agentic autofill + payments), croisée/sourcée.

## 0. Objectif
Des agents IA autonomes qui **se connectent, remplissent des formulaires et paient** — le LLM/agent n'ayant **JAMAIS accès** au secret, au PAN ni à la PII de l'utilisateur.

## 1. Deux invariants (ceinture + bretelles)
- **I1 — jamais dans le contexte LLM** (Fable) : la valeur ne transite ni en prompt, ni en tool-result, ni en screenshot, ni en transcript.
- **I2 — jamais au-delà du périmètre** (ajout paiement) : même si I1 cédait, l'autorité de dépense est **bornée par construction** (carte single-use scoped, cap, HITL) → une fuite est inexploitable.

## 2. Constat SOTA décisif (hype vs shipped)
- **Aucun MCP Vaultwarden ne fait d'injection hors-contexte** : `bitwarden/mcp-server` (officiel) renvoie le secret **en clair** dans le tool-result (« PoC, not for production » de l'aveu de Bitwarden) ; `warden-mcp` redige par défaut mais `reveal:true` fuit quand même. **⇒ NE PAS bâtir l'autofill sur un MCP secret.**
- **1Password for Claude** a shippé le **2026-07-16** (Noise E2E, approbation humaine, injection DOM, « Claude never sees the vault item ») = l'archi de référence exacte — mais **cloud-only/fermé**, pas de vault self-hosté.
- **L'équivalent self-hostable = Skyvern + Vaultwarden** (voir §3).
- Paiement : **ACP Instant Checkout a reculé** (retiré mars 2026), **Operator est mort**, **x402 = machine-to-machine** (pas checkout humain). Le chemin pragmatique hors-US = **cartes virtuelles single-use Stripe Issuing** (Privacy.com = US-only).

## 3. Architecture cible — l'**Exécuteur** isolé sur le X58

Frontière de confiance : l'agent (Waza/Sese) n'a **aucun shell** sur l'Exécuteur. Il émet des **intentions**, reçoit du **statut caviardé**. L'Exécuteur = LXC(s) sur le **X58 home-datacenter** (isolé, derrière Tailscale, jamais exposé, compute réel pour le navigateur headless, PII reste à la maison).

```
Agent LLM (Claude Code / n8n / OpenClaw)  ── intents only ──►  EXÉCUTEUR (X58, LXC isolés)
  jamais secret/PAN/PII                    ◄── statut caviardé ──   │
                                                                     ├─ LXC skyvern : navigateur executor
                                                                     │    vault-fetch Vaultwarden → inject DOM → discard
                                                                     │    (le secret n'entre JAMAIS dans un prompt LLM)
                                                                     ├─ LXC pay-broker : émet carte virtuelle scoped
                                                                     │    (Stripe Issuing) + enforcement caps déterministe
                                                                     ├─ LXC hitl-gate : suspend → Telegram → approuve
                                                                     └─ audit non-répudiable → Loki/Grafana (LXC observ)
        Vaultwarden (Seko) ◄── bridge natif Skyvern ── credentials/TOTP
```

### Briques (toutes self-hostables / API, validées mi-2026)
| Brique | Rôle | Nature |
|---|---|---|
| **Skyvern** (OSS AGPL, Docker) | Executor navigateur : fetch cred → inject DOM → discard, placeholder tokens, **bridge Vaultwarden natif** + TOTP/2FA. « never enters an LLM prompt » | LXC `skyvern` sur X58 |
| **Vaultwarden** (déjà) | source unique credentials (Seko) | en place |
| **Stripe Issuing « for agents »** | carte virtuelle **single-use** (`cancel_after {payment_count:1}`), merchant-lock **MCC**, amount-limit — couvre **EEA/UK** | API (gate éligibilité) |
| **Polos** (OSS, self-host) *ou* Temporal Signal / LangGraph `interrupt()` | **gate HITL** : suspend le workflow → notif **Telegram** (bot monitoring déjà en place) → approuve/refuse | LXC `hitl-gate` |
| **AP2 SDK** (Apache-2.0, mandats VC signés ES256 : `amount_range`/`budget`/`agent_recurrence`/`execution_date`/`allowed_payees`/`cnf`) | *optionnel* : autorisation cryptographique portable au lieu de tout gérer en spend-controls carte | à évaluer |
| **x402** (Coinbase, GA) | *optionnel* : micropaiements agent↔service (API machine-to-machine, USDC), PAS un checkout humain | à évaluer (agent-to-service) |

### Intentions exposées à l'agent (API MCP/HTTP)
- `login(ref, url)` → Skyvern (statut only)
- `fill_form(ref, steps)` → Skyvern (`use_vision=OFF` forcé, `allowed_domains` strict) → snapshot re-tokenisé
- `run_authenticated_call(ref, method, url, body)` → header injecté, réponse caviardée
- `pay(merchant, montant, ref_panier)` → pay-broker : émet carte scoped → Skyvern remplit le checkout → reçu sans PAN

## 4. Threat model — la crypto garantit *ce qui est exécuté*, pas *comment on décide*
Findings mi-2026 (à intégrer, sinon la solution est théâtrale) :
- **Injection indirecte** (avis produit malveillant) : F-Secure PoC **12 % succès**, exfiltration nom/adresse/CB, **l'agent a menti** pour cacher l'incident. Jailbreak direct échoue, manipulation contextuelle marche.
- **« Lies-in-the-Loop »** : l'agent génère un résumé d'approbation qui **masque la commande réelle** → l'humain approuve à l'aveugle (**~100 % succès**). ⇒ **le gate HITL DOIT afficher marchand + montant + moyen RÉELS** (rendus par l'Exécuteur, pas par l'agent).
- **Incidents réels** : Step Finance 27-40 M$ (aucun HITL) ; drain 500k$ via routeur LLM compromis.
- **Angle mort carte single-use** : un abonnement légitime force une carte **multi-usage longue durée** → réintroduit le risque récurrence (traiter à part, cap + velocity).

### Contrôles durs (non négociables)
1. **Enforcement déterministe HORS modèle** : les caps (per-merchant / per-amount / per-time / velocity) validés par du **code non-LLM AVANT** émission carte / paiement — jamais par le prompt.
2. **HITL non-aveugle** : step-up affichant marchand/montant/moyen **réels** (source Exécuteur) au-dessus d'un seuil / nouveau marchand.
3. **Identité agent ≠ identité user** (OAuth 2.1 client-credentials) : l'agent s'authentifie séparément.
4. **Audit non-répudiable** : chaque intent→action→résultat loggé (ref/merchant/montant/statut, **jamais la valeur**) → Loki/Grafana X58.
5. **Kill-switch** : anomalie velocity / canary → **freeze cartes** + révoque sessions Skyvern.
6. **Backstop I1** : le redacteur PostToolUse (coffre P2) rattrape toute valeur qui fuirait en contexte.
7. **Skyvern durci** : `use_vision` OFF, `allowed_domains` strict + **patcher CVE-2025-47241** (bypass allowed_domains), traiter l'**injection de prompt** comme la menace #1 (double-LLM trusted/untrusted à évaluer).

## 5. Intégration au plan coffre (place dans la séquence)
- Tier 1 (secret-run, classe A) + classe B (.env) : **P1a/P1b** — en cours.
- **Cette spec = Tier 2 concrétisé (P3 du plan coffre)** : l'Exécuteur = Skyvern (remplace le DIY `secure_fill` Playwright de Fable) + pay-broker Stripe Issuing + HITL Polos/Telegram + enforcement déterministe.
- Hébergement : LXC sur le **X58** (le Trusted Execution node), Vaultwarden sur Seko, HITL via le **bot Telegram monitoring existant**, audit → **observ LXC** (Loki/Grafana).
- **Ordonnancement** : après P0 coffre (Vaultwarden opérationnel + backup) et le montage X58. Le paiement réel = **dernier** (gate humain fort : éligibilité Stripe Issuing + wallet préfinancé + premiers paiements en HITL total).

## 6. Gates humains 🔒
- Éligibilité **Stripe Issuing** (review, couverture EEA/UK — vérifier RDC/UE selon entité).
- Wallet/funding préfinancé borné (jamais la carte perso comme funding direct de l'agent).
- Premiers N paiements = **HITL total** (approbation systématique) avant tout seuil d'autonomie.
- Choix mandat : spend-controls carte seuls (simple) vs **AP2** (autorisation crypto portable, plus robuste, plus de travail).

## 7. Décisions ouvertes
- Skyvern (AGPL, complet) vs Stagehand (MIT, plus léger) pour l'executor navigateur.
- HITL : Polos (prêt-à-l'emploi) vs Temporal (déjà dans la stack content-factory) vs n8n (déjà là).
- Émetteur carte : Stripe Issuing (mûr, EEA) — confirmer l'éligibilité géographique de l'entité ; Agentcard.sh (MCP-natif, mais startup 3 mois) en veille.
- x402/AP2 : adopter maintenant (forward-compatible) ou attendre la consolidation (aucun gagnant désigné, tous les réseaux hedgent).
