#!/usr/bin/env python3
"""Bulk write remaining role files for Phases 2-6."""
import os
import sys

BASE = '/home/asus/seko/VPAI'
files = {}

# ============================================================
# PHASE 2 — Caddy remaining, PostgreSQL, Redis, Qdrant
# ============================================================

# Caddy meta
files['roles/caddy/meta/main.yml'] = '---\ngalaxy_info:\n  role_name: caddy\n  author: VPAI\n  description: Caddy reverse proxy with TLS auto, rate limiting, VPN ACL\n  license: MIT\n  min_ansible_version: "2.16"\n  platforms:\n    - name: Debian\n      versions:\n        - bookworm\n        - trixie\n\ndependencies:\n  - role: docker\n'

# Caddy verify
files['roles/caddy/molecule/default/verify.yml'] = "---\n- name: Verify caddy role\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: Check Caddyfile exists\n      ansible.builtin.stat:\n        path: \"/opt/{{ project_name | default('vpai') }}/configs/caddy/Caddyfile\"\n      register: caddyfile\n      failed_when: not caddyfile.stat.exists\n"

# Caddy README
files['roles/caddy/README.md'] = '# Role: caddy\n\n## Description\n\nCaddy reverse proxy with automatic TLS, security headers, VPN-only ACL for admin UIs, rate limiting, and health endpoint.\n\n## Variables\n\n| Variable | Default | Description |\n|----------|---------|-------------|\n| `caddy_domain` | `{{ domain_name }}` | Public domain |\n| `caddy_admin_domain` | `admin.{{ domain_name }}` | Admin subdomain (VPN-only) |\n| `caddy_vpn_cidr` | `{{ vpn_network_cidr }}` | VPN CIDR for ACL |\n\n## Dependencies\n\n- `docker`\n\n## Example\n\n```yaml\n- role: caddy\n  tags: [caddy]\n```\n'

# Caddy Caddyfile template
files['roles/caddy/templates/Caddyfile.j2'] = '{\n    email {{ caddy_notification_email }}\n    servers {\n        protocols h1 h2 h3\n    }\n}\n\n(vpn_only) {\n    @blocked not remote_ip {{ caddy_vpn_cidr }}\n    respond @blocked 403\n}\n\n{{ caddy_domain }} {\n    handle /litellm/* {\n        uri strip_prefix /litellm\n        reverse_proxy litellm:4000\n    }\n\n    handle /health {\n        respond "OK" 200\n    }\n\n    handle {\n        respond "Not Found" 404\n    }\n\n    header {\n        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"\n        X-Content-Type-Options "nosniff"\n        X-Frame-Options "DENY"\n        Referrer-Policy "strict-origin-when-cross-origin"\n        -Server\n    }\n\n    rate_limit {\n        zone global {\n            key {remote_host}\n            events {{ caddy_rate_limit_events }}\n            window {{ caddy_rate_limit_window }}\n        }\n    }\n}\n\n{{ caddy_admin_domain }} {\n    import vpn_only\n\n    handle /n8n/* {\n        uri strip_prefix /n8n\n        reverse_proxy n8n:5678\n    }\n\n    handle /grafana/* {\n        uri strip_prefix /grafana\n        reverse_proxy grafana:3000\n    }\n\n    handle /openclaw/* {\n        uri strip_prefix /openclaw\n        reverse_proxy openclaw:8080\n    }\n\n    handle /qdrant/* {\n        uri strip_prefix /qdrant\n        reverse_proxy qdrant:6333\n    }\n\n    header {\n        Strict-Transport-Security "max-age=31536000; includeSubDomains"\n        X-Content-Type-Options "nosniff"\n        X-Frame-Options "SAMEORIGIN"\n        -Server\n    }\n}\n'

