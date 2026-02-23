# REX — Session 2026-02-23 (Session 9)

> **Theme** : Creative Stack Pi (DNS, ComfyUI, Remotion, OpenCut), VPN Error Pages, Subdomain Swap
> **Duree** : ~5h
> **Resultat** : DNS Pi corrige, Remotion API OK, OpenCut role cree (on-demand), pages d'erreur stylees, sous-domaines reorganises

---

## Problemes Resolus

### REX-39 — Split DNS : subdomains Pi absents de Headscale extra_records

**Symptome** : `studio.ewutelo.cloud` et `cut.ewutelo.cloud` resolvent vers `87.106.30.160` (IP publique VPS) au lieu de `100.64.0.1` (Tailscale Pi). `oc.ewutelo.cloud` fonctionne.

**Cause** : `remotion_subdomain` et `comfyui_subdomain` etaient declares **uniquement** dans les role defaults (`roles/remotion/defaults/main.yml`, `roles/comfyui/defaults/main.yml`). Le role `vpn-dns` s'execute sur le serveur VPN, pas sur le Pi → les role defaults du Pi ne sont pas charges → variables vides → records silencieusement omis.

**Fix** :
1. Declarer les variables dans `inventory/group_vars/all/main.yml` (visible par tous les hosts) :
```yaml
comfyui_subdomain: "studio"
remotion_subdomain: "re"
opencut_subdomain: "cut"
```
2. Creer `playbooks/vpn-dns.yml` — playbook dedie qui :
   - Play 1 : Gather `tailscale ip -4` depuis `prod` + `workstation`
   - Play 2 : Execute `vpn-dns` sur `vpn-server` avec les facts collectes

**Regle** : Toute variable utilisee par un role qui s'execute sur un **autre host** doit etre dans `group_vars/all`, pas dans les role defaults.

---

### REX-40 — ComfyUI crash loop : ModuleNotFoundError `requests`

**Symptome** : Container ComfyUI en restart loop. Logs : `ModuleNotFoundError: No module named 'requests'`.

**Cause** : ComfyUI v0.3.27 importe `requests` dans `frontend_management.py` mais ne l'inclut pas dans `requirements.txt`.

**Fix** : Ajouter `requests` au pip install dans le Dockerfile :
```dockerfile
RUN pip install --no-cache-dir --target=/build/deps \
    -r /build/comfyui/requirements.txt \
    requests
```

**Regle** : Toujours verifier les imports Python du code source — ne pas se fier uniquement au `requirements.txt` du projet.

---

### REX-41 — Remotion "Cannot GET /"

**Symptome** : `https://cut.ewutelo.cloud/` retourne `Cannot GET /` (Express 404).

**Cause** : Le serveur Express Remotion n'avait aucune route pour `GET /` — seulement `/health`, `/renders`, etc.

**Fix** : Ajouter une route `GET /` retournant un JSON d'info API dans `roles/remotion/files/server/index.ts` :
```typescript
app.get("/", (_req, res) => {
  res.json({
    service: "Remotion Render Server",
    status: "ok",
    endpoints: { health: "GET /health", createRender: "POST /renders", ... }
  });
});
```

---

### REX-42 — Docker network stale reference apres docker rmi

**Symptome** : `docker compose up -d` echoue avec `network 8dba971dd46... not found`.

**Cause** : `docker rmi` supprime les images mais pas les references reseaux dans les containers arretes. Au restart, Docker cherche l'ancien network ID qui n'existe plus.

**Fix** : `docker compose -f <file> down && docker compose -f <file> up -d` (down supprime containers + reseaux, up recree tout proprement).

**Regle** : Ne jamais utiliser `docker rmi` seul — toujours faire un `docker compose down` d'abord pour nettoyer les references.

---

### REX-43 — handle_response vs handle_errors dans Caddy

**Symptome** : `handle_response` pour intercepter les 502 (service arrete) ne fonctionne pas.

