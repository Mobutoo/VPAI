# Guide OAuth OpenAI — Onboarding Client Flash Studio

> **Statut** : Validé en production (Sese-AI, mars 2026)
> **Cible** : Onboarding automatisé des clients Flash Studio via leur abonnement ChatGPT Plus/Pro

---

## 1. Contexte

### Problème

OpenClaw utilise des modèles IA via LiteLLM (API keys payantes au token). Les clients Flash Studio ont déjà un abonnement ChatGPT Plus/Pro (20$/mois) qui inclut l'accès aux modèles OpenAI sans frais supplémentaires.

### Solution

OpenClaw v2026.3.13+ intègre nativement le provider `openai-codex` qui authentifie via OAuth PKCE auprès de `auth.openai.com` et utilise l'endpoint `chatgpt.com/backend-api` (pas `api.openai.com`). Le coût est inclus dans l'abonnement ChatGPT du client — zéro crédit API consommé.

### Ce que ça débloque

| Modèle | Provider | Usage |
|--------|----------|-------|
| `openai-codex/gpt-5.4` | openai-codex | Défaut (conversations, orchestration) |
| `openai-codex/gpt-5.3-codex` | openai-codex | Code (génération, review, debug) |
| `openai-codex/o4-mini` | openai-codex | Raisonnement (analyse, planification) |
| `openai-codex/gpt-4.1-mini` | openai-codex | Quick (tâches légères, rapides) |

---

## 2. Architecture du Flow OAuth

```
┌──────────────┐     1. Génère URL OAuth      ┌──────────────┐
│  Serveur     │◄──────────────────────────────│  Ansible     │
│  (OpenClaw)  │     (PKCE challenge+verifier) │  (Makefile)  │
└──────┬───────┘                               └──────────────┘
       │
       │  2. URL retournée
       ▼
┌──────────────┐     3. Client ouvre URL       ┌──────────────┐
│  Site Web    │─────────────────────────────► │  auth.openai │
│  Flash Studio│     (ou envoi par email)      │  .com        │
└──────────────┘                               └──────┬───────┘
                                                      │
       4. Client se connecte (ChatGPT login)          │
       5. Autorise l'accès                            │
                                                      │
┌──────────────┐     6. Redirect callback      ◄──────┘
│  Client      │     http://localhost:1455/auth/callback?code=...
│  (navigateur)│
└──────┬───────┘
       │
       │  7. Client copie l'URL de callback
       ▼
┌──────────────┐     8. Échange code → token   ┌──────────────┐
│  Site Web    │─────────────────────────────► │  Serveur     │
│  Flash Studio│     (ou via make)             │  (OpenClaw)  │
└──────────────┘                               └──────────────┘
       │
       │  9. Token sauvé dans auth-profiles.json
       │  10. OpenClaw redémarre + auto-refresh activé
       ▼
   ✅ Client opérationnel — modèles OpenAI actifs
```

---

## 3. Prérequis

- **Abonnement ChatGPT** : Plus ($20/mois) ou Pro ($200/mois)
- **OpenClaw** : v2026.3.13+ (provider `openai-codex` natif)
- **Profil modèle** : `openai` configuré dans `openclaw_model_profiles`

---

## 4. Mode Opératoire (Manuel — Admin)

### Étape 1 — Générer l'URL OAuth

```bash
source .venv/bin/activate
make openclaw-oauth-start
```

**Résultat** : une URL longue s'affiche :
```
https://auth.openai.com/oauth/authorize?client_id=app_EMoamEEZ73f0CkXaXp7hrann&redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback&response_type=code&scope=openid%20profile%20email%20offline_access&state=abc123&code_challenge=XYZ&code_challenge_method=S256&id_token_add_organizations=true&codex_cli_simplified_flow=true
```

> L'état PKCE (code_verifier + state) est sauvé dans `/tmp/openclaw-oauth-pkce.json` sur le serveur.

### Étape 2 — Le client ouvre l'URL