# PostgreSQL defaults
files['roles/postgresql/defaults/main.yml'] = "---\n# postgresql \u2014 defaults\n\npostgresql_config_dir: \"/opt/{{ project_name }}/configs/postgresql\"\npostgresql_data_dir: \"/opt/{{ project_name }}/data/postgresql\"\n\npostgresql_shared_buffers: \"{{ '256MB' if target_env == 'prod' else '128MB' }}\"\npostgresql_effective_cache_size: \"{{ '512MB' if target_env == 'prod' else '256MB' }}\"\npostgresql_work_mem: \"{{ '16MB' if target_env == 'prod' else '8MB' }}\"\npostgresql_maintenance_work_mem: \"{{ '128MB' if target_env == 'prod' else '64MB' }}\"\n\npostgresql_databases:\n  - name: n8n\n    user: n8n\n    extensions:\n      - uuid-ossp\n  - name: openclaw\n    user: openclaw\n    extensions:\n      - uuid-ossp\n      - vector\n  - name: litellm\n    user: litellm\n    extensions:\n      - uuid-ossp\n"

# PostgreSQL tasks
files['roles/postgresql/tasks/main.yml'] = "---\n# postgresql \u2014 tasks\n\n- name: Create PostgreSQL config directory\n  ansible.builtin.file:\n    path: \"{{ postgresql_config_dir }}\"\n    state: directory\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0755\"\n  become: true\n\n- name: Create PostgreSQL data directory\n  ansible.builtin.file:\n    path: \"{{ postgresql_data_dir }}\"\n    state: directory\n    owner: \"999\"\n    group: \"999\"\n    mode: \"0700\"\n  become: true\n\n- name: Deploy PostgreSQL init script\n  ansible.builtin.template:\n    src: init.sql.j2\n    dest: \"{{ postgresql_config_dir }}/init.sql\"\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0644\"\n  become: true\n\n- name: Deploy pg_hba.conf\n  ansible.builtin.template:\n    src: pg_hba.conf.j2\n    dest: \"{{ postgresql_config_dir }}/pg_hba.conf\"\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0644\"\n  become: true\n  notify: Restart postgresql stack\n\n- name: Deploy postgresql.conf\n  ansible.builtin.template:\n    src: postgresql.conf.j2\n    dest: \"{{ postgresql_config_dir }}/postgresql.conf\"\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0644\"\n  become: true\n  notify: Restart postgresql stack\n"

# PostgreSQL handlers
files['roles/postgresql/handlers/main.yml'] = "---\n# postgresql \u2014 handlers\n\n- name: Restart postgresql stack\n  community.docker.docker_compose_v2:\n    project_src: \"/opt/{{ project_name }}\"\n    files:\n      - docker-compose.yml\n    services:\n      - postgresql\n    state: restarted\n  become: true\n"

# PostgreSQL meta
files['roles/postgresql/meta/main.yml'] = '---\ngalaxy_info:\n  role_name: postgresql\n  author: VPAI\n  description: PostgreSQL 18.1 deployment with multi-DB init, tuning, and pg_hba\n  license: MIT\n  min_ansible_version: "2.16"\n  platforms:\n    - name: Debian\n      versions:\n        - bookworm\n        - trixie\n\ndependencies:\n  - role: docker\n'

# PostgreSQL verify
files['roles/postgresql/molecule/default/verify.yml'] = "---\n- name: Verify postgresql role\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: Check PostgreSQL config directory exists\n      ansible.builtin.stat:\n        path: \"/opt/{{ project_name | default('vpai') }}/configs/postgresql\"\n      register: pg_config\n      failed_when: not pg_config.stat.exists\n\n    - name: Check init.sql exists\n      ansible.builtin.stat:\n        path: \"/opt/{{ project_name | default('vpai') }}/configs/postgresql/init.sql\"\n      register: pg_init\n      failed_when: not pg_init.stat.exists\n"

