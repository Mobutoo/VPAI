# REX — Mission Control / OpenClaw : Connexion WebSocket bloquée

**Date** : 2026-02-20
**Statut** : 🔴 Bloqué — connexion `wss://javisi.ewutelo.cloud` échoue depuis Mission Control (Pi)

---

## 1. Objectif

Mission Control est un dashboard Next.js (v1.1.0, installé sur le Pi à `/opt/workstation/mission-control`)
qui doit se connecter au gateway WebSocket OpenClaw hébergé sur le VPS Sese-AI pour :

- Lister et piloter les sessions d'agents IA
- Afficher l'état des agents (concierge, builder, writer…)
- Créer des tâches et les dispatcher aux agents
- Montrer le statut "online" dans le dashboard

**Architecture visée :**

```
[Browser Pi]
     |
     | HTTP
     v
[Mission Control :4000]   ← Next.js server-side
     |
     | wss://javisi.ewutelo.cloud  (WebSocket Secure)
     |
     v
[Caddy VPS]  (proxy TLS, VPN-only ACL)
     |
     | ws://openclaw:18789  (réseau backend Docker)
     v
[OpenClaw Gateway]  (port 18789, protocole v3, challenge Ed25519)
```

---

## 2. Ce qui fonctionne

| Composant | Statut | Preuve |
|-----------|--------|--------|
| Mission Control service | ✅ UP | `✓ Ready in 426ms` |
| DB SQLite | ✅ Correct path | `/opt/workstation/data/mission-control/mission-control.db` |
| Workspace dirs | ✅ Créés | `/home/mobuone/projects` |
| DNS `mc.ewutelo.cloud` | ✅ Résout | → `100.64.0.1` (Pi via Headscale) |
| HTTPS `javisi.ewutelo.cloud` | ✅ 200 OK depuis Pi | `curl -s ... → 200` |
| WebSocket HTTP/1.1 upgrade | ✅ 101 depuis Pi | Test Python → `HTTP 101 Switching Protocols` |
| Caddy `versions 1.1` fix | ✅ Déployé | Voir fix section 3.1 |
| Device identity MC | ✅ Générée | `~/.mission-control/identity/device.json` |
| OpenClaw `allowedOrigins` | ✅ Mis à jour | `["https://javisi.ewutelo.cloud", "https://mc.ewutelo.cloud"]` |
| OpenClaw `allowInsecureAuth` | ✅ Activé | `true` dans config runtime |
| Control UI web (browser) | ✅ Connecté | Logs OC : `webchat connected remote=172.20.2.5 client=openclaw-control-ui` |

---

## 3. Historique des corrections déjà appliquées

### 3.1 Fix Caddy : HTTP/2 casse le WebSocket upgrade (✅ résolu)

**Symptôme** : Caddy répondait `HTTP/2 200` au lieu de `HTTP/1.1 101 Switching Protocols` lors du handshake WebSocket.

**Cause** : HTTP/2 ne supporte pas le WebSocket upgrade RFC 6455. Caddy utilisait H2 par défaut pour le reverse_proxy vers OpenClaw.

**Fix** dans `roles/caddy/templates/Caddyfile.j2` :
```caddyfile
reverse_proxy openclaw:18789 {
    transport http {
        versions 1.1
    }
}
```

**Vérification** (depuis le Pi) :
```bash
python3 -c "
import http.client, ssl
conn = http.client.HTTPSConnection('javisi.ewutelo.cloud', context=ssl.create_default_context())
conn.request('GET', '/', headers={'Connection':'Upgrade','Upgrade':'websocket','Sec-WebSocket-Key':'dGhlIHNhbXBsZSBub25jZQ==','Sec-WebSocket-Version':'13'})
print(conn.getresponse().status)  # → 101 ✅
"
```

### 3.2 Fix .env Mission Control : mauvais nom de variable (✅ résolu)

**Symptôme** : DB créée à `/opt/workstation/mission-control/mission-control.db` au lieu de `/opt/workstation/data/mission-control/mission-control.db`.

**Cause** : Le template `.env.j2` utilisait `DATABASE_URL=file:...` mais le code source MC lit `process.env.DATABASE_PATH`.

