# Guide : Montee en Version OpenClaw (One-Shot)

> **But** : Monter la version d'OpenClaw en production sans aller-retours ni regression.
> **Temps estime** : 20-30 min si tout va bien, 45 min avec investigation.
> **Prerequis** : Stack deployee et fonctionnelle, bot Telegram actif.

---

## 0. Avant de commencer — Lire le changelog

OpenClaw n'a pas de changelog officiel detaille. Les sources d'information sont :

| Source | Acces |
|--------|-------|
| GitHub Releases | `https://github.com/anthropics/openclaw/releases` (si public) |
| Tags Docker | `ghcr.io/openclaw/openclaw` — comparer les dates |
| Logs de demarrage | `docker logs javisi_openclaw 2>&1 | head -30` |
| Config audit | `/home/node/.openclaw/logs/config-audit.jsonl` |

**Breaking changes connus par version** :
- `v2026.2.22` : Plugins bundled desactives par defaut (voir section 3.B)
- `v2026.2.22` : `memorySearch` natif (pas encore active dans notre stack)

---

## 1. Snapshot pre-upgrade (OBLIGATOIRE)

```bash
# 1.a Backup la config runtime
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@<VPS_IP> \
  "cp /opt/javisi/data/openclaw/system/openclaw.json \
      /opt/javisi/data/openclaw/system/openclaw.json.pre-upgrade-$(date +%Y%m%d)"

# 1.b Etat du bot avant upgrade — garder la trace
docker logs --tail 20 javisi_openclaw 2>&1 | grep -E "telegram|health-monitor|started"
# Resultat attendu : "[telegram] [default] starting provider (@WazaBangaBot)"

# 1.c Verifier l'etat des plugins AVANT
docker exec javisi_openclaw node /app/openclaw.mjs plugins list 2>&1 | head -20

# 1.d Verifier les agents AVANT
docker exec javisi_openclaw node /app/openclaw.mjs agents list 2>&1
```

Conserver ces sorties dans un fichier ou un snippet avant de continuer.

---

## 2. Mettre a jour la version

```bash
# 2.a Editer versions.yml
# Dans inventory/group_vars/all/versions.yml :
openclaw_image: "ghcr.io/openclaw/openclaw:YYYY.M.DD"  # nouvelle version
```

**Format des tags** : Toujours `YYYY.M.DD` (pas de `v` prefixe, pas de `:latest`).

Verifier que le tag existe avant de le mettre :
```bash
# Via skopeo (si installe) :
skopeo list-tags docker://ghcr.io/openclaw/openclaw | grep "2026" | tail -10

# Ou via l'API GitHub Container Registry depuis le browser :
# https://github.com/openclaw/openclaw/pkgs/container/openclaw
```

---

## 3. Deploiement

```bash
cd /home/asus/seko/VPAI
source .venv/bin/activate
make lint  # Toujours avant
make deploy-role ROLE=openclaw ENV=prod
```

Le handler `Restart openclaw stack` se declenche automatiquement si la config change.

---

## 4. Checklist de Validation Post-Upgrade (CRITIQUE)

Executer **dans cet ordre** apres le redemarrage :

### 4.A Container sain

```bash
# Attendre 30s que le container soit stable, puis :
ansible prod -i inventory/hosts.yml -m shell \
  -a "docker ps --filter name=javisi_openclaw --format '{{.Status}}'" -b
# Resultat attendu : "Up X seconds (healthy)"
# Si "Restarting" → voir section 5.A (crash loop)
```

### 4.B Plugins charges — VERIF OBLIGATOIRE depuis v2026.2.22

```bash
docker exec javisi_openclaw node /app/openclaw.mjs plugins list 2>&1
```

**Resultat attendu** :
```
Telegram | telegram | loaded
```

**Resultat dangereux** (bot silencieux) :
```
telegram | disabled | bundled (disabled by default)
```

→ Si "disabled" : la section `plugins.entries.telegram.enabled: true` est absente du template `openclaw.json.j2`. Voir TROUBLESHOOTING.md section 11.10.

### 4.C Channels configures

```bash
docker exec javisi_openclaw node /app/openclaw.mjs channels list 2>&1
```

**Resultat attendu** :
```
Telegram default: configured, token=config, enabled
```

### 4.D Logs de demarrage propres

```bash
docker logs --tail 30 javisi_openclaw 2>&1 | grep -E "telegram|error|Error|warn"
```

**Attendu** :
```
[telegram] [default] starting provider (@WazaBangaBot)
[telegram] autoSelectFamily=true
[telegram] dnsResultOrder=ipv4first
```

**Signaux d'alarme** :
- `No API key found for provider "openrouter"` → credits OpenRouter epuises (voir 5.B)
- `Unknown channel: telegram` → mauvaise commande (channels add est inutile, ne pas utiliser)
- `changedPaths=1` → normal (doctor migration, voir TROUBLESHOOTING 11.11)
- `changedPaths > 3` → investiguer

### 4.E Test fonctionnel Telegram

Envoyer un message sur Telegram au bot. Attendre 30s. Si pas de reponse :

```bash
# Chercher le message dans les logs
docker logs --tail 50 javisi_openclaw 2>&1 | grep -E "message|webhook|recv"
```

### 4.F Agents et modeles

```bash
docker exec javisi_openclaw node /app/openclaw.mjs agents list 2>&1 | grep -E "^- |Model:"
```

