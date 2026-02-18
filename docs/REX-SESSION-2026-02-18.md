# REX — Session 2026-02-18 (Session 8)

> **Thème** : VPN-Only Mode, Split DNS, Caddy ACL, LiteLLM Cost Control
> **Durée** : ~6h
> **Résultat** : Tous les services derrière VPN, Split DNS fonctionnel, bot Telegram opérationnel

---

## Problèmes Résolus

### REX-33 (suite) — Split DNS non fonctionnel malgré extra_records

**Symptôme** : `Resolve-DnsName mayi.ewutelo.cloud` retournait `137.74.114.167` (IP publique) alors que les extra_records Headscale étaient déployés.

**Cause** : `override_local_dns: false` (défaut Headscale) → Tailscale ne forçait pas son DNS sur les clients Windows. Le client utilisait le DNS de la box internet → résolution publique.

**Fix** : `override_local_dns: true` dans `roles/headscale/templates/config.yaml.j2` (Seko-VPN).

**Vérification** :
```powershell
Resolve-DnsName mayi.ewutelo.cloud -Server 100.100.100.100  # Doit retourner 100.64.0.14
Resolve-DnsName mayi.ewutelo.cloud                          # Idem après fix
```

---

### REX-34 — Caddy ACL bloque tout (même les connexions VPN)

**Symptôme** : Après activation de `caddy_vpn_enforce=true`, sites inaccessibles depuis VPN ET depuis Internet.

**Cause** : HTTP/3 (QUIC/UDP) via DNAT Docker → `client_ip = 172.20.1.1` (gateway bridge Docker frontend), pas l'IP Tailscale `100.64.x.x`. Le snippet `vpn_only` ne permettait que `100.64.0.0/10`.

**Fix** : Ajout de `caddy_docker_frontend_cidr: 172.20.1.0/24` dans le snippet `vpn_only` :
```caddyfile
@blocked not client_ip 100.64.0.0/10 172.20.1.0/24
error @blocked 403
```

**Sécurité** : `172.20.1.0/24` est le réseau Docker interne — inatteignable depuis Internet. Aucun risque d'usurpation.

---

### REX-35 — Caddyfile heredoc crash en boucle

**Symptôme** : Caddy en `Restarting` en boucle, erreur `unrecognized directive: 200` à la ligne 95.

**Cause** : Dans le template `Caddyfile.j2`, le heredoc Caddy `respond <<BOOTSTRAP` avait le code HTTP 200 sur une ligne séparée :
```caddyfile
BOOTSTRAP
 200           ← Caddy interprète "200" comme une directive inconnue
```

**Fix** : `BOOTSTRAP 200` sur une seule ligne.

**Impact** : 1525 occurrences de `lookup n8n: i/o timeout` sur 16h (Caddy redémarrait avant que le DNS Docker soit initialisé).

---

### REX-36 — LiteLLM health checks : $11.64 en 16h

**Symptôme** : Grafana montre 2 requêtes à ~$8.69 chacune. OpenRouter identifie Perplexity Sonar Pro.

**Cause** : LiteLLM exécute des health checks sur **tous** les modèles configurés toutes les ~38 secondes. Tag : `litellm-internal-health-check`. Perplexity Sonar Pro coûte ~$0.01/appel.

**Données** :
- 1488 health checks Sonar Pro en 16h
- $11.64 gaspillés
- Cadence : 1 check toutes les ~38 secondes

**Fix** : `health_check_interval: 0` dans `router_settings` de `litellm_config.yaml.j2`.

**Alternative** : `health_check_interval: 3600` pour check horaire uniquement.

---

### REX-37 — LiteLLM max_tokens : erreur 402 OpenRouter

**Symptôme** : Bot Telegram retourne "Context overflow prompt too large for the model". Logs LiteLLM : `This request requires more credits, or fewer max_tokens. You requested up to 16000 tokens, but can only afford XXXX`.

