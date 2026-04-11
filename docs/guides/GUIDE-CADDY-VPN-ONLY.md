# Guide — Mise sous VPN d'un Caddy en Docker (Headscale/Tailscale)

> **Destinataire** : Claude Sonnet 4 chargé de sécuriser le Caddy de **Seko-VPN** (serveur Ionos hébergeant Headscale)
>
> **Contexte** : Ce guide est extrait du REX complet du projet VPAI après la mise sous VPN réussie du VPS principal (OVH). Il documente tous les pièges rencontrés et leurs solutions, pour qu'une session future puisse reproduire la même configuration sans les mêmes erreurs.

---

## 1. Contexte et Objectif

**Seko-VPN** est un serveur distinct (Ionos) qui héberge Headscale (serveur de coordination Tailscale auto-hébergé). Il a son propre Caddy en Docker. L'objectif est de restreindre ses interfaces admin (Headscale UI, Grafana éventuel, dashboard) aux seuls clients connectés au mesh VPN Tailscale.

**Ce qui a été fait sur le VPS OVH (référence)** :
- Caddy avec snippet `vpn_only` : bloque tout client non-VPN → renvoie `restricted-zone.html`
- Split DNS via Headscale `extra_records` + `override_local_dns: true`
- Fix HTTP/3 QUIC/UDP (Docker bridge DNAT)
- Fix heredoc Caddyfile (`MARKER 200` sur une ligne)

---

## 2. Prérequis Obligatoires

### 2.1 Split DNS — SANS ça, le VPN ACL ne fonctionne pas

**Le piège le plus critique** : si les clients résolvent les sous-domaines vers l'IP publique du serveur, leur trafic transite par Internet → Caddy voit une IP publique, pas une IP Tailscale → **bloqué même si le client est sur le VPN**.

**Solution obligatoire** : les clients Tailscale doivent résoudre les domaines admin vers l'IP Tailscale de Seko-VPN.

Dans la config Headscale (`config.yaml`), deux paramètres indispensables :

```yaml
dns:
  magic_dns: true
  base_domain: <headscale_base_domain>
  override_local_dns: true          # CRITIQUE — sans ça, Windows ignore les extra_records
  nameservers:
    global:
      - 1.1.1.1
      - 8.8.8.8
  extra_records:
    # Pour chaque domaine admin de Seko-VPN, ajouter un enregistrement
    # pointant vers l'IP Tailscale de Seko-VPN (ex: 100.64.0.X)
    - name: "headscale.<domain>"
      type: "A"
      value: "<seko_vpn_tailscale_ip>"
    - name: "grafana.<domain>"
      type: "A"
      value: "<seko_vpn_tailscale_ip>"
    # ... autant que nécessaire
```

> **REX** : `override_local_dns: false` (défaut Headscale) = le DNS Tailscale est "advisory" uniquement. Windows utilise ses propres DNS et ignore les `extra_records`. **Doit être `true`** pour que les clients utilisent le DNS Headscale.

**Vérification côté client Windows** :
```powershell
# Doit retourner l'IP Tailscale de Seko-VPN (100.64.0.X), PAS l'IP publique
Resolve-DnsName headscale.<domain>

# Si retourne l'IP publique → override_local_dns non actif ou Tailscale DNS désactivé
# → Vérifier : Tailscale Settings → "Use Tailscale DNS" = ON
```

**Forcer la résolution via le DNS Headscale** (debug) :
```powershell
Resolve-DnsName headscale.<domain> -Server 100.100.100.100
# 100.100.100.100 = IP fixe du resolver MagicDNS Tailscale
```

---

## 3. Configuration Caddy — Snippet VPN ACL

### 3.1 Structure de base

```caddyfile
{
    admin localhost:2019
    servers {
        # OBLIGATOIRE pour que client_ip fonctionne en Docker DNAT
        trusted_proxies static private_ranges
    }
}

# Snippet réutilisable — à importer sur chaque vhost protégé
(vpn_only) {
    # DEUX CIDRs obligatoires (voir section 3.2)
    @blocked not client_ip 100.64.0.0/10 172.20.1.0/24
    error @blocked 403
}

(vpn_error_page) {
    handle_errors {
        root * /srv
        rewrite * /restricted-zone.html
        file_server
    }
}

# Exemple de vhost protégé
headscale.<domain> {
    import vpn_only
    import vpn_error_page
    reverse_proxy headscale:8080
}
```

