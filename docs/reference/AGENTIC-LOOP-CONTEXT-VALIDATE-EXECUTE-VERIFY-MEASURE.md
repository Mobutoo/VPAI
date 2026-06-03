# Référence — La boucle agentique : CONTEXT → VALIDATE → EXECUTE → VERIFY → MEASURE/LEARN

> Statut : **RÉFÉRENCE PÉRENNE** — sources vérifiées en direct 2026-06-04 (citations réelles, pas de mémoire).
> Rôle : cadre conceptuel derrière `docs/superpowers/specs/2026-06-04-loi-system-bricks-design.md` (le système maison vu comme briques).
> Lien LOI : `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` (chaque règle Rn appartient à une brique).

## 1. Le principe

Un agent fiable n'est pas un prompt : c'est une **boucle instrumentée** où le modèle agit, observe l'environnement réel (ground truth), et corrige — encerclée par des guardrails entrée/sortie et fermée par la mesure.

```
            ┌─────────── OUTPUT-guard (scan sortie) ───────────┐
  INPUT  →  CONTEXT  →  VALIDATE  →  EXECUTE  →  VERIFY  →  MEASURE/LEARN
  guard      ↑                                                   │
             └──────────────── le REX/la mesure reboucle ────────┘
```

> Anthropic, *Building effective agents* : les agents utilisent « tools based on environmental feedback **in a loop** », récoltant le ground truth de l'environnement à chaque pas pour évaluer la progression avant d'agir à nouveau.

Les 5 briques + 2 guardrails ci-dessous, chacune avec son principe, sa **source vérifiée**, et son ancrage dans le système maison (règles LOI + hooks).

---

## 2. Les briques

### CONTEXT — rassembler le bon signal avant d'agir
**Principe** : ne pas tout pré-charger ; maintenir des identifiants légers (paths, requêtes) et charger au runtime ; écrire des notes persistées hors-contexte ; compacter quand la fenêtre sature.

- *Just-in-time* : « agents [...] maintain lightweight identifiers (file paths, stored queries, web links, etc.) and use these references to dynamically load data into context at runtime ».
- *Note-taking / agentic memory* : « the agent regularly writes notes persisted to memory outside of the context window ».
- *Compaction* : « taking a conversation nearing the context window limit, summarizing its contents, and reinitiating a new context window with the summary ».

**Source** ✅ : Anthropic, *Effective context engineering for AI agents* (2025-09-29) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

**Système maison** : R0 (mémoire), R8 (doc-first), R4 (sibling test), R6 (subagent paths-only) ; hooks R0-Continu (memory-search-start, r0-topic-injector, ledger), worker `memory_v1`.

---

### VALIDATE — prouver l'artefact avant l'effet de bord
**Principe** : guardrails en **défense par couches** (LLM + règles/regex + modération) ; valider l'input et les **appels d'outils à risque** avant exécution. Les guardrails sont des objets de première classe : ils lèvent un *tripwire* qui halte l'exécution.

- *Tripwire* : « If the input or output fails the guardrail, the Guardrail can signal this with a tripwire. »
- *Portée* : « Input guardrails run only for the first agent in the chain. Output guardrails run only for the agent that produces the final output. »
- *Tool risk rating* (PDF) : noter chaque outil low/medium/high selon read-only vs write, réversibilité, permissions, impact financier → pause/gate avant les fonctions high-risk.

**Sources** ✅ : OpenAI *Agents SDK — Guardrails* — https://openai.github.io/openai-agents-python/guardrails/ · OpenAI *A practical guide to building agents* (PDF, existe — binaire) — https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf

**Système maison** : R1 (validate_workflow avant import — **actuellement advisory, à durcir, cf spec D1**), R3 (file-first) ; hook `loi-op-enforcer`. *Risk-tier non implémenté → spec D4.*

---

### EXECUTE — agir par les canaux sanctionnés
**Principe** : outils bien conçus, peu nombreux, non ambigus ; un jeu d'outils bloated = mauvais choix d'agent. Privilégier des actions déterministes et scoped.

**Source** : Anthropic, *Writing tools for agents* — https://www.anthropic.com/engineering/writing-tools-for-agents *(cité par la passe de recherche, non re-vérifié cette session)* ; Claude Code best practices — https://code.claude.com/docs/en/best-practices *(idem)*.

**Système maison** : R2 (Playwright), R7 (canal Tailscale), R11 (REST API), MCP-first table ; hooks `loi-op-enforcer` (R2/R7 bloc dur), `bash-lint`, `mcp-intent-guard`.

---

### VERIFY — preuve > assertion, fermer la boucle sur le ground truth
**Principe** : un agent s'arrête quand ça *semble* fait ; sans check exécutable, **l'humain devient la boucle de vérification**. Vérifier contre l'état réel (DB/fichier/test), pas contre le texte de confirmation. Donner un **contrat de sortie** explicite = ce qui compte comme « fait » et comment le vérifier.

