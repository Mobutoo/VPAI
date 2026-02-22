# Role: openclaw

## Description

OpenClaw AI agent platform configured to use LiteLLM as LLM proxy, PostgreSQL, Redis, and Qdrant.

## Variables

All variables come from group_vars/all/secrets.yml (Ansible Vault).

## Dependencies

- `docker`
- `postgresql`
- `redis`
- `qdrant`
