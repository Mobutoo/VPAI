# Role: docker-stack

Déploie le fichier `docker-compose.yml` centralisé et lance l'ensemble de la stack Docker.

## Description

Ce rôle est le **point central de déploiement** de tous les conteneurs. Il doit être exécuté **APRÈS** que tous les rôles de configuration (postgresql, redis, n8n, etc.) aient préparé leurs fichiers de config, mais **AVANT** les smoke tests.

## Variables

Aucune variable spécifique à ce rôle. Il utilise les variables globales du projet.

## Dépendances

Ce rôle dépend de tous les rôles de services qui préparent les configs :
- `docker` - Docker CE installé
- `postgresql` - Config PostgreSQL
- `redis` - Config Redis
- `qdrant` - Config Qdrant
- `caddy` - Config Caddy
- `n8n` - Config n8n
- `litellm` - Config LiteLLM
- `openclaw` - Config OpenClaw
- `monitoring` - Config monitoring (Grafana, VictoriaMetrics, Loki, Alloy)
- `diun` - Config DIUN

## Exemple d'utilisation

```yaml
- hosts: prod
  roles:
    # Préparer toutes les configs d'abord
    - role: postgresql
    - role: redis
    - role: n8n
    # ... autres rôles ...

    # Puis déployer la stack complète
    - role: docker-stack
```

## Templates

- `docker-compose.yml.j2` - Template du fichier docker-compose centralisé (12KB)

## Handlers

- `Restart docker stack` - Redémarre l'ensemble de la stack Docker

## Notes

- Ce rôle utilise `community.docker.docker_compose_v2`
- Le docker-compose.yml est déployé dans `/opt/{{ project_name }}/docker-compose.yml`
- Tous les conteneurs sont lancés avec `docker compose up -d`
