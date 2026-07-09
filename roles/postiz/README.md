# postiz — Ansible role (variante Sese-AI, FRUGAL)

Postiz self-host (planification/publication réseaux sociaux) — **Content Factory V-0**
(spec `content-factory/docs/specs/2026-07-09-video-refs-decoupe-edition-native-postiz.md`).

## Architecture (réutilisation infra prod)

| Brique | Choix | Pourquoi |
|---|---|---|
| Postgres | DB `postiz` (owner `postiz_app`) dans `javisi_postgresql` | Convention repo : mdp UNIQUE `postgresql_password` ; Prisma migre au boot en tant qu'owner |
| Temporal | `cf-temporal` mutualisé, namespace dédié `postiz` (retention 720h) | Postiz ≥ 2.12 exige Temporal (posts planifiés) ; un 2ᵉ stack Temporal+ES = ~1 Go évités |
| Redis | `postiz-redis` DÉDIÉ (`redis_image` pin global, `noeviction`, AOF) | `javisi_redis` = cache LiteLLM avec éviction → perdrait des jobs BullMQ |
| Réseaux | `javisi_backend` (PG/Temporal/redis) + `javisi_frontend` (Caddy) | Externes, jamais créés ici |
| Caddy | `postiz.<domain>` **vpn_only**, upload 500MB | Outil opérateur interne ; Postiz appelle les plateformes en sortie |

## Secrets vault requis AVANT déploiement

| Variable | Rôle |
|---|---|
| `vault_postiz_jwt_secret` | `JWT_SECRET` (≥ 32 chars aléatoires) — assert fail-loud en tête de rôle |

## Ordre de déploiement

`cf-temporal` doit tourner pour l'enregistrement du namespace (sinon skip propre,
le run suivant converge). Déploiement : `make deploy-role ROLE=postiz ENV=prod`
puis `make deploy-role ROLE=caddy ENV=prod` (vhost) + DNS
`ansible-playbook playbooks/utils/ovh-dns-add.yml -e "dns_subdomain=postiz dns_target=<ip>"`.

## GATE HUMAIN post-install

1. Créer le compte opérateur dans l'UI (`https://postiz.<domain>`), puis passer
   `postiz_disable_registration: true` + redeploy.
2. Connecter les comptes sociaux (OAuth par plateforme dans l'UI ; certaines
   plateformes exigent des clés API → env `# Comptes sociaux` de `postiz.env.j2`).
3. L'intégration CF→Postiz (S6, MCP natif Postiz) = tranche séparée APRÈS ce gate.

## Pièges connus

- Healthcheck : `127.0.0.1` explicite (REX cf-studio — `localhost` peut résoudre `::1`).
- `tctl` doit cibler `$(hostname -i):7233` (BIND_ON_IP, pas 127.0.0.1) — REX content-factory.
- env_file → handler `recreate: always`, jamais `state: restarted` (règle CLAUDE.md).
