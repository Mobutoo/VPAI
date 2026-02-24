# Credit Error Alerting — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Détecter les erreurs crédit provider (Anthropic 402, OpenRouter 429, LiteLLM budget,
OpenAI direct 402) et envoyer une alerte Telegram immédiatement.

**Architecture:** Double couverture — (1) LiteLLM native `alerting: ["webhook"]` → n8n workflow
→ Telegram (monitoring bot) pour toutes les erreurs passant par LiteLLM ; (2) Section dans
IDENTITY.md du concierge pour les erreurs OpenAI direct qui n'ont pas de hook LiteLLM.
Le workflow n8n filtre le payload LiteLLM avant d'envoyer (évite le spam sur erreurs non-crédit).

**Tech Stack:** LiteLLM v1.81.3 alerting config (YAML/Jinja2), n8n v2.7.x workflow JSON,
OpenClaw IDENTITY.md, Ansible roles litellm + openclaw + n8n-provision.

---

### Task 1 : LiteLLM alerting webhook

**Files:**
- Modify: `roles/litellm/templates/litellm_config.yaml.j2` (section `general_settings`, après `health_check_interval: 0`)

**Step 1 : Ajouter la config alerting dans general_settings**

Ouvrir `roles/litellm/templates/litellm_config.yaml.j2`.
Localiser la ligne `health_check_interval: 0` (autour de la ligne 353).
Insérer **après** cette ligne :

```yaml
  # Credit error alerting — webhook → n8n → Telegram (monitoring bot)
  # alert_types limite au strict nécessaire : llm_exceptions (402/RateLimit) + budget_alerts
  # Le workflow n8n filtre en plus les patterns crédit avant d'envoyer (double filtre).
  alerting: ["webhook"]
  alerting_webhook_url: "http://n8n:5678/webhook/litellm-credit-alert"
  alert_types:
    - "llm_exceptions"
    - "budget_alerts"
```

**Step 2 : Vérifier que l'indentation est cohérente**

La section `general_settings` utilise 2 espaces. Vérifier que les 3 nouvelles lignes sont
indentées à 2 espaces (alignées avec `master_key`, `database_url`, etc.).

**Step 3 : Lint**

```bash
source .venv/bin/activate && make lint
```

Expected : 0 erreurs yamllint + ansible-lint.

**Step 4 : Commit**

```bash
git add roles/litellm/templates/litellm_config.yaml.j2
git commit -m "feat(litellm): activer alerting webhook pour erreurs crédit providers (REX-49)"
```

---

### Task 2 : IDENTITY.md concierge — détection patterns crédit direct

**Files:**
- Modify: `roles/openclaw/templates/agents/concierge/IDENTITY.md.j2`
  (insérer avant `## Protocole de Securite Absolu`, autour de la ligne 269)

**Step 1 : Insérer la section de détection**

Localiser la ligne `## Protocole de Securite Absolu` et insérer **juste avant** :

```markdown
## Alerte Provider Credit (AUTOMATIQUE)

Si ta reponse ou le resultat d'un outil contient l'un de ces patterns :
- "credit balance too low"
- "insufficient_quota"
- "402" + mention d'un provider (OpenAI, Anthropic, OpenRouter)
- "RouterRateLimitError"
- "budget_limit_exceeded"
- "AuthenticationError" + "credit"

Emettre IMMEDIATEMENT ce bloc en debut de reponse, avant tout autre contenu :

⚠️ **ALERTE CREDIT PROVIDER**
- **Provider** : [OpenAI / Anthropic / OpenRouter — identifie depuis le message d'erreur]
- **Erreur** : [message exact, tronque si > 150 chars]
- **Action** : Recharger les credits [provider] ou attendre la reinitialisation quotidienne
- **Fallback** : [Si disponible, suggerer un modele alternatif — ex: custom-litellm/deepseek-v3-free]

Puis tenter de continuer avec un modele fallback si possible.
Ne pas te bloquer sur cette erreur — alerter et continuer la conversation.

```

**Step 2 : Lint**

```bash
source .venv/bin/activate && make lint
```

Expected : 0 erreurs.

**Step 3 : Commit**

```bash
git add roles/openclaw/templates/agents/concierge/IDENTITY.md.j2
git commit -m "feat(openclaw): détection patterns erreur crédit dans IDENTITY.md concierge"
```

---

### Task 3 : Workflow n8n litellm-credit-alert

**Files:**
- Create: `roles/n8n-provision/files/workflows/litellm-credit-alert.json`

**Step 1 : Comprendre le payload LiteLLM**

LiteLLM envoie un POST JSON avec ce format :
```json
{
  "alert_type": "llm_exceptions",
  "event_message": "AnthropicException: credit balance too low for model claude-opus",
  "model": "claude-opus",
  "litellm_call_id": "abc123",
  "time_stamp": "2026-02-24T12:00:00Z"
}
```
Pour `budget_alerts` :
```json
{
  "alert_type": "budget_alerts",
  "event_message": "Budget limit exceeded: $5.00 daily limit reached",
  "user_current_spend": 5.01,
  "user_max_budget": 5.0,
  "time_stamp": "2026-02-24T12:00:00Z"
}
```

