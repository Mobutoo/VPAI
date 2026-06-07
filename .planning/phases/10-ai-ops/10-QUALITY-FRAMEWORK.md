# Phase 10 — Grille Qualité Sessions Claude Code

**Date :** 2026-04-12  
**Statut :** Finalisé — prêt pour Plan 10-B1/B3  
**Source :** Analyse 1,945 messages réels + audit MOP-generator + recherche 2025-2026

---

## Ce que "qualité d'une session" signifie réellement

Langfuse mesure des traces LLM génériques : latence, tokens, erreurs API. Ce n'est pas ce dont nous avons besoin.

**Nos sessions sont des séances de travail d'ingénierie.** La qualité = le ratio entre l'effort consommé (tokens/temps/corrections) et la valeur produite (code déployé, tâche terminée, décision prise).

Trois axes fondamentaux :

```
EFFICACITÉ        : est-ce que Claude utilise les bons outils ?
PROGRESSION       : est-ce qu'on avance vers la tâche ou on tourne en rond ?
ALIGNEMENT        : est-ce que les règles (LOI OP, LOI) sont respectées ?
```

---

## Grille de scoring (1–10 points)

### Axe 1 — Efficacité outil (0–3 pts)

| Signal | Points |
|--------|--------|
| bash_avoidable = 0 | +1 |
| bash_avoidable < 5% du total tool_calls | +0.5 |
| MCP utilisé au moins 1 fois (si applicable) | +0.5 |
| Subagent délégué quand > 10 Bash calls consécu | +0.5 |
| bash_avoidable > 20% du total | -1 |
| bash_avoidable > 40% du total | -2 |

**Baseline mesurée :** session MOP-debug = 806 Bash, 0 MCP → score axe 1 = 0/3.  
**Session déploiement réussi :** 396 Bash + 17 MCP calls → score axe 1 = 2.5/3.

### Axe 2 — Progression de tâche (0–3 pts)

| Signal | Points |
|--------|--------|
| Tâche terminée (verifiable output détecté) | +2 |
| Tâche partiellement terminée | +1 |
| correction_signals = 0 | +1 |
| correction_signals < 3 | +0.5 |
| correction_signals > 5 | -1 |
| max_repeated_tool_streak > 3 (loop) | -1 |
| max_repeated_tool_streak > 6 (loop sévère) | -2 |
| compact_count > 2 (context overflow) | -1 |

**Baseline mesurée :** "tu tournes en rond" = correction_signals élevé + 23 compacts.

### Axe 3 — Alignement directives (0–4 pts)

| Signal | Points |
|--------|--------|
| R0 mémoire cherchée au début de session | +1 |
| Pas de violation LOI OP détectée | +1 |
| Skill `systematic-debugging` invoquée si session debug | +1 |
| Skill `verification-before-completion` invoquée en fin | +1 |
| `localhost:5678` détecté dans les commandes (R7) | -1 |
| IP directe `137.74.114.167` détectée (R7) | -1 |
| `n8n import:workflow` sans `validate_workflow` (R1) | -0.5 |

**Baseline mesurée :** session MOP = `systematic-debugging` ×1 en 11h, `verification-before-completion` ×0.

---

## Signaux détectables dans le JSONL

### Signaux tool calls (quantifiables)

```python
# À extraire dans parser.py

# Loop detection
def detect_tool_streak(tool_timeline: list[ToolEvent]) -> int:
    """Longueur de la séquence répétée la plus longue."""
    max_streak = 1
    current_streak = 1
    for i in range(1, len(tool_timeline)):
        if tool_timeline[i].name == tool_timeline[i-1].name:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 1
    return max_streak

# MCP usage detection
MCP_TOOL_PREFIXES = ["mcp__", "browser_", "qdrant-", "sequentialthinking"]

def count_mcp_calls(tool_distribution: dict) -> int:
    return sum(v for k, v in tool_distribution.items() 
               if any(k.startswith(p) for p in MCP_TOOL_PREFIXES))

# LOI OP R7 violation
def detect_r7_violation(bash_commands: list[str]) -> int:
    violations = 0
    for cmd in bash_commands:
        if "localhost:5678" in cmd or "137.74.114.167" in cmd:
            violations += 1
    return violations

# LOI OP R1 violation (n8n import sans validate)
def detect_r1_violation(bash_commands: list[str], tool_timeline) -> bool:
    has_import = any("n8n import:workflow" in cmd for cmd in bash_commands)
    has_validate = any("validate_workflow" in str(t) for t in tool_timeline)
    return has_import and not has_validate

# Skill usage
QUALITY_SKILLS = ["systematic-debugging", "verification-before-completion", 
                  "subagent-driven-development", "test-driven-development"]

def extract_skills_used(messages: list) -> list[str]:
    """Extrait les skills invoquées depuis les tool_use Skill calls."""
    skills = []
    for msg in messages:
        for content in msg.get("content", []):
            if content.get("type") == "tool_use" and content.get("name") == "Skill":
                skill_name = content.get("input", {}).get("skill", "")
                if skill_name:
                    skills.append(skill_name)
    return skills
```

