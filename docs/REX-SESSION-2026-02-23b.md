# REX — Session 2026-02-23b (Session 10)

> **Theme** : OpenClaw v2026.2.22 — Bot Telegram inactif, plugin architecture breaking change, modeles OpenRouter epuises
> **Duree** : ~4h
> **Resultat** : Bot Telegram @WazaBangaBot operationnel, erreurs diagnostic eliminees, stack migree sur modeles :free OpenRouter

---

## Problemes Resolus

### REX-45 — OpenClaw v2026.2.22 : plugin telegram desactive par defaut

**Symptome** : Container sain (`Up, healthy`), `TELEGRAM_BOT_TOKEN` present en env, config `channels.telegram` correcte — mais aucun log `[telegram]`, bot injoignable.

**Cause** : Breaking change en v2026.2.22. Tous les plugins "channel" (telegram, discord, whatsapp…) sont desactives par defaut. Seuls 3 plugins sont charges automatiquement :
```javascript
// /app/dist/manifest-registry-*.js
const BUNDLED_ENABLED_BY_DEFAULT = new Set(["device-pair", "phone-control", "talk-voice"]);
```
La fonction `resolveEnableState()` retourne `{enabled: false, reason: "bundled (disabled by default)"}` pour tout plugin absent de ce set. La config `channels.telegram` est lue mais le plugin n'est jamais charge → gateway demarre, Telegram silencieux.

**Diagnostic** :
```bash
docker exec javisi_openclaw node /app/openclaw.mjs plugins list
# Avant fix → "telegram | disabled | bundled (disabled by default)"
# 4/37 loaded : uniquement device-pair, memory-core, phone-control, talk-voice
```

**Fix** : Ajouter `"plugins"` dans `openclaw.json.j2` :
```json
"plugins": {
  "entries": {
{% if telegram_openclaw_bot_token | default('') | length > 0 %}
    "telegram": { "enabled": true }{{ ',' if whatsapp_tutor_enabled | default(false) else '' }}
{% endif %}
{% if whatsapp_tutor_enabled | default(false) %}
    "whatsapp": { "enabled": true }
{% endif %}
  }
},
```

**Verification** :
```bash
docker exec javisi_openclaw node /app/openclaw.mjs plugins list
# Apres fix → "Telegram | telegram | loaded"
docker exec javisi_openclaw node /app/openclaw.mjs channels list
# → "Telegram default: configured, token=config, enabled"
# Logs : "[telegram] [default] starting provider (@WazaBangaBot)"
```

**Commit** : `4481e93`

**Regle** : A chaque montee de version majeure OpenClaw, verifier `plugins list`. Si un canal est marque `disabled (bundled by default)`, il faut l'activer explicitement via `plugins.entries.<id>.enabled: true`.

---

### REX-46 — OpenClaw doctor : cle `compaction` ajoutee silencieusement au redemarrage

**Symptome** : `Config overwrite changedPaths=1` dans les logs a chaque redemarrage. Le fichier `.bak` differe du fichier courant.

**Cause** : Le "doctor" OpenClaw (migration automatique) ajoute `agents.defaults.compaction: {mode: "safeguard"}` si absent. Ce n'est PAS une erreur — c'est une migration normale.

**Impact** : Nul. Le doctor ne retire aucune cle existante.

**Regle** : `changedPaths=1` au demarrage = ajout de defaults de migration. Ne pas le traiter comme une erreur. Si `changedPaths > 3`, investiguer.

---

### REX-47 — OpenRouter : credits epuises, erreur 402 dans les sessions

**Symptome** : Logs `[diagnostic] lane task error: No API key found for provider "openrouter"`. Sessions concierge contenant `OpenrouterException 402: This request requires more credits`.

**Cause** : Mauvaise comprehension de la chaine. OpenClaw parle a LiteLLM (provider `custom-litellm`). LiteLLM route ensuite vers OpenRouter. Quand le solde OpenRouter est a zero :
- LiteLLM retourne une erreur 402 dans la reponse
- OpenClaw (model-auth) la fait remonter comme "No API key found for provider openrouter"
- Le message est trompeur : ce n'est pas une cle manquante, c'est un solde epuise

Le concierge utilisait `custom-litellm/minimax-m25` → LiteLLM route vers `openrouter/minimax/minimax-m1` (payant, 16384 max_tokens, ~$0.002/1k tokens).

**Diagnostic** :
```bash
# Lire les sessions du concierge pour voir l'erreur reelle
docker exec javisi_openclaw sh -c "grep -l 'openrouter' /home/node/.openclaw/agents/concierge/sessions/*.jsonl"
# Inspecter la session :
docker exec javisi_openclaw cat /home/node/.openclaw/agents/concierge/sessions/<uuid>.jsonl | grep OpenrouterException
```

**Fix** : Migrer les modeles par defaut vers les variantes `:free` OpenRouter (0 credit requis) :

| Avant | Apres |
|-------|-------|
| `custom-litellm/minimax-m25` (payant) | `custom-litellm/deepseek-v3-free` |
| `custom-litellm/deepseek-v3` (payant) | `custom-litellm/deepseek-v3-free` |
| `custom-litellm/glm-5` (payant) | `custom-litellm/deepseek-v3-free` |
| `custom-litellm/qwen3-coder` (payant) | `custom-litellm/qwen3-coder` (→ `:free`) |

Nouveaux models LiteLLM ajoutes dans `litellm_config.yaml.j2` :
- `deepseek-v3-free` → `openrouter/deepseek/deepseek-chat:free`
- `deepseek-r1-free` → `openrouter/deepseek/deepseek-r1:free`
- `qwen3-coder` → `openrouter/qwen/qwen3-coder:free` (suffix `:free` ajoute)

**Commit** : `ada6f1a`

**Regle** : OpenRouter distingue les modeles payants (`/model-name`) et gratuits (`/model-name:free`). Les variantes `:free` ont des rate-limits plus strictes (20 req/min) mais ne consomment pas de credits. Toujours verifier le solde OpenRouter avant de choisir un modele primaire.

---

## Analyse : Pourquoi la montee v2026.2.15 → v2026.2.22 a casse le bot

La root cause est une **assumption implicite** : on supposait que `channels.telegram` dans la config suffisait pour activer le bot. En v2026.2.15, les plugins etaient probablement charges differemment (ou telegram etait dans le set `BUNDLED_ENABLED_BY_DEFAULT`).

Lecon : OpenClaw n'a pas de changelog public detaille par version. La strategie de montee en version doit inclure une **verification systematique des plugins** avant de declarer le deploiement reussi.

---

## Etat post-session

| Composant | Etat |
|-----------|------|
| Bot Telegram @WazaBangaBot | ✅ Operationnel |
| plugins list | ✅ `Telegram | loaded` |
| channels list | ✅ `configured, enabled` |
| Erreurs diagnostic | ✅ Eliminees (plus de 402/No API key) |
| Modeles agents | ✅ Tous sur variantes `:free` (0 credit) |
| LiteLLM fallbacks | ✅ Chaines free-first |
