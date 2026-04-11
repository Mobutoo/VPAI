# SPEC — Gitea sur Seko-VPN (repo separe)

> Ce fichier documente les specifications pour deployer Gitea sur Seko-VPN (Ionos).
> L'implementation se fait dans le **repo Seko-VPN**, pas dans VPAI.

## Pourquoi Seko-VPN

- Serveur sous-exploite (Headscale + Caddy relay uniquement)
- ~90% RAM libre
- Backup naturel (Zerobyte deja sur ce serveur)
- Separation des concerns (templates != prod IA != station creative)

## Image Docker

```yaml
gitea_image: "gitea/gitea:1.23-rootless"
```

- Variante `rootless` (securite) — pas besoin de `privileged`
- Architecture: `linux/amd64` (Ionos = x86_64)

## Sous-domaine

```
git.<domain_name>
```

- VPN-only (Caddy ACL sur Tailscale CIDR)
- Split DNS record pointant vers `vpn_tailscale_ip`

## Resource Limits

```yaml
gitea_memory_limit: "512M"
gitea_memory_reservation: "128M"
gitea_cpu_limit: "0.5"
```

## Volumes

```yaml
volumes:
  - /opt/services/gitea/data:/var/lib/gitea
  - /opt/services/gitea/config:/etc/gitea
```

## Ports

```yaml
ports:
  - "127.0.0.1:3000:3000"   # Web UI (Caddy reverse proxy)
  - "127.0.0.1:2222:2222"   # SSH git clone (optionnel, VPN mesh suffit)
```

## Caddy Config (ajout au Caddyfile existant sur Seko-VPN)

```caddyfile
git.<domain> {
    tls {
        dns ovh { ... }
        resolvers 8.8.8.8 1.1.1.1
    }

    @blocked not client_ip <vpn_network_cidr>
    error @blocked 403

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        -Server
    }

    reverse_proxy localhost:3000
}
```

## Split DNS (a ajouter dans vpn-dns/defaults/main.yml de VPAI)

Deja fait : si `gitea_subdomain` est defini dans main.yml, ajouter le record.
Pour l'instant on ne l'ajoute pas car Gitea n'est pas encore deploye.

Quand Gitea sera pret dans le repo Seko-VPN, ajouter dans VPAI :

```yaml
# main.yml
gitea_subdomain: "git"

# vpn-dns/defaults/main.yml — nouveau record
([{"name": gitea_subdomain ~ "." ~ domain_name, "type": "A",
   "value": vpn_tailscale_ip}]
 if (gitea_subdomain | default('')) | length > 0
    and vpn_tailscale_ip | default('') | length > 0
 else [])
```

## Docker Compose (dans le repo Seko-VPN)

```yaml
services:
  gitea:
    image: gitea/gitea:1.23-rootless
    container_name: seko_gitea
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
    environment:
      GITEA__database__DB_TYPE: sqlite3
      GITEA__server__ROOT_URL: "https://git.<domain>"
      GITEA__server__SSH_DOMAIN: "git.<domain>"
      GITEA__server__SSH_PORT: "2222"
    volumes:
      - /opt/services/gitea/data:/var/lib/gitea
      - /opt/services/gitea/config:/etc/gitea
    ports:
      - "127.0.0.1:3000:3000"
      - "127.0.0.1:2222:2222"
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "0.5"
        reservations:
          memory: 128M
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:3000/api/v1/version || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

## Usage par VideoRef Engine

Le VideoRef Engine sur Waza clone les templates ComfyUI depuis Gitea via le mesh VPN :

```
git clone https://git.<domain>/mobuone/comfyui-templates.git
```

Variables d'env dans `videoref.env` :
- `GITEA_URL=https://git.<domain>`
- `GITEA_TOKEN=<token>`

## Checklist Deploy (repo Seko-VPN)

- [ ] Creer le role `gitea` dans le repo Seko-VPN
- [ ] Ajouter au playbook Seko-VPN
- [ ] Configurer Caddy (ajout bloc au Caddyfile existant)
- [ ] UFW : port 3000 localhost only (Caddy proxy)
- [ ] Creer le repo `comfyui-templates` dans Gitea
- [ ] Generer un token API pour VideoRef Engine
- [ ] Ajouter `vault_videoref_gitea_url` et `vault_videoref_gitea_token` dans VPAI secrets.yml
- [ ] Ajouter le record Split DNS dans VPAI vpn-dns