### Signaux textuels utilisateur (correction signals)

```python
# Version enrichie — au-delà du simple "non/stop"
CORRECTION_PATTERNS_FR = [
    # Rejets directs
    r"\bnon\b", r"\bstop\b", r"\barrête\b", r"\bannule\b",
    # Recadrages
    r"tu tournes en rond", r"c'est pas ça", r"tu n'as pas compris",
    r"recommence", r"repart de zéro", r"oublie ça",
    # Frustration implicite
    r"pourquoi tu", r"j'avais dit", r"comme je t'ai dit",
    # Scope explosion (signal ambigu — peut être positif)
    r"en fait il faut aussi", r"j'ai oublié de dire",
]

LOOP_SIGNALS_FR = [
    r"encore la même erreur", r"toujours pareil", r"ça ne marche toujours pas",
    r"tu refais la même chose", r"on a déjà essayé ça",
]

COMPLETION_SIGNALS_FR = [
    r"parfait", r"c'est bon", r"nickel", r"ça marche",
    r"déployé", r"vérifié", r"done", r"ok ça marche",
]
```

### Signaux de progression (détection completion)

```python
# Indicateurs de complétion dans les tool_results
COMPLETION_INDICATORS = [
    "successfully deployed",
    "PLAY RECAP",                    # Ansible OK
    "changed=",                      # Ansible changed count
    "All tests passed",
    "✅",                             # Succès explicite
    "HTTP 200",
    "container started",
]

# Indicateurs d'échec
FAILURE_INDICATORS = [
    "FAILED", "Error:", "Exception:", "Traceback",
    "connection refused", "timeout", "404", "500",
]

def infer_task_completion(tool_results: list[str]) -> str:
    """'completed' | 'failed' | 'partial' | 'unknown'"""
    last_results = tool_results[-5:]  # 5 derniers résultats
    has_success = any(ind in r for r in last_results for ind in COMPLETION_INDICATORS)
    has_failure = any(ind in r for r in last_results for ind in FAILURE_INDICATORS)
    
    if has_success and not has_failure:
        return "completed"
    elif has_failure and not has_success:
        return "failed"
    elif has_success and has_failure:
        return "partial"
    return "unknown"
```

---

## Nouvelles métriques à ajouter à ExtractedSession

```python
@dataclass
class ExtractedSession:
    # ... champs existants ...

    # Nouveaux — Axe 1 Efficacité
    mcp_calls_count: int                # appels MCP (tous serveurs)
    mcp_utilization_rate: float         # mcp_calls / total_tool_calls
    bash_vs_mcp_ratio: float            # bash_calls / (mcp_calls + 0.001)
    subagent_delegations: int           # appels Agent tool

    # Nouveaux — Axe 2 Progression  
    task_completion_status: str         # completed / failed / partial / unknown
    loop_events: int                    # séquences répétées > 3 mêmes tools
    loop_tool_name: str | None          # outil le plus loopé
    scope_expansions: int               # "en fait il faut aussi" patterns
    
    # Nouveaux — Axe 3 Alignement
    loi_r0_done: bool                   # search_memory.py appelé en début session
    loi_r1_violated: bool               # n8n import sans validate
    loi_r7_violated: bool               # localhost/IP directe
    skills_invoked: list[str]           # skills réellement utilisées
    systematic_debug_used: bool         # skill systematic-debugging invoquée
    verification_used: bool             # skill verification-before-completion invoquée
    
    # Nouveaux — Contexte prompt
    multi_request_messages: int         # messages user avec > 2 requêtes
    question_messages: int              # messages user purement interrogatifs
    continuation_messages: int          # "ok", "oui", "go", "continue"
    long_messages_count: int            # messages > 200 chars (specs/PRDs)
    
    # Computed score
    efficiency_score: float | None      # 0–3 (calculé localement)
    progression_score: float | None     # 0–3 (calculé localement)
    alignment_score: float | None       # 0–4 (calculé localement)
    quality_score: float | None         # 1–10 (LLM juge via n8n, ou somme locale)
```

---

## Prompt juge amélioré (n8n + LiteLLM)

