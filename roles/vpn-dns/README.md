# vpn-dns

Deploy Headscale extra DNS records for VPN admin access

## Rôle

Rôle Ansible du projet VPAI. Deploy Headscale extra DNS records for VPN admin access

## Structure

`tasks`, `handlers`, `templates`, `defaults`, `meta`, `tests Molecule`

## Variables principales

Définies dans `defaults/main.yml` :

- `vpn_dns_headscale_config_path`
- `vpn_dns_headscale_compose_path`
- `vpn_dns_records`

## Utilisation

Déployé via le playbook principal :

```bash
ansible-playbook playbooks/stacks/site.yml --tags vpn-dns
```

## Tests

```bash
cd roles/vpn-dns && molecule test
```

---

_Voir le `README.md` racine et `TECHNICAL-SPEC.md` pour le contexte plateforme._