### 3.2 Piège HTTP/3 — Deux CIDRs obligatoires

**Symptôme** : Sites inaccessibles même connecté au VPN Tailscale. Caddy access logs montrent `"client_ip": "172.20.1.1"` au lieu d'une IP Tailscale.

**Cause** : HTTP/3 utilise QUIC/UDP. Docker fait un DNAT UDP qui substitue l'IP source par l'IP de la gateway du réseau bridge Docker. Le client Tailscale a bien son IP `100.64.x.x` mais Caddy reçoit `172.20.1.1` (gateway du réseau frontend Docker).

**Flux HTTP/3 problématique** :
```
Client Tailscale (100.64.0.5)
  → UDP/443 vers VPS
  → Docker DNAT UDP → substitue source par 172.20.1.1 (gateway bridge)
  → Caddy voit client_ip = 172.20.1.1 (hors CIDR 100.64.0.0/10)
  → BLOQUÉ même si client est sur VPN ✗
```

**Flux HTTP/2 (TCP) — pas de problème** :
```
Client Tailscale (100.64.0.5)
  → TCP/443 vers VPS
  → Docker DNAT TCP → préserve l'IP source
  → Caddy voit client_ip = 100.64.0.5 ✓
```

**Fix** : ajouter le CIDR du réseau frontend Docker dans la règle `not client_ip` :

```caddyfile
# À adapter avec ton sous-réseau Docker frontend réel
@blocked not client_ip 100.64.0.0/10 172.20.1.0/24
#                      ^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^
#                      Tailscale     Docker bridge frontend
```

> **Sécurité** : La plage `172.20.1.0/24` est un réseau Docker interne, inatteignable depuis Internet. Pas de risque d'usurpation.

**Attention** : Appliquer ce double CIDR **partout** où tu écris une règle `client_ip` manuellement, pas seulement dans le snippet. Tout bloc `handle {}` inline avec sa propre règle `@blocked` doit aussi avoir les deux CIDRs (voir section 3.3).

### 3.3 Piège des règles inline — cohérence obligatoire

Si un bloc `handle` a sa propre règle `@blocked` (sans utiliser le snippet `vpn_only`), elle doit aussi inclure les deux CIDRs :

```caddyfile
# ✗ FAUX — manque le CIDR Docker bridge → 403 en HTTP/3
handle {
    @blocked_root not client_ip 100.64.0.0/10
    error @blocked_root 403
    file_server
}

# ✓ CORRECT
handle {
    @blocked_root not client_ip 100.64.0.0/10 172.20.1.0/24
    error @blocked_root 403
    file_server
}
```

> **REX** : Sur le VPS OVH, le domaine racine `ewutelo.cloud` retournait 403 sous VPN car son `handle {}` catch-all avait la règle inline avec un seul CIDR, alors que le snippet `vpn_only` avait correctement les deux. **Toute règle `client_ip` manuelle = double CIDR**.

### 3.4 Piège heredoc — status code sur la même ligne

Si tu utilises `respond <<MARKER` (heredoc Caddyfile), le code HTTP doit être **sur la même ligne** que le marqueur de fermeture :

```caddyfile
# ✗ FAUX — "unrecognized directive: 200" → crash Caddy
respond <<BOOTSTRAP
<!DOCTYPE html>...
BOOTSTRAP
200

# ✓ CORRECT — code HTTP immédiatement après le marqueur
respond <<BOOTSTRAP
<!DOCTYPE html>...
BOOTSTRAP 200
```

**Impact du crash** : Caddy redémarre en boucle. Pendant ce temps, le DNS Docker interne ne se résout pas encore (container pas UP) → les autres containers qui dépendent de noms DNS Caddy accumulent des timeouts.

---

## 4. Page d'erreur VPN (restricted-zone.html)

Quand un client non-VPN tente d'accéder, Caddy sert une page HTML statique depuis `/srv` via `handle_errors`. Elle doit exister dans `/srv/restricted-zone.html` à l'intérieur du container Caddy.

**Caddy ne retourne pas un message d'erreur standard** — il sert un fichier HTML. C'est pourquoi un service en 502 peut ressembler à un 403 VPN (les deux affichent `restricted-zone.html` si `handle_errors` est configuré globalement).

