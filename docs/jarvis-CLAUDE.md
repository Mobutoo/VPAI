# CLAUDE.md — Jarvis Bridge

## Identite du Projet

**Jarvis Bridge** : daemon Python qui connecte Telegram a Claude Code CLI.
Version maison d'OpenClaw — multi-agent, memoire Qdrant, tracking Plane.

## Plan d'implementation

**LIRE EN PREMIER** : `docs/plans/2026-03-01-jarvis-bridge-plan.md`
Ce plan contient 17 tasks avec le code complet. Execute-le task par task.

**Design doc** : `docs/plans/2026-03-01-jarvis-bridge-design.md`

## Environnement

| Element | Valeur |
|---|---|
| Machine | Waza — RPi5 16GB ARM64, Ubuntu 24.04 |
| Python | 3.12.3 (`/usr/bin/python3`) |
| Claude CLI | 2.1.62 (`/usr/bin/claude`), auth OAuth |
| Venv | `/home/mobuone/jarvis/.venv/` |
| Projet | `/home/mobuone/jarvis/` |
| Git remote | `git@github-seko:Mobutoo/jarvis.git` |
| Secrets | `~/.jarvis.env` (NE JAMAIS lire ou afficher son contenu) |

## Services accessibles

| Service | URL | Auth |
|---|---|---|
| Qdrant | `https://qd.ewutelo.cloud` | `QDRANT_API_KEY` header `api-key` |
| Plane | `https://work.ewutelo.cloud` | `PLANE_API_TOKEN` header `X-Api-Key` |
| Telegram | `https://api.telegram.org/bot{token}/` | `TELEGRAM_BOT_TOKEN` |
| LiteLLM | `https://llm.ewutelo.cloud` | VPN only |
| n8n | `https://mayi.ewutelo.cloud` | VPN only |

## Conventions

### Python
- **Python 3.12+** — utiliser `from __future__ import annotations` dans chaque fichier
- **Type hints** sur toutes les signatures de fonctions
- **Async/await** partout (asyncio event loop)
- **httpx.AsyncClient** pour tous les appels HTTP (jamais requests, jamais urllib)
- **Pas de classes inutiles** — utiliser des dataclasses ou des dicts simples
- **Logging** : `logging.getLogger(__name__)` dans chaque module
- **Pas de print()** — toujours logger

### Securite
- **JAMAIS de secrets en clair** dans le code, les logs, ou les commits
- **Secrets** : charges depuis `~/.jarvis.env` via python-dotenv
- **Qdrant** : `httpx verify=False` (Tailscale SSL, pas de CA locale)
- **Telegram** : whitelist stricte sur `TELEGRAM_CHAT_ID`
- **Claude CLI agents (runtime)** : jamais `bypassPermissions` — utiliser `acceptEdits` + `--settings`

### Git
- **Remote** : `git@github-seko:Mobutoo/jarvis.git`
- **Branche** : `main`
- **Commits** : prefixes conventionnels (`feat:`, `fix:`, `test:`, `docs:`, `chore:`)
- **Jamais de secrets dans les commits** — verifier avant chaque commit

### Tests
- **pytest + pytest-asyncio** (`@pytest.mark.asyncio`)
- **Mocks** : `unittest.mock.AsyncMock` pour httpx et subprocess
- **Lancer** : `source .venv/bin/activate && python3 -m pytest tests/ -v`

### Claude CLI
- Foreground : `claude -p --output-format json --resume <sid> "message"`
- Worker : `claude -p --output-format stream-json --verbose "message"`
- `--append-system-prompt "$(cat agents/<agent>/CLAUDE.md)"`
- `--settings config/settings-<agent>.json`
- `--max-budget-usd N` pour les workers
- Stream JSON types : `system` (init, session_id), `assistant` (content), `result` (final)

## Structure

```
jarvis/
  bridge/          # Code Python du daemon
  agents/          # CLAUDE.md par agent (concierge, builder, ops, writer, explorer)
  config/          # settings-<agent>.json (permissions CLI par agent)
  workspace/       # Cree dynamiquement par les workers (gitignored)
  state/           # Etat chaud ephemere : offset.txt, workers.json (gitignored)
  tests/           # pytest
  docs/plans/      # Design doc + plan d'implementation
```

## Commandes

```bash
source .venv/bin/activate       # Toujours activer le venv
make install                    # Installer dependances + creer repertoires
make test                       # Lancer les tests
make start                      # Demarrer le service systemd
make stop                       # Arreter le service
make logs                       # Voir les logs (journalctl)
```

## Strategie d'execution (gestion du contexte)

Ce plan a 17 tasks. Le contexte Sonnet (~200K tokens) ne peut PAS les contenir toutes.
Execute en 3 phases avec session fraiche entre chaque phase.

