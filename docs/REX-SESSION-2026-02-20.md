# REX Session 2026-02-20 — Workstation Pi : Déploiement complet + VPN

## Contexte

Suite du déploiement du Raspberry Pi 5 (16GB, SSD 256Go) comme **Mission Control / Workstation**.
Continuation de la session 2026-02-18 (voir `REX-SESSION-2026-02-18.md`).

---

## Architecture actuelle (état fin de session)

### Serveurs

| Serveur | IP | Rôle | État |
|---|---|---|---|
| **Sese-AI** (OVH VPS) | 137.74.114.167 | Cerveau IA | ✅ Opérationnel |
| **Seko-VPN** (Ionos) | 87.106.30.160 | Headscale hub VPN | ⚠️ Down (déploiement raté autre session) |
| **Workstation Pi** (RPi5) | 192.168.1.8 (LAN) | Mission Control | ✅ Partiellement opérationnel |

### Services sur Sese-AI (VPS OVH — 137.74.114.167, port SSH 804)

Tous les containers Docker **healthy** :

| Container | Image | État |
|---|---|---|
| javisi_openclaw | ghcr.io/openclaw/openclaw:2026.2.15 | ✅ Up 2j |
| javisi_litellm | ghcr.io/berriai/litellm:v1.81.3-stable | ✅ Up 34h |
| javisi_n8n | docker.n8n.io/n8nio/n8n:2.7.3 | ✅ Up 36h |
| javisi_caddy | caddy:2.10.2-alpine | ✅ Up 34h |
| javisi_postgresql | postgres:18.1-bookworm | ✅ Up 2j |
| javisi_redis | redis:8.0-bookworm | ✅ Up 2j |
| javisi_qdrant | qdrant/qdrant:v1.16.3 | ✅ Up 2j |
| javisi_grafana | grafana/grafana:12.3.2 | ✅ Up 2j |
| javisi_victoriametrics | victoriametrics/victoria-metrics:v1.135.0 | ✅ Up 2j |
| javisi_loki | grafana/loki:3.6.5 | ✅ Up 2j |
| javisi_alloy | grafana/alloy:v1.13.0 | ✅ Up 2j |
| javisi_cadvisor | ghcr.io/google/cadvisor:0.55.1 | ✅ Up 2j |
| javisi_diun | crazymax/diun:4.31.0 | ✅ Up 2j |

### Services sur Workstation Pi (192.168.1.8, port SSH 22)

| Service | Version | Port | État |
|---|---|---|---|
| Mission Control | v1.1.0 | 4000 | ✅ active (running) |
| OpenCode | 1.2.8 | 3456 | ✅ active (running) |
| Caddy (xcaddy+OVH) | v2.10.2 | 80/443 | ❌ caddy.service not found |
| Claude Code CLI | 2.1.49 | — | ✅ installé, OAuth Max Plan ✅ |
| Tailscale | installé | — | ❌ Logged out (Headscale down) |

---

## Ce qui a été fait cette session

### 1. Corrections pre-déploiement

- `workstation_pi_user` corrigé : `pi` → `mobuone`
- `vault_workstation_pi_ip: "192.168.1.8"` ajouté dans `secrets.yml`
- SSH key : `~/.ssh/seko-vpn-deploy` (sur Windows : `/c/Users/mmomb/.ssh/seko-vpn-deploy`)
- `ansible_become_pass` via `vault_workstation_become_pass: "Elikya2015"` dans vault + `hosts.yml`

### 2. Déploiement complet Pi (commit `249afff`)

**workstation-common** : ✅
- Ubuntu 24.04 ARM64, hostname `workstation-pi`
- Node.js v22.22.0 (NodeSource)
- Docker CE, UFW (LAN 192.168.0.0/16 + Tailscale 100.64.0.0/10 autorisés)
- Arborescence `/opt/workstation/{configs,data,logs}`