- *Ground truth* (loop) : récolter la vérité de l'environnement à chaque pas — cf. *Building effective agents*.
- *Output contract* : « Define the output contract: exact deliverables such as files changed, expected outputs, API responses, CLI behavior, and tests passing. »
- *Output guardrail* : tourne sur l'agent qui produit la sortie finale (scan secrets/PII avant rendu).

**Sources** ✅ : Anthropic *Building effective agents* (2024-12-19) — https://www.anthropic.com/engineering/building-effective-agents · OpenAI *GPT-5 prompting guide* — https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide · OpenAI *Agents SDK Guardrails* (output) — https://openai.github.io/openai-agents-python/guardrails/

**Système maison** : R10 (workflow_history = source de vérité) ; `stop-gate` (faible). **GAP** → spec D3 (VERIFY stop-gate) + D4 (output guard). Aligné skill `superpowers:verification-before-completion`.

---

### MEASURE / LEARN — mesurer l'adhérence, apprendre des échecs
**Principe** : boucle *measure → improve → ship*. Construire les evals **à partir des vrais échecs** ; séparer **régression (~100 %)** et **capacité (départ bas)** ; **grader le résultat, pas le chemin**. Tracer chaque run (model/tool/guardrail/handoff). C'est exactement la donnée de l'audit fondateur maison (806 Bash / 0 MCP / 23 compacts) — produite a posteriori.

- *Depuis les échecs* : « Converting user-reported failures into test cases ensures your suite reflects actual usage. »
- *Régression vs capacité* : « Capability evals [...] should start at a low pass rate. Regression evals [...] should have a nearly 100% pass rate. »
- *Grader le résultat* : « It's often better to grade what the agent produced, not the path it took. »
- *Trace* : « Tracing collects a comprehensive record of events during an agent run: LLM generations, tool calls, handoffs, guardrails, and even custom events. »
- *Eval-driven* : « Writing evals to understand how your LLM applications are performing [...] is an essential component to building reliable applications. »

**Sources** ✅ : Anthropic *Demystifying evals for AI agents* (2026-01-09) — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents · OpenAI *Agents SDK — Tracing* — https://openai.github.io/openai-agents-python/tracing/ · OpenAI *Evals guide* — https://developers.openai.com/api/docs/guides/evals

**Système maison** : `session-memory-writer` **émet déjà** (bash_pct, MCP/Bash, compacts) vers n8n/Telegram — **boucle ouverte, personne n'agrège**. → spec D2 (fermer la boucle). LEARN = `r0-rex-watcher` (REX écrit → réinjecté, spec Partie A décl. B).

---

## 3. Carte brique → règle LOI → enforcement (résumé)

| Brique | Règles LOI | Hooks | État maison |
|---|---|---|---|
| INPUT guard | — | prompt-preprocessor (normalise) | gap mineur |
| CONTEXT | R0,R8,R4,R6 | R0-Continu (4 hooks) + worker | **FORT** |
| VALIDATE | R1,R3 | loi-op-enforcer (advisory) | FAIBLE (R1 à durcir) |
| EXECUTE | R2,R7,R11 | loi-op-enforcer (R2/R7 bloc), bash-lint, mcp-intent | FORT (méthode) / ABSENT (risque) |
| VERIFY | — (R10 vérité) | stop-gate (faible) | GAP |
| OUTPUT guard | Secrets (prose) | aucun | GAP |
| MEASURE/LEARN | — | session-memory-writer (émet) | boucle ouverte |

---

## 4. Index des sources

| # | Source | Vérifié 2026-06-04 | URL |
|---|---|---|---|
| 1 | Anthropic — Building effective agents (2024-12-19) | ✅ citation | https://www.anthropic.com/engineering/building-effective-agents |
| 2 | Anthropic — Effective context engineering (2025-09-29) | ✅ citation | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents |
| 3 | Anthropic — Demystifying evals for AI agents (2026-01-09) | ✅ citation | https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents |
| 4 | Anthropic — Writing tools for agents | ⚠️ non re-vérifié | https://www.anthropic.com/engineering/writing-tools-for-agents |
| 5 | Anthropic — Claude Code best practices | ⚠️ non re-vérifié | https://code.claude.com/docs/en/best-practices |
| 6 | Anthropic — Building agents with the Agent SDK | ⚠️ non re-vérifié | https://claude.com/blog/building-agents-with-the-claude-agent-sdk |
| 7 | OpenAI — A practical guide to building agents (PDF) | ✅ existe (binaire) | https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf |
| 8 | OpenAI — Agents SDK Guardrails | ✅ citation | https://openai.github.io/openai-agents-python/guardrails/ |
| 9 | OpenAI — Agents SDK Tracing | ✅ citation | https://openai.github.io/openai-agents-python/tracing/ |
| 10 | OpenAI — Evals guide | ✅ citation | https://developers.openai.com/api/docs/guides/evals |
| 11 | OpenAI — GPT-5 prompting guide | ✅ citation | https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide |

> ⚠️ = cité par la passe de recherche (subagents), non re-fetché dans la session de rédaction. Les ✅ ont une citation textuelle vérifiée le 2026-06-04.