**Step 2 : Créer le fichier workflow JSON**

Créer `roles/n8n-provision/files/workflows/litellm-credit-alert.json` avec ce contenu exact :

```json
{
  "name": "litellm-credit-alert",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "litellm-credit-alert",
        "responseMode": "responseNode",
        "options": {}
      },
      "id": "ca-0001-0000-0000-0000-000000000001",
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [260, 300],
      "webhookId": "litellm-credit-alert"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": false,
            "leftValue": "",
            "typeValidation": "loose"
          },
          "conditions": [
            {
              "id": "cond-credit",
              "leftValue": "={{ $json.body.event_message ?? '' }}",
              "rightValue": "credit|quota|402|budget|RateLimit|rate_limit|insufficient|AuthenticationError",
              "operator": {
                "type": "string",
                "operation": "regex"
              }
            }
          ],
          "combinator": "or"
        },
        "options": {}
      },
      "id": "ca-0001-0000-0000-0000-000000000002",
      "name": "Est erreur crédit?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [480, 300]
    },
    {
      "parameters": {
        "jsCode": "const body = $input.first().json.body || {};\nconst msg = body.event_message || '';\nconst alertType = body.alert_type || 'unknown';\nconst model = body.model || 'N/A';\nconst ts = body.time_stamp ? new Date(body.time_stamp).toLocaleString('fr-FR', {timeZone: 'Europe/Paris'}) : new Date().toLocaleString('fr-FR', {timeZone: 'Europe/Paris'});\n\n// Détecter le provider depuis le message\nlet provider = 'Unknown';\nif (msg.toLowerCase().includes('anthropic')) provider = 'Anthropic';\nelse if (msg.toLowerCase().includes('openrouter')) provider = 'OpenRouter';\nelse if (msg.toLowerCase().includes('openai')) provider = 'OpenAI';\nelse if (msg.toLowerCase().includes('budget')) provider = 'LiteLLM (budget global)';\nelse if (alertType === 'budget_alerts') provider = 'LiteLLM (budget global)';\n\n// Tronquer le message\nconst msgShort = msg.length > 200 ? msg.substring(0, 200) + '...' : msg;\n\n// Construire le message Telegram\nconst text = `⚠️ <b>ALERTE CRÉDIT PROVIDER</b>\\n\\n` +\n  `<b>Provider</b> : ${provider}\\n` +\n  `<b>Type</b>    : ${alertType}\\n` +\n  `<b>Modèle</b>  : ${model}\\n` +\n  `<b>Erreur</b>  : <code>${msgShort}</code>\\n` +\n  `<b>Heure</b>   : ${ts}\\n\\n` +\n  `→ Vérifier le dashboard provider et recharger si nécessaire`;\n\nreturn [{ json: { text } }];\n"
      },
      "id": "ca-0001-0000-0000-0000-000000000003",
      "name": "Formater alerte",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [700, 180]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "=https://api.telegram.org/bot{{ $env.TELEGRAM_MONITORING_BOT_TOKEN }}/sendMessage",
        "sendBody": true,
        "bodyParameters": {
          "parameters": [
            { "name": "chat_id", "value": "={{ $env.TELEGRAM_MONITORING_CHAT_ID }}" },
            { "name": "text",    "value": "={{ $json.text }}" },
            { "name": "parse_mode", "value": "HTML" }
          ]
        },
        "options": {}
      },
      "id": "ca-0001-0000-0000-0000-000000000004",
      "name": "Telegram Alert",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [920, 180]
    },
    {
      "parameters": {
        "respondWith": "json",
        "responseBody": "={ \"ok\": true }"
      },
      "id": "ca-0001-0000-0000-0000-000000000005",
      "name": "HTTP Response OK",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1,
      "position": [700, 420]
    }
  ],
  "connections": {
    "Webhook": {
      "main": [
        [{ "node": "Est erreur crédit?", "type": "main", "index": 0 }]
      ]
    },
    "Est erreur crédit?": {
      "main": [
        [{ "node": "Formater alerte",  "type": "main", "index": 0 }],
        [{ "node": "HTTP Response OK", "type": "main", "index": 0 }]
      ]
    },
    "Formater alerte": {
      "main": [
        [{ "node": "Telegram Alert",   "type": "main", "index": 0 }]
      ]
    },
    "Telegram Alert": {
      "main": [
        [{ "node": "HTTP Response OK", "type": "main", "index": 0 }]
      ]
    }
  },
  "settings": { "executionOrder": "v1" },
  "staticData": null,
  "tags": [{ "name": "monitoring" }],
  "triggerCount": 0,
  "versionId": "ca-0001-0000-0000-0000-000000000000"
}
```

**Note importante sur `responseMode`**: Le nœud Webhook est en `responseMode: "responseNode"`,
ce qui signifie que c'est le nœud `HTTP Response OK` qui répond à LiteLLM. Quand l'erreur n'est
pas un crédit error, le nœud IF branche sur `HTTP Response OK` directement (pas de Telegram).