Remplace le prompt simplifié de la spec Track B. Utilisé dans le workflow `session-quality-eval`.

```
Tu es un expert en efficacité d'agents IA de type Claude Code.

MÉTRIQUES STRUCTURÉES :
- Projet : {project_slug} | Modèle : {model} | Durée : {duration_minutes}min
- Tokens : {total_tokens} ({input_tokens} in / {output_tokens} out / {cache_read_tokens} cache_hit)
- Coût : ${cost_usd:.4f}

EFFICACITÉ OUTIL :
- Total tool calls : {tool_calls_count}
- Bash calls : {bash_calls_total} dont {bash_avoidable} évitables (grep/find/cat/ls)
- MCP calls : {mcp_calls_count} (utilisation : {mcp_utilization_rate:.0%})
- Subagents délégués : {subagent_delegations}

PROGRESSION :
- Statut inféré : {task_completion_status}
- Corrections utilisateur : {correction_signals}
- Loops détectés : {loop_events} (outil : {loop_tool_name})
- Auto-compacts (overflow contexte) : {compact_count}

ALIGNEMENT DIRECTIVES :
- R0 mémoire consultée : {loi_r0_done}
- Violation R1 (n8n sans validate) : {loi_r1_violated}
- Violation R7 (IP directe/localhost) : {loi_r7_violated}
- Skills invoquées : {skills_invoked}
- systematic-debugging utilisé : {systematic_debug_used}
- verification-before-completion : {verification_used}

CONTEXTE PROMPT :
- Messages multi-requêtes : {multi_request_messages}
- Messages questions : {question_messages}
- Messages continuation : {continuation_messages}

---

Évalue cette session sur 3 axes (sois sévère, la baseline est haute) :

1. EFFICACITÉ (0–3) : Outils bien choisis ? Bash évité quand mieux disponible ? MCP utilisé ?
2. PROGRESSION (0–3) : Tâche terminée ? Pas de loop ? Contexte géré proprement ?
3. ALIGNEMENT (0–4) : LOI OP respectée ? Skills activées au bon moment ?

Réponds UNIQUEMENT en JSON :
{
  "efficiency_score": 2.5,
  "progression_score": 1.5,
  "alignment_score": 3.0,
  "quality_score": 7.0,
  "verdict": "completed|partial|failed|loop",
  "top_issue": "une phrase sur le problème principal",
  "top_strength": "une phrase sur le meilleur signal"
}
```

---

## Dashboard Grafana — Panels qualité

Au-delà des métriques tokens/coût de la spec Track B :

### Panel 1 — Carte thermique qualité par projet × semaine
```promql
avg(claude_quality_score) by (project, week)
```
Révèle les projets/périodes où la qualité dégrade.

### Panel 2 — Taux de correction (baseline 25.9%)
```promql
# Alerte si > 30% (dégradation vs baseline)
sum(claude_session_correction_signals) / sum(claude_session_user_turns)
```

### Panel 3 — Ratio Bash/MCP (baseline : 806/0 = mauvais, cible < 10)
```promql
sum(claude_session_bash_calls_total) / (sum(claude_session_mcp_calls_total) + 1)
```

### Panel 4 — Taux de complétion (target > 85%)
```promql
count(claude_session_completion_status{status="completed"}) 
/ count(claude_session_completion_status)
```

### Panel 5 — Loops par semaine
```promql
sum(claude_session_loop_events) by (project)
```

### Panel 6 — Utilisation skills qualité
```promql
# Taux sessions debug qui utilisent systematic-debugging
sum(claude_session_systematic_debug_used{systematic_debug_used="true"}) 
/ sum(claude_session_is_debug_session)
```

### Panel 7 — Score qualité tendance 30j + alertes < 6
```promql
avg_over_time(claude_quality_score[7d])
```

---

## Alertes Telegram (au-delà de score < 6)

| Condition | Alerte | Fréquence |
|-----------|--------|-----------|
| `quality_score < 5` | "Session critique détectée" + top_issue | Immédiat |
| `loop_events > 3` | "Loop sévère — {loop_tool_name} × {loop_events}" | Immédiat |
| `loi_r7_violated = true` | "Violation R7 détectée — IP directe dans session {slug}" | Immédiat |
| `bash_avoidable > 50%` | "Usage Bash dégradé — {bash_avoidable}/{bash_calls_total}" | Quotidien |
| `correction_signals > 8` | "Friction élevée — {correction_signals} corrections" | Immédiat |
| Semaine : avg score < 6.5 | "Semaine dégradée — avg {score:.1f}/10 sur {project}" | Hebdo |

---

## Recherche sémantique Qdrant — Queries utiles

