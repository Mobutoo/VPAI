# Role: smoke-tests

## Description

Deploys and executes a comprehensive smoke test script that validates the entire stack is operational. The script checks:

- **HTTPS & TLS**: Health endpoint, certificate validity, DNS resolution
- **Application Endpoints**: n8n, Grafana, LiteLLM health endpoints
- **Container Status**: All 12 containers running
- **Container Health**: Docker healthchecks passing
- **Database Connectivity**: PostgreSQL (pg_isready), Redis (PING), Qdrant (healthz)
- **LiteLLM API**: Model list available

## Exit Codes

- `0` — All tests passed
- `1` — At least one test failed

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `smoke_test_script_path` | `/opt/{{ project_name }}/scripts/smoke-test.sh` | Script location |
| `smoke_test_base_url` | `https://{{ domain_name }}` | Public base URL |
| `smoke_test_admin_url` | `https://admin.{{ domain_name }}` | Admin (VPN) base URL |
| `smoke_test_timeout` | `10` | HTTP request timeout (seconds) |

## Usage

```bash
# Via Ansible role (included in site.yml post_tasks)
ansible-playbook playbooks/site.yml --tags smoke-tests

# Via script directly on the VPS
/opt/{{ project_name }}/scripts/smoke-test.sh

# Via GitHub Actions (CI/CD)
bash scripts/smoke-test.sh https://preprod.example.com
```

## Dependencies

None (but all other roles should be deployed first).
