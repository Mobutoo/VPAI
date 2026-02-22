# Role: litellm

## Description

LiteLLM proxy with model routing (Claude, GPT-4o), fallbacks, Redis caching, PostgreSQL logging, and master key auth.

## Variables

All variables come from group_vars/all/secrets.yml (Ansible Vault).

## Dependencies

- `docker`
- `postgresql`
- `redis`
