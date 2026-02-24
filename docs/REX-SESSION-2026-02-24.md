# REX — Session 11 — 2026-02-24

**Durée** : ~14h (sessions multiples)
**Objectif initial** : Corriger `spawn docker EACCES` + faire fonctionner les sous-agents OpenClaw
**Résultat** : Stack fonctionnelle, sous-agents actifs, 10 bugs corrigés

---

## Chronologie et Bugs Corrigés

### REX-49a — Image `openclaw-sandbox:bookworm-slim` absente

**Symptôme** : `spawn docker EACCES` au lancement de tout sous-agent via `sessions_spawn`.

**Cause** : L'image `openclaw-sandbox:bookworm-slim` n'avait jamais été construite sur le host.
Le rôle Ansible ne la construisait pas — lacune depuis le début.

**Fix** : Ajout de 5 tâches dans `roles/openclaw/tasks/main.yml` :
1. Check si l'image existe (`docker image inspect`)
2. Créer le répertoire de build (`/opt/<project>/configs/openclaw/build/openclaw-sandbox`)
3. Extraire `Dockerfile.sandbox` depuis l'image OpenClaw (`docker run --rm --entrypoint cat`)
4. Écrire le Dockerfile dans le répertoire de build
5. Build l'image avec `community.docker.docker_image`

**Idempotence** : Gated sur `openclaw_sandbox_image_check.rc != 0` — ne rebuild pas si l'image existe.

---

### REX-49b — `spawn docker EACCES` : binaire docker absent du container OpenClaw

**Symptôme** : Même avec l'image sandbox construite, `EACCES` persiste sur `spawn("docker", ...)`.

**Cause** : OpenClaw appelle `child_process.spawn("docker", ["run", ...])` (pas dockerode SDK).
`PATH` dans l'image = `/root/.bun/bin:/usr/local/sbin:/usr/local/bin:...`
`/root/.bun/bin` = mode 700 (root-owned, inaccessible à node:1000).
`execvp("docker")` → EACCES au premier répertoire PATH → ne cherche pas plus loin.

**Fix** : Monter le binaire docker du host dans le container :
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
  - /usr/bin/docker:/usr/local/bin/docker:ro
```
`/usr/local/bin` vient APRÈS `/root/.bun/bin` dans PATH → node trouve docker sans passer par le répertoire inaccessible.

**Fichier** : `roles/docker-stack/templates/docker-compose.yml.j2`

---

### REX-50 — Crédits Anthropic + OpenRouter épuisés

**Symptôme** : Après que spawn EACCES soit résolu, les sous-agents échouent :
- `AnthropicException: credit balance too low`
- `RouterRateLimitError: deepseek-v3-free cooldown 60s`

**Cause** : Crédits Anthropic et OpenRouter épuisés simultanément.

**Fix temporaire** : Basculer tous les agents sur `openai/gpt-4o-mini` (OpenAI direct, compte séparé).

---

### REX-51 — `custom-litellm/gpt-4o-mini` ≠ `openai/gpt-4o-mini`

**Symptôme** : Modèle configuré comme `custom-litellm/gpt-4o-mini` mais l'utilisateur voulait OpenAI direct.

**Cause** : `custom-litellm/xxx` passe par le proxy LiteLLM (toujours soumis aux crédits OpenRouter/Anthropic si LiteLLM reroute). `openai/xxx` appelle OpenAI directement (provider séparé dans `openclaw.json`).

**Fix** :
1. `roles/openclaw/defaults/main.yml` : tous les modèles → `openai/gpt-4o-mini`
2. `roles/openclaw/templates/openclaw.env.j2` : expose `OPENAI_API_KEY={{ openai_api_key }}`
3. `roles/openclaw/templates/openclaw.json.j2` : ajoute provider `openai` avec `baseUrl: "https://api.openai.com/v1"` et `gpt-4o-mini` + `gpt-4o`

**Note** : Budget LiteLLM non actif pour les appels via le provider `openai` direct. Surveiller dans le dashboard OpenAI.

---

### REX-52 — Handler `state: restarted` ne relit pas `env_file`

**Symptôme** : Après déploiement de `OPENAI_API_KEY` dans l'env file, OpenClaw fail au démarrage : `MissingEnvVarError: Missing env var "OPENAI_API_KEY"`. L'env file a bien été mis à jour.

**Cause** : Le handler Ansible utilisait `state: restarted` = `docker compose restart`. Cette commande **ne relit pas** les `env_file` — le container redémarre avec le même environnement que la dernière fois qu'il a été `up`.

**Fix** : Changer le handler en `state: present + recreate: always` = `docker compose up -d --force-recreate`. Docker Compose re-lit l'env_file et recrée le container avec le nouvel environnement.

```yaml
- name: Restart openclaw stack
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - openclaw
    state: present
    recreate: always
  become: true