**Cause** : Sans `max_tokens` explicite dans `litellm_params`, LiteLLM utilise la valeur par défaut du modèle (16000 pour minimax-m1). OpenRouter facture sur la **réservation** au moment de la requête.

**Fix** : `max_tokens: 4096` sur tous les modèles OpenRouter dans `litellm_config.yaml.j2`.

**Modèles corrigés** : minimax-m25, deepseek-r1, deepseek-v3, glm-5, kimi-k2, grok-search, perplexity-pro, qwen3-coder, seedream.

---

### REX-38 — N8N_PROXY_HOPS manquant

**Symptôme** : Logs n8n : `ERR_ERL_UNEXPECTED_X_FORWARDED_FOR` en boucle.

**Cause** : Caddy ajoute `X-Forwarded-For` mais Express (n8n) a `trust proxy = false` par défaut → express-rate-limit rejette le header.

**Fix** : `N8N_PROXY_HOPS=1` dans `roles/n8n/templates/n8n.env.j2`.

---

## Learnings Architecturaux

### 1. Override DNS Tailscale obligatoire
`override_local_dns: true` est **obligatoire** pour que les extra_records Headscale prennent effet sur les clients. Sans ça, le client utilise son DNS habituel et ignore les extra_records.

### 2. HTTP/3 QUIC/UDP + Docker DNAT = client_ip ≠ IP source
Avec HTTP/3, le DNAT Docker masque l'IP source. Caddy voit le gateway Docker bridge (`172.20.1.1`) au lieu de l'IP Tailscale. Toujours inclure le subnet Docker frontend dans les ACL VPN.

### 3. LiteLLM health checks = coût caché majeur
Par défaut, LiteLLM ping **tous** les modèles toutes les ~38s. Sur des modèles payants comme Perplexity Sonar Pro, c'est ruineux. **Toujours désactiver** avec `health_check_interval: 0`.

### 4. OpenRouter : réservation vs consommation
OpenRouter facture `max_tokens` à la réservation, pas à la consommation. Toujours définir `max_tokens` explicitement dans `litellm_params` pour les modèles OpenRouter.

### 5. Headscale dans Docker : chemins host ≠ chemins container
- Hôte : `/opt/services/headscale/config/config.yaml`
- Container : `/etc/headscale/config.yaml`
- Stratégie Ansible : slurp/parse YAML/combine/write (pas lineinfile, pas JSON séparé)

---

## Fichiers Modifiés

| Fichier | Type de changement |
|---|---|
| `inventory/group_vars/all/main.yml` | `caddy_vpn_enforce: true` permanent |
| `roles/caddy/defaults/main.yml` | Ajout `caddy_docker_frontend_cidr` |
| `roles/caddy/templates/Caddyfile.j2` | Fix ACL CIDR Docker + fix BOOTSTRAP 200 |
| `roles/n8n/templates/n8n.env.j2` | Ajout `N8N_PROXY_HOPS=1` |
| `roles/litellm/templates/litellm_config.yaml.j2` | `health_check_interval: 0` + `max_tokens: 4096` OpenRouter |
| `roles/vpn-dns/defaults/main.yml` | 6 records + chemin Docker correct |
| `roles/vpn-dns/tasks/main.yml` | Réécriture slurp/parse/combine/write |
| `roles/vpn-dns/handlers/main.yml` | community.docker.docker_compose_v2 |
| `VPN/Seko-VPN/roles/headscale/templates/config.yaml.j2` | `override_local_dns: true` |

---

## Commits de cette Session

- `1f1194b` — feat: VPN-only mode — Split DNS, Headscale extra_records, Caddy ACL
- `0b9427f` — fix(litellm): add max_tokens=4096 on all OpenRouter models
- `629297b` — fix(litellm): disable health checks — coût $11.64 en 16h sur Sonar Pro

*Rédigé le 2026-02-18*
