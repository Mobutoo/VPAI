# webhook-relay

Relay Meta/Instagram webhooks via Seko-VPN to the VPS over the Headscale mesh.

## Rôle

Rôle Ansible du projet VPAI. Installe Caddy (apt) sur l'hôte VPN (Seko-VPN) et
configure un reverse proxy qui relaie les webhooks entrants vers le Caddy du VPS
via le mesh WireGuard :

```
Meta → hook.<domain> (IP publique Seko-VPN) → Caddy apt → VPN mesh → VPS Caddy → n8n
```

Remplace l'ancien tunnel cloudflared.

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`

## Variables principales

Définies dans `defaults/main.yml` :

- `webhook_relay_enabled`
- `webhook_relay_domain`
- `webhook_relay_vps_tailscale_ip`
- `webhook_relay_vps_domain`
- `webhook_relay_paths`
- `webhook_relay_acme_email`
- `webhook_relay_caddy_version`
- `webhook_relay_config_dir`
- `webhook_relay_log_dir`

## Utilisation

Déployé via son playbook dédié, ciblant le groupe d'hôtes `vpn` :

```bash
ansible-playbook playbooks/apps/webhook-relay.yml
```

## Tests

- Le playbook est couvert par `ansible-lint` en CI.
- Scénario Molecule : `molecule/default/` (conteneur Debian systemd). Le scénario
  installe Caddy (apt), rend et **valide** le `Caddyfile` (`caddy validate`), puis
  vérifie la présence des chemins de relay. Les tâches runtime (démarrage du
  service systemd, règles UFW, health-check HTTP public) sont neutralisées via
  `common_molecule_mode: true` — même pattern que le rôle `caddy` —, donc aucun
  impact sur le comportement de production (`default(false)`).

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