**mission-control** : ✅ (avec fixes)
- Repo : `crshdn/mission-control` pinné `v1.1.0`
- Fix : `npm ci` (pas `--omit=dev` — tailwindcss est devDep requis pour build)
- Fix : ExecStart = `next start -p 4000` (pas `node .next/standalone/server.js` — repo sans `output:'standalone'`)
- Fix : healthcheck sur `/` (pas `/api/health` — 404)
- Artefact de build : `.next/BUILD_ID`

**opencode** : ✅ (avec fixes)
- Version `1.2.8` — config format changé, `providers`/`workspace` supprimés au niveau root
- npm prefix : `/usr` (NodeSource installe dans `/usr/bin`, pas `/usr/local/bin`)
- Config minimale valide : `{"username": "mobuone"}`

**workstation-caddy** : ✅ (xcaddy ARM64)
- Ubuntu 24.04 n'a que Go 1.22 → plugin `caddy-dns/ovh` requiert Go >= 1.24
- Fix : installation Go 1.24.2 ARM64 depuis `dl.google.com/go/`
- Build : `xcaddy v0.4.5` + `caddy v2.10.2` + `--with github.com/caddy-dns/ovh`
- Caddyfile : proxy `mc.ewutelo.cloud` → :4000 et `oc.ewutelo.cloud` → :3456

### 3. Claude Code CLI OAuth Max Plan (commit `45cb125`)

- Claude Code CLI v2.1.49 installé via npm global dans `workstation-common`
- Auth OAuth faite manuellement via `claude` en SSH (PowerShell → lien URL copié dans navigateur)
- Tokens sauvegardés dans `~/.claude/` sur le Pi — **persistants, auto-renouvelés**
- **Claude Code utilise le quota Max Plan, pas l'API billing**

### 4. OpenCode → LiteLLM (commit `45cb125`)

- `ANTHROPIC_API_KEY` retiré du service systemd
- `LITELLM_API_KEY` injecté à la place
- `opencode.json.j2` configuré avec provider custom LiteLLM (OpenAI-compatible) :
  - Base URL : `https://llm.ewutelo.cloud/v1`
  - Modèles : `litellm/claude-sonnet` (défaut), `litellm/claude-haiku`
- **OpenCode passe par LiteLLM → budget $5/jour centralisé**

### 5. Headscale-node pour Ubuntu (commit `45cb125`, déploiement incomplet)

- Rôle `headscale-node` corrigé pour Ubuntu (était hardcodé Debian) :
  - `DISTRO=$(ansible_facts['distribution'] | lower)` dans l'URL GPG et le repo apt
- `headscale_hostname` : utilise `workstation_pi_hostname` au lieu de `prod_hostname`
- Ajouté dans `playbooks/workstation.yml` (phase 1, avant mission-control)
- **Tailscale installé sur le Pi mais non connecté** — Seko-VPN (Headscale) est down

---

## Ce qui reste à faire

### 🔴 Priorité 1 — Remettre Seko-VPN en ligne

Le serveur Headscale (Ionos 87.106.30.160) est indisponible suite à un déploiement raté depuis une autre session Claude.

**Diagnostic à faire :**
- Accès console Ionos (KVM/VNC) si SSH impossible
- Identifier ce qui a cassé (UFW lockout ? service crash ? mauvais deploy ?)
- Redémarrer Headscale si nécessaire

**Une fois Seko-VPN remonté :**
```bash
# Générer une nouvelle clé preauth (l'ancienne est expirée/utilisée)
# Sur Seko-VPN :
headscale preauthkeys create --user default --expiration 24h
# Mettre à jour dans vault : headscale_auth_key: "nouvelle_cle"
ansible-vault edit inventory/group_vars/all/secrets.yml

# Redéployer Tailscale sur le Pi :
make deploy-role ROLE=headscale-node ENV=workstation
# ou :
wsl.exe -d Ubuntu -e bash -c "cd /home/asus/seko/VPAI && source .venv/bin/activate && ansible-playbook playbooks/workstation.yml --vault-password-file .vault_pass --tags headscale-node"
```