**Cause** : `handle_response` intercepte les **reponses de l'upstream**. Quand l'upstream est down, il n'y a **pas de reponse** — c'est une erreur Caddy interne. Il faut utiliser `handle_errors` pour les erreurs Caddy (502, 503 quand l'upstream est inatteignable).

**Fix** :
```caddyfile
handle_errors {
    @stopped expression `{http.error.status_code} in [502, 503]`
    respond @stopped <<HTML
    ...page stylisee...
    HTML 502
}
```

---

### REX-44 — Caddy workstation : service systemd = caddy-workstation

**Symptome** : `systemctl status caddy` retourne `Unit caddy.service not found`. Le Caddyfile n'est pas a `/etc/caddy/Caddyfile`.

**Cause** : Le role `workstation-caddy` deploie un service custom :
- Service : `caddy-workstation.service`
- Config : `/opt/workstation/configs/caddy/Caddyfile`
- Binary : `/usr/bin/caddy` (custom build xcaddy + module OVH DNS)

**Commandes correctes** :
```bash
sudo systemctl status caddy-workstation
sudo systemctl reload caddy-workstation
sudo caddy validate --config /opt/workstation/configs/caddy/Caddyfile
```

---

## Fonctionnalites Ajoutees

### OpenCut — Editeur video on-demand sur Pi

**Role** : `roles/opencut/` — deploy OpenCut (Next.js video editor) sur le Pi.

**Architecture** :
- 4 containers : opencut (Next.js) + opencut-db (PostgreSQL) + opencut-valkey (Redis) + opencut-redis (serverless-redis-http)
- `opencut_autostart: false` → deploye mais pas demarre
- Controle via Telegram : `/opencut start`, `/opencut stop`, `/opencut status`
- Workflow n8n `opencut-control` : SSH sur Pi via Tailscale VPN

**Secrets Vault requis** :
```yaml
vault_opencut_db_password: "..."       # openssl rand -hex 24
vault_opencut_auth_secret: "..."       # openssl rand -hex 32
vault_opencut_redis_token: "..."       # openssl rand -hex 24
```

### VPN Error Pages — Pages stylees terminal/hacker

Deux themes de pages d'erreur sur le workstation Pi Caddy :

| Erreur | Theme | Couleurs | Message |
|--------|-------|----------|---------|
| **403** (hors VPN) | Rouge/vert | `#ff3c3c` + `#00ff41` | "Acces non autorise — VPN requis" |
| **502/503** (OpenCut arrete) | Bleu/cyan | `#0096ff` + `#00d4ff` | "Service en veille — /opencut start" |

Les deux pages reprennent le style de `restricted-zone.html` du VPS (terminal hacker, coins decoratifs, scanlines, grille de fond).

### Reorganisation des sous-domaines

| Service | Avant | Apres | Raison |
|---------|-------|-------|--------|
| OpenCut | `edit.ewutelo.cloud` | `cut.ewutelo.cloud` | Plus intuitif pour un editeur video |
| Remotion API | `cut.ewutelo.cloud` | `re.ewutelo.cloud` | API interne, sous-domaine court |

**Fichiers impactes** (tous via variables Jinja2 — un seul changement dans `group_vars/all/main.yml`) :
- `inventory/group_vars/all/main.yml`
- `roles/opencut/defaults/main.yml`
- `roles/remotion/defaults/main.yml`
- `roles/n8n-provision/files/workflows/opencut-control.json` (fallback JS)
- Tous les templates `.j2` s'adaptent automatiquement

### Playbook VPN-DNS dedie

`playbooks/vpn-dns.yml` — resout le probleme de scoping des variables entre hosts :
- Play 1 : Gather Tailscale IPs depuis `prod` + `workstation`
- Play 2 : Deploie les extra_records Headscale sur `vpn-server`
- Commande : `make deploy-vpn-dns`

---

## Deploiements de la Session

```bash
# 1. DNS VPN (extra_records Headscale)
make deploy-vpn-dns

# 2. Caddy workstation (pages d'erreur + nouveaux sous-domaines)
ansible-playbook playbooks/workstation.yml --tags workstation-caddy --diff

# 3. Remotion (route GET / ajoutee)
make deploy-remotion
```

---

## Fichiers Modifies

### Nouveaux fichiers
- `playbooks/vpn-dns.yml`
- `roles/opencut/defaults/main.yml`
- `roles/opencut/files/Dockerfile`
- `roles/opencut/templates/docker-compose-opencut.yml.j2`
- `roles/opencut/tasks/main.yml`
- `roles/opencut/handlers/main.yml`
- `roles/n8n-provision/files/workflows/opencut-control.json`
- `docs/REX-SESSION-2026-02-23.md`

### Fichiers modifies
- `inventory/group_vars/all/main.yml` — subdomains Pi + opencut
- `roles/comfyui/files/Dockerfile` — ajout `requests` pip dep
- `roles/remotion/files/server/index.ts` — ajout `GET /` route
- `roles/remotion/defaults/main.yml` — subdomain `re`
- `roles/opencut/defaults/main.yml` — subdomain `cut`
- `roles/workstation-caddy/templates/Caddyfile-workstation.j2` — VPN ACL + error pages
- `roles/n8n-provision/tasks/main.yml` — opencut-control dans 4 listes
- `roles/n8n/templates/n8n.env.j2` — OPENCUT_DOMAIN
- `roles/vpn-dns/defaults/main.yml` — opencut DNS record
- `playbooks/workstation.yml` — ajout role opencut
- `Makefile` — deploy-opencut, deploy-vpn-dns
- `docs/TROUBLESHOOTING.md` — sections 0.12, 12.7

*Derniere mise a jour : 2026-02-23 — Session 9*