# PostgreSQL README
files['roles/postgresql/README.md'] = '# Role: postgresql\n\n## Description\n\nDeploys PostgreSQL 18.1 with multi-database init (n8n, openclaw, litellm), memory tuning, pg_hba.conf for backend network only.\n\n## Variables\n\n| Variable | Default | Description |\n|----------|---------|-------------|\n| `postgresql_shared_buffers` | `256MB/128MB` | Shared buffers (prod/preprod) |\n| `postgresql_effective_cache_size` | `512MB/256MB` | Effective cache size |\n| `postgresql_databases` | See defaults | Databases and users to create |\n\n## Dependencies\n\n- `docker`\n'

# PostgreSQL templates
files['roles/postgresql/templates/init.sql.j2'] = "-- {{ ansible_managed }}\n-- PostgreSQL init script\n\n{% for db in postgresql_databases %}\nCREATE DATABASE {{ db.name }};\nCREATE USER {{ db.user }} WITH ENCRYPTED PASSWORD '{{ postgresql_password }}';\nGRANT ALL PRIVILEGES ON DATABASE {{ db.name }} TO {{ db.user }};\nALTER DATABASE {{ db.name }} OWNER TO {{ db.user }};\n\n\\c {{ db.name }}\n{% for ext in db.extensions %}\nCREATE EXTENSION IF NOT EXISTS \"{{ ext }}\";\n{% endfor %}\nGRANT ALL ON SCHEMA public TO {{ db.user }};\n\n{% endfor %}\n"

files['roles/postgresql/templates/pg_hba.conf.j2'] = "# {{ ansible_managed }}\n# PostgreSQL Client Authentication Configuration\n\n# TYPE  DATABASE        USER            ADDRESS                 METHOD\nlocal   all             all                                     trust\nhost    all             all             127.0.0.1/32            md5\nhost    all             all             ::1/128                 md5\n# Allow connections from Docker backend network\nhost    all             all             {{ docker_network_backend_subnet }}    md5\n"

files['roles/postgresql/templates/postgresql.conf.j2'] = "# {{ ansible_managed }}\n# PostgreSQL configuration \u2014 tuned for {{ target_env }}\n\nlisten_addresses = '*'\nport = 5432\nmax_connections = 100\n\n# Memory\nshared_buffers = {{ postgresql_shared_buffers }}\neffective_cache_size = {{ postgresql_effective_cache_size }}\nwork_mem = {{ postgresql_work_mem }}\nmaintenance_work_mem = {{ postgresql_maintenance_work_mem }}\n\n# WAL\nwal_buffers = 16MB\ncheckpoint_completion_target = 0.9\n\n# Logging\nlog_timezone = '{{ timezone }}'\nlogging_collector = on\nlog_directory = 'log'\nlog_filename = 'postgresql-%Y-%m-%d.log'\nlog_rotation_age = 1d\nlog_rotation_size = 100MB\n\n# Locale\ndatestyle = 'iso, mdy'\ntimezone = '{{ timezone }}'\nlc_messages = 'en_US.utf8'\nlc_monetary = 'en_US.utf8'\nlc_numeric = 'en_US.utf8'\nlc_time = 'en_US.utf8'\ndefault_text_search_config = 'pg_catalog.english'\n"

# Redis defaults
files['roles/redis/defaults/main.yml'] = "---\n# redis \u2014 defaults\n\nredis_config_dir: \"/opt/{{ project_name }}/configs/redis\"\nredis_data_dir: \"/opt/{{ project_name }}/data/redis\"\nredis_maxmemory: \"{{ '384mb' if target_env == 'prod' else '192mb' }}\"\nredis_maxmemory_policy: \"allkeys-lru\"\nredis_io_threads: 2\n"

# Redis tasks
files['roles/redis/tasks/main.yml'] = "---\n# redis \u2014 tasks\n\n- name: Create Redis config directory\n  ansible.builtin.file:\n    path: \"{{ redis_config_dir }}\"\n    state: directory\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0755\"\n  become: true\n\n- name: Create Redis data directory\n  ansible.builtin.file:\n    path: \"{{ redis_data_dir }}\"\n    state: directory\n    owner: \"999\"\n    group: \"999\"\n    mode: \"0755\"\n  become: true\n\n- name: Deploy redis.conf\n  ansible.builtin.template:\n    src: redis.conf.j2\n    dest: \"{{ redis_config_dir }}/redis.conf\"\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0644\"\n  become: true\n  notify: Restart redis stack\n"