### 🔴 Priorité 2 — Caddy non démarré sur le Pi

`systemctl status caddy` → `Unit caddy.service could not be found`

Le binaire Caddy est buildé (`/usr/bin/caddy`) mais le service systemd n'est pas installé.
Le rôle `workstation-caddy` n'a probablement pas été rejoué après les fixes.

**Fix :**
```bash
wsl.exe -d Ubuntu -e bash -c "cd /home/asus/seko/VPAI && source .venv/bin/activate && ansible-playbook playbooks/workstation.yml --vault-password-file .vault_pass --tags workstation-caddy"
```

Vérifier ensuite :
- `systemctl status caddy` → active
- `curl -k https://mc.ewutelo.cloud` → Mission Control accessible
- `curl -k https://oc.ewutelo.cloud` → OpenCode accessible

### 🟡 Priorité 3 — OpenClaw ↔ Mission Control connectivity

Une fois VPN + Caddy fonctionnels, configurer la communication :

**Architecture cible :**
```
Mission Control (Pi) ←→ OpenClaw (VPS)
    mc.ewutelo.cloud          openclaw.ewutelo.cloud
         ↓ VPN                       ↓ VPN
   Headscale mesh ←——————————→ Headscale mesh
```

Mission Control doit connaître l'URL d'OpenClaw. Vérifier dans la config Mission Control :
```bash
cat /opt/workstation/configs/opencode/.env 2>/dev/null
# ou
grep -r 'openclaw\|OPENCLAW\|OPENCODE' /opt/workstation/
```

Potentiellement ajouter dans le `.env` de Mission Control :
```
OPENCLAW_URL=https://openclaw.ewutelo.cloud
OPENCLAW_API_KEY=<vault_openclaw_api_key>
```

### 🟡 Priorité 4 — DNS records mc/oc dans Headscale

Une fois VPN actif, ajouter les records DNS Split dans Headscale pour que mc/oc soient accessibles depuis le mesh VPN :
```yaml
# Dans config Headscale sur Seko-VPN :
dns:
  extra_records:
    - name: "mc.ewutelo.cloud"
      type: A
      value: "<workstation_pi_tailscale_ip>"
    - name: "oc.ewutelo.cloud"
      type: A
      value: "<workstation_pi_tailscale_ip>"
```

### 🟢 Nice to have — Vérifier OVH credentials dans Caddy Pi

Le Caddyfile utilise `{env.OVH_APPLICATION_KEY}` etc. Vérifier que les credentials OVH sont bien injectés dans le service Caddy (via EnvironmentFile ou Environment= dans le .service).

---

## Fichiers modifiés cette session (vs main avant session)

| Fichier | Changement |
|---|---|
| `inventory/hosts.yml` | + `ansible_become_pass` pour workstation |
| `inventory/group_vars/all/main.yml` | + `workstation_pi_become_pass`, user `mobuone` |
| `inventory/group_vars/all/secrets.yml` | + `vault_workstation_pi_ip`, `vault_workstation_become_pass` |
| `roles/workstation-common/tasks/main.yml` | + installation Claude Code CLI |
| `roles/workstation-common/defaults/main.yml` | + `workstation_claude_code_version: "2.1.49"` |
| `roles/opencode/templates/opencode.service.j2` | `ANTHROPIC_API_KEY` → `LITELLM_API_KEY` |
| `roles/opencode/templates/opencode.json.j2` | Config provider LiteLLM custom |
| `roles/headscale-node/tasks/main.yml` | Debian → Ubuntu/générique |
| `roles/headscale-node/defaults/main.yml` | hostname : `prod_hostname` → `workstation_pi_hostname` |
| `playbooks/workstation.yml` | + rôle `headscale-node`, commentaires mis à jour |

**Dernier commit pushé : `45cb125`** sur `main`

