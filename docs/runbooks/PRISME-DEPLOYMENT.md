# Prisme — déploiement et reprise

Source d’autorité : rôle `roles/prisme`, exécuté dans `playbooks/stacks/site.yml`.

## Préconditions

- image applicative et images knowledge pinnées par digest ;
- `prisme_enabled=true` uniquement pendant le rollout ciblé ;
- PostgreSQL `prisme`, Qdrant `knowledge_current` et services Banga sains ;
- secrets Prisme déchiffrables ;
- capacité Sese conforme ;
- DNS VPN traité séparément par `playbooks/utils/vpn-dns.yml`.

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

## PostgreSQL

Le drill restaure `pg_dump -Fc` dans une base temporaire, vérifie tables, migrations et clés
étrangères, puis supprime uniquement cette base et le dump temporaire.

## Limite offsite

Prisme utilise exclusivement le hub zerobyte v3 pour l’offsite de `tank/knowledge`. En l’absence
de destination validée, conserver l’état `AWAITING_OFFSITE_DESTINATION`; ne créer aucun bucket
ni credential parallèle.