**Fix** : `DATABASE_URL` → `DATABASE_PATH` dans `roles/mission-control/templates/mission-control.env.j2`.

### 3.3 Fix OpenClaw config : allowedOrigins et allowInsecureAuth manquants (✅ résolu partiellement)

La config live sur le VPS (`/home/node/.openclaw/openclaw.json`, gérée par le container runtime) n'avait pas `allowedOrigins` ni `allowInsecureAuth`.

**Fix** : Redéploiement du role `openclaw` → config mise à jour dans le container.

**Config gateway actuelle (runtime)** :
```json
{
  "port": 18789,
  "mode": "local",
  "bind": "lan",
  "controlUi": {
    "enabled": true,
    "basePath": "/",
    "allowedOrigins": [],
    "allowInsecureAuth": true
  },
  "auth": {
    "mode": "token",
    "token": "${OPENCLAW_GATEWAY_TOKEN}"
  },
  "trustedProxies": ["172.20.2.0/24"]
}
```

> Note : `allowedOrigins` est maintenant vide (`[]`) après test pour éliminer cette piste — sans effet, la connexion échoue toujours.

---

## 4. Problème actuel : connexion refusée sans trace dans les logs

### Symptôme

```bash
# Depuis le Pi
curl http://localhost:4000/api/openclaw/status
→ {"connected":false,"error":"Failed to connect to OpenClaw Gateway","gateway_url":"wss://javisi.ewutelo.cloud"}
```

### Observation clé

**Les logs OpenClaw ne montrent AUCUNE trace de connexion entrante de Mission Control.**

Quand la Control UI web (navigateur) se connecte, on voit :
```
[ws] webchat connected conn=3a5645bc... remote=172.20.2.5 client=openclaw-control-ui webchat vdev
```

Quand Mission Control Node.js essaie de se connecter : **rien**.

Dans les anciens logs (avant le fix HTTP/2), on voyait :
```
[ws] closed before connect conn=... remote=172.20.2.5 fwd=172.20.1.1 origin=n/a host=javisi.ewutelo.cloud ua=node code=1005
```

Après le fix Caddy `versions 1.1` : **ces lignes ont disparu aussi** — la connexion ne reach plus du tout OpenClaw.

### Analyse

Le client MC (`src/lib/openclaw/client.ts`) fait :
```typescript
this.ws = new WebSocket(wsUrl.toString());
// wsUrl = wss://javisi.ewutelo.cloud?token=sk-oc-XcplHPYAUVKhxhvvIBLLLn5OOQcy4LjV
```

Il s'attend à recevoir un `connect.challenge` event pour compléter l'auth Ed25519. Il a un **timeout de 10 secondes**. Si aucun challenge n'arrive → timeout → `close()`.

Le protocole d'auth MC :
1. MC ouvre le WebSocket avec `?token=...` dans l'URL
2. OpenClaw envoie `connect.challenge` avec un nonce
3. MC signe le nonce avec sa clé Ed25519 privée (`~/.mission-control/identity/device.json`)
4. MC envoie `req/connect` avec `{ method: "connect", params: { deviceId, publicKey, signature, ... } }`
5. OpenClaw accepte ou rejette selon si le device est pairé

**Le device MC (`f32631c4...`) est apparu une fois dans `pending.json` mais n'a jamais été approuvé.**

---

## 5. Hypothèses de blocage (par ordre de probabilité)

### H1 — Le gateway ne délivre pas le challenge à un client `ua=node` sans Origin (probable)

OpenClaw fait la distinction entre :
- `client=openclaw-control-ui webchat vdev` → Control UI web (navigateur, envoie `Origin`)
- Connexion Node.js sans `Origin` header → traitement différent, pas de challenge envoyé

Le fix `allowedOrigins: []` n'a pas suffi. La vérification se fait peut-être **avant** d'envoyer le challenge, pas après.

**Test à faire** : Forcer un header `Origin: https://javisi.ewutelo.cloud` dans le client WebSocket de MC :
```typescript
this.ws = new WebSocket(wsUrl.toString(), {
  headers: { Origin: 'https://javisi.ewutelo.cloud' }
});
```