Avec le framework qualité, `sessions_v1` devient une base de connaissances opérationnelle :

```bash
# "Quelles sessions ressemblent à ce que je fais ?"
$MEM --query "n8n webhook binary PDF form multi-step" --repo VPAI

# "Sessions où le juge dit 'loop sévère'"
$MEM --query "loop tool Bash répété context overflow 23 compacts" --repo all

# "Sessions avec violations R7 pour audit"
$MEM --query "localhost 5678 IP directe violation LOI OP" --repo all

# "Meilleures sessions ce mois (score > 8)"
# → NocoDB: WHERE quality_score > 8 ORDER BY timestamp_start DESC
```

Le résumé Qdrant doit inclure le `verdict` et `top_issue` du juge → embedding textuel riche.

**Résumé enrichi pour embedding :**
```python
def generate_summary(session: ExtractedSession) -> str:
    return (
        f"Session {session.project_slug} ({session.model}), "
        f"durée {int(session.duration_seconds/60)}min, "
        f"statut {session.task_completion_status}, "
        f"score {session.quality_score}/10 — {session.quality_verdict}. "
        f"Problème: {session.quality_top_issue}. "
        f"Force: {session.quality_top_strength}. "
        f"Outils: {top_tools_str}, "
        f"bash évitables {session.bash_avoidable}, "
        f"MCP {session.mcp_calls_count}, "
        f"corrections {session.correction_signals}, "
        f"loops {session.loop_events}."
    )
```

---

## OpenClaw skill `session-stats` — Queries enrichies

Avec le framework qualité complet :

```
"Mes pires sessions cette semaine"
→ NocoDB: WHERE quality_score < 6 AND timestamp > now()-7j ORDER BY quality_score ASC LIMIT 5

"Quand est-ce que je boucle le plus ?"
→ NocoDB: sum(loop_events) GROUP BY hour_of_day ORDER BY sum DESC

"Quel projet a le meilleur ratio MCP ?"
→ NocoDB: avg(mcp_utilization_rate) GROUP BY project_slug

"Mes sessions les plus chères qui ont échoué"
→ NocoDB: WHERE task_completion_status = 'failed' ORDER BY cost_usd DESC LIMIT 5

"Evolution correction rate sur 30j"
→ VictoriaMetrics: rate(claude_session_correction_signals[30d])
```

---

## Ce que Track B apporte que Langfuse n'a pas

| Fonctionnalité | Langfuse | Track B (ce framework) |
|---------------|---------|----------------------|
| Trace timeline par tool call | ✅ (via spans) | ✅ Tempo |
| Score qualité LLM générique | ✅ (scores API) | ✅ + grille 3 axes sur données réelles |
| Détection loops | ❌ | ✅ `max_repeated_tool_streak` |
| Violations LOI OP | ❌ | ✅ R0/R1/R7 détectés |
| Ratio Bash/MCP | ❌ | ✅ `bash_vs_mcp_ratio` |
| Baseline calibrée sur tes sessions | ❌ | ✅ 1,945 messages analysés |
| Recherche sémantique "sessions similaires" | ❌ | ✅ Qdrant `sessions_v1` |
| Corrélation hooks version ↔ qualité | ❌ | ✅ `git_sha_hooks` |
| Alerte loop en temps réel | ❌ | ✅ Telegram immediate |
| Skill usage rate | ❌ | ✅ `skills_invoked` list |
| Statut complétion inféré | ❌ | ✅ `task_completion_status` |
| Contexte sessions similaires au démarrage | ❌ | ✅ R0 SessionStart + Qdrant |
| Stockage long terme (> 30j) | ❌ (30j max free) | ✅ NocoDB illimité |
| Confidentialité totale | ❌ (cloud externe) | ✅ 100% self-hosted |

---

## Batch rétroactif — 2,240 sessions historiques

Avant le déploiement "live" du SessionStop hook, lancer un batch sur l'historique :

```bash
python3 session-analyst.py --batch ~/.claude/projects/ \
  --since 2026-01-01 \
  --dry-run  # vérifier d'abord
  
python3 session-analyst.py --batch ~/.claude/projects/ \
  --since 2026-01-01 \
  --skip-if-exists  # idempotent
```

Cela bootstrappe :
- NocoDB avec 2,240 lignes historiques
- Qdrant `sessions_v1` avec embeddings historiques
- VictoriaMetrics avec métriques passées (backfill timestamp)
- Le juge LiteLLM tournera sur les 2,240 sessions — coût estimé : 2,240 × $0.001 = **$2.24**

---

## Modèle d'équipe — Teneur d'ordre ↔ Exécutant