# Redis handlers
files['roles/redis/handlers/main.yml'] = "---\n# redis \u2014 handlers\n\n- name: Restart redis stack\n  community.docker.docker_compose_v2:\n    project_src: \"/opt/{{ project_name }}\"\n    files:\n      - docker-compose.yml\n    services:\n      - redis\n    state: restarted\n  become: true\n"

# Redis meta
files['roles/redis/meta/main.yml'] = '---\ngalaxy_info:\n  role_name: redis\n  author: VPAI\n  description: Redis 8.0 deployment with auth, maxmemory, RDB persistence, io-threads\n  license: MIT\n  min_ansible_version: "2.16"\n  platforms:\n    - name: Debian\n      versions:\n        - bookworm\n        - trixie\n\ndependencies:\n  - role: docker\n'

# Redis verify
files['roles/redis/molecule/default/verify.yml'] = "---\n- name: Verify redis role\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: Check Redis config exists\n      ansible.builtin.stat:\n        path: \"/opt/{{ project_name | default('vpai') }}/configs/redis/redis.conf\"\n      register: redis_conf\n      failed_when: not redis_conf.stat.exists\n"

# Redis README
files['roles/redis/README.md'] = '# Role: redis\n\n## Description\n\nRedis 8.0 with password auth, maxmemory with LRU eviction, RDB persistence, and I/O threading.\n\n## Variables\n\n| Variable | Default | Description |\n|----------|---------|-------------|\n| `redis_maxmemory` | `384mb/192mb` | Max memory (prod/preprod) |\n| `redis_maxmemory_policy` | `allkeys-lru` | Eviction policy |\n| `redis_io_threads` | `2` | Redis 8.0 I/O threads |\n\n## Dependencies\n\n- `docker`\n'

# Redis template
files['roles/redis/templates/redis.conf.j2'] = '# {{ ansible_managed }}\n# Redis configuration\n\nbind 0.0.0.0\nport 6379\nrequirepass {{ redis_password }}\n\nmaxmemory {{ redis_maxmemory }}\nmaxmemory-policy {{ redis_maxmemory_policy }}\n\n# Persistence (RDB)\nsave 900 1\nsave 300 10\nsave 60 10000\ndbfilename dump.rdb\ndir /data\n\n# I/O threading (Redis 8.0)\nio-threads {{ redis_io_threads }}\nio-threads-do-reads yes\n\n# Logging\nloglevel notice\nlogfile ""\n\n# Security\nrename-command FLUSHDB ""\nrename-command FLUSHALL ""\n'

# Qdrant defaults
files['roles/qdrant/defaults/main.yml'] = "---\n# qdrant \u2014 defaults\n\nqdrant_config_dir: \"/opt/{{ project_name }}/configs/qdrant\"\nqdrant_data_dir: \"/opt/{{ project_name }}/data/qdrant\"\nqdrant_hnsw_m: 16\nqdrant_hnsw_ef_construct: 100\n"

# Qdrant tasks
files['roles/qdrant/tasks/main.yml'] = "---\n# qdrant \u2014 tasks\n\n- name: Create Qdrant config directory\n  ansible.builtin.file:\n    path: \"{{ qdrant_config_dir }}\"\n    state: directory\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0755\"\n  become: true\n\n- name: Create Qdrant data directory\n  ansible.builtin.file:\n    path: \"{{ qdrant_data_dir }}\"\n    state: directory\n    owner: \"1000\"\n    group: \"1000\"\n    mode: \"0755\"\n  become: true\n\n- name: Deploy Qdrant config\n  ansible.builtin.template:\n    src: config.yaml.j2\n    dest: \"{{ qdrant_config_dir }}/config.yaml\"\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0644\"\n  become: true\n  notify: Restart qdrant stack\n"