**Debug** : vérifier les logs Caddy access pour voir le vrai statut :
```bash
docker logs <projet>_caddy 2>&1 | grep -E '"status":[0-9]+' | tail -20
# Chercher "status":502 vs "status":403
```

---

## 5. trusted_proxies — Pourquoi c'est obligatoire

Sans `trusted_proxies static private_ranges`, Caddy calcule `client_ip` différemment de `remote_ip`. En environnement Docker :

- `remote_ip` = IP source TCP du paquet entrant (ce que le kernel voit)
- `client_ip` = IP dans l'en-tête `X-Forwarded-For` si le proxy est trusted, sinon = `remote_ip`

Avec `trusted_proxies static private_ranges`, Caddy fait confiance aux proxies sur les plages RFC 1918 (172.16.0.0/12, 10.0.0.0/8, 192.168.0.0/16) → utilise `X-Forwarded-For` correctement → `client_ip` = vraie IP du client.

Sans ça, les règles `client_ip` dans les snippets peuvent ne pas fonctionner comme attendu.

---

## 6. Checklist de Validation

Après déploiement, valider dans cet ordre :

```
□ 1. Split DNS actif
      Windows : Resolve-DnsName headscale.<domain>
      → doit retourner IP Tailscale de Seko-VPN (100.64.0.X)
      → PAS l'IP publique

□ 2. Accès VPN
      Navigateur avec VPN actif : https://headscale.<domain>
      → doit afficher l'interface (HTTP 200)

□ 3. Blocage hors VPN
      Navigateur sans VPN : https://headscale.<domain>
      → doit afficher restricted-zone.html (HTTP 403)

□ 4. HTTP/3 spécifiquement
      Vérifier les logs Caddy : grep "client_ip" access.log
      → connexions VPN doivent montrer 100.64.0.X OU 172.20.1.1
      → connexions bloquées doivent montrer IP publique + status 403

□ 5. Domaine racine
      https://<domain> sous VPN → page d'accueil (ou redirect)
      https://<domain> hors VPN → restricted-zone.html
      (Bug courant : le catch-all handle {} a souvent un seul CIDR)

□ 6. Health endpoint (si applicable)
      curl https://<domain>/health → "OK" depuis Internet
      (ce endpoint reste public pour les smoke tests externes)
```

---

## 7. Variables Ansible de Référence (VPAI)

Pour un portage Ansible, voici les variables utilisées côté VPS OVH, à adapter pour Seko-VPN :

```yaml
# Dans defaults/main.yml du rôle caddy
caddy_vpn_cidr: "100.64.0.0/10"              # CIDR Tailscale/Headscale
caddy_docker_frontend_cidr: "172.20.1.0/24"  # Réseau bridge Docker frontend
                                              # Adapter si subnet différent sur Seko-VPN
caddy_vpn_enforce: true                       # Active le snippet vpn_only

# Le snippet vpn_only utilise les deux :
# @blocked not client_ip {{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }}
```

Pour trouver le subnet Docker frontend réel sur Seko-VPN :
```bash
docker network inspect <nom_reseau_frontend> | grep Subnet
```

---

## 8. Résumé des REX (erreurs vécues, à ne pas reproduire)

| # | Symptôme | Cause | Fix |
|---|----------|-------|-----|
| REX-34 | Sites VPN bloqués en HTTP/3 | `client_ip=172.20.1.1` (DNAT UDP Docker) — 1 seul CIDR dans la règle | Ajouter `caddy_docker_frontend_cidr` aux règles `client_ip` |
| REX-35 | Caddy crash loop, directive inconnue `200` | Heredoc : code HTTP sur ligne séparée du marqueur | `MARKER 200` sur la même ligne |
| REX-33 | Split DNS ignoré par Windows | `override_local_dns: false` (défaut Headscale) | `override_local_dns: true` dans `config.yaml` |
| REX-40 | Domaine racine 403 sous VPN | Règle inline `@blocked_root` avec 1 seul CIDR (sans `docker_frontend_cidr`) | Double CIDR sur toute règle `client_ip` manuelle |

> **Règle d'or** : Toute règle `not client_ip` dans Caddy derrière Docker = **deux CIDRs** : le CIDR VPN + le CIDR du réseau bridge Docker frontend.