La qualité n'est pas unilatérale. Deux agents, deux responsabilités.

```
Teneur d'ordre (utilisateur)     ←→     Exécutant (Claude)
       briefing                               interprétation
       feedback                               clarification
       correction                             adaptation
```

Un taux de correction à 25.9% est un signal **mixte** — on ne sait pas qui a causé la correction sans attribution. Optimiser uniquement l'exécutant sans mesurer la qualité des ordres = améliorer la moitié du problème.

### Indice d'Alignement Équipe

```
Indice Alignement = 1 - (corrections / exchanges)
Baseline actuelle : 1 - 0.259 = 0.741
Cible             : > 0.85
```

### Attribution des corrections — Architecture à 3 niveaux

**Niveau 1 — Heuristiques locales (0ms, 0€) — couvre ~75% des cas**

```python
EXECUTOR_SIGNALS = [
    r"tu n'as pas\b", r"\bj'avais dit\b", r"\bj'ai (pourtant )?dit\b",
    r"\bcomme (je t'ai |indiqué|précisé)\b", r"\btu as ignoré\b",
    r"\bencore la même (erreur|chose)\b", r"\btu refais\b",
    r"\btoujours (pareil|la même)\b",
]
BRIEFER_SIGNALS = [
    r"\ben fait (je|c')\b", r"\bj'aurais dû (préciser|dire|mentionner)\b",
    r"\bje voulais (dire|plutôt)\b", r"\boublie ce que j'ai\b",
    r"\ben fait il faut aussi\b",    # scope expansion = briefer
    r"\bj'ai oublié de (dire|préciser|mentionner)\b",
]

def attribute_correction(correction: str, prior_order: str) -> tuple[str, float]:
    c = correction.lower()
    exec_score  = sum(1 for p in EXECUTOR_SIGNALS if re.search(p, c))
    brief_score = sum(1 for p in BRIEFER_SIGNALS  if re.search(p, c))
    if exec_score > 0 and brief_score == 0:
        return ('executor', 0.9)
    if brief_score > 0 and exec_score == 0:
        return ('briefer', 0.9)
    if len(prior_order.split()) < 8:       # ordre trop court → briefer par défaut
        return ('briefer', 0.7)
    if len(correction.split()) < 5:         # correction trop courte → ambigu
        return ('ambiguous', 0.4)
    return ('ambiguous', 0.3)
```

**Niveau 2 — Score contextuel (0ms) — confidence 0.4–0.6**
- Longueur de l'ordre < 8 mots → briefer probable
- Ordre sans chemin ni contexte technique → briefer probable
- Correction contient le même verbe que l'ordre → executor probable

**Niveau 3 — LiteLLM deepseek-v3 (≤200ms, $0.004/mois) — cas ambigus uniquement**

```python
ATTRIBUTION_PROMPT_EN = """Classify this conversation exchange.

ORDER: "{order}"
ASSISTANT DID: "{assistant_summary}"
USER CORRECTION: "{correction}"

Who caused the correction?
- "executor": assistant didn't follow an explicit instruction
- "briefer": order lacked necessary context, target, or constraint
- "ambiguous": cannot determine from text alone

Reply JSON only: {{"attribution": "executor|briefer|ambiguous", "reason": "one sentence"}}"""

def safe_attribute_with_llm(order, assistant_summary, correction):
    # Scrubber AVANT envoi — voir security note
    return litellm_call(
        model="deepseek/deepseek-chat",
        prompt=ATTRIBUTION_PROMPT_EN.format(
            order=scrub_secrets(order)[:300],
            assistant_summary=scrub_secrets(assistant_summary)[:200],
            correction=scrub_secrets(correction)[:150],
        ),
        max_tokens=80, temperature=0,
    )
```

**Règle de sélection :** si `confidence < 0.6` aux niveaux 1+2 → appel niveau 3.  
**Coût estimé :** ~37 appels LLM/mois = **$0.004/mois** sous le cap $5/jour LiteLLM.

### Tableau de bord équipe (Grafana)

| Métrique | Mesure | Qui améliore |
|---------|--------|-------------|
| Indice Alignement | `1 - corrections/exchanges` | Les deux |
| Attribution Executor % | corrections causées par Claude | Exécutant |
| Attribution Briefer % | corrections causées par l'ordre | Teneur d'ordre |
| Briefing Completeness | % ordres avec chemin + critère + contexte | Teneur d'ordre |
| Evolution 30j | tendance indice alignement | Les deux |

### Rapport hebdo Telegram — Format équipe