# Qdrant handlers
files['roles/qdrant/handlers/main.yml'] = "---\n# qdrant \u2014 handlers\n\n- name: Restart qdrant stack\n  community.docker.docker_compose_v2:\n    project_src: \"/opt/{{ project_name }}\"\n    files:\n      - docker-compose.yml\n    services:\n      - qdrant\n    state: restarted\n  become: true\n"

# Qdrant meta
files['roles/qdrant/meta/main.yml'] = '---\ngalaxy_info:\n  role_name: qdrant\n  author: VPAI\n  description: Qdrant vector database with API key auth and HNSW tuning\n  license: MIT\n  min_ansible_version: "2.16"\n  platforms:\n    - name: Debian\n      versions:\n        - bookworm\n        - trixie\n\ndependencies:\n  - role: docker\n'

# Qdrant verify
files['roles/qdrant/molecule/default/verify.yml'] = "---\n- name: Verify qdrant role\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: Check Qdrant config exists\n      ansible.builtin.stat:\n        path: \"/opt/{{ project_name | default('vpai') }}/configs/qdrant/config.yaml\"\n      register: qdrant_config\n      failed_when: not qdrant_config.stat.exists\n"

# Qdrant README
files['roles/qdrant/README.md'] = '# Role: qdrant\n\n## Description\n\nQdrant vector database with API key authentication and HNSW index tuning for text embeddings.\n\n## Variables\n\n| Variable | Default | Description |\n|----------|---------|-------------|\n| `qdrant_api_key` | Vault | API authentication key |\n| `qdrant_hnsw_m` | `16` | HNSW M parameter |\n| `qdrant_hnsw_ef_construct` | `100` | HNSW ef_construct parameter |\n\n## Dependencies\n\n- `docker`\n'

# Qdrant template
files['roles/qdrant/templates/config.yaml.j2'] = '# {{ ansible_managed }}\n# Qdrant configuration\n\nstorage:\n  storage_path: /qdrant/storage\n\nservice:\n  api_key: {{ qdrant_api_key }}\n  host: 0.0.0.0\n  http_port: 6333\n  grpc_port: 6334\n\noptimizers:\n  default_segment_number: 2\n\nhnsw_index:\n  m: {{ qdrant_hnsw_m }}\n  ef_construct: {{ qdrant_hnsw_ef_construct }}\n  full_scan_threshold: 10000\n'

# ============================================================
# PHASE 3 — n8n, LiteLLM, OpenClaw
# ============================================================

# n8n defaults
files['roles/n8n/defaults/main.yml'] = "---\n# n8n \u2014 defaults\n\nn8n_config_dir: \"/opt/{{ project_name }}/configs/n8n\"\nn8n_data_dir: \"/opt/{{ project_name }}/data/n8n\"\n"

# n8n tasks
files['roles/n8n/tasks/main.yml'] = "---\n# n8n \u2014 tasks\n\n- name: Create n8n config directory\n  ansible.builtin.file:\n    path: \"{{ n8n_config_dir }}\"\n    state: directory\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0755\"\n  become: true\n\n- name: Create n8n data directory\n  ansible.builtin.file:\n    path: \"{{ n8n_data_dir }}\"\n    state: directory\n    owner: \"1000\"\n    group: \"1000\"\n    mode: \"0755\"\n  become: true\n\n- name: Deploy n8n environment file\n  ansible.builtin.template:\n    src: n8n.env.j2\n    dest: \"{{ n8n_config_dir }}/n8n.env\"\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0600\"\n  become: true\n  notify: Restart n8n stack\n"

# n8n handlers
files['roles/n8n/handlers/main.yml'] = "---\n# n8n \u2014 handlers\n\n- name: Restart n8n stack\n  community.docker.docker_compose_v2:\n    project_src: \"/opt/{{ project_name }}\"\n    files:\n      - docker-compose.yml\n    services:\n      - n8n\n    state: restarted\n  become: true\n"

