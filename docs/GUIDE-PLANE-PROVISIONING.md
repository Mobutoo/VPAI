# GUIDE — Provisioning Plane (semi-automatisé)

> Plan source : `.planning/phases/01-plane-deployment/01-02b-PLAN.md` (Task T2)
> Rôle : `roles/plane-provision/` — script `templates/provision-plane.sh.j2`

Le provisioning Plane est **semi-automatisé** : le token admin doit être créé
**manuellement** via l'UI (impossible par API en v1.2.2), puis le rôle
`plane-provision` génère automatiquement les 10 tokens agents, le projet
Onboarding et les custom fields.

| Donnée | Valeur réelle (defaults du rôle) |
|---|---|
| URL Plane | `https://work.{{ domain_name }}` (`plane_subdomain: work`) |
| Workspace slug | `ewutelo` (`plane_workspace_slug`) |
| Workspace nom | `Ewutelo` (`plane_workspace_name`) |
| En-tête d'auth API | `X-API-Key: <token>` (⚠️ **pas** `Authorization: Bearer`) |
| Accès | VPN Tailscale uniquement |

---

## 1. Premier login (manuel — prérequis avant toute automatisation)

1. Accéder à `https://work.{{ domain_name }}` **via le VPN** (Tailscale up).
2. Compléter l'assistant **God Mode** (création du compte instance-admin) au tout
   premier accès.
3. Se connecter avec le compte admin que tu viens de créer.

> Tant que cette étape n'est pas faite, le workspace n'existe pas et l'API
> renvoie `401`.

---

## 2. Création du token admin API (manuel)

1. UI Plane → **Profile Settings → Personal Access Tokens**.
2. **Create New Token** :
   - Nom : `ansible-provisioning`
   - Scope : accès complet (instance admin)
   - Expiration : **Never** (service interne VPN)
3. Copier la valeur du token (affichée **une seule fois**).
4. Injecter dans le Vault :

   ```bash
   source .venv/bin/activate
   ansible-vault edit inventory/group_vars/all/secrets.yml
   ```

   Remplacer le placeholder :

   ```yaml
   vault_plane_admin_api_token: "REPLACE_AFTER_FIRST_LOGIN"   # ← coller le vrai token
   ```

---

## 3. Lancer le provisioning

```bash
source .venv/bin/activate
make deploy-role ROLE=plane-provision ENV=prod
```

Le script exécute 4 étapes (cf `provision-plane.sh.j2`) :

| Étape | Action |
|---|---|
| `[1/4]` | Crée les 10 comptes agents (`<agent>@ewutelo.local`) |
| `[2/4]` | Invite/ajoute les agents au workspace `ewutelo` |
| `[3/4]` | Génère un token API par agent et **imprime** les lignes vault |
| `[4/4]` | Crée le projet **Onboarding** (`identifier: ONBOARD`, privé) + custom fields |

Les 10 agents (source : script, **fait foi** sur le plan d'origine) :

```
concierge   imhotep   thot   basquiat   r2d2
piccolo     cfo       maintainer   hermes   marketer
```

> ⚠️ Le plan 01-02b citait un agent `shuri` — la réalité du script est `marketer`.
> Référence = le script.

### Récupérer les tokens agents dans le Vault

L'étape `[3/4]` imprime un bloc à **copier tel quel** dans le Vault :

```
----- PLANE API TOKENS (copy to vault) -----
vault_plane_token_concierge: "plane_api_xxxxx"
vault_plane_token_imhotep:   "plane_api_xxxxx"
...
---- END PLANE API TOKENS ----
```

> ⚠️ **Format réel = clés plates** `vault_plane_token_<agent>`, **pas** le dict
> `vault_plane_agent_tokens` décrit dans le plan T1. Coller les lignes émises
> par le script dans `secrets.yml` via `ansible-vault edit`.

---

## 4. Vérification

```bash
# Workspace présent (doit retourner 200 + le slug ewutelo)
curl -s -H "X-API-Key: <ADMIN_TOKEN>" \
  https://work.{{ domain_name }}/api/v1/workspaces/ | grep ewutelo

# Projet Onboarding présent
curl -s -H "X-API-Key: <ADMIN_TOKEN>" \
  https://work.{{ domain_name }}/api/v1/workspaces/ewutelo/projects/ | grep ONBOARD

# Token admin n'est plus le placeholder
ansible-vault view inventory/group_vars/all/secrets.yml \
  | grep vault_plane_admin_api_token | grep -v REPLACE

# Les 10 tokens agents sont présents et non vides (doit retourner 10)
ansible-vault view inventory/group_vars/all/secrets.yml \
  | grep -cE '^vault_plane_token_[a-z]+: *"[^"]+"'

# Aucun token vide (doit retourner 0)
ansible-vault view inventory/group_vars/all/secrets.yml \
  | grep -cE '^vault_plane_token_[a-z]+: *""'
```

Dans l'UI :
- Workspace **Ewutelo** existe.
- Projet **Onboarding** présent.
- **Settings → Custom Fields** : `agent_id`, `cost_estimate`, `confidence_score`,
  `session_id`.

---

## 5. Troubleshooting

| Symptôme | Cause / fix |
|---|---|
| API `401` | Token admin invalide/expiré ou God Mode non complété → régénérer via UI |
| API `403` | Token sans scope instance-admin → recréer avec accès complet |
| `Workspace already exists` | Script idempotent — relance sans risque |
| Custom fields échouent | Work-item-type ID mismatch → vérifier `GET /api/v1/workspaces/ewutelo/work-item-types/` |
| Tokens agents vides après run | Voir logs `[3/4]` du script ; vérifier que le token admin est valide ; un `[SKIP] token already exists` signifie qu'il faut **récupérer la valeur existante depuis le vault** (Plane ne ré-affiche pas un token déjà créé) |
| `make deploy-role` ne route pas | Caddy doit router `/api/v1/*` → backend Plane (cf LOI R11) |
| MCP `list_projects` → 404 (mais `get_me` OK, slug/URL corrects) | `uvx plane-mcp-server` non pinné = latest (0.2.10) appelle `/projects-lite/`, absent en self-hosted v1.2.2 → pinner `plane-mcp-server==0.2.9` dans `~/.claude.json` (`mcpServers.plane.args`) + recharger la session MCP. Détail : `docs/TROUBLESHOOTING.md` §56 |

---

## Checkpoint (Task T3 — action opérateur, AUTH-03)

Avant de passer au plan **01-03** (monitoring / smoke tests), confirmer :

1. ✅ `vault_plane_admin_api_token` ≠ `REPLACE_AFTER_FIRST_LOGIN`
2. ✅ `make deploy-role ROLE=plane-provision ENV=prod` exécuté sans erreur
3. ✅ Les 10 `vault_plane_token_<agent>` sont non vides
   (`grep -cE '^vault_plane_token_[a-z]+: *""'` → **0**)

Sans ces tokens réels, les smoke tests de 01-03 valideraient à vide (faux positif).