---

## PIèges et REX techniques

### REX-W1 — npm prefix NodeSource
`npm install -g` avec NodeSource v22 installe dans `/usr/bin`, pas `/usr/local/bin`.
→ `opencode_npm_prefix: "/usr"` dans defaults.

### REX-W2 — Mission Control next.config.mjs
`crshdn/mission-control` n'a pas `output: 'standalone'` → pas de `.next/standalone/server.js`.
→ ExecStart : `next start -p {{ mc_port }}` (via node_modules/.bin/next).
→ Artefact : `.next/BUILD_ID` (pas `.next/standalone/server.js`).
→ `npm ci` obligatoire (pas `--omit=dev`) — tailwindcss est devDep requis pour build.

### REX-W3 — OpenCode v1.2.8 config
Config schema changé : `providers` et `workspace` ne sont plus des clés root valides.
→ Config minimale : `{"username": "mobuone"}`.
→ Auth : via `ANTHROPIC_API_KEY` env var OU `opencode auth login` OAuth.

### REX-W4 — xcaddy ARM64 Go version
Ubuntu 24.04 ARM64 = Go 1.22 → insuffisant pour `caddy-dns/ovh` (requiert Go >= 1.24).
→ Installer Go 1.24.2 depuis `dl.google.com/go/go1.24.2.linux-arm64.tar.gz`.
→ xcaddy v0.4.5 depuis `/usr/local/go/bin/go install`.

### REX-W5 — Claude Code OAuth Max Plan
LiteLLM NE PEUT PAS utiliser le Max Plan — c'est OAuth browser-based.
→ Seul `claude` CLI supporte OAuth Max Plan (quota abonnement, pas API billing).
→ Auth : SSH dans tmux → lancer `claude` → copier URL dans navigateur Windows → done.
→ Tokens persistants dans `~/.claude/`, auto-renouvelés.

### REX-W6 — Headscale preauth key usage unique
La clé `headscale_auth_key` dans le vault est à usage unique ET expirante.
→ Après utilisation ou expiration, en générer une nouvelle via `headscale preauthkeys create`.
→ Ne jamais réutiliser une ancienne clé.

### REX-W7 — tailscale up bloque si Headscale down
`tailscale up --login-server=...` attend indéfiniment si le serveur est inaccessible.
→ Ansible timeout ou kill manuel nécessaire.
→ Toujours vérifier Headscale accessible avant de lancer le rôle.

### REX-W8 — SSH key path selon environnement
- WSL Ubuntu : `~/.ssh/seko-vpn-deploy` = `/home/asus/.ssh/seko-vpn-deploy`
- Git Bash / PowerShell Windows : `/c/Users/mmomb/.ssh/seko-vpn-deploy`
- Ansible (WSL) lit depuis WSL → utiliser chemins WSL dans `ansible.cfg`

---

## Commandes utiles pour la reprise

```bash
# SSH Pi (depuis Git Bash/PowerShell Windows)
ssh -i /c/Users/mmomb/.ssh/seko-vpn-deploy mobuone@192.168.1.8

# SSH VPS prod
ssh -i /c/Users/mmomb/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167

# Deploy depuis WSL
wsl.exe -d Ubuntu -e bash -c "cd /home/asus/seko/VPAI && source .venv/bin/activate && ansible-playbook playbooks/workstation.yml --vault-password-file .vault_pass --tags <role>"

# Vérifier état Pi
ssh -i /c/Users/mmomb/.ssh/seko-vpn-deploy mobuone@192.168.1.8 'systemctl status opencode mission-control --no-pager'

# Vérifier état VPS
ssh -i /c/Users/mmomb/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 'docker ps --format "table {{.Names}}\t{{.Status}}"'

# Statut Tailscale Pi
ssh -i /c/Users/mmomb/.ssh/seko-vpn-deploy mobuone@192.168.1.8 'echo Elikya2015 | sudo -S tailscale status'
```