# n8n meta
files['roles/n8n/meta/main.yml'] = '---\ngalaxy_info:\n  role_name: n8n\n  author: VPAI\n  description: n8n workflow automation with PostgreSQL backend and task runners\n  license: MIT\n  min_ansible_version: "2.16"\n  platforms:\n    - name: Debian\n      versions:\n        - bookworm\n        - trixie\n\ndependencies:\n  - role: docker\n  - role: postgresql\n'

# n8n verify
files['roles/n8n/molecule/default/verify.yml'] = "---\n- name: Verify n8n role\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: Check n8n env file exists\n      ansible.builtin.stat:\n        path: \"/opt/{{ project_name | default('vpai') }}/configs/n8n/n8n.env\"\n      register: n8n_env\n      failed_when: not n8n_env.stat.exists\n"

# n8n README
files['roles/n8n/README.md'] = '# Role: n8n\n\n## Description\n\nn8n workflow automation with PostgreSQL backend, encryption key, basic auth, task runners, and execution data pruning.\n\n## Variables\n\nAll variables come from group_vars/all/secrets.yml (Ansible Vault).\n\n## Dependencies\n\n- `docker`\n- `postgresql`\n'

# n8n template
files['roles/n8n/templates/n8n.env.j2'] = "# {{ ansible_managed }}\n# n8n environment configuration\n\n# Database\nDB_TYPE=postgresdb\nDB_POSTGRESDB_HOST=postgresql\nDB_POSTGRESDB_PORT=5432\nDB_POSTGRESDB_DATABASE=n8n\nDB_POSTGRESDB_USER=n8n\nDB_POSTGRESDB_PASSWORD={{ postgresql_password }}\n\n# Encryption\nN8N_ENCRYPTION_KEY={{ n8n_encryption_key }}\n\n# URLs\nN8N_HOST=0.0.0.0\nN8N_PORT=5678\nN8N_PROTOCOL=https\nWEBHOOK_URL=https://{{ domain_name }}/n8n/\nN8N_EDITOR_BASE_URL=https://admin.{{ domain_name }}/n8n/\n\n# Security\nN8N_BASIC_AUTH_ACTIVE=true\nN8N_BASIC_AUTH_USER={{ n8n_basic_auth_user }}\nN8N_BASIC_AUTH_PASSWORD={{ n8n_basic_auth_password }}\n\n# Task Runners (v2.0 security)\nN8N_RUNNERS_ENABLED=true\nN8N_RUNNERS_MODE=internal\n\n# Timezone\nGENERIC_TIMEZONE={{ timezone }}\nTZ={{ timezone }}\n\n# Executions\nEXECUTIONS_DATA_PRUNE=true\nEXECUTIONS_DATA_MAX_AGE=168\n"

# LiteLLM defaults
files['roles/litellm/defaults/main.yml'] = "---\n# litellm \u2014 defaults\n\nlitellm_config_dir: \"/opt/{{ project_name }}/configs/litellm\"\n"

# LiteLLM tasks
files['roles/litellm/tasks/main.yml'] = "---\n# litellm \u2014 tasks\n\n- name: Create LiteLLM config directory\n  ansible.builtin.file:\n    path: \"{{ litellm_config_dir }}\"\n    state: directory\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0755\"\n  become: true\n\n- name: Deploy LiteLLM config\n  ansible.builtin.template:\n    src: litellm_config.yaml.j2\n    dest: \"{{ litellm_config_dir }}/litellm_config.yaml\"\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0600\"\n  become: true\n  notify: Restart litellm stack\n\n- name: Deploy LiteLLM environment file\n  ansible.builtin.template:\n    src: litellm.env.j2\n    dest: \"{{ litellm_config_dir }}/litellm.env\"\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0600\"\n  become: true\n  notify: Restart litellm stack\n"

# LiteLLM handlers
files['roles/litellm/handlers/main.yml'] = "---\n# litellm \u2014 handlers\n\n- name: Restart litellm stack\n  community.docker.docker_compose_v2:\n    project_src: \"/opt/{{ project_name }}\"\n    files:\n      - docker-compose.yml\n    services:\n      - litellm\n    state: restarted\n  become: true\n"

