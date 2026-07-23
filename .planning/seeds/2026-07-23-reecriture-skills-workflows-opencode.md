# Seed — réécrire skills/workflows Claude Code en version allégée pour OpenCode

**Date** : 2026-07-23
**Type** : seed (idée capturée, PAS planifiée — nécessite sa propre session de planification)
**Déclencheur** : debug tool-calling OpenCode→Banga (voir `.planning/handoffs/2026-07-23-opencode-banga-temperature-tool-calling.md`)

## Constat qui motive ce chantier

En debuggant pourquoi `banga/coder` (14B) rejette la vraie requête OpenCode
(`exceed_context_size_error`), mesure précise du system prompt réel envoyé par l'agent
`build` d'OpenCode : **38 743 caractères, dont 74% est du bruit sans rapport avec un
modèle local Qwen** :

| Section | Taille | Utile pour Qwen/Banga ? |
|---|---|---|
| Instructions génériques OpenCode | 8 895 car. | Oui |
| `~/.claude/CLAUDE.md` (doctrine Claude Code globale — routing Opus/Sonnet/Fable, GSD) | 8 879 car. | Non |
| `VPAI/AGENTS.md` (règle R0 memory-first du projet) | 1 186 car. | Oui |
| Catalogue complet des skills Claude Code (`<available_skills>`) | **19 783 car.** | Non (verbeux, écrit pour Claude) |

Le catalogue skills à lui seul (51% du prompt) liste tous les skills installés
(`gsd-*`, `caveman`, `ui-ux-pro-max` avec ses "67 styles, 96 palettes"...) avec leurs
descriptions complètes — écrites pour être comprises et déclenchées par un modèle
Claude, pas pour un modèle local à faible contexte.

**Mitigation immédiate déjà déployée** (pas ce chantier) : `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=1`
+ `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` sur le service OpenCode — coupe tout, brutal
mais fonctionnel. Ce seed est l'option plus fine : **garder l'esprit des skills/workflows
mais dans une forme adaptée à OpenCode**, pas les jeter.

## Objectif du chantier (à définir précisément en session dédiée)

Réécrire les personnalisations Claude Code (skills `~/.claude/skills/`, workflows,
conventions CLAUDE.md) en une **version parallèle allégée destinée à OpenCode** :
- Descriptions courtes (1-2 lignes déclencheur, pas les pavés actuels)
- Probablement un sous-ensemble seulement (les skills GSD/superpowers présupposent des
  capacités/outils Claude Code — Task tool, subagents nommés, hooks — qui n'existent
  probablement pas tels quels côté OpenCode)
- Un CLAUDE.md/AGENTS.md "OpenCode-native" séparé du global waza (qui parle de routage
  Opus/Sonnet/Fable — zéro sens pour un modèle Qwen local)

## Pourquoi PAS traité maintenant

- Chantier transverse (`~/.claude/skills/` est global, pas scopé à VPAI)
- Gros volume (potentiellement 80+ skills/commandes à trier : lesquels ont un sens pour
  un modèle local, lesquels sont Claude-only par construction)
- Dépend d'abord de la résolution du blocage tool-calling réel (voir handoff ci-dessus,
  §2) — réécrire les skills ne sert à rien si `coder`/`coder_longctx` ne peuvent pas
  fiablement appeler d'outils du tout via OpenCode

## Prérequis avant de lancer ce chantier

1. Tool-calling Banga fiable via OpenCode (blocage actuel : patch autoparser llama.cpp
   ne couvre pas le format que Qwen émet avec un jeu d'outils réel à 10 entrées — voir
   handoff §2, chantier séparé côté `banga`)
2. Décider du périmètre : réécrire TOUS les skills, ou seulement ceux qu'on veut
   réellement utiliser via un agent local (probablement un sous-ensemble restreint —
   pas caveman/gsd-*/interface-design qui présupposent l'écosystème Claude Code)

## Prochaine étape suggérée
Quand prêt : `/gsd-new-project` ou seed → discuss-phase dédié, PAS une exécution
inline — trop large pour une tâche ad-hoc.
