# Prisme — déploiement et reprise

Source d’autorité : rôle `roles/prisme`, exécuté dans `playbooks/stacks/site.yml`.

## Préconditions

- image applicative et images knowledge pinnées par digest ;
- `prisme_enabled=true` uniquement pendant le rollout ciblé ;
- PostgreSQL `prisme`, Qdrant `knowledge_current` et services Banga sains ;
- secrets Prisme déchiffrables ;
- capacité Sese conforme ;
- DNS VPN traité séparément par `playbooks/utils/vpn-dns.yml`.

## DNS — les deux enregistrements sont obligatoires

Le vhost est VPN-only, mais son certificat vient d'ACME : il faut **aussi** un
enregistrement public, sinon Let's Encrypt échoue en `NXDOMAIN looking up A` et Caddy ne sert
aucun certificat (handshake TLS en `internal error`). Même doctrine que `qd`/`mayi`/`tala`.

| Enregistrement | Cible | Source |
|---|---|---|
| Tailnet (split-DNS) | `100.64.0.14` | `roles/vpn-dns/defaults/main.yml` |
| Public OVH (ACME) | IP publique Sese | `ansible-playbook playbooks/utils/ovh-dns-add.yml -e dns_subdomain=prisme -e 'dns_target={{ prod_ip }}'` |

Le nom devient résoluble publiquement ; l'accès reste fermé par l'ACL `vpn_only` de Caddy.

Si l'enregistrement public est ajouté **après** un démarrage de Caddy, le job ACME reste bloqué
sur son verrou (`/data/caddy/locks/issue_cert_<host>.lock`, rafraîchi en continu) et un
`caddy reload` ne le relance pas : redémarrer le conteneur `javisi_caddy`.

## Déploiement ciblé

```bash
ansible-playbook playbooks/stacks/site.yml \
  --tags prisme \
  --skip-tags vpn-dns \
  -e prisme_enabled=true \
  -e prisme_deploy_enabled=true
```

Le rôle provisionne la clé virtuelle LiteLLM avec un plafond de 0,50 USD/jour, télécharge le
snapshot BM25 exact si nécessaire, migre la base puis démarre le web, six workers, le sidecar
sparse et le proxy PostgreSQL. Aucun service étranger n’est arrêté.

## Vérifications

```bash
ansible prod-server -b -m command \
  -a 'docker compose -f /opt/javisi/configs/prisme/docker-compose.yml ps'
```

Vérifier `/health/live`, `/health/ready`, `/metrics` avec son Bearer, l’absence de restart loop,
le dashboard `Prisme — Operations` et l’état de la clé LiteLLM.

## Rollback

Repinner le digest applicatif précédent dans `inventory/group_vars/all/versions.yml`, relancer le
déploiement ciblé et conserver les migrations additives. Ne jamais purger PostgreSQL, Qdrant ou
`tank/knowledge` pour un rollback applicatif.

## Secrets partagés VPAI ↔ banga

`vault_prisme_embedding_token`, `vault_prisme_knowledge_store_token` et
`vault_prisme_knowledge_worker_token` existent dans **les deux vaults** (VPAI et banga) et rien ne
garantit mécaniquement leur synchronisation. Toute rotation doit mettre à jour les deux vaults puis
redéployer les deux côtés (sidecar `sparse-query` sur Sese, rôles `knowledge-*` sur banga) dans la
même fenêtre. Le token embedding n'apparaît plus dans le compose : il est rendu dans
`prisme-embedding.env` (0640, `no_log`), fichier dédié au sidecar — jamais `prisme.env`.

## PostgreSQL

Le drill restaure `pg_dump -Fc` dans une base temporaire, vérifie tables, migrations et clés
étrangères, puis supprime uniquement cette base et le dump temporaire.

## Limite offsite

Prisme utilise exclusivement le hub zerobyte v3 pour l’offsite de `tank/knowledge`. En l’absence
de destination validée, conserver l’état `AWAITING_OFFSITE_DESTINATION`; ne créer aucun bucket
ni credential parallèle.