# LiteLLM meta
files['roles/litellm/meta/main.yml'] = '---\ngalaxy_info:\n  role_name: litellm\n  author: VPAI\n  description: LiteLLM proxy with model routing, fallbacks, Redis cache, PostgreSQL logging\n  license: MIT\n  min_ansible_version: "2.16"\n  platforms:\n    - name: Debian\n      versions:\n        - bookworm\n        - trixie\n\ndependencies:\n  - role: docker\n  - role: postgresql\n  - role: redis\n'

# LiteLLM verify
files['roles/litellm/molecule/default/verify.yml'] = "---\n- name: Verify litellm role\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: Check LiteLLM config exists\n      ansible.builtin.stat:\n        path: \"/opt/{{ project_name | default('vpai') }}/configs/litellm/litellm_config.yaml\"\n      register: litellm_config\n      failed_when: not litellm_config.stat.exists\n"

# LiteLLM README
files['roles/litellm/README.md'] = '# Role: litellm\n\n## Description\n\nLiteLLM proxy with model routing (Claude, GPT-4o), fallbacks, Redis caching, PostgreSQL logging, and master key auth.\n\n## Variables\n\nAll variables come from group_vars/all/secrets.yml (Ansible Vault).\n\n## Dependencies\n\n- `docker`\n- `postgresql`\n- `redis`\n'

# LiteLLM config template
files['roles/litellm/templates/litellm_config.yaml.j2'] = "# {{ ansible_managed }}\n# LiteLLM configuration\n\nmodel_list:\n  - model_name: \"claude-sonnet\"\n    litellm_params:\n      model: \"anthropic/claude-sonnet-4-20250514\"\n      api_key: \"os.environ/ANTHROPIC_API_KEY\"\n      max_tokens: 8192\n    model_info:\n      max_input_tokens: 200000\n      max_output_tokens: 8192\n\n  - model_name: \"claude-haiku\"\n    litellm_params:\n      model: \"anthropic/claude-haiku-4-5-20251001\"\n      api_key: \"os.environ/ANTHROPIC_API_KEY\"\n      max_tokens: 8192\n\n  - model_name: \"gpt-4o\"\n    litellm_params:\n      model: \"openai/gpt-4o\"\n      api_key: \"os.environ/OPENAI_API_KEY\"\n\n  - model_name: \"gpt-4o-mini\"\n    litellm_params:\n      model: \"openai/gpt-4o-mini\"\n      api_key: \"os.environ/OPENAI_API_KEY\"\n\n  - model_name: \"default\"\n    litellm_params:\n      model: \"anthropic/claude-sonnet-4-20250514\"\n      api_key: \"os.environ/ANTHROPIC_API_KEY\"\n\nlitellm_settings:\n  drop_params: true\n  set_verbose: false\n  num_retries: 2\n  request_timeout: 120\n  fallbacks:\n    - model: \"claude-sonnet\"\n      fallback: [\"gpt-4o\"]\n  cache: true\n  cache_params:\n    type: \"redis\"\n    host: \"redis\"\n    port: 6379\n    password: \"{{ redis_password }}\"\n\ngeneral_settings:\n  master_key: \"{{ litellm_master_key }}\"\n  database_url: \"postgresql://litellm:{{ postgresql_password }}@postgresql:5432/litellm\"\n  alerting:\n    - \"webhook\"\n  alerting_args:\n    webhook_url: \"{{ notification_webhook_url }}\"\n"

# LiteLLM env template
files['roles/litellm/templates/litellm.env.j2'] = "# {{ ansible_managed }}\n# LiteLLM environment\n\nANTHROPIC_API_KEY={{ anthropic_api_key }}\nOPENAI_API_KEY={{ openai_api_key }}\nLITELLM_MASTER_KEY={{ litellm_master_key }}\nDATABASE_URL=postgresql://litellm:{{ postgresql_password }}@postgresql:5432/litellm\n"

