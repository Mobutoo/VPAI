# Design — Pipeline CI Intégration (CX22 Éphémère)

**Date** : 2026-03-03
**Statut** : Approuvé
**Contexte** : La CI dispose de 25 tests molecule (unitaires par rôle). Ce document décrit l'ajout d'un pipeline d'intégration qui déploie la stack complète sur un serveur réel et valide les services.

---

## Objectif

Valider que l'ensemble de la stack (docker-compose-infra.yml + docker-compose.yml) se déploie correctement et passe les healthchecks sur un serveur Debian 13 propre, en conditions proches de la production.

---

## Architecture

```
integration.yml (schedule dim 05:00 UTC + workflow_dispatch)
├── Job provision  (~3 min)   : hcloud CX22 + OVH DNS *.preprod.ewutelo.cloud
├── Job deploy     (~8 min)   : Ansible site.yml ×2 (deploy + idempotence)
├── Job smoke-tests (~5 min)  : 9 checks HTTPS + 8 checks internes SSH
└── Job destroy    (always)   : delete CX22 + DNS record
```

---

## Déclencheurs

```yaml
on:
  schedule:
    - cron: '0 5 * * 0'   # Dimanche 05:00 UTC — après backups 03:00
  workflow_dispatch:       # Manuel via GitHub UI ou make integration (Waza)
```

**Waza CLI** : `make integration` → `gh workflow run integration.yml --ref main`

---

## Détail des Jobs

### Job 1 — `provision`

**Entrées** : `HETZNER_CLOUD_TOKEN`, `OVH_*` secrets
**Sorties** : `server_id`, `server_ip`

1. Créer CX22 (Debian 13 trixie) via hcloud CLI
   - Label : `ci-integration-${{ github.run_id }}`
   - SSH key : injectée depuis secret
2. Attendre SSH disponible (retry 12×5s)
3. Créer enregistrement DNS via Ansible task :
   - `*.preprod.ewutelo.cloud` → IP CX22 (community.general.ovh_dns)
4. Output `server_id` et `server_ip` pour les jobs suivants

### Job 2 — `deploy` (needs: provision)

1. **Premier déploiement** (serveur vierge) :
   ```
   ansible-playbook playbooks/site.yml
     -e "ansible_host=<ip> ansible_port=22 ansible_user=root ansible_port_override=22"
   ```
   - Attend que tous les services soient `healthy`
2. **Deuxième déploiement** (idempotence) :
   ```
   ansible-playbook playbooks/site.yml
     -e "ansible_host=<ip>"
   ```
   - Parse la sortie Ansible → `changed=0` obligatoire
   - Fail si `changed > 0`

**Note** : Premier deploy via port 22 (avant hardening). Deuxième deploy via port 804 (après hardening — SSH rebind sur Tailscale IP, mais en CI on passe par IP publique via `ansible_port_override` si nécessaire).

### Job 3 — `smoke-tests` (needs: deploy)

#### Checks HTTPS (depuis le runner CI)

| Service | URL | Attendu |
|---------|-----|---------|
| n8n | `https://n8n.preprod.ewutelo.cloud/healthz` | HTTP 200 |
| LiteLLM | `https://llm.preprod.ewutelo.cloud/health` + Bearer | HTTP 200 |
| Grafana | `https://tala.preprod.ewutelo.cloud/api/health` | HTTP 200 |
| Qdrant | `https://qdrant.preprod.ewutelo.cloud/healthz` | HTTP 200 |
| NocoDB | `https://nocodb.preprod.ewutelo.cloud/api/v1/db/meta/projects` | HTTP 200/401 |
| OpenClaw | `https://oc.preprod.ewutelo.cloud/health` | HTTP 200 |
| Palais | `https://palais.preprod.ewutelo.cloud/health` | HTTP 200 |
| Plane | `https://plane.preprod.ewutelo.cloud/api/` | HTTP 200 |
| Caddy | `https://preprod.ewutelo.cloud/health` | HTTP 200 |

#### Checks internes SSH (sur le CX22)

```bash
docker ps --filter health=unhealthy → 0 résultats
psql -c '\l'                        → tables n8n, litellm, nocodb, palais visibles
redis-cli -a $PASS ping             → PONG
curl localhost:6333/healthz         → Qdrant OK
curl localhost:8428/-/healthy       → VictoriaMetrics OK
curl localhost:3100/ready           → Loki OK
curl localhost:5678/healthz         → n8n OK
curl localhost:4000/health          → LiteLLM OK
```

### Job 4 — `destroy` (if: always())

1. `hcloud server delete $server_id`
2. Ansible OVH DNS : supprimer `*.preprod.ewutelo.cloud`

---

## Fichiers à Créer/Modifier

| Fichier | Action |
|---------|--------|
| `.github/workflows/integration.yml` | CRÉER — workflow complet |
| `roles/smoke-tests/templates/smoke-test.sh.j2` | MODIFIER — 17 checks (9 HTTPS via vars + 8 internes) |
| `Makefile` | MODIFIER — ajouter cible `integration` |
| `scripts/ci-provision.sh` | CRÉER — script hcloud provision (optionnel, ou inline) |

---

## Secrets GitHub Requis (environnement `integration`)

| Secret | Usage |
|--------|-------|
| `HETZNER_CLOUD_TOKEN` | Créer/supprimer le CX22 |
| `ANSIBLE_VAULT_PASSWORD` | Déchiffrer secrets.yml |
| `SSH_PRIVATE_KEY` | Connexion SSH au CX22 |
| `OVH_APPLICATION_KEY` | API OVH DNS |
| `OVH_APPLICATION_SECRET` | API OVH DNS |
| `OVH_CONSUMER_KEY` | API OVH DNS |
| `PREPROD_DOMAIN` | `preprod.ewutelo.cloud` |
| `LITELLM_MASTER_KEY` | Smoke test LiteLLM auth |

---

## Contraintes et Décisions

- **Debian 13 trixie** : image `debian-13` sur Hetzner (miroir prod)
- **Domaine preprod** : `preprod.ewutelo.cloud` (différent de prod `ewutelo.cloud`) — aucun impact, Caddy génère les subdomains depuis `{{ domain_name }}`
- **Idempotence stricte** : `changed > 0` au deuxième run = fail CI
- **Cleanup garanti** : job `destroy` avec `if: always()` — le CX22 est supprimé même si les tests échouent
- **Coût estimé** : CX22 ~0.006€/run × 52 runs/an ≈ 0.31€/an (+ runs manuels)
- **Durée totale** : ~16 min (provision 3 + deploy 8 + tests 5)