> **Note importante** : `WebSocket` natif du browser N'accepte pas d'option `headers`. Mais MC tourne en Node.js server-side et utilise la lib `ws` (via Next.js) qui, elle, accepte les options. Il faudrait vérifier si Next.js 14 passe les options `ws` ou remplace par `WebSocket` natif.

### H2 — Next.js 14 en production utilise `WebSocket` natif Node.js 22 (probable)

Node.js 22 a `WebSocket` intégré (global, pas besoin de `ws`). Next.js 14 en production peut utiliser ce `WebSocket` natif qui **n'accepte pas d'options headers**.

Si MC utilise le `WebSocket` natif Node.js, il ne peut pas envoyer d'`Origin` et ne peut peut-être pas non plus gérer le handshake de la même façon que la lib `ws`.

**Test à faire** : Vérifier quel `WebSocket` est utilisé à runtime dans le process Next.js de MC.

### H3 — Le device MC n'est pas pairé et le gateway rejette silencieusement (possible)

OpenClaw requiert que les devices se pairent avant de pouvoir se connecter (sauf si `allowInsecureAuth: true` bypasse cette étape). Avec `allowInsecureAuth: true`, le token seul devrait suffire — mais peut-être que ce flag ne s'applique qu'à certains `clientMode`.

Le device MC se déclare avec :
- `clientId: "cli"`
- `clientMode: "ui"`
- `role: "operator"`
- `scopes: ["operator.admin"]`

Le Control UI web utilise probablement `clientMode: "webchat"` — le seul qui semble accepté sans pairing explicite.

**Test à faire** : Modifier temporairement le client MC pour utiliser `clientMode: "webchat"` et voir si la connexion passe.

### H4 — Problème de TLS/SNI dans le contexte Next.js (peu probable)

Le test Python direct depuis le Pi montre que le TLS fonctionne. Mais Next.js en production pourrait avoir un comportement différent (ex: vérification de certificat plus stricte).

---

## 6. Prochaines étapes recommandées

### Étape 1 — Lire les logs MC au niveau console (priorité haute)

Les logs `console.log` de MC ne remontent pas dans `journalctl`. Il faut les capturer directement :

```bash
# Sur le Pi — relancer MC en foreground temporairement pour voir les logs WebSocket
cd /opt/workstation/mission-control
node_modules/.bin/next start --port 4000 2>&1 | tee /tmp/mc-debug.log &
# Puis déclencher la connexion :
curl http://localhost:4000/api/openclaw/status
cat /tmp/mc-debug.log | grep -i openclaw
```

### Étape 2 — Tester avec header Origin forcé (priorité haute)

Identifier exactement quel `WebSocket` est utilisé et si les headers sont supportés.

Sur le Pi :
```bash
cd /opt/workstation/mission-control
node -e "
// Tester si WebSocket natif ou ws lib
const WS = global.WebSocket || require('./node_modules/ws');
const ws = new WS('wss://javisi.ewutelo.cloud?token=sk-oc-XcplHPYAUVKhxhvvIBLLLn5OOQcy4LjV', {
  headers: { 'Origin': 'https://javisi.ewutelo.cloud' }
});
ws.onopen = () => console.log('OPEN');
ws.onmessage = (e) => console.log('MSG:', e.data.substring(0, 200));
ws.onerror = (e) => console.log('ERR:', e.message);
ws.onclose = (e) => console.log('CLOSE:', e.code, e.reason);
setTimeout(() => process.exit(0), 10000);
" 2>&1
```

### Étape 3 — Consulter la documentation OpenClaw (priorité haute)

URL : https://docs.openclaw.ai/cli/gateway

Chercher spécifiquement :
- Comment configurer un client UI externe (non-browser) ?
- `allowInsecureAuth` : qu'est-ce que ça bypasse exactement ?
- `clientMode: "ui"` vs `"webchat"` : quelle différence ?
- Faut-il approuver le device avant la première connexion même avec `allowInsecureAuth: true` ?

### Étape 4 — Patcher MC pour envoyer un Origin header (si Étape 2 confirme que c'est le fix)