**Verifier** : Les modeles correspondent bien aux valeurs de `roles/openclaw/defaults/main.yml`.

---

## 5. Resolution des Problemes Courants

### 5.A Crash loop apres upgrade

```bash
docker logs --tail 50 javisi_openclaw 2>&1 | grep -iE "error|fatal|crash|unknown key"
```

**Causes frequentes** :
- Cle de config inconnue en nouvelle version → doctor rejette la config
- `tools.web.fetch.readability` : CLE NON RECONNUE, cause crash (voir TROUBLESHOOTING 11.4)
- Mauvais type pour un champ (ex: `model` doit etre objet `{"primary": "..."}`, pas string)

**Fix rapide** : restaurer le backup et deployer sans la cle problematique :
```bash
# Sur le VPS :
cp /opt/javisi/data/openclaw/system/openclaw.json.pre-upgrade-YYYYMMDD \
   /opt/javisi/data/openclaw/system/openclaw.json
docker restart javisi_openclaw
```

Puis identifier la cle incriminee en comparant les `.bak` generees par le doctor :
```bash
docker exec javisi_openclaw python3 -c "
import json
a = json.load(open('/home/node/.openclaw/openclaw.json.bak.1'))
b = json.load(open('/home/node/.openclaw/openclaw.json'))
def diff(a, b, p=''):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(list(a)+list(b)):
            diff(a.get(k), b.get(k), p+'.'+k)
    elif a != b:
        print(f'DIFF {p}: {repr(a)[:80]} -> {repr(b)[:80]}')
diff(a, b)
"
```

### 5.B Erreur "No API key found for provider openrouter"

Ce message est trompeur. Cause reelle = credits OpenRouter epuises.

```bash
# Verifier le solde OpenRouter via LiteLLM
curl -s http://localhost:4000/v1/model/list \
  -H "Authorization: Bearer $LITELLM_API_KEY" | python3 -m json.tool | grep openrouter

# Ou directement dans les sessions :
docker exec javisi_openclaw sh -c \
  "grep -rl 'OpenrouterException\|402' /home/node/.openclaw/agents/concierge/sessions/ | head -3"
```

**Fix** : Basculer les modeles sur les variantes `:free` dans `defaults/main.yml` :
```yaml
openclaw_concierge_model: "custom-litellm/deepseek-v3-free"
openclaw_messenger_model: "custom-litellm/qwen3-coder"
# etc.
```
Puis redeploy `make deploy-role ROLE=openclaw ENV=prod`.

### 5.C Plugin "disabled (bundled by default)" apres upgrade

Verifier que `openclaw.json.j2` contient la section `plugins.entries` :

```bash
grep -A 10 '"plugins"' roles/openclaw/templates/openclaw.json.j2
```

Si absente, ajouter avant `"logging"` :
```json
"plugins": {
  "entries": {
    "telegram": { "enabled": true }
  }
},
```
Redeploy `make deploy-role ROLE=openclaw ENV=prod`.

### 5.D "channels list" retourne vide malgre plugin loaded

Cause possible : La config `channels.telegram` manque ou `TELEGRAM_BOT_TOKEN` non injecte.

```bash
# Verifier l'env du container
docker exec javisi_openclaw sh -c "env | grep TELEGRAM"
# Doit retourner TELEGRAM_BOT_TOKEN=<token>

# Verifier la config live
docker exec javisi_openclaw node /app/openclaw.mjs config show 2>&1 | python3 -m json.tool | grep -A5 '"channels"'
```

### 5.E Doctor modifie config en boucle (changedPaths=5 ou plus)

Indique une cle que le doctor corrige systematiquement → conflit entre template Ansible et ce qu'attend OpenClaw.

Identifier la cle avec le script diff (voir 5.A), puis mettre a jour `openclaw.json.j2` pour eliminer le conflit.

---

## 6. Rollback

Si la validation echoue et que le fix rapide ne suffit pas :

```bash
# 6.a Restaurer la version precedente dans versions.yml
openclaw_image: "ghcr.io/openclaw/openclaw:2026.2.15"  # version precedente

# 6.b Restaurer la config runtime si elle a ete corrompue
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@<VPS_IP> \
  "cp /opt/javisi/data/openclaw/system/openclaw.json.pre-upgrade-YYYYMMDD \
      /opt/javisi/data/openclaw/system/openclaw.json"

# 6.c Redeploy
make deploy-role ROLE=openclaw ENV=prod
```

---

## 7. References

| Document | Contenu |
|----------|---------|
| `docs/TROUBLESHOOTING.md` section 11 | Tous les pieges OpenClaw par categorie |
| `docs/REX-SESSION-2026-02-23b.md` | Pieges decouverts lors de la montee v2026.2.15 → v2026.2.22 |
| `roles/openclaw/templates/openclaw.json.j2` | Template de config (source de verite) |
| `inventory/group_vars/all/versions.yml` | Version pinned |
| `roles/openclaw/defaults/main.yml` | Modeles par defaut des agents |

---

## 8. Historique des Versions Deployees

| Version | Date | Statut | Pieges |
|---------|------|--------|--------|
| `2026.2.15` | 2026-02-15 | Remplace | Premier deploiement — config compat |
| `2026.2.22` | 2026-02-23 | **Actuelle** | Plugins bundled desactives par defaut (REX-45) |