> **Note permission-mode** : `bypassPermissions` est utilise UNIQUEMENT pour la session
> executeur (developpement sur RPi5 isole). Les agents Jarvis Bridge en production
> utilisent `acceptEdits` + `--settings` (voir plan Task 5 et Task 14).

### Phase 1 — Fondations (Tasks 1-6)

**Session 1** : Scaffold, config, logging, telegram, claude_runner, memory.

```
Prompt de lancement :
  cd /home/mobuone/jarvis
  claude --permission-mode bypassPermissions
  > Lis docs/plans/2026-03-01-jarvis-bridge-plan.md, Tasks 1 a 6. Execute-les une par une.
```

- A la fin de Task 6 : `git add -A && git commit -m "feat: phase 1 — scaffold + core modules (tasks 1-6)"`
- Verifier : `python3 -c "from bridge.config import load_config; from bridge.memory import QdrantMemory; print('OK')"`
- Quitter la session (`/exit` ou Ctrl+C)

### Phase 2 — Integration (Tasks 7-12)

**Session 2** (contexte frais) : approvals, plane_client, workers, dispatcher, server, main.

```
Prompt de lancement :
  cd /home/mobuone/jarvis
  claude --permission-mode bypassPermissions
  > Continue l'implementation de Jarvis Bridge. Lis docs/plans/2026-03-01-jarvis-bridge-plan.md, Tasks 7 a 12.
  > Le code des Tasks 1-6 est deja en place (voir git log). Execute Tasks 7 a 12.
```

- A la fin de Task 12 : `git add -A && git commit -m "feat: phase 2 — agents + integration (tasks 7-12)"`
- Verifier : `source .venv/bin/activate && python3 -m pytest tests/ -v`
- Quitter la session

### Phase 3 — Finalisation (Tasks 13-17)

**Session 3** (contexte frais) : tests complets, agent configs, settings, systemd, PRD.

```
Prompt de lancement :
  cd /home/mobuone/jarvis
  claude --permission-mode bypassPermissions
  > Continue l'implementation de Jarvis Bridge. Lis docs/plans/2026-03-01-jarvis-bridge-plan.md, Tasks 13 a 17.
  > Le code des Tasks 1-12 est deja en place (voir git log). Execute Tasks 13 a 17, puis lance la Final Verification Checklist.
```

- A la fin : `python3 -m pytest tests/ -v && git add -A && git commit -m "feat: phase 3 — tests + deploy (tasks 13-17)"`

### Regles de gestion du contexte en cours de session

- **Utiliser `/compact`** si le contexte depasse ~70% (le CLI le signale)
- **Maximum 1 compaction par session** — apres la 2eme compaction, la qualite se degrade
- **Ne pas lire le plan entier d'un coup** — lire uniquement la section de la task en cours
- **Commit souvent** : chaque task terminee = un commit (le plan contient les commandes git)
- **Si le CLI ralentit ou hallucine** : quitter, ouvrir une nouvelle session avec le prompt de phase

### Commande unique de lancement

Pour chaque phase, la commande complete est :

```bash
cd /home/mobuone/jarvis
claude --permission-mode bypassPermissions
```

Le fichier `.claude/settings.local.json` est deja configure avec les permissions necessaires (voir ci-dessous).

## Pieges connus

1. `--output-format stream-json` requiert `--verbose` avec `-p`
2. `--verbose` ajoute des lignes non-JSON dans stdout — filtrer avec `line.startswith("{")`
3. `claude -p` lit le CLAUDE.md du cwd — le cwd du foreground doit etre `/home/mobuone/jarvis`
4. Chaque ligne du stream-json est un objet JSON independant (pas de tableau)
5. `session_id` change a chaque appel meme avec `--resume` — toujours sauvegarder le nouveau
6. `--append-system-prompt` ne doit PAS etre utilise avec `--resume` (doublon de prompt)
7. `claude -p` est NON-INTERACTIF — pas de stdin pour approuver/refuser. Securite = `--settings`
8. `sentence-transformers` charge ~90MB en RAM — charger paresseusement dans un thread (`asyncio.to_thread`)
9. ARM64 : installer `torch` depuis `--index-url https://download.pytorch.org/whl/cpu` AVANT sentence-transformers
10. Qdrant via Tailscale necessite `verify=False` (pas de CA locale) + `urllib3.disable_warnings()`
11. Les boutons Telegram InlineKeyboard necessitent `answerCallbackQuery` pour enlever le spinner
12. Le RPi5 n'a pas de swap — gerer la RAM avec attention (max 2 workers simultanes)
13. Toujours `process.terminate()` puis `process.kill()` sur timeout (SIGTERM avant SIGKILL)
14. Utiliser `asyncio.Lock()` pour le foreground (pas un bool — race condition)