**Step 3 : Valider le JSON**

```bash
python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/litellm-credit-alert.json')); print('JSON valide')"
```

Expected : `JSON valide`

**Step 4 : Vérifier que le fichier est listé dans le rôle n8n-provision**

Lire `roles/n8n-provision/tasks/main.yml` et chercher comment les workflows sont importés
(probablement une loop sur `files/workflows/*.json`). Si la loop est automatique (glob), aucune
modification supplémentaire n'est nécessaire. Si les workflows sont listés manuellement dans
`defaults/main.yml`, ajouter `litellm-credit-alert` à la liste.

**Step 5 : Lint**

```bash
source .venv/bin/activate && make lint
```

**Step 6 : Commit**

```bash
git add roles/n8n-provision/files/workflows/litellm-credit-alert.json
git commit -m "feat(n8n): workflow litellm-credit-alert — alerting crédit provider via Telegram"
```

---

### Task 4 : Documentation TROUBLESHOOTING.md

**Files:**
- Modify: `docs/TROUBLESHOOTING.md` (section OpenClaw ou LiteLLM)

**Step 1 : Ajouter entrée REX**

Localiser la section LiteLLM dans `docs/TROUBLESHOOTING.md` et ajouter :

```markdown
### X.Y Alerting erreurs crédit provider — setup

**Symptôme** : `AnthropicException: credit balance too low`, `RouterRateLimitError`,
`budget_limit_exceeded` dans les logs LiteLLM — pas de notification Telegram.

**Solution** : Double couverture implémentée :
1. **LiteLLM → n8n** : `alerting: ["webhook"]` dans `general_settings` du litellm_config.
   Webhook URL: `http://n8n:5678/webhook/litellm-credit-alert`.
   Filtre n8n sur patterns `credit|quota|402|budget|RateLimit`.
   Alerte Telegram via monitoring bot.
2. **IDENTITY.md concierge** : Section "Alerte Provider Credit" — détection patterns
   dans les erreurs OpenAI direct (bypass LiteLLM).

**Test** :
```bash
# Simuler une alerte LiteLLM depuis le serveur
curl -X POST http://localhost:5678/webhook/litellm-credit-alert \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"llm_exceptions","event_message":"AnthropicException: credit balance too low","model":"claude-opus"}'
# Vérifier que Telegram reçoit l'alerte
```
```

**Step 2 : Commit**

```bash
git add docs/TROUBLESHOOTING.md
git commit -m "docs: documenter alerting erreurs crédit provider (TROUBLESHOOTING)"
```

---

### Task 5 : Deploy + Vérification end-to-end

**Step 1 : Déployer les 3 rôles modifiés**

```bash
source .venv/bin/activate
# LiteLLM (alerting config)
make deploy-role ROLE=litellm ENV=prod
# OpenClaw (IDENTITY.md concierge)
make deploy-role ROLE=openclaw ENV=prod
# n8n-provision (workflow)
make deploy-role ROLE=n8n-provision ENV=prod
```

**Step 2 : Vérifier que LiteLLM a redémarré avec la config alerting**

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 \
  'docker logs javisi_litellm 2>&1 | tail -30 | grep -i "alert\|webhook"'
```

Expected : mention de l'alerting webhook dans les logs de démarrage.

**Step 3 : Vérifier que le workflow n8n est actif**

Aller dans `https://hq.<domain>/n8n/workflows` et vérifier que `litellm-credit-alert` est
présent et activé.

**Step 4 : Test end-to-end via curl depuis le VPS**

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 \
  'docker exec javisi_n8n curl -s -X POST http://localhost:5678/webhook/litellm-credit-alert \
   -H "Content-Type: application/json" \
   -d "{\"alert_type\":\"llm_exceptions\",\"event_message\":\"AnthropicException: credit balance too low\",\"model\":\"claude-opus\"}"'
```

Expected : Telegram reçoit l'alerte ⚠️ dans les secondes qui suivent.

**Step 5 : Vérifier le filtre (non-crédit error ne doit PAS envoyer Telegram)**

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 \
  'docker exec javisi_n8n curl -s -X POST http://localhost:5678/webhook/litellm-credit-alert \
   -H "Content-Type: application/json" \
   -d "{\"alert_type\":\"llm_exceptions\",\"event_message\":\"Timeout connecting to API\",\"model\":\"claude-opus\"}"'
```

Expected : réponse HTTP 200 `{"ok":true}` mais **pas de Telegram** (le filtre IF rejette).

---

## Ordre d'exécution recommandé

1. Task 1 (LiteLLM config) → commit
2. Task 2 (IDENTITY.md) → commit
3. Task 3 (n8n workflow JSON) → commit
4. Task 4 (doc) → commit
5. Task 5 (deploy + test)

## Rollback

Si problème avec l'alerting LiteLLM (ex: trop de spam) :
- Supprimer `alerting: [...]` et les 3 lignes suivantes de `litellm_config.yaml.j2`
- `make deploy-role ROLE=litellm ENV=prod`