# OpenClaw defaults
files['roles/openclaw/defaults/main.yml'] = "---\n# openclaw \u2014 defaults\n\nopenclaw_config_dir: \"/opt/{{ project_name }}/configs/openclaw\"\n"

# OpenClaw tasks
files['roles/openclaw/tasks/main.yml'] = "---\n# openclaw \u2014 tasks\n\n- name: Create OpenClaw config directory\n  ansible.builtin.file:\n    path: \"{{ openclaw_config_dir }}\"\n    state: directory\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0755\"\n  become: true\n\n- name: Deploy OpenClaw environment file\n  ansible.builtin.template:\n    src: openclaw.env.j2\n    dest: \"{{ openclaw_config_dir }}/openclaw.env\"\n    owner: \"{{ prod_user }}\"\n    group: \"{{ prod_user }}\"\n    mode: \"0600\"\n  become: true\n  notify: Restart openclaw stack\n"

# OpenClaw handlers
files['roles/openclaw/handlers/main.yml'] = "---\n# openclaw \u2014 handlers\n\n- name: Restart openclaw stack\n  community.docker.docker_compose_v2:\n    project_src: \"/opt/{{ project_name }}\"\n    files:\n      - docker-compose.yml\n    services:\n      - openclaw\n    state: restarted\n  become: true\n"

# OpenClaw meta
files['roles/openclaw/meta/main.yml'] = '---\ngalaxy_info:\n  role_name: openclaw\n  author: VPAI\n  description: OpenClaw AI agent platform with LiteLLM proxy integration\n  license: MIT\n  min_ansible_version: "2.16"\n  platforms:\n    - name: Debian\n      versions:\n        - bookworm\n        - trixie\n\ndependencies:\n  - role: docker\n  - role: postgresql\n  - role: redis\n  - role: qdrant\n'

# OpenClaw verify
files['roles/openclaw/molecule/default/verify.yml'] = "---\n- name: Verify openclaw role\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: Check OpenClaw env file exists\n      ansible.builtin.stat:\n        path: \"/opt/{{ project_name | default('vpai') }}/configs/openclaw/openclaw.env\"\n      register: openclaw_env\n      failed_when: not openclaw_env.stat.exists\n"

# OpenClaw README
files['roles/openclaw/README.md'] = '# Role: openclaw\n\n## Description\n\nOpenClaw AI agent platform configured to use LiteLLM as LLM proxy, PostgreSQL, Redis, and Qdrant.\n\n## Variables\n\nAll variables come from group_vars/all/secrets.yml (Ansible Vault).\n\n## Dependencies\n\n- `docker`\n- `postgresql`\n- `redis`\n- `qdrant`\n'

# OpenClaw template
files['roles/openclaw/templates/openclaw.env.j2'] = "# {{ ansible_managed }}\n# OpenClaw environment configuration\n\n# Database\nDATABASE_URL=postgresql://openclaw:{{ postgresql_password }}@postgresql:5432/openclaw\n\n# Redis\nREDIS_URL=redis://:{{ redis_password }}@redis:6379/0\n\n# Qdrant\nQDRANT_URL=http://qdrant:6333\nQDRANT_API_KEY={{ qdrant_api_key }}\n\n# LiteLLM (local proxy)\nLITELLM_BASE_URL=http://litellm:4000\nLITELLM_API_KEY={{ litellm_master_key }}\n\n# Defaults\nDEFAULT_MODEL=claude-sonnet\nEMBEDDING_MODEL=text-embedding-3-small\n\n# Server\nHOST=0.0.0.0\nPORT=8080\nAPI_KEY={{ openclaw_api_key }}\n\n# Timezone\nTZ={{ timezone }}\n"

# Write all files
count = 0
for path, content in files.items():
    full_path = os.path.join(BASE, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w') as f:
        f.write(content)
    count += 1

print(f'Written {count} files for Phases 2-3')