1. Copier l'URL et l'envoyer au client (email, site web, Telegram)
2. Le client ouvre l'URL dans son navigateur
3. Il se connecte avec son compte ChatGPT (login OpenAI)
4. Il autorise l'accès
5. Le navigateur redirige vers `http://localhost:1455/auth/callback?code=...&state=...`
6. **La page ne charge pas** (c'est normal — localhost sur le poste client)
7. Le client copie l'URL complète de la barre d'adresse

### Étape 3 — Échanger le code contre un token

```bash
make openclaw-oauth-complete URL="http://localhost:1455/auth/callback?code=ac_xxx...&scope=openid+profile+email+offline_access&state=abc123"
```

**Ce qui se passe :**
1. Le code d'autorisation est extrait de l'URL
2. Le code_verifier PKCE est lu depuis `/tmp/openclaw-oauth-pkce.json`
3. Échange via `POST https://auth.openai.com/oauth/token`
4. Le token est sauvé dans `auth-profiles.json` au bon format
5. OpenClaw est redémarré pour charger les credentials
6. Le fichier PKCE temporaire est supprimé

### Étape 4 — Vérifier

```bash
make openclaw-oauth-status
```

**Résultat attendu :**
```
Providers w/ OAuth/tokens (1): openai-codex (1)
- openai-codex:default ok expires in 10d
```

---

## 5. Détails Techniques Critiques

### Format auth-profiles.json

Le fichier DOIT respecter ce format exact (sinon OpenClaw ignore silencieusement) :

```json
{
  "version": 1,
  "profiles": {
    "openai-codex:default": {
      "type": "oauth",
      "provider": "openai-codex",
      "access": "<access_token_jwt>",
      "refresh": "<refresh_token>",
      "expires": 1742000000,
      "accountId": "<chatgpt_account_id>"
    }
  }
}
```

**Champs obligatoires :**
| Champ | Source | Notes |
|-------|--------|-------|
| `version` | Fixe | Toujours `1` |
| `type` | Fixe | Toujours `"oauth"` |
| `provider` | Fixe | Toujours `"openai-codex"` |
| `access` | Token response | JWT access token |
| `refresh` | Token response | Pour auto-refresh (durée ~10j) |
| `expires` | `time() + expires_in` | Timestamp Unix d'expiration |
| `accountId` | JWT claims | Extrait de `https://api.openai.com/auth.chatgpt_account_id` |

### Chemin du fichier

```
Host:      /opt/<project>/data/openclaw/state/agents/main/agent/auth-profiles.json
Container: /opt/<project>/data/openclaw/system/agents/main/agent/auth-profiles.json
```

> **Piège Docker** : le volume `state/agents` est monté comme `system/agents` dans le container. Écrire côté host dans `state/agents/`.

### Paramètres OAuth

| Paramètre | Valeur |
|-----------|--------|
| Client ID | `app_EMoamEEZ73f0CkXaXp7hrann` |
| Auth URL | `https://auth.openai.com/oauth/authorize` |
| Token URL | `https://auth.openai.com/oauth/token` |
| Redirect URI | `http://localhost:1455/auth/callback` |
| Scopes | `openid profile email offline_access` |
| PKCE | S256 (obligatoire) |

### Auto-refresh

OpenClaw gère automatiquement le refresh des tokens expirés via le `refresh_token`. Aucune intervention manuelle nécessaire après le setup initial.

---

## 6. Adaptation Onboarding Flash Studio (Site Web)

### Flow cible pour les clients

```
┌─────────────┐   1. Click "Connecter    ┌─────────────┐
│  Dashboard  │      mon ChatGPT"        │  Backend    │
│  Client     │─────────────────────────►│  Flash      │
│  (React)    │                          │  Studio     │
└─────────────┘                          └──────┬──────┘
                                                │
       2. Backend génère PKCE + URL OAuth       │
       3. Stocke code_verifier en session       │
                                                │
┌─────────────┐   4. Redirect vers       ◄──────┘
│  auth.openai│      auth.openai.com
│  .com       │
└──────┬──────┘
       │
       5. Client login ChatGPT + autorise
       │
       ▼
┌─────────────┐   6. Redirect callback
│  Flash      │      /api/oauth/openai/callback?code=...&state=...
│  Studio     │
│  (backend)  │
└──────┬──────┘
       │
       │  7. Échange code → tokens (server-side)
       │  8. Décode JWT → accountId
       │  9. Écrit auth-profiles.json sur le serveur client
       │  10. Restart OpenClaw container
       │  11. Vérifie models status
       ▼
┌─────────────┐
│  Dashboard  │   12. "ChatGPT connecté ✓"
│  Client     │       (badge vert, modèles actifs)
└─────────────┘
```

### Différences clé vs mode admin

| Aspect | Admin (Makefile) | Client (Site Web) |
|--------|-----------------|-------------------|
| **Génération URL** | `make openclaw-oauth-start` | API backend `/api/oauth/openai/start` |
| **Redirect URI** | `http://localhost:1455/auth/callback` | `https://app.flashstudio.io/api/oauth/openai/callback` |
| **Échange code** | `make openclaw-oauth-complete URL=...` | Automatique (callback backend) |
| **Stockage verifier** | Fichier `/tmp/` sur serveur | Session DB (Redis/PostgreSQL) |
| **Écriture token** | Ansible SSH → shell | API interne → SSH/Docker exec |
| **UX** | Terminal | 1 click + login ChatGPT |

### Endpoints backend à implémenter

#### `POST /api/oauth/openai/start`

```
Request:  { "client_id": "uuid-client" }
Response: { "redirect_url": "https://auth.openai.com/oauth/authorize?..." }

Side effects:
  - Génère code_verifier (43 chars, base64url)
  - Calcule code_challenge (SHA256 + base64url)
  - Génère state (random hex 32)
  - Stocke { code_verifier, state, client_id } en session (TTL 10min)
```

#### `GET /api/oauth/openai/callback`

```
Query params: code, state, scope
Response: Redirect vers dashboard client avec status

Side effects:
  - Valide state vs session
  - POST https://auth.openai.com/oauth/token (code + verifier)
  - Décode JWT → accountId
  - Écrit auth-profiles.json sur le serveur du client
  - Restart container OpenClaw
  - Supprime session PKCE
```

### Sécurité onboarding

- **PKCE obligatoire** : le code_verifier ne quitte jamais le backend
- **State validation** : empêche CSRF (vérifier state reçu vs session)
- **TTL session** : 10 minutes max pour compléter le flow (expire le verifier)
- **Pas de client_secret** : flow public client (PKCE remplace le secret)
- **Token serveur uniquement** : le access_token n'est jamais exposé au navigateur client
- **Refresh token** : stocké uniquement dans `auth-profiles.json` côté serveur

### Redirect URI pour Flash Studio

Le `redirect_uri` doit être enregistré auprès d'OpenAI. Options :

1. **Même client_id** (`app_EMoamEEZ73f0CkXaXp7hrann`) : si OpenAI accepte des redirect_uri dynamiques → idéal
2. **Nouveau client_id** : enregistrer une app OAuth dédiée Flash Studio auprès d'OpenAI avec `https://app.flashstudio.io/api/oauth/openai/callback`

> **À valider** : est-ce que le client_id Codex CLI accepte des redirect_uri custom ? Sinon, fallback sur `http://localhost:1455/auth/callback` avec capture côté client (moins élégant mais fonctionnel).

---

## 7. Pièges Connus (REX Production)

| # | Piège | Impact | Solution |
|---|-------|--------|----------|
| 1 | Scope `model.request` invalide | `invalid_scope` error | Utiliser `openid profile email offline_access` |
| 2 | Format auth-profiles.json plat | Token ignoré silencieusement | Wrapper `{ "version": 1, "profiles": { ... } }` |
| 3 | Champ `type` manquant | Token ignoré | Toujours mettre `"type": "oauth"` |
| 4 | Champ `provider` manquant | Token ignoré | Toujours mettre `"provider": "openai-codex"` |
| 5 | Champ `accountId` manquant | Token ignoré | Décoder JWT → `https://api.openai.com/auth.chatgpt_account_id` |
| 6 | Écriture dans `system/agents/` (host) | Fichier pas visible dans container | Écrire dans `state/agents/` (host = monté comme `system/` dans container) |
| 7 | Provider custom `openai-codex` dans config | Masque le provider natif | Ne PAS ajouter de provider custom — laisser le built-in |
| 8 | Token OAuth sur `api.openai.com/v1` | 401 Unauthorized | OAuth = `chatgpt.com/backend-api` (provider natif gère) |
| 9 | `openclaw_state_dir` non défini | Ansible fail | Passer `-e project_name=xxx` explicitement |

---

## 8. Commandes de Référence

```bash
# Générer l'URL OAuth
make openclaw-oauth-start

# Échanger le code (coller l'URL callback complète)
make openclaw-oauth-complete URL="http://localhost:1455/auth/callback?code=...&state=..."

# Vérifier le statut OAuth
make openclaw-oauth-status

# Basculer tous les agents sur le profil OpenAI
make openclaw-profile PROFILE=openai

# Vérifier manuellement sur le serveur
ssh <server> 'docker exec javisi_openclaw openclaw models status'

# Voir le contenu du fichier auth-profiles
ssh <server> 'cat /opt/javisi/data/openclaw/state/agents/main/agent/auth-profiles.json | python3 -m json.tool'
```

---

## 9. Checklist Onboarding Client

- [ ] Client a un abonnement ChatGPT Plus ou Pro actif
- [ ] Instance OpenClaw v2026.3.13+ déployée
- [ ] Profil modèle `openai` configuré dans defaults
- [ ] `make openclaw-oauth-start` → URL générée
- [ ] Client ouvre l'URL → login ChatGPT → autorise
- [ ] Client copie l'URL de callback (localhost:1455/...)
- [ ] `make openclaw-oauth-complete URL=...` → token échangé
- [ ] `make openclaw-oauth-status` → `ok expires in Xd`
- [ ] Test : envoyer un message via Telegram → réponse d'un modèle `openai-codex/*`

---

## 10. Fichiers Source

| Fichier | Rôle |
|---------|------|
| `playbooks/openclaw-oauth.yml` | Playbook Ansible headless PKCE (2 étapes) |
| `roles/openclaw/defaults/main.yml` | Profil `openai` (modèles openai-codex/*) |
| `roles/openclaw/templates/openclaw.json.j2` | Config agents (pas de provider custom) |
| `roles/openclaw/templates/openclaw.env.j2` | Variables env (OPENAI_API_KEY = fallback) |
| `Makefile` | Targets `openclaw-oauth-start`, `openclaw-oauth-complete`, `openclaw-oauth-status` |