```
Semaine 17 — Équipe VPAI :
Alignement : 0.78 (+0.04 vs S16) ↗
  Exécutant  : 3 corrections (loop×2, ignore-constraint×1)
  Teneur     : 5 corrections (missing-context×3, scope-change×2)
Pattern récurrent : prompts "fix" sans chemin → correction 67% du temps.
```

---

## Système d'injection de contexte — prompt-preprocessor.js

### Principe

```
Tu tapes : "déploie le rôle caddy"
    │
    ▼  UserPromptSubmit hook (settings.json)
    │
    ▼  prompt-preprocessor.js  ← analyse locale <5ms
    │
    ▼  Claude Code injecte en <system-reminder> AVANT le message
    │
    ▼  LLM reçoit : [injection EN] + [message utilisateur FR]
```

Le LLM voit l'injection — l'utilisateur ne la voit pas dans l'interface (mais elle est dans le JSONL).

### Langue des injections — Anglais obligatoire

| Contenu | Langue | Raison |
|---------|--------|--------|
| Réponses Claude → utilisateur | Français | CLAUDE.md |
| Injections hook → Claude | **Anglais** | Instructions machine, compliance plus fiable |
| Code, commits, configs | Anglais | Standard technique |

### Règles actuelles (1–7, existantes) + Nouvelles règles (8–11)

```javascript
// Règle 8 — Auto-inject git context si keyword deploy/commit/push
if (/déploie|deploy|push|commit|merge/i.test(msg)) {
  const status = execSync(`git -C ${cwd} status --short 2>/dev/null`).toString().trim();
  if (status) notes.push(`[GIT-CONTEXT] Modified files:\n${status}`);
}

// Règle 9 — Ambiguity flag : fix/bug sans contexte
if (/\b(fix|répare|corrige|bug|marche pas|ne fonctionne)\b/i.test(msg) && msg.length < 70) {
  notes.push(
    '[AMBIGUOUS-PROMPT] Short fix/bug request without context. ' +
    'Ask for: (1) exact error message OR (2) file path concerned before acting.'
  );
}

// Règle 10 — Memory search + injection résultat (si score > 0.65)
if (foundTopic) {
  const hits = spawnMemorySearch(msg.slice(0, 100), limit=2);
  const top = hits[0];
  const second = hits[1];
  const clearSignal = top?.score > 0.65 && (!second || top.score - second.score > 0.05);
  if (clearSignal) {
    notes.push(
      `[MEMORY-HIT score=${top.score.toFixed(2)}] ${top.relative_path}\n` +
      `Cite this source if applicable.`
    );
  }
}

// Règle 11 — Team patterns coaching (cache JSON local, <1ms)
// Déclenche si taux correction historique > 55% ET ≥ 5 occurrences
const patterns = loadTeamPatternsCache(); // /tmp/claude-team-patterns.json
const detectedType = classifyPromptType(msg);
if (patterns) {
  const rate    = patterns.correction_rate_by_type?.[detectedType] ?? 0;
  const samples = patterns.sample_size_by_type?.[detectedType] ?? 0;
  if (rate > 0.55 && samples >= 5) {
    notes.push(
      `[TEAM-PATTERN] This prompt type has ${Math.round(rate*100)}% correction rate ` +
      `(${samples} observations). Include: ${patterns.missing_context_hint[detectedType]}`
    );
  }
}
```

### Cache `/tmp/claude-team-patterns.json`

Produit par `session-analyst --update-cache` après chaque session. Lu par le hook en <1ms.

```json
{
  "updated_at": "2026-04-12T18:00:00Z",
  "sample_size": 1945,
  "correction_rate_by_type": {
    "fix_without_context": 0.67,
    "deploy_without_target": 0.52,
    "ambiguous_short": 0.71,
    "multi_request_3plus": 0.44,
    "with_file_path": 0.09,
    "with_error_message": 0.11
  },
  "sample_size_by_type": {
    "fix_without_context": 89,
    "deploy_without_target": 34,
    "ambiguous_short": 127
  },
  "missing_context_hint": {
    "fix_without_context": "file path OR exact error message",
    "deploy_without_target": "target role + environment (prod|staging)",
    "ambiguous_short": "symptom + what was already tried"
  },
  "alignment_index_trend": [0.74, 0.76, 0.78, 0.81],
  "last_7_sessions_avg_score": 7.2
}
```

---

## Analyse per-prompt post-session

`session-analyst.py` analyse chaque message utilisateur dans le JSONL :

