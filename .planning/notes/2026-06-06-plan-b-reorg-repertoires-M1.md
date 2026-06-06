# Plan B / M1 — Refactorisation des répertoires de travail (`~/work/`)

> **Statut** : plan exécutable. À traiter dans une **session dédiée** (déplace 24 repos + met à jour des chemins absolus dans plusieurs configs — pas en fin de chat).
> **Contexte** : différé du rebuild mémoire (cf `.planning/notes/2026-06-05-memory-rebuild-execution-checkpoint.md` §7 « Plan B à écrire »). Le manifeste **M5 existe déjà** : `docs/runbooks/MEMORY-TAXONOMY-MANIFEST.md`.
> **Sûr pour la mémoire** : `node_id`/`relative_path`/`repo` sont **path-indépendants** (relatifs au repo) → déplacer une racine ne change RIEN dans `memory_v2`. Seuls les **chemins absolus** des configs/outillage changent.

## 1. État actuel (24 repos git dispersés)

| Emplacement | Repos |
|---|---|
| `~/` | VPAI, flash-studio (+`flash-infra` imbriqué), flash-suite, jarvis, macgyver, DOCS (+litellm/n8n/openclaw-docs imbriqués) |
| `~/projects/` | claw-code, typebot-docs |
| `~/projects/saas/` | ase, fantrad, hawkeye, koodia, mediahall, podpilot, riposte, simubot, story-engine, trek, vps, zimboo |

## 2. Layout cible proposé (`~/work/`, par wing — aligné taxonomie M5)

```
~/work/
  infra/      VPAI
  saas/       flash-studio (+flash-infra), flash-suite, story-engine, fantrad,
              hawkeye, riposte, podpilot, ase, koodia, mediahall, simubot, trek, vps, zimboo
  refdocs/    DOCS (+litellm/n8n/openclaw-docs), typebot-docs
  tools/      jarvis, macgyver, claw-code
```

Wings = ceux du manifeste M5 (infra/saas/refdocs/tools). Repos imbriqués (flash-infra, *-docs sous DOCS) **restent imbriqués** (sous-modules de fait).

## 3. Décisions ouvertes (à trancher en session)

1. **VPAI** : le déplacer (`~/work/infra/VPAI`) est le plus à **fort ripple** (CLAUDE.md, venv `.venv`, `.planning`, cwd des sessions, remote git, scripts Ansible, hooks `~/.claude` qui citent `/home/mobuone/VPAI`). → **Recommandation : laisser VPAI à `~/VPAI` + symlink** `~/work/infra/VPAI → ~/VPAI`, OU le déplacer en acceptant la maj exhaustive. À décider.
2. **Repos non-mémoire** (ase, koodia, mediahall, simubot, trek, vps, zimboo) : déplacés aussi (cohérence) ou laissés ? Ils ne sont pas dans `sources.yml`.
3. **Symlinks de compat** aux anciens chemins (`~/projects/saas/* → ~/work/saas/*`) : OUI par défaut (filet pour tout outillage non recensé), à retirer après stabilisation.

## 4. Procédure d'exécution (idempotente, par lots)

```bash
mkdir -p ~/work/{infra,saas,refdocs,tools}
# Exemple saas (git mv = rien, c'est un déplacement FS ; les repos restent intacts) :
mv ~/projects/saas/story-engine ~/work/saas/story-engine
mv ~/flash-studio ~/work/saas/flash-studio
# … (un mv par repo, cf layout §2)
# Symlinks de compat (optionnel) :
ln -s ~/work/saas/story-engine ~/projects/saas/story-engine
```
> Vérifier `git -C <nouveau_chemin> status` après chaque lot (le repo doit être sain, remote intact).

## 5. Checklist chemins absolus à mettre à jour (le vrai travail)

| Fichier | Clé | Action |
|---|---|---|
| `/opt/workstation/configs/ai-memory-worker/config.yml` | `repos:` (2) | → `~/work/saas/flash-studio`, `~/work/saas/story-engine` |
| `/opt/workstation/configs/ai-memory-worker/sources.yml` | `root:` (9) | → nouveaux chemins par wing |
| `~/.claude/CLAUDE.md` (global) | « Tes fichiers : `/home/mobuone/projects/` », workspace | maj |
| `VPAI/CLAUDE.md` (projet) | refs `/home/mobuone/projects/saas/...`, SSH paths | maj |
| `~/.claude/hooks/*` , `.mcp.json` filesystem | chemins éventuels | grep + maj |
| systemd-user units, scripts worker | chemins repos | grep `/home/mobuone/projects` partout |

**Commande d'audit ripple** (à lancer en session) :
```bash
grep -rIl "/home/mobuone/\(projects\|flash-studio\|flash-suite\|jarvis\|macgyver\|DOCS\)" \
  ~/.claude ~/VPAI /opt/workstation/configs /opt/workstation/ai-memory-worker 2>/dev/null
```

## 6. Validation post-reorg

1. `git -C <chaque repo déplacé> status` → sain, remote OK.
2. Worker : `index.py --preflight-only` (valide que les `root:` de sources.yml existent).
3. Recherche froide : `search_memory.py --query "..."` → toujours des résultats (memory_v2 inchangée, paths relatifs).
4. **PAS de ré-ingestion nécessaire** (node_id path-indépendant) — c'est tout l'intérêt d'avoir différé M1 après M3/M4.
5. Session Claude : confirmer que les hooks R0/cwd fonctionnent depuis le nouveau layout.

## 7. Rollback

Les repos sont intacts (simple déplacement FS). Rollback = `mv` inverse + restaurer les chemins dans les configs (git diff). Aucune donnée perdue.

## 8. Lien

Manifeste taxonomie (M5, fait) : `docs/runbooks/MEMORY-TAXONOMY-MANIFEST.md`. Rebuild M3/M4 (fait) : `docs/rex/REX-SESSION-2026-06-06-memory-bulk-gpu-bf16.md`.