```

**Fichier** : `roles/openclaw/handlers/main.yml`

---

### REX-53 — `workspaceAccess: "none"` bloque l'écriture des sous-agents

**Symptôme** : Les sous-agents (writer, builder) produisent des erreurs :
```
write failed: Sandbox path is read-only; cannot create directories: /workspace
```

**Cause** : Config sandbox `workspaceAccess: "none"` + `readOnlyRoot: true` → `/workspace` dans le container sandbox est read-only. Les agents ne peuvent pas créer de fichiers.

**Valeurs valides** (découvertes en parsant le schéma Zod depuis `/app/dist/config-T-YRaqlE.js`) :
- `"none"` — pas d'accès workspace (défaut)
- `"ro"` — workspace monté en lecture seule
- `"rw"` — workspace monté en lecture/écriture

**Note** : `"write"` → `Invalid input` (erreur config). La valeur correcte est `"rw"`.

**Fix** :
- Default sandbox : `workspaceAccess: "rw"` (writer, builder, artist, tutor, cfo, explorer peuvent écrire)
- Messenger sandbox override : `workspaceAccess: "none"` (il n'a besoin que d'API calls, pas de FS)

**Fichier** : `roles/openclaw/templates/openclaw.json.j2`

---

### REX-54 — Routing Marketer absent — concierge délègue au Messenger

**Symptôme** : Une demande de type "marketing" est routée par le concierge vers le Messenger (Hermes) au lieu du Marketer.

**Cause** : Le tableau de routing dans `IDENTITY.md` du concierge n'avait pas d'entrée pour le Marketer. Sans trigger explicite, le concierge tombait sur la règle catch-all "demande longue → Messenger".

**Fix** : Ajouter dans le tableau de routing de `IDENTITY.md.j2` du concierge :
```markdown
| marketing, prospection, acquisition, campagne, promotion, publicite, audience, growth | `marketer` | Toujours deleguer |
```

**Fichier** : `roles/openclaw/templates/agents/concierge/IDENTITY.md.j2`

---

## État de la Stack au 2026-02-24

### Fonctionnel ✅

| Composant | État |
|---|---|
| OpenClaw gateway | Opérationnel — `openai/gpt-4o-mini` direct |
| Telegram bot (@WazaBangaBot) | Actif |
| Sandbox image `openclaw-sandbox:bookworm-slim` | Construite, 4 containers actifs |
| Docker socket + CLI binary montés | ✅ |
| Spawn sous-agents | Fonctionnel (EACCES résolu) |
| Workspace write (sandbox rw) | Actif |
| Routing Marketer | Corrigé |

### Modèles actifs

Tous les agents utilisent `openai/gpt-4o-mini` (OpenAI direct, bypass LiteLLM).
À restaurer après rechargement des crédits :
- Concierge → `custom-litellm/deepseek-v3-free` ou `kimi-k2`
- Builder/Maintainer → `custom-litellm/qwen3-coder`
- Writer/Artist/Explorer → `custom-litellm/deepseek-v3-free`

### En cours / À faire

| Tâche | Statut |
|---|---|
| Test spawn end-to-end via Telegram | 🔄 En cours |
| Vérification Kaneo task tracking | 🔄 En cours |
| Credit error alerting (LiteLLM webhook + IDENTITY.md) | 📋 Planifié — `docs/plans/2026-02-24-credit-error-alerting.md` |

---

## Variables Critiques à Retenir

```yaml
# Valeurs valides workspaceAccess (OpenClaw v2026.2.22)
# none | ro | rw  (PAS "write", "read", "readwrite")
openclaw_sandbox_workspaceAccess: "rw"

# Provider openai direct dans openclaw.json — requiert OPENAI_API_KEY dans env
# Différent de custom-litellm/gpt-4o-mini (proxy LiteLLM)
openclaw_default_model: "openai/gpt-4o-mini"

# Handler openclaw — TOUJOURS recreate: always pour relire env_file
# state: restarted NE relit PAS env_file
```

---

## Commits Session 11

```
cc53a7a fix(openclaw): workspaceAccess rw + routing marketer + messenger none
e0e7aa4 revert(openclaw): workspaceAccess none — "write" est invalide
a2fdb21 fix(openclaw): workspaceAccess write — (revert car invalide)
af45ab3 fix(openclaw): handler recreate: always — prend en compte les changements env_file
e34c7af docs(plans): design + plan implémentation credit error alerting
d017d8f fix(openclaw): openai/gpt-4o-mini direct — bypass LiteLLM pour résilience
45f3edf chore(openclaw): bascule tous les agents sur gpt-4o-mini
fe9f868 fix(openclaw): monter docker CLI depuis le host — corrige spawn EACCES (REX-49)
1cbfbb2 fix(openclaw): build image sandbox manquante — corrige spawn docker EACCES
```