Dans `src/lib/openclaw/client.ts`, ligne ~184 :
```typescript
// Avant (probablement)
this.ws = new WebSocket(wsUrl.toString());

// Après (patch)
// @ts-ignore — ws lib accepte les options, WebSocket natif non
this.ws = new WebSocket(wsUrl.toString(), {
  headers: {
    'Origin': new URL(process.env.OPENCLAW_GATEWAY_URL || '').origin
  }
});
```

Ou forcer l'import de la lib `ws` au lieu du WebSocket global :
```typescript
import WebSocket from 'ws';
```

### Étape 5 — Alternative : approuver manuellement le device MC (si pairing requis)

Si `allowInsecureAuth: true` ne bypasse pas le pairing, il faut approuver le device. Le deviceId MC est :
`f32631c483bfadb35d530d8bac4e45d3ac3987914f60d647e783a0529ccfec3b`

Script pour approuver directement via `paired.json` :
```bash
docker exec javisi_openclaw node -e "
const fs = require('fs');
const path = '/home/node/.openclaw/devices/paired.json';
const paired = JSON.parse(fs.readFileSync(path, 'utf8'));
paired['f32631c483bfadb35d530d8bac4e45d3ac3987914f60d647e783a0529ccfec3b'] = {
  deviceId: 'f32631c483bfadb35d530d8bac4e45d3ac3987914f60d647e783a0529ccfec3b',
  publicKey: 'txuqCzVOaQCgoxqtJD8H9myt_UXZxlQSF7DiMS6vWDI',
  platform: 'linux',
  clientId: 'cli',
  clientMode: 'ui',
  role: 'operator',
  scopes: ['operator.admin'],
  approvedAtMs: Date.now(),
  label: 'Mission Control Pi'
};
fs.writeFileSync(path, JSON.stringify(paired, null, 2));
console.log('Device approuvé');
"
# Puis restart OpenClaw pour recharger
docker restart javisi_openclaw
```

---

## 7. Ce qu'on ne sait pas encore

1. **Pourquoi les connexions MC ont disparu des logs OpenClaw** après le fix `versions 1.1` de Caddy. Avant : `closed before connect ua=node code=1005`. Après : silence total. Ça suggère que la connexion échoue maintenant avant même d'atteindre Caddy — potentiellement un bug dans le transport HTTP/1.1 forcé avec WebSocket.

2. **Si `allowInsecureAuth: true` bypass le pairing** ou seulement le challenge Ed25519. La doc officielle n'a pas été consultée.

3. **Quel WebSocket est utilisé** par Next.js 14 en production sur Node.js 22 — natif global ou lib `ws` de `node_modules`.

---

## 8. Commits liés à cette investigation

| Hash | Description |
|------|-------------|
| `e483de5` | `fix(mission-control): DATABASE_PATH + workspace paths + DB migration` |
| `1670136` | `fix(caddy): force HTTP/1.1 pour reverse_proxy OpenClaw (WebSocket)` |
| `8db2294` | `docs: HTTP/2+WebSocket piege dans TROUBLESHOOTING section 11` |

---

## 9. REX — Leçons pour la suite

- **Le fix Caddy `versions 1.1` est correct** pour le WebSocket RFC 6455, mais il a peut-être introduit un comportement inattendu pour les clients Node.js (`ua=node`) qui ne voient plus leurs connexions dans les logs OC. À investiguer.
- **`allowedOrigins` n'est pas le problème** — vider le tableau n'a rien changé.
- **Le pairing device OpenClaw est obligatoire** même pour les clients UI sauf si `allowInsecureAuth` bypasse tout — à confirmer via la doc.
- **Les logs Next.js en production sont invisibles** dans `journalctl` — prévoir un mode debug ou un fichier de log explicite pour les sessions de debug.
- **Deux configs OpenClaw à distinguer** :
  - `/opt/javisi/configs/openclaw/openclaw.json` → config déployée par Ansible (source de vérité)
  - `/home/node/.openclaw/openclaw.json` → config runtime dans le container (celle qui compte)
  - Ces deux fichiers peuvent diverger si le container modifie sa config à chaud (reload automatique détecté).
