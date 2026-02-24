# Design — Détection erreurs crédit provider + alerting Telegram

**Date** : 2026-02-24
**Status** : Approuvé
**Session** : Session 11

---

## Problème

Quand un provider IA retourne une erreur de crédit (Anthropic 402, OpenRouter 429, LiteLLM budget
exhausted), il n'y a actuellement pas de notification proactive. L'utilisateur découvre le problème
seulement quand un agent échoue à répondre.

Providers concernés :
- Anthropic : `AnthropicException: credit balance too low`
- OpenRouter : `RouterRateLimitError` (cooldown 60s) / `402`
- LiteLLM global : budget $5/jour épuisé → `429 budget_limit_exceeded`
- OpenAI direct (nouvelle route OpenClaw) : `insufficient_quota` / `402`

---

## Architecture retenue — Double couverture

```
Provider 402/429
    │
    ├── Via LiteLLM (Anthropic, OpenRouter, budget global)
    │   general_settings.alerting: ["webhook"]
    │   ─────────────────────────────────────────────────
    │   alert payload → http://n8n:5678/webhook/litellm-credit-alert
    │        │
    │        ├── Filtre n8n : patterns crédit/budget/rate-limit
    │        └── Telegram : "⚠️ ALERTE CRÉDIT [provider] — [erreur]"
    │
    └── Via OpenClaw direct (OpenAI gpt-4o-mini)
        IDENTITY.md concierge — section "Alerte Provider Crédit"
        ───────────────────────────────────────────────────────
        Patterns : "credit balance too low", "insufficient_quota",
                   "402", "RouterRateLimitError", "budget_limit_exceeded"
        → Message structuré dans le chat Telegram immédiatement
```

### Pourquoi pas n8n scraping logs ?

Rejeté : délai 5-15 min, parsing fragile (grep sur logs Docker).

### Pourquoi pas LiteLLM seul ?

Rejeté pour la couverture complète : LiteLLM ne voit pas les erreurs des routes directes
(OpenAI direct depuis OpenClaw). IDENTITY.md couvre cette lacune.

---

## Fichiers à modifier

| Fichier | Type | Modification |
|---|---|---|
| `roles/litellm/templates/litellm_config.yaml.j2` | Edit | Ajouter alerting webhook dans `general_settings` |
| `roles/openclaw/templates/agents/concierge/IDENTITY.md.j2` | Edit | Section détection patterns crédit |
| `roles/n8n-provision/files/workflows/litellm-credit-alert.json` | **New** | Workflow n8n : webhook → filtre → Telegram |

---

## Détail des modifications

### 1. LiteLLM alerting config

Ajouter dans `general_settings` :
```yaml
general_settings:
  # ... existing ...
  alerting: ["webhook"]
  alerting_webhook_url: "http://n8n:5678/webhook/litellm-credit-alert"
  alert_types:
    - "llm_exceptions"
    - "budget_alerts"
```

LiteLLM envoie un POST JSON au webhook avec :
```json
{
  "alert_type": "llm_exceptions",
  "event_message": "AnthropicException: credit balance too low",
  "model": "claude-opus",
  "litellm_call_id": "...",
  "time_stamp": "..."
}
```

### 2. IDENTITY.md concierge — section "Alerte Provider Crédit"

Ajouter avant le "Protocole de Sécurité Absolu" :

```markdown
## Alerte Provider Crédit (AUTOMATIQUE)

Si ta réponse ou le résultat d'un outil contient l'un de ces patterns :
- "credit balance too low"
- "insufficient_quota"
- "402" (avec mention OpenAI, Anthropic, ou OpenRouter)
- "RouterRateLimitError"
- "budget_limit_exceeded"

→ Émettre IMMÉDIATEMENT ce bloc en début de réponse :

⚠️ **ALERTE CRÉDIT PROVIDER**
- **Provider** : [OpenAI / Anthropic / OpenRouter — identifié depuis l'erreur]
- **Erreur** : [message exact de l'erreur]
- **Action** : Recharger les crédits [provider] ou attendre la réinitialisation
- **Fallback** : Si disponible, suggérer un modèle alternatif

→ Puis tenter de continuer avec un modèle fallback si possible.
```

### 3. Workflow n8n `litellm-credit-alert`

Structure du workflow :
1. **Webhook trigger** : `POST /webhook/litellm-credit-alert` (requiert auth token)
2. **Filtre** : `event_message` contient `credit`, `quota`, `402`, `budget`, `RateLimit`
3. **Formatter** : Construit le message Telegram
4. **Telegram** : Envoie au chat_id configuré

Message Telegram formaté :
```
⚠️ ALERTE CRÉDIT PROVIDER
Provider : [extrait du event_message]
Erreur   : [event_message tronqué à 200 chars]
Modèle   : [model]
Action   : Vérifier crédits dans le dashboard provider
```

---

## Format message Telegram type

```
⚠️ ALERTE CRÉDIT PROVIDER
Provider : OpenRouter
Erreur   : RouterRateLimitError — deepseek-v3-free cooldown 60s
Action   : Recharger crédits ou basculer modèle
Fallback : custom-litellm/gpt-4o-mini (déjà actif)
```

---

## Notes d'implémentation

- LiteLLM `alert_types` filtre au niveau LiteLLM pour ne pas spammer n8n avec des erreurs
  non liées au crédit (latence, DB, etc.)
- Le filtre n8n est une sécurité supplémentaire (double filtre)
- L'IDENTITY.md couvre les erreurs OpenAI direct qui ne passent pas par LiteLLM
- Idempotent : redéployer le rôle litellm ou openclaw n'impacte pas les alertes en cours

---

## Vérification

```bash
# 1. LiteLLM alerting actif
ssh prod 'docker logs javisi_litellm 2>&1 | grep alerting'

# 2. Test webhook n8n (simuler une erreur crédit)
curl -X POST http://n8n:5678/webhook/litellm-credit-alert \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"llm_exceptions","event_message":"credit balance too low","model":"claude-opus"}'

# 3. Telegram reçoit l'alerte
# Vérifier dans le chat
```