```python
@dataclass
class PromptQualitySignal:
    message_index: int
    text: str
    length: int
    prompt_type: str            # fix_without_context | multi_request | deploy_without_target | ...
    is_ambiguous: bool
    is_multi_request: bool
    has_implicit_ref: bool      # "le fichier", "l'erreur" sans chemin
    is_correction: bool
    scope_expansion: bool       # "en fait il faut aussi"
    generates_clarification: bool   # Claude répond par une question
    correction_triggered: bool      # message SUIVANT est une correction
    attribution: str            # executor | briefer | ambiguous
    attribution_confidence: float
```

**Règle d'or :** les prompts précédés d'une correction au tour suivant = les plus instructifs.

### NocoDB table `prompt_improvements`

```
session_id          Text (FK claude_sessions)
message_index       Number
original_prompt     LongText
improved_prompt     LongText      ← généré par LiteLLM coach si correction_signals > 3
rule                Text          ← multi-request | missing-context | ambiguous | implicit-ref | no-success-criteria
attribution         Text          ← executor | briefer | ambiguous
attribution_conf    Decimal(3,2)
timestamp           DateTime
project_slug        Text
```

**Coach LiteLLM** (déclenché si `correction_signals > 3` dans la session) :

```
You are an expert in writing effective Claude Code prompts.

A user prompt triggered an immediate correction:
ORIGINAL: "{original_prompt}"
NEXT CORRECTION: "{next_message}"
CONTEXT (2 prior messages): "{context}"

Rewrite the prompt to eliminate the problem. Rules:
- Single, clear task
- Explicit success criteria
- Sufficient context (paths, errors, service name)
- ≤ 3 sentences

Reply JSON only:
{{"problem": "what was missing", "improved": "rewritten prompt", 
  "rule": "multi-request|missing-context|ambiguous|implicit-ref|no-success-criteria"}}
```

---

## Seuils validés — Recherche 2025-2026

| Paramètre | Valeur | Source |
|-----------|--------|--------|
| Qdrant injection threshold | **0.65** cosine similarity | Industry baseline 2025 |
| Qdrant margin (top1 vs top2) | **+0.05** | Évite injections ambiguës |
| Coaching trigger rate | **55%** correction rate | KnowBe4 + evidentlyai 2025 |
| Coaching min observations | **≥ 5** occurrences | Évite faux positifs statistiques |
| Max coaching triggers/jour | **3** | Alert fatigue prevention |
| LLM attribution threshold | confidence **< 0.6** → appel niveau 3 | Trade-off précision/coût |

```python
# session-analyst/config/destinations.env
QDRANT_INJECT_THRESHOLD      = 0.65
QDRANT_MARGIN_THRESHOLD      = 0.05
COACHING_RATE_THRESHOLD      = 0.55
COACHING_MIN_OBSERVATIONS    = 5
ALERT_FATIGUE_MAX_PER_DAY    = 3
ATTRIBUTION_LLM_THRESHOLD    = 0.60   # confidence < 0.60 → appel LiteLLM
LLM_ATTRIBUTION_MODEL        = "deepseek/deepseek-chat"
LLM_COACH_MODEL              = "deepseek/deepseek-chat"
```

---

## Ce que Track B apporte que Langfuse n'a pas (mis à jour)

| Fonctionnalité | Langfuse | Track B |
|---------------|---------|---------|
| Trace timeline tool calls | ✅ | ✅ Tempo |
| Score qualité LLM | ✅ | ✅ Grille 3 axes calibrée |
| Détection loops | ❌ | ✅ |
| Violations LOI OP | ❌ | ✅ R0/R1/R7 |
| Ratio Bash/MCP | ❌ | ✅ |
| Modèle équipe executor/briefer | ❌ | ✅ Attribution 3 niveaux |
| Indice Alignement équipe | ❌ | ✅ Trend 30j |
| Injection contexte temps réel | ❌ | ✅ Hook règles 1–11 |
| Coaching per-prompt | ❌ | ✅ prompt_improvements NocoDB |
| Patterns historiques injectés | ❌ | ✅ Cache JSON local <1ms |
| Amélioration prompts automatique | ❌ | ✅ LiteLLM coach post-session |
| Baseline calibrée sur tes sessions | ❌ | ✅ 1,945 messages analysés |
| Stockage long terme | ❌ 30j max | ✅ NocoDB illimité |
| Confidentialité | ❌ cloud | ✅ 100% self-hosted |

---

---

## Coach — Déploiement progressif + Mesure de qualité

### Décision architecture

**Mode retenu : Option C semi-auto avec smoke test 2 semaines**

```
SessionStop → session-analyst détecte correction_signals > 3
           → génère coaching (LiteLLM deepseek)
           → stocke dans NocoDB table coach_log (review_pending = True)
           → N'injecte PAS encore dans team-patterns.json
           → Envoie sur Telegram : "[COACH-DRAFT] ..." + boutons 👍 👎

Après 2 semaines : analyse human_rating → si précision > 70% → activer injection
Activation : COACH_MODE = "observe" → "active" dans config session-analyst
```

### Table NocoDB `coach_log`

```
session_id           Text (FK claude_sessions)
generated_at         DateTime
coaching_text        LongText      ← ce que le coach aurait injecté
attribution          Text          ← briefer | executor | ambiguous
target_pattern       Text          ← ex: fix_without_context
evidence             LongText      ← extrait JSONL cité comme preuve
baseline_rate        Decimal(4,3)  ← taux du pattern avant coaching
review_pending       Checkbox      ← True pendant smoke test
human_rating         Number        ← NULL | 0 (irrelevant) | 1 (ok) | 2 (spot-on)
human_comment        LongText      ← feedback libre
outcome_delta        Decimal(4,3)  ← post_rate - baseline_rate (calculé J+7)
outcome_status       Text          ← improved | no_change | degraded | pending
```

---

## Mesure de qualité du coaching (méta-qualité)

**Problème** : un coach qui donne de mauvais conseils avec confiance est pire que l'absence de coach. Le coaching lui-même doit être mesuré.

### Dimension 1 — Cohérence immédiate (au moment de génération)

```python
@dataclass
class CoachingQualitySignals:
    evidence_cited: bool           # cite un exemple exact du JSONL
    attribution_confidence: float  # confiance attribution (0-1)
    advice_specificity: int        # 0=vague | 1=pattern nommé | 2=pattern+exemple+réécriture
    session_sample_size: int       # sessions ayant alimenté ce coaching

def is_low_quality_draft(s: CoachingQualitySignals) -> bool:
    return (
        not s.evidence_cited or
        s.advice_specificity == 0 or
        s.session_sample_size < 5
    )
# Si True → ne pas envoyer Telegram, logger coach_skipped_low_quality
```

### Dimension 2 — Validité différée (J+7)

```python
def compute_coaching_outcome(coaching_id: str, sessions_after: list) -> str:
    coaching = fetch_coach_log(coaching_id)
    post_sessions = [s for s in sessions_after
                     if s.timestamp > coaching.generated_at + timedelta(days=1)]
    post_rate = compute_pattern_rate(post_sessions, coaching.target_pattern)
    delta = post_rate - coaching.baseline_rate
    if delta < -0.10: return "improved"
    if delta > +0.05: return "degraded"
    return "no_change"
```

### Dimension 3 — Pertinence subjective (smoke test 14 jours)

Boutons Telegram sur chaque draft :
- 👍 spot-on → human_rating = 2
- 👌 ok/générique → human_rating = 1
- 👎 hors cible → human_rating = 0

Workflow n8n : webhook Telegram → PATCH `coach_log.human_rating`

### Script d'analyse smoke test

```bash
python3 scripts/coach-audit.py --since 2026-04-12 --mode smoke-test
```

Sortie :
```
Coach Audit — 2 semaines
Générés : 23 | Skipped low-quality : 4 | Envoyés : 19 | Notés : 15

Précision : spot-on=47% + ok=33% = 80% >= seuil 70% → ACTIVER injection
Attribution : executor 80% | briefer 80% | ambiguous 50% ← améliorer prompt
```

### Variables d'ajustement prompt coach si précision < 70%

| Problème | Ajustement |
|---------|-----------|
| Attribution toujours "briefer" | "When in doubt, prefer 'ambiguous' over 'briefer'" |
| Exemples vagues | "Always quote the exact message text from the JSONL" |
| Conseils génériques | "Suggest a concrete rewrite of the original prompt" |
| Faux positifs sessions courtes | "Minimum 8 exchanges before generating coaching" |

Le prompt coach est versionné dans le repo avec changelog et effet mesuré.

### Flags de déploiement

```python
# session-analyst/config/destinations.env
COACH_MODE                    = "observe"   # "observe" | "active"
COACH_SMOKE_TEST_DAYS         = 14
COACH_ACTIVATION_THRESHOLD    = 0.70
COACH_QUALITY_MIN_SPECIFICITY = 1
```

---

*Framework finalisé 2026-04-12*
*Coaching : Option C semi-auto, smoke test 14j, activation si précision > 70%*
*Score qualité : Option A local (axes 1-3) pour 30 premiers jours, puis hybride LLM*
*Seuils : Qdrant 0.65, coaching 55%, margin +0.05*
*Langue injections : anglais (instructions machine)*
*Intégrer dans : Plan 10-B1 (parser + hook) + Plan 10-B3 (juge + dashboard + coach)*
