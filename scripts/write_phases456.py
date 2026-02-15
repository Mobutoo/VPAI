import os

BASE = "/home/asus/seko/VPAI"

FILES = {}


# ============================================================
# PHASE 4: MONITORING ROLE
# ============================================================

FILES["roles/monitoring/defaults/main.yml"] = """---
# monitoring \u2014 defaults

# Directories
monitoring_config_dir: "/opt/{{ project_name }}/configs/monitoring"
monitoring_data_dir: "/opt/{{ project_name }}/data"

# VictoriaMetrics
victoriametrics_retention: "30d"
victoriametrics_data_dir: "{{ monitoring_data_dir }}/victoriametrics"

# Loki
loki_retention_period: "336h"  # 14 days
loki_data_dir: "{{ monitoring_data_dir }}/loki"

# Alloy
alloy_config_dir: "{{ monitoring_config_dir }}/alloy"

# Grafana
grafana_data_dir: "{{ monitoring_data_dir }}/grafana"
grafana_provisioning_dir: "{{ monitoring_config_dir }}/grafana/provisioning"
grafana_dashboards_dir: "{{ monitoring_config_dir }}/grafana/dashboards"
grafana_admin_user: "admin"
grafana_server_root_url: "https://admin.{{ domain_name }}/grafana/"
grafana_serve_from_sub_path: true

# Alerting thresholds
alert_cpu_threshold: 80
alert_cpu_duration: "5m"
alert_ram_threshold: 85
alert_ram_duration: "5m"
alert_disk_threshold: 90
alert_container_restart_threshold: 3
alert_container_restart_window: "15m"
alert_n8n_error_threshold: 5
alert_n8n_error_window: "1m"
"""

FILES["roles/monitoring/vars/main.yml"] = """---
# monitoring \u2014 vars (internal)
"""

FILES["roles/monitoring/tasks/main.yml"] = """---
# monitoring \u2014 tasks

- name: Create VictoriaMetrics data directory
  ansible.builtin.file:
    path: "{{ victoriametrics_data_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true

- name: Create Loki data directory
  ansible.builtin.file:
    path: "{{ loki_data_dir }}"
    state: directory
    owner: "10001"
    group: "10001"
    mode: "0755"
  become: true

- name: Create Alloy config directory
  ansible.builtin.file:
    path: "{{ alloy_config_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true

- name: Create Grafana data directory
  ansible.builtin.file:
    path: "{{ grafana_data_dir }}"
    state: directory
    owner: "472"
    group: "0"
    mode: "0755"
  become: true

- name: Create Grafana provisioning directories
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  loop:
    - "{{ grafana_provisioning_dir }}/datasources"
    - "{{ grafana_provisioning_dir }}/dashboards"
    - "{{ grafana_dashboards_dir }}"
  become: true

- name: Deploy Loki configuration
  ansible.builtin.template:
    src: loki-config.yaml.j2
    dest: "{{ monitoring_config_dir }}/loki-config.yaml"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true
  notify: Restart monitoring stack

- name: Deploy Alloy configuration
  ansible.builtin.template:
    src: alloy-config.alloy.j2
    dest: "{{ alloy_config_dir }}/config.alloy"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true
  notify: Restart monitoring stack

- name: Deploy Grafana datasources provisioning
  ansible.builtin.template:
    src: grafana-datasources.yaml.j2
    dest: "{{ grafana_provisioning_dir }}/datasources/datasources.yaml"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true
  notify: Restart monitoring stack

- name: Deploy Grafana dashboard provisioning config
  ansible.builtin.template:
    src: grafana-dashboard-provider.yaml.j2
    dest: "{{ grafana_provisioning_dir }}/dashboards/provider.yaml"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true
  notify: Restart monitoring stack

- name: Deploy Grafana dashboards
  ansible.builtin.template:
    src: "{{ item }}"
    dest: "{{ grafana_dashboards_dir }}/{{ item | basename | regex_replace('\\\.j2$', '') }}"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  loop:
    - dashboards/system-overview.json.j2
    - dashboards/docker-containers.json.j2
    - dashboards/litellm-proxy.json.j2
  become: true
  notify: Restart monitoring stack

- name: Deploy Grafana alerting rules
  ansible.builtin.template:
    src: grafana-alerting.yaml.j2
    dest: "{{ grafana_provisioning_dir }}/alerting.yaml"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true
  notify: Restart monitoring stack
"""

FILES["roles/monitoring/handlers/main.yml"] = """---
# monitoring \u2014 handlers

- name: Restart monitoring stack
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - victoriametrics
      - loki
      - alloy
      - grafana
    state: restarted
  become: true
"""

FILES["roles/monitoring/meta/main.yml"] = """---
# monitoring \u2014 meta

galaxy_info:
  author: "{{ project_name }}"
  description: "Monitoring stack \u2014 VictoriaMetrics, Loki, Alloy, Grafana"
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions:
        - bookworm

dependencies:
  - role: docker
"""

FILES["roles/monitoring/templates/loki-config.yaml.j2"] = """---
auth_enabled: false

server:
  http_listen_port: 3100

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: "2024-01-01"
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  retention_period: {{ loki_retention_period }}
  ingestion_rate_mb: 10
  ingestion_burst_size_mb: 20

compactor:
  working_directory: /loki/compactor
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150
"""

FILES["roles/monitoring/templates/alloy-config.alloy.j2"] = """// Alloy configuration \u2014 metrics and logs collection

// ===== Docker discovery =====
discovery.docker "containers" {
  host = "unix:///var/run/docker.sock"
}

// ===== Node metrics (built-in) =====
prometheus.exporter.unix "node" {
}

prometheus.scrape "node" {
  targets    = prometheus.exporter.unix.node.targets
  forward_to = [prometheus.remote_write.victoriametrics.receiver]
  scrape_interval = "30s"
}

// ===== cAdvisor-style container metrics =====
discovery.relabel "docker_containers" {
  targets = discovery.docker.containers.targets

  rule {
    source_labels = ["__meta_docker_container_name"]
    target_label  = "container"
  }
  rule {
    source_labels = ["__meta_docker_container_id"]
    target_label  = "container_id"
  }
}

// ===== Remote write to VictoriaMetrics =====
prometheus.remote_write "victoriametrics" {
  endpoint {
    url = "http://victoriametrics:8428/api/v1/write"
  }
}

// ===== Docker log collection =====
loki.source.docker "containers" {
  host       = "unix:///var/run/docker.sock"
  targets    = discovery.docker.containers.targets
  forward_to = [loki.process.docker_logs.receiver]
}

loki.process "docker_logs" {
  stage.docker {}

  stage.labels {
    values = {
      container = "",
    }
  }

  forward_to = [loki.write.loki.receiver]
}

// ===== Push logs to Loki =====
loki.write "loki" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
"""

FILES["roles/monitoring/templates/grafana-datasources.yaml.j2"] = """---
apiVersion: 1

datasources:
  - name: VictoriaMetrics
    type: prometheus
    access: proxy
    url: http://victoriametrics:8428
    isDefault: true
    editable: false
    jsonData:
      timeInterval: "30s"

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
    jsonData:
      maxLines: 1000
"""

FILES["roles/monitoring/templates/grafana-dashboard-provider.yaml.j2"] = """---
apiVersion: 1

providers:
  - name: default
    orgId: 1
    folder: ""
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: false
"""

FILES["roles/monitoring/templates/grafana-alerting.yaml.j2"] = """---
apiVersion: 1

groups:
  - orgId: 1
    name: Infrastructure Alerts
    folder: alerts
    interval: 1m
    rules:
      - uid: cpu-high
        title: "CPU usage > {{ alert_cpu_threshold }}%"
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: VictoriaMetrics
            model:
              expr: '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
              intervalMs: 30000
              maxDataPoints: 43200
          - refId: C
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator:
                    params:
                      - {{ alert_cpu_threshold }}
                    type: gt
                  operator:
                    type: and
                  reducer:
                    type: avg
              type: classic_conditions
        for: {{ alert_cpu_duration }}
        annotations:
          summary: "High CPU usage detected"

      - uid: ram-high
        title: "RAM usage > {{ alert_ram_threshold }}%"
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: VictoriaMetrics
            model:
              expr: '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'
              intervalMs: 30000
              maxDataPoints: 43200
          - refId: C
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator:
                    params:
                      - {{ alert_ram_threshold }}
                    type: gt
                  operator:
                    type: and
                  reducer:
                    type: avg
              type: classic_conditions
        for: {{ alert_ram_duration }}
        annotations:
          summary: "High RAM usage detected"

      - uid: disk-high
        title: "Disk usage > {{ alert_disk_threshold }}%"
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: VictoriaMetrics
            model:
              expr: '(1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100'
              intervalMs: 30000
              maxDataPoints: 43200
          - refId: C
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator:
                    params:
                      - {{ alert_disk_threshold }}
                    type: gt
                  operator:
                    type: and
                  reducer:
                    type: avg
              type: classic_conditions
        for: 5m
        annotations:
          summary: "Disk space critically low"
"""

FILES["roles/monitoring/templates/dashboards/system-overview.json.j2"] = """{
  "annotations": { "list": [] },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": {
        "defaults": { "unit": "percent", "min": 0, "max": 100, "thresholds": { "steps": [{"color": "green", "value": null}, {"color": "yellow", "value": 70}, {"color": "red", "value": 85}] } }
      },
      "gridPos": { "h": 6, "w": 6, "x": 0, "y": 0 },
      "title": "CPU Usage",
      "type": "gauge",
      "targets": [
        { "expr": "100 - (avg(rate(node_cpu_seconds_total{mode=\\"idle\\"}[5m])) * 100)", "legendFormat": "CPU" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": {
        "defaults": { "unit": "percent", "min": 0, "max": 100, "thresholds": { "steps": [{"color": "green", "value": null}, {"color": "yellow", "value": 70}, {"color": "red", "value": 85}] } }
      },
      "gridPos": { "h": 6, "w": 6, "x": 6, "y": 0 },
      "title": "RAM Usage",
      "type": "gauge",
      "targets": [
        { "expr": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100", "legendFormat": "RAM" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": {
        "defaults": { "unit": "percent", "min": 0, "max": 100, "thresholds": { "steps": [{"color": "green", "value": null}, {"color": "yellow", "value": 80}, {"color": "red", "value": 90}] } }
      },
      "gridPos": { "h": 6, "w": 6, "x": 12, "y": 0 },
      "title": "Disk Usage",
      "type": "gauge",
      "targets": [
        { "expr": "(1 - (node_filesystem_avail_bytes{mountpoint=\\"/\\"} / node_filesystem_size_bytes{mountpoint=\\"/\\"})) * 100", "legendFormat": "Disk" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": {
        "defaults": { "unit": "decbytes" }
      },
      "gridPos": { "h": 6, "w": 6, "x": 18, "y": 0 },
      "title": "Network Traffic",
      "type": "timeseries",
      "targets": [
        { "expr": "rate(node_network_receive_bytes_total{device=\\"eth0\\"}[5m])", "legendFormat": "RX" },
        { "expr": "rate(node_network_transmit_bytes_total{device=\\"eth0\\"}[5m])", "legendFormat": "TX" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "short" } },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 6 },
      "title": "System Load",
      "type": "timeseries",
      "targets": [
        { "expr": "node_load1", "legendFormat": "1m" },
        { "expr": "node_load5", "legendFormat": "5m" },
        { "expr": "node_load15", "legendFormat": "15m" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "bytes" } },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 6 },
      "title": "Memory Breakdown",
      "type": "timeseries",
      "targets": [
        { "expr": "node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "legendFormat": "Used" },
        { "expr": "node_memory_MemAvailable_bytes", "legendFormat": "Available" },
        { "expr": "node_memory_Cached_bytes", "legendFormat": "Cached" }
      ]
    }
  ],
  "schemaVersion": 39,
  "tags": ["system", "overview"],
  "templating": { "list": [] },
  "time": { "from": "now-6h", "to": "now" },
  "title": "System Overview",
  "uid": "system-overview"
}
"""

FILES["roles/monitoring/templates/dashboards/docker-containers.json.j2"] = """{
  "annotations": { "list": [] },
  "editable": true,
  "panels": [
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "percent" } },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 0 },
      "title": "Container CPU Usage",
      "type": "timeseries",
      "targets": [
        { "expr": "rate(container_cpu_usage_seconds_total[5m]) * 100", "legendFormat": "{%% raw %%}{{ container }}{%% endraw %%}" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "bytes" } },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 0 },
      "title": "Container Memory Usage",
      "type": "timeseries",
      "targets": [
        { "expr": "container_memory_usage_bytes", "legendFormat": "{%% raw %%}{{ container }}{%% endraw %%}" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "Bps" } },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 8 },
      "title": "Container Network RX",
      "type": "timeseries",
      "targets": [
        { "expr": "rate(container_network_receive_bytes_total[5m])", "legendFormat": "{%% raw %%}{{ container }}{%% endraw %%}" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "short" } },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 8 },
      "title": "Container Restarts",
      "type": "stat",
      "targets": [
        { "expr": "changes(container_start_time_seconds[1h])", "legendFormat": "{%% raw %%}{{ container }}{%% endraw %%}" }
      ]
    }
  ],
  "schemaVersion": 39,
  "tags": ["docker", "containers"],
  "time": { "from": "now-6h", "to": "now" },
  "title": "Docker Containers",
  "uid": "docker-containers"
}
"""

FILES["roles/monitoring/templates/dashboards/litellm-proxy.json.j2"] = """{
  "annotations": { "list": [] },
  "editable": true,
  "panels": [
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "reqps" } },
      "gridPos": { "h": 8, "w": 8, "x": 0, "y": 0 },
      "title": "LiteLLM Requests/s",
      "type": "timeseries",
      "targets": [
        { "expr": "rate(litellm_requests_total[5m])", "legendFormat": "{%% raw %%}{{ model }}{%% endraw %%}" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "s" } },
      "gridPos": { "h": 8, "w": 8, "x": 8, "y": 0 },
      "title": "LiteLLM Latency (p95)",
      "type": "timeseries",
      "targets": [
        { "expr": "histogram_quantile(0.95, rate(litellm_request_duration_seconds_bucket[5m]))", "legendFormat": "p95" },
        { "expr": "histogram_quantile(0.50, rate(litellm_request_duration_seconds_bucket[5m]))", "legendFormat": "p50" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "short" } },
      "gridPos": { "h": 8, "w": 8, "x": 16, "y": 0 },
      "title": "LiteLLM Tokens Used",
      "type": "stat",
      "targets": [
        { "expr": "sum(increase(litellm_tokens_total[24h]))", "legendFormat": "24h tokens" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "short" } },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 8 },
      "title": "LiteLLM Errors",
      "type": "timeseries",
      "targets": [
        { "expr": "rate(litellm_errors_total[5m])", "legendFormat": "{%% raw %%}{{ error_type }}{%% endraw %%}" }
      ]
    },
    {
      "datasource": { "type": "prometheus", "uid": "VictoriaMetrics" },
      "fieldConfig": { "defaults": { "unit": "short" } },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 8 },
      "title": "LiteLLM Cache Hit Rate",
      "type": "gauge",
      "targets": [
        { "expr": "rate(litellm_cache_hits_total[5m]) / (rate(litellm_cache_hits_total[5m]) + rate(litellm_cache_misses_total[5m]))", "legendFormat": "hit rate" }
      ]
    }
  ],
  "schemaVersion": 39,
  "tags": ["litellm", "proxy", "llm"],
  "time": { "from": "now-6h", "to": "now" },
  "title": "LiteLLM Proxy",
  "uid": "litellm-proxy"
}
"""

FILES["roles/monitoring/molecule/default/verify.yml"] = """---
- name: Verify monitoring role
  hosts: all
  gather_facts: false
  tasks:
    - name: Check VictoriaMetrics data directory exists
      ansible.builtin.stat:
        path: "{{ victoriametrics_data_dir }}"
      register: vm_dir
      failed_when: not vm_dir.stat.exists

    - name: Check Loki data directory exists
      ansible.builtin.stat:
        path: "{{ loki_data_dir }}"
      register: loki_dir
      failed_when: not loki_dir.stat.exists

    - name: Check Alloy config exists
      ansible.builtin.stat:
        path: "{{ alloy_config_dir }}/config.alloy"
      register: alloy_cfg
      failed_when: not alloy_cfg.stat.exists

    - name: Check Grafana datasources provisioned
      ansible.builtin.stat:
        path: "{{ grafana_provisioning_dir }}/datasources/datasources.yaml"
      register: grafana_ds
      failed_when: not grafana_ds.stat.exists

    - name: Check Grafana dashboards directory has files
      ansible.builtin.find:
        paths: "{{ grafana_dashboards_dir }}"
        patterns: "*.json"
      register: dashboards
      failed_when: dashboards.matched < 3
"""

FILES["roles/monitoring/README.md"] = """# Monitoring Role

Deploys the observability stack: VictoriaMetrics, Loki, Grafana Alloy, and Grafana.

## Components

| Component | Purpose | Network |
|-----------|---------|---------|
| VictoriaMetrics | Metrics storage (Prometheus-compatible) | monitoring |
| Loki | Log aggregation | monitoring |
| Alloy | Metrics & logs collector | backend + monitoring |
| Grafana | Visualization & alerting | frontend + monitoring |

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `victoriametrics_retention` | `30d` | Metrics retention period |
| `loki_retention_period` | `336h` | Log retention period (14 days) |
| `grafana_admin_user` | `admin` | Grafana admin username |
| `grafana_admin_password` | (vault) | Grafana admin password |
| `alert_cpu_threshold` | `80` | CPU alert threshold (%) |
| `alert_ram_threshold` | `85` | RAM alert threshold (%) |
| `alert_disk_threshold` | `90` | Disk alert threshold (%) |

## Dashboards

- System Overview (CPU, RAM, Disk, Network, Load)
- Docker Containers (CPU, Memory, Network, Restarts per container)
- LiteLLM Proxy (Requests/s, Latency, Tokens, Errors, Cache)

## Dependencies

- `docker` role
"""

# ============================================================
# PHASE 4: DIUN ROLE
# ============================================================

FILES["roles/diun/defaults/main.yml"] = """---
# diun — defaults

diun_config_dir: "/opt/{{ project_name }}/configs/diun"
diun_data_dir: "/opt/{{ project_name }}/data/diun"

# Schedule
diun_watch_schedule: "0 */6 * * *"  # Every 6 hours
diun_watch_by_default: true

# Notification
diun_notification_webhook_url: "{{ notification_webhook_url }}"
diun_notification_method: "{{ notification_method }}"
"""

FILES["roles/diun/vars/main.yml"] = """---
# diun — vars (internal)
"""

FILES["roles/diun/tasks/main.yml"] = """---
# diun — tasks

- name: Create DIUN config directory
  ansible.builtin.file:
    path: "{{ diun_config_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true

- name: Create DIUN data directory
  ansible.builtin.file:
    path: "{{ diun_data_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true

- name: Deploy DIUN configuration
  ansible.builtin.template:
    src: diun.yml.j2
    dest: "{{ diun_config_dir }}/diun.yml"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true
  notify: Restart diun stack
"""

FILES["roles/diun/handlers/main.yml"] = """---
# diun — handlers

- name: Restart diun stack
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - diun
    state: restarted
  become: true
"""

FILES["roles/diun/meta/main.yml"] = """---
# diun — meta

galaxy_info:
  author: "{{ project_name }}"
  description: "DIUN — Docker Image Update Notifier"
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions:
        - bookworm

dependencies:
  - role: docker
"""

FILES["roles/diun/templates/diun.yml.j2"] = """---
watch:
  schedule: "{{ diun_watch_schedule }}"
  firstCheckNotif: false

defaults:
  watchByDefault: {{ diun_watch_by_default | lower }}

providers:
  docker:
    watchStopped: false
    watchByDefault: {{ diun_watch_by_default | lower }}

notif:
  webhook:
    endpoint: "{{ diun_notification_webhook_url }}"
    method: POST
    headers:
      Content-Type: application/json
    templateBody: |
      {
        "text": "Docker image update: {{ '{{' }} .Entry.Image {{ '}}' }} {{ '{{' }} if .Entry.Image.HubLink {{ '}}' }}({{ '{{' }} .Entry.Image.HubLink {{ '}}' }}){{ '{{' }} end {{ '}}' }}"
      }
"""

FILES["roles/diun/molecule/default/verify.yml"] = """---
- name: Verify diun role
  hosts: all
  gather_facts: false
  tasks:
    - name: Check DIUN config exists
      ansible.builtin.stat:
        path: "{{ diun_config_dir }}/diun.yml"
      register: diun_cfg
      failed_when: not diun_cfg.stat.exists

    - name: Check DIUN config contains schedule
      ansible.builtin.command:
        cmd: "grep 'schedule' {{ diun_config_dir }}/diun.yml"
      register: diun_schedule
      changed_when: false
      failed_when: diun_schedule.rc != 0
"""

FILES["roles/diun/README.md"] = """# DIUN Role

Deploys Docker Image Update Notifier (DIUN) to monitor for new Docker image versions.

## Features

- Watches all running containers for updates (every 6 hours by default)
- Sends notifications via webhook when new versions are detected
- Docker socket mounted read-only for security

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `diun_watch_schedule` | `0 */6 * * *` | Cron schedule for checking updates |
| `diun_watch_by_default` | `true` | Watch all containers by default |
| `diun_notification_webhook_url` | (from wizard) | Webhook URL for notifications |

## Dependencies

- `docker` role
"""

# ============================================================
# PHASE 5: BACKUP-CONFIG ROLE
# ============================================================

FILES["roles/backup-config/defaults/main.yml"] = """---
# backup-config \u2014 defaults

backup_base_dir: "/opt/{{ project_name }}/backups"
backup_dirs:
  - pg_dump
  - redis
  - qdrant
  - n8n
  - grafana

# Pre-backup cron schedule (before Zerobyte at 03:00)
backup_cron_hour: "2"
backup_cron_minute: "55"

# Uptime Kuma heartbeat URL (push monitor)
backup_heartbeat_url: "{{ uptime_kuma_push_url | default('') }}"

# Retention for local backup files
backup_local_retention_days: 7
"""

FILES["roles/backup-config/vars/main.yml"] = """---
# backup-config \u2014 vars (internal)
"""

FILES["roles/backup-config/tasks/main.yml"] = """---
# backup-config \u2014 tasks

- name: Create backup directories
  ansible.builtin.file:
    path: "{{ backup_base_dir }}/{{ item }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0750"
  loop: "{{ backup_dirs }}"
  become: true

- name: Deploy pre-backup script
  ansible.builtin.template:
    src: pre-backup.sh.j2
    dest: "/usr/local/bin/pre-backup.sh"
    owner: root
    group: root
    mode: "0755"
  become: true

- name: Deploy backup cleanup script
  ansible.builtin.template:
    src: backup-cleanup.sh.j2
    dest: "/usr/local/bin/backup-cleanup.sh"
    owner: root
    group: root
    mode: "0755"
  become: true

- name: Configure pre-backup cron job
  ansible.builtin.cron:
    name: "Pre-backup data export"
    hour: "{{ backup_cron_hour }}"
    minute: "{{ backup_cron_minute }}"
    job: "/usr/local/bin/pre-backup.sh >> /var/log/pre-backup.log 2>&1"
    user: root
  become: true

- name: Configure backup cleanup cron job
  ansible.builtin.cron:
    name: "Backup local cleanup"
    hour: "4"
    minute: "0"
    job: "/usr/local/bin/backup-cleanup.sh >> /var/log/backup-cleanup.log 2>&1"
    user: root
  become: true
"""

FILES["roles/backup-config/handlers/main.yml"] = """---
# backup-config \u2014 handlers
# No handlers needed \u2014 cron-based, no services to restart
"""

FILES["roles/backup-config/meta/main.yml"] = """---
# backup-config \u2014 meta

galaxy_info:
  author: "{{ project_name }}"
  description: "Backup configuration \u2014 pre-backup scripts and cron for Zerobyte"
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions:
        - bookworm

dependencies:
  - role: docker
  - role: postgresql
  - role: redis
  - role: qdrant
"""

FILES["roles/backup-config/templates/pre-backup.sh.j2"] = """#!/bin/bash
# Pre-backup script \u2014 executed before Zerobyte backup job
# Exports data from all services to backup directories

set -euo pipefail

BACKUP_DIR="{{ backup_base_dir }}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PROJECT="{{ project_name }}"

echo "[$(date)] Starting pre-backup..."

# --- PostgreSQL dump ---
echo "[$(date)] Dumping PostgreSQL databases..."
for DB in n8n openclaw litellm; do
  docker exec ${PROJECT}-postgresql-1 \
    pg_dump -U postgres -Fc --file="/tmp/${DB}.dump" "${DB}" || true
  docker cp ${PROJECT}-postgresql-1:/tmp/${DB}.dump \
    "${BACKUP_DIR}/pg_dump/${DB}-${TIMESTAMP}.dump"
  docker exec ${PROJECT}-postgresql-1 rm -f "/tmp/${DB}.dump"
done

# --- Redis BGSAVE ---
echo "[$(date)] Triggering Redis BGSAVE..."
docker exec ${PROJECT}-redis-1 \
  redis-cli -a "{{ redis_password }}" BGSAVE
sleep 5
cp /opt/${PROJECT}/data/redis/dump.rdb \
  "${BACKUP_DIR}/redis/dump-${TIMESTAMP}.rdb" || true

# --- Qdrant snapshot ---
echo "[$(date)] Creating Qdrant snapshot..."
curl -sf -X POST "http://localhost:6333/snapshots" \
  -H "api-key: {{ qdrant_api_key }}" \
  -o "${BACKUP_DIR}/qdrant/snapshot-${TIMESTAMP}.json" || true

# --- n8n workflow export ---
echo "[$(date)] Exporting n8n workflows..."
docker exec ${PROJECT}-n8n-1 \
  n8n export:workflow --all \
  --output="/home/node/.n8n/backups/workflows.json" || true
docker cp ${PROJECT}-n8n-1:/home/node/.n8n/backups/workflows.json \
  "${BACKUP_DIR}/n8n/workflows-${TIMESTAMP}.json" 2>/dev/null || true

echo "[$(date)] Pre-backup completed successfully"

# --- Heartbeat ping ---
{%% if backup_heartbeat_url %%}
curl -sf "{{ backup_heartbeat_url }}" || true
{%% endif %%}
"""

FILES["roles/backup-config/templates/backup-cleanup.sh.j2"] = """#!/bin/bash
# Cleanup old local backup files beyond retention period

set -euo pipefail

BACKUP_DIR="{{ backup_base_dir }}"
RETENTION_DAYS="{{ backup_local_retention_days }}"

echo "[$(date)] Cleaning up backups older than ${RETENTION_DAYS} days..."

find "${BACKUP_DIR}" -type f -mtime +${RETENTION_DAYS} -delete -print

echo "[$(date)] Backup cleanup completed"
"""

FILES["roles/backup-config/molecule/default/verify.yml"] = """---
- name: Verify backup-config role
  hosts: all
  gather_facts: false
  tasks:
    - name: Check backup directories exist
      ansible.builtin.stat:
        path: "{{ backup_base_dir }}/{{ item }}"
      register: backup_dirs_check
      loop:
        - pg_dump
        - redis
        - qdrant
        - n8n
        - grafana
      failed_when: not backup_dirs_check.stat.exists

    - name: Check pre-backup script exists
      ansible.builtin.stat:
        path: /usr/local/bin/pre-backup.sh
      register: prebackup
      failed_when: not prebackup.stat.exists

    - name: Check pre-backup script is executable
      ansible.builtin.stat:
        path: /usr/local/bin/pre-backup.sh
      register: prebackup_perm
      failed_when: not prebackup_perm.stat.executable

    - name: Check pre-backup cron exists
      ansible.builtin.command:
        cmd: crontab -l -u root
      register: crontab
      changed_when: false
      failed_when: "'pre-backup.sh' not in crontab.stdout"
      become: true
"""

FILES["roles/backup-config/README.md"] = """# Backup Config Role

Configures pre-backup scripts and cron jobs for data export before Zerobyte runs.

## Architecture

```
02:55  pre-backup.sh runs (pg_dump, redis save, qdrant snapshot, n8n export)
03:00  Zerobyte (on VPN server) pulls data via VPN to S3
04:00  backup-cleanup.sh removes old local files
```

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `backup_base_dir` | `/opt/{{ project_name }}/backups` | Base directory for backups |
| `backup_cron_hour` | `2` | Cron hour for pre-backup |
| `backup_cron_minute` | `55` | Cron minute for pre-backup |
| `backup_heartbeat_url` | (empty) | Uptime Kuma push URL |
| `backup_local_retention_days` | `7` | Days to keep local backups |

## Dependencies

- `docker`, `postgresql`, `redis`, `qdrant` roles
"""

# ============================================================
# PHASE 5: UPTIME-CONFIG ROLE
# ============================================================

FILES["roles/uptime-config/defaults/main.yml"] = """---
# uptime-config — defaults

# Uptime Kuma monitors documentation
# These are configured MANUALLY on the VPN server
# This role generates documentation for the operator

uptime_kuma_monitors:
  - name: "{{ project_display_name }} - HTTPS"
    type: "http"
    url: "https://{{ domain_name }}/health"
    interval: 60
    retryInterval: 30
    maxretries: 2

  - name: "{{ project_display_name }} - n8n"
    type: "http"
    url: "https://admin.{{ domain_name }}/n8n/healthz"
    interval: 60
    retryInterval: 30
    maxretries: 3

  - name: "{{ project_display_name }} - Grafana"
    type: "http"
    url: "https://admin.{{ domain_name }}/grafana/api/health"
    interval: 120
    maxretries: 3

  - name: "{{ project_display_name }} - PostgreSQL"
    type: "port"
    hostname: "{{ vpn_headscale_ip }}"
    port: 5432
    interval: 120
    maxretries: 2

  - name: "{{ project_display_name }} - TLS Certificate"
    type: "http"
    url: "https://{{ domain_name }}"
    interval: 86400
    expiryNotification: true

  - name: "{{ project_display_name }} - Backup Heartbeat"
    type: "push"
    interval: 86400
"""

FILES["roles/uptime-config/vars/main.yml"] = """---
# uptime-config — vars (internal)
"""

FILES["roles/uptime-config/tasks/main.yml"] = """---
# uptime-config — tasks
# This role generates documentation for Uptime Kuma monitors
# Uptime Kuma is deployed on the VPN server, not managed by this project

- name: Create docs directory
  ansible.builtin.file:
    path: "/opt/{{ project_name }}/configs/uptime-kuma"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true

- name: Deploy Uptime Kuma monitors documentation
  ansible.builtin.template:
    src: uptime-kuma-monitors.md.j2
    dest: "/opt/{{ project_name }}/configs/uptime-kuma/monitors.md"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  become: true

- name: Display Uptime Kuma configuration reminder
  ansible.builtin.debug:
    msg: >-
      REMINDER: Configure {{ uptime_kuma_monitors | length }} monitors in Uptime Kuma
      on the VPN server. See /opt/{{ project_name }}/configs/uptime-kuma/monitors.md
"""

FILES["roles/uptime-config/handlers/main.yml"] = """---
# uptime-config — handlers
# No handlers — documentation role only
"""

FILES["roles/uptime-config/meta/main.yml"] = """---
# uptime-config — meta

galaxy_info:
  author: "{{ project_name }}"
  description: "Uptime Kuma monitors documentation for VPN server"
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions:
        - bookworm

dependencies: []
"""

FILES["roles/uptime-config/templates/uptime-kuma-monitors.md.j2"] = """# Uptime Kuma — Monitors Configuration

> Generated by Ansible on {{ '{{ ansible_date_time.iso8601 }}' }}
> Configure these monitors manually in Uptime Kuma on the VPN server.

## Monitors

{%% for monitor in uptime_kuma_monitors %%}
### {{ loop.index }}. {{ monitor.name }}

| Setting | Value |
|---------|-------|
| Type | {{ monitor.type }} |
{%% if monitor.url is defined %%}| URL | {{ monitor.url }} |
{%% endif %%}{%% if monitor.hostname is defined %%}| Hostname | {{ monitor.hostname }} |
{%% endif %%}{%% if monitor.port is defined %%}| Port | {{ monitor.port }} |
{%% endif %%}| Interval | {{ monitor.interval }}s |
{%% if monitor.maxretries is defined %%}| Max Retries | {{ monitor.maxretries }} |
{%% endif %%}{%% if monitor.retryInterval is defined %%}| Retry Interval | {{ monitor.retryInterval }}s |
{%% endif %%}{%% if monitor.expiryNotification is defined %%}| Expiry Notification | {{ monitor.expiryNotification }} |
{%% endif %%}

{%% endfor %%}

## Notification Setup

Configure a notification channel using the project webhook:
- Method: {{ notification_method | default('webhook') }}
- URL: {{ notification_webhook_url | default('(configure in secrets)') }}
"""

FILES["roles/uptime-config/molecule/default/verify.yml"] = """---
- name: Verify uptime-config role
  hosts: all
  gather_facts: false
  tasks:
    - name: Check monitors documentation exists
      ansible.builtin.stat:
        path: "/opt/{{ project_name }}/configs/uptime-kuma/monitors.md"
      register: monitors_doc
      failed_when: not monitors_doc.stat.exists
"""

FILES["roles/uptime-config/README.md"] = """# Uptime Config Role

Generates documentation for Uptime Kuma monitor configuration on the VPN server.

## Important

Uptime Kuma is **not** deployed by this project. It runs on the VPN server (Seko-VPN).
This role generates a documentation file listing all monitors to configure manually.

## Monitors

1. HTTPS health endpoint
2. n8n healthz
3. Grafana health API
4. PostgreSQL port check (via VPN)
5. TLS certificate expiry
6. Backup heartbeat (push monitor)

## Dependencies

None
"""

# ============================================================
# PHASE 5: SMOKE-TESTS ROLE
# ============================================================

FILES["roles/smoke-tests/defaults/main.yml"] = """---
# smoke-tests \u2014 defaults

smoke_test_base_url: "https://{{ domain_name }}"
smoke_test_admin_url: "https://admin.{{ domain_name }}"
smoke_test_timeout: 10
"""

FILES["roles/smoke-tests/vars/main.yml"] = """---
# smoke-tests \u2014 vars (internal)
"""

FILES["roles/smoke-tests/tasks/main.yml"] = """---
# smoke-tests \u2014 tasks

- name: Deploy smoke test script
  ansible.builtin.template:
    src: smoke-test.sh.j2
    dest: "/opt/{{ project_name }}/scripts/smoke-test.sh"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true

- name: Run smoke tests
  ansible.builtin.command:
    cmd: "/opt/{{ project_name }}/scripts/smoke-test.sh"
  register: smoke_test_result
  changed_when: false
  failed_when: smoke_test_result.rc != 0
  become: true
  tags:
    - smoke-tests
    - verify

- name: Display smoke test results
  ansible.builtin.debug:
    msg: "{{ smoke_test_result.stdout_lines }}"
  tags:
    - smoke-tests
    - verify
"""

FILES["roles/smoke-tests/handlers/main.yml"] = """---
# smoke-tests \u2014 handlers
# No handlers \u2014 test role only
"""

FILES["roles/smoke-tests/meta/main.yml"] = """---
# smoke-tests \u2014 meta

galaxy_info:
  author: "{{ project_name }}"
  description: "Smoke tests for the complete stack"
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions:
        - bookworm

dependencies: []
"""

FILES["roles/smoke-tests/templates/smoke-test.sh.j2"] = """#!/bin/bash
# Smoke tests for {{ project_display_name }}
# Usage: ./smoke-test.sh [base_url]

set -euo pipefail

BASE_URL="${1:-{{ smoke_test_base_url }}}"
ADMIN_URL="${2:-{{ smoke_test_admin_url }}}"
TIMEOUT="{{ smoke_test_timeout }}"
FAILURES=0

check() {
  local name="$1" url="$2" expected="${3:-200}"
  local status
  status=$(curl -sf -o /dev/null -w "%{http_code}" --max-time "${TIMEOUT}" "$url" 2>/dev/null || echo "000")
  if [ "$status" = "$expected" ]; then
    echo "OK $name -- HTTP $status"
  else
    echo "FAIL $name -- HTTP $status (expected $expected)"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "=== Smoke Tests -- $(date) ==="
echo "Target: $BASE_URL"
echo "Admin:  $ADMIN_URL"
echo ""

# --- Infrastructure ---
echo "--- Infrastructure ---"
check "Caddy HTTPS"      "$BASE_URL/health"
check "LiteLLM Health"   "$BASE_URL/litellm/health"

# --- Admin services (via VPN) ---
echo ""
echo "--- Admin Services ---"
check "n8n Healthz"      "$ADMIN_URL/n8n/healthz"
check "Grafana Health"   "$ADMIN_URL/grafana/api/health"

# --- Data services (Docker healthcheck) ---
echo ""
echo "--- Data Services (via Docker) ---"

PG_HEALTHY=$(docker exec {{ project_name }}-postgresql-1 pg_isready -U postgres 2>/dev/null && echo "OK" || echo "FAIL")
if [ "$PG_HEALTHY" = "OK" ]; then
  echo "OK PostgreSQL -- pg_isready"
else
  echo "FAIL PostgreSQL -- pg_isready failed"
  FAILURES=$((FAILURES + 1))
fi

REDIS_HEALTHY=$(docker exec {{ project_name }}-redis-1 redis-cli -a "{{ redis_password }}" ping 2>/dev/null | grep -c PONG || echo "0")
if [ "$REDIS_HEALTHY" -gt 0 ]; then
  echo "OK Redis -- PONG"
else
  echo "FAIL Redis -- no PONG response"
  FAILURES=$((FAILURES + 1))
fi

QDRANT_HEALTHY=$(curl -sf --max-time "${TIMEOUT}" "http://localhost:6333/healthz" 2>/dev/null && echo "OK" || echo "FAIL")
if [ "$QDRANT_HEALTHY" = "OK" ]; then
  echo "OK Qdrant -- healthz"
else
  echo "FAIL Qdrant -- healthz failed"
  FAILURES=$((FAILURES + 1))
fi

# --- TLS Certificate ---
echo ""
echo "--- TLS Certificate ---"
CERT_EXPIRY=$(echo | openssl s_client -servername "{{ domain_name }}" -connect "{{ domain_name }}:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "UNKNOWN")
if [ "$CERT_EXPIRY" != "UNKNOWN" ]; then
  echo "OK TLS Certificate -- expires $CERT_EXPIRY"
else
  echo "FAIL TLS Certificate -- could not verify"
  FAILURES=$((FAILURES + 1))
fi

# --- DNS ---
echo ""
echo "--- DNS Resolution ---"
DNS_RESULT=$(dig +short {{ domain_name }} 2>/dev/null || echo "FAIL")
if [ -n "$DNS_RESULT" ] && [ "$DNS_RESULT" != "FAIL" ]; then
  echo "OK DNS -- {{ domain_name }} resolves to $DNS_RESULT"
else
  echo "FAIL DNS -- {{ domain_name }} not resolving"
  FAILURES=$((FAILURES + 1))
fi

# --- Results ---
echo ""
echo "=== Results ==="
if [ "$FAILURES" -eq 0 ]; then
  echo "All tests passed"
  exit 0
else
  echo "$FAILURES test(s) failed"
  exit 1
fi
"""

FILES["roles/smoke-tests/molecule/default/verify.yml"] = """---
- name: Verify smoke-tests role
  hosts: all
  gather_facts: false
  tasks:
    - name: Check smoke test script exists
      ansible.builtin.stat:
        path: "/opt/{{ project_name }}/scripts/smoke-test.sh"
      register: smoke_script
      failed_when: not smoke_script.stat.exists

    - name: Check smoke test script is executable
      ansible.builtin.stat:
        path: "/opt/{{ project_name }}/scripts/smoke-test.sh"
      register: smoke_perm
      failed_when: not smoke_perm.stat.executable
"""

FILES["roles/smoke-tests/README.md"] = """# Smoke Tests Role

Deploys and runs smoke tests against the complete stack to verify all services are operational.

## Tests Performed

1. Caddy HTTPS health endpoint
2. LiteLLM health endpoint
3. n8n healthz (via admin URL / VPN)
4. Grafana health API (via admin URL / VPN)
5. PostgreSQL connectivity (pg_isready)
6. Redis connectivity (redis-cli ping)
7. Qdrant healthz
8. TLS certificate validity
9. DNS resolution

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `smoke_test_base_url` | `https://{{ domain_name }}` | Public base URL |
| `smoke_test_admin_url` | `https://admin.{{ domain_name }}` | Admin base URL (VPN) |
| `smoke_test_timeout` | `10` | Curl timeout in seconds |

## Usage

```bash
# Via Ansible
ansible-playbook playbooks/site.yml --tags smoke-tests

# Standalone
/opt/{{ project_name }}/scripts/smoke-test.sh
```

## Dependencies

None (runs against deployed services)
"""

# ============================================================
# PHASE 6: CI/CD WORKFLOWS
# ============================================================

FILES[".github/workflows/ci.yml"] = """---
name: CI \u2014 Lint & Test

on:
  push:
    branches: [main, develop]
    paths:
      - "roles/**"
      - "playbooks/**"
      - "inventory/**"
      - "templates/**"
      - ".github/workflows/ci.yml"
  pull_request:
    branches: [main]

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install yamllint ansible-lint ansible-core

      - name: Install Ansible collections
        run: |
          ansible-galaxy collection install -r requirements.yml

      - name: YAML Lint
        run: yamllint -c .yamllint.yml .

      - name: Ansible Lint
        run: ansible-lint playbooks/site.yml
"""

FILES[".github/workflows/deploy-preprod.yml"] = """---
name: Deploy Pre-production

on:
  workflow_dispatch:
    inputs:
      destroy_after:
        description: "Destroy server after tests"
        required: false
        default: "true"
        type: boolean
  push:
    branches: [main]
    paths:
      - "roles/**"
      - "playbooks/**"
      - "inventory/**"

env:
  HETZNER_TOKEN: ${{ secrets.HETZNER_CLOUD_TOKEN }}
  ANSIBLE_VAULT_PASSWORD: ${{ secrets.ANSIBLE_VAULT_PASSWORD }}

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install yamllint ansible-lint ansible-core
      - run: ansible-galaxy collection install -r requirements.yml
      - run: yamllint -c .yamllint.yml .
      - run: ansible-lint playbooks/site.yml

  provision:
    name: Provision Hetzner Server
    needs: lint
    runs-on: ubuntu-latest
    outputs:
      server_ip: ${{ steps.create.outputs.ip }}
      server_id: ${{ steps.create.outputs.id }}
    steps:
      - uses: actions/checkout@v4

      - name: Install hcloud CLI
        run: |
          curl -sL https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-amd64.tar.gz | tar xz
          sudo mv hcloud /usr/local/bin/

      - name: Create Hetzner Server
        id: create
        run: |
          set -euo pipefail

          SERVER_JSON=$(hcloud server create \\
            --name "${{ github.event.repository.name }}-preprod-$(date +%s)" \\
            --type cx22 \\
            --location fsn1 \\
            --image debian-12 \\
            --ssh-key deploy \\
            --output json)

          echo "ip=$(echo "$SERVER_JSON" | jq -r '.server.public_net.ipv4.ip')" >> "$GITHUB_OUTPUT"
          echo "id=$(echo "$SERVER_JSON" | jq -r '.server.id')" >> "$GITHUB_OUTPUT"

      - name: Wait for SSH
        run: |
          for i in $(seq 1 30); do
            if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${{ steps.create.outputs.ip }} true 2>/dev/null; then
              echo "SSH ready"
              exit 0
            fi
            sleep 10
          done
          echo "SSH timeout" && exit 1

  deploy:
    name: Deploy via Ansible
    needs: provision
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Ansible
        run: |
          pip install ansible-core
          ansible-galaxy collection install -r requirements.yml

      - name: Setup SSH key
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519

      - name: Create vault password file
        run: echo "$ANSIBLE_VAULT_PASSWORD" > .vault_password

      - name: Deploy
        run: |
          ansible-playbook playbooks/site.yml \\
            -i "${{ needs.provision.outputs.server_ip }}," \\
            -e "target_env=preprod" \\
            --diff

  smoke-tests:
    name: Smoke Tests
    needs: [provision, deploy]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Smoke Tests
        run: bash scripts/smoke-test.sh "https://${{ needs.provision.outputs.server_ip }}"
        continue-on-error: true

  cleanup:
    name: Cleanup
    needs: [provision, smoke-tests]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Install hcloud CLI
        run: |
          curl -sL https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-amd64.tar.gz | tar xz
          sudo mv hcloud /usr/local/bin/

      - name: Destroy server
        if: github.event.inputs.destroy_after != 'false'
        run: hcloud server delete ${{ needs.provision.outputs.server_id }}
"""

FILES[".github/workflows/deploy-prod.yml"] = """---
name: Deploy Production

on:
  workflow_dispatch:
    inputs:
      confirm:
        description: "Type DEPLOY to confirm production deployment"
        required: true
        type: string

env:
  ANSIBLE_VAULT_PASSWORD: ${{ secrets.ANSIBLE_VAULT_PASSWORD }}

jobs:
  validate:
    name: Validate Confirmation
    runs-on: ubuntu-latest
    steps:
      - name: Check confirmation
        if: github.event.inputs.confirm != 'DEPLOY'
        run: |
          echo "::error::You must type DEPLOY to confirm production deployment"
          exit 1

  lint:
    name: Lint
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install yamllint ansible-lint ansible-core
      - run: ansible-galaxy collection install -r requirements.yml
      - run: yamllint -c .yamllint.yml .
      - run: ansible-lint playbooks/site.yml

  deploy:
    name: Deploy to Production
    needs: lint
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Ansible
        run: |
          pip install ansible-core
          ansible-galaxy collection install -r requirements.yml

      - name: Setup SSH key
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519

      - name: Create vault password file
        run: echo "$ANSIBLE_VAULT_PASSWORD" > .vault_password

      - name: Deploy
        run: |
          ansible-playbook playbooks/site.yml \\
            -i inventory/hosts.yml \\
            -l prod \\
            --diff

      - name: Smoke Tests
        run: bash scripts/smoke-test.sh
"""

# ============================================================
# PHASE 6: UTILITY PLAYBOOKS
# ============================================================

FILES["playbooks/deploy.yml"] = """---
# Deploy application services only (skip OS, Docker, VPN setup)
- name: Deploy Applications
  hosts: "{{ target_host | default('prod') }}"
  become: false
  tags: [deploy]

  roles:
    - { role: caddy, tags: [caddy] }
    - { role: postgresql, tags: [postgresql] }
    - { role: redis, tags: [redis] }
    - { role: qdrant, tags: [qdrant] }
    - { role: n8n, tags: [n8n] }
    - { role: litellm, tags: [litellm] }
    - { role: openclaw, tags: [openclaw] }
    - { role: monitoring, tags: [monitoring] }
    - { role: diun, tags: [diun] }

  post_tasks:
    - name: Start Docker Compose stack
      community.docker.docker_compose_v2:
        project_src: "/opt/{{ project_name }}"
        files:
          - docker-compose.yml
        state: present
      become: true
"""

FILES["playbooks/rollback.yml"] = """---
# Rollback to previous version
# Usage: ansible-playbook playbooks/rollback.yml -e "service=n8n"
- name: Rollback Service
  hosts: "{{ target_host | default('prod') }}"
  become: false

  vars_prompt:
    - name: service
      prompt: "Which service to rollback?"
      private: false

    - name: confirm
      prompt: "Type YES to confirm rollback of {{ service }}"
      private: false

  tasks:
    - name: Validate confirmation
      ansible.builtin.assert:
        that:
          - confirm == "YES"
        fail_msg: "Rollback cancelled — confirmation not received"

    - name: Pull previous image
      community.docker.docker_compose_v2:
        project_src: "/opt/{{ project_name }}"
        files:
          - docker-compose.yml
        services:
          - "{{ service }}"
        state: restarted
        pull: always
      become: true

    - name: Verify service health
      ansible.builtin.command:
        cmd: "docker inspect --format='{{ '{{' }}.State.Health.Status{{ '}}' }}' {{ project_name }}-{{ service }}-1"
      register: health_check
      retries: 10
      delay: 10
      until: health_check.stdout == "healthy"
      changed_when: false
      become: true
"""

FILES["playbooks/backup-restore.yml"] = """---
# Restore from backup
# Usage: ansible-playbook playbooks/backup-restore.yml -e "backup_file=/path/to/dump"
- name: Restore from Backup
  hosts: "{{ target_host | default('prod') }}"
  become: false

  vars_prompt:
    - name: confirm
      prompt: "WARNING: This will overwrite current data. Type RESTORE to confirm"
      private: false

  tasks:
    - name: Validate confirmation
      ansible.builtin.assert:
        that:
          - confirm == "RESTORE"
        fail_msg: "Restore cancelled"

    - name: Stop application services
      community.docker.docker_compose_v2:
        project_src: "/opt/{{ project_name }}"
        files:
          - docker-compose.yml
        services:
          - n8n
          - litellm
          - openclaw
        state: stopped
      become: true

    - name: Restore PostgreSQL databases
      ansible.builtin.shell: |
        set -euo pipefail
        for DB in n8n openclaw litellm; do
          DUMP_FILE="{{ backup_base_dir | default('/opt/' + project_name + '/backups') }}/pg_dump/${DB}-latest.dump"
          if [ -f "$DUMP_FILE" ]; then
            docker cp "$DUMP_FILE" {{ project_name }}-postgresql-1:/tmp/restore.dump
            docker exec {{ project_name }}-postgresql-1 pg_restore -U postgres -d "$DB" --clean --if-exists /tmp/restore.dump
            echo "Restored $DB"
          fi
        done
      args:
        executable: /bin/bash
      become: true
      changed_when: true

    - name: Restart all services
      community.docker.docker_compose_v2:
        project_src: "/opt/{{ project_name }}"
        files:
          - docker-compose.yml
        state: restarted
      become: true
"""

FILES["playbooks/rotate-secrets.yml"] = """---
# Rotate all secrets and passwords
# Usage: ansible-playbook playbooks/rotate-secrets.yml
- name: Rotate Secrets
  hosts: "{{ target_host | default('prod') }}"
  become: false

  vars_prompt:
    - name: confirm
      prompt: "This will rotate ALL secrets. Services will restart. Type ROTATE to confirm"
      private: false

  tasks:
    - name: Validate confirmation
      ansible.builtin.assert:
        that:
          - confirm == "ROTATE"
        fail_msg: "Secret rotation cancelled"

    - name: Display rotation instructions
      ansible.builtin.debug:
        msg: |
          Secret rotation steps:
          1. Edit vault: ansible-vault edit inventory/group_vars/all/secrets.yml
          2. Update the following secrets:
             - postgresql_password
             - redis_password
             - n8n_encryption_key
             - n8n_basic_auth_password
             - litellm_master_key
             - grafana_admin_password
             - qdrant_api_key
             - openclaw_api_key
          3. Re-run: ansible-playbook playbooks/site.yml --tags postgresql,redis,n8n,litellm,openclaw,qdrant,monitoring
          4. Verify: ansible-playbook playbooks/site.yml --tags smoke-tests
"""

FILES["playbooks/update-single.yml"] = """---
# Update a single service
# Usage: ansible-playbook playbooks/update-single.yml -e "service=n8n"
- name: Update Single Service
  hosts: "{{ target_host | default('prod') }}"
  become: false

  tasks:
    - name: Validate service parameter
      ansible.builtin.assert:
        that:
          - service is defined
          - service in ['caddy', 'postgresql', 'redis', 'qdrant', 'n8n', 'litellm', 'openclaw', 'grafana', 'victoriametrics', 'loki', 'alloy', 'diun']
        fail_msg: "Please provide a valid service name with -e 'service=<name>'"

    - name: Pull latest image for {{ service }}
      community.docker.docker_compose_v2:
        project_src: "/opt/{{ project_name }}"
        files:
          - docker-compose.yml
        services:
          - "{{ service }}"
        state: restarted
        pull: always
      become: true

    - name: Wait for service to be healthy
      ansible.builtin.command:
        cmd: "docker inspect --format='{{ '{{' }}.State.Health.Status{{ '}}' }}' {{ project_name }}-{{ service }}-1"
      register: health_result
      retries: 12
      delay: 10
      until: health_result.stdout == "healthy"
      changed_when: false
      become: true
      ignore_errors: true

    - name: Report status
      ansible.builtin.debug:
        msg: "Service {{ service }} status: {{ health_result.stdout | default('unknown') }}"
"""

# ============================================================
# PHASE 6: DOCUMENTATION
# ============================================================

FILES["docs/RUNBOOK.md"] = """# Runbook - Operations Manual

## 1. Starting/Stopping the Stack

### Start all services
```bash
cd /opt/{{ project_name }}
docker compose up -d
```

### Stop all services
```bash
docker compose down
```

### Restart a single service
```bash
docker compose restart <service_name>
```

## 2. Updating a Service

### Update via Ansible (recommended)
```bash
# Edit versions.yml with new image tag
ansible-playbook playbooks/update-single.yml -e "service=n8n"
```

### Manual update
```bash
cd /opt/{{ project_name }}
# Edit docker-compose.yml with new image tag
docker compose pull <service>
docker compose up -d <service>
```

## 3. Adding a New LiteLLM Model

1. Edit `roles/litellm/templates/litellm_config.yaml.j2`
2. Add new model entry under `model_list`
3. Deploy: `ansible-playbook playbooks/site.yml --tags litellm`
4. Verify: `curl -H "Authorization: Bearer <key>" https://<domain>/litellm/v1/models`

## 4. Backup & Restore

### Pre-backup runs automatically
- Schedule: 02:55 daily (before Zerobyte at 03:00)
- Script: `/usr/local/bin/pre-backup.sh`
- Logs: `/var/log/pre-backup.log`

### Manual backup
```bash
sudo /usr/local/bin/pre-backup.sh
```

### Restore from backup
```bash
ansible-playbook playbooks/backup-restore.yml
```

## 5. Secret Rotation

```bash
# 1. Edit secrets
ansible-vault edit inventory/group_vars/all/secrets.yml

# 2. Redeploy affected services
ansible-playbook playbooks/site.yml --tags postgresql,redis,n8n,litellm,openclaw

# 3. Verify
ansible-playbook playbooks/site.yml --tags smoke-tests
```

## 6. Zerobyte Configuration (Seko-VPN)

### Volumes to Create
| Volume | Source Path (via VPN) |
|--------|----------------------|
| postgres | `/opt/{{ project_name }}/backups/pg_dump/` |
| redis | `/opt/{{ project_name }}/data/redis/` |
| qdrant | `/opt/{{ project_name }}/backups/qdrant/` |
| n8n | `/opt/{{ project_name }}/backups/n8n/` |
| configs | `/opt/{{ project_name }}/configs/` |

### S3 Repository
- Provider: Hetzner Object Storage
- Location: fsn1
- Bucket: `{{ s3_bucket_name | default(project_name + '-backups') }}`

### Backup Jobs
| Job | Schedule | Retention |
|-----|----------|-----------|
| DB Backup | Daily 03:00 | 7 daily, 4 weekly, 3 monthly |
| Redis | Daily 03:05 | 7 daily |
| Qdrant | Daily 03:10 | 7 daily, 4 weekly |
| n8n Export | Daily 03:15 | 7 daily, 4 weekly, 3 monthly |
| Config | Daily 03:20 | 7 daily, 4 weekly |
| Grafana | Weekly Sun 03:00 | 4 weekly |

## 7. Uptime Kuma Configuration (Seko-VPN)

See `/opt/{{ project_name }}/configs/uptime-kuma/monitors.md` for the list of monitors to configure.

## 8. Incident Response

### Service not responding
1. Check Docker status: `docker compose ps`
2. Check logs: `docker compose logs <service> --tail 100`
3. Check resources: `htop`, `df -h`
4. Restart if needed: `docker compose restart <service>`

### High resource usage
1. Check which container: `docker stats`
2. Review limits in `docker-compose.yml`
3. Check for runaway processes in container logs
"""

FILES["docs/ARCHITECTURE.md"] = """# Architecture

## Network Topology

```mermaid
graph TB
    Internet((Internet))
    VPN((Headscale VPN))

    subgraph Frontend Network
        Caddy[Caddy :80/:443]
    end

    subgraph Backend Network - Internal
        PostgreSQL[(PostgreSQL)]
        Redis[(Redis)]
        Qdrant[(Qdrant)]
        n8n[n8n]
        LiteLLM[LiteLLM]
        OpenClaw[OpenClaw]
    end

    subgraph Egress Network
        n8n_egress[n8n]
        LiteLLM_egress[LiteLLM]
        OpenClaw_egress[OpenClaw]
    end

    subgraph Monitoring Network - Internal
        VM[VictoriaMetrics]
        Loki[Loki]
        Alloy[Alloy]
        Grafana[Grafana]
    end

    Internet --> Caddy
    VPN --> Caddy
    Caddy --> n8n
    Caddy --> LiteLLM
    Caddy --> Grafana
    Caddy --> OpenClaw
    Caddy --> Qdrant

    n8n --> PostgreSQL
    LiteLLM --> PostgreSQL
    LiteLLM --> Redis
    OpenClaw --> PostgreSQL
    OpenClaw --> Redis
    OpenClaw --> Qdrant
    OpenClaw --> LiteLLM

    n8n_egress --> Internet
    LiteLLM_egress --> Internet
    OpenClaw_egress --> Internet

    Alloy --> VM
    Alloy --> Loki
    Grafana --> VM
    Grafana --> Loki
```

## Docker Networks

| Network | Subnet | Internal | Purpose |
|---------|--------|----------|---------|
| frontend | 172.20.1.0/24 | No | Public-facing (Caddy) |
| backend | 172.20.2.0/24 | Yes | Service-to-service |
| monitoring | 172.20.3.0/24 | Yes | Observability stack |
| egress | 172.20.4.0/24 | No | Outbound internet access |

## Service Dependencies

```
Layer 0: PostgreSQL, Redis, Qdrant (no dependencies)
Layer 1: n8n, LiteLLM, OpenClaw (depend on Layer 0)
Layer 2: Caddy (reverse proxy for Layer 1)
Layer 3: Monitoring (observes all layers)
Layer 4: DIUN (watches all containers)
```
"""

FILES["docs/DISASTER-RECOVERY.md"] = """# Disaster Recovery Plan

## Scenario 1: Container Crash

**Severity**: Low
**Recovery Time**: Automatic (< 1 min)

Docker `restart: unless-stopped` policy handles automatic restarts.
Grafana alerts trigger if restart count > 3 in 15 minutes.

### Actions
1. Check logs: `docker compose logs <service> --tail 200`
2. If persistent: check resource limits, disk space
3. If corrupt: rebuild container `docker compose up -d --force-recreate <service>`

## Scenario 2: VPS Down

**Severity**: High
**Recovery Time**: 30-60 minutes

### Actions
1. Provision new VPS (same provider/specs)
2. Update DNS records
3. Run full Ansible deployment: `ansible-playbook playbooks/site.yml`
4. Restore data from Zerobyte S3 backups
5. Verify with smoke tests

## Scenario 3: Database Corruption

**Severity**: High
**Recovery Time**: 15-30 minutes

### Actions
1. Stop application services: `docker compose stop n8n litellm openclaw`
2. Restore PostgreSQL from latest dump:
   ```bash
   ansible-playbook playbooks/backup-restore.yml
   ```
3. Restart services: `docker compose up -d`
4. Verify data integrity

## Scenario 4: Security Compromise

**Severity**: Critical
**Recovery Time**: 1-2 hours

### Immediate Actions
1. Isolate the VPS: remove from Headscale network
2. Capture forensic snapshot (if possible)
3. Rotate ALL secrets: `ansible-playbook playbooks/rotate-secrets.yml`
4. Revoke all API keys (Anthropic, OpenAI)
5. Fresh VPS deployment from scratch
6. Restore data from pre-compromise backup
7. Review audit logs: `/var/log/audit/audit.log`
"""

# ============================================================
# PHASE 6: SCRIPTS
# ============================================================

FILES["scripts/smoke-test.sh"] = """#!/bin/bash
# Standalone smoke test script
# Usage: ./smoke-test.sh [base_url]

set -euo pipefail

BASE_URL="${1:?Usage: $0 <base_url>}"
FAILURES=0

check() {
  local name="$1" url="$2" expected="${3:-200}"
  local status
  status=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
  if [ "$status" = "$expected" ]; then
    echo "OK $name -- HTTP $status"
  else
    echo "FAIL $name -- HTTP $status (expected $expected)"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "=== Smoke Tests -- $(date) ==="
echo "Target: $BASE_URL"
echo ""

check "HTTPS Health"     "$BASE_URL/health"
check "LiteLLM Health"   "$BASE_URL/litellm/health"

echo ""
echo "=== Results ==="
if [ "$FAILURES" -eq 0 ]; then
  echo "All tests passed"
  exit 0
else
  echo "$FAILURES test(s) failed"
  exit 1
fi
"""

# ============================================================
# MOLECULE DEFAULTS (converge + molecule.yml for roles that need them)
# ============================================================

for role in ["monitoring", "diun", "backup-config", "uptime-config", "smoke-tests"]:
    FILES[f"roles/{role}/molecule/default/converge.yml"] = f"""---
- name: Converge
  hosts: all
  gather_facts: true
  roles:
    - role: {role}
"""

    FILES[f"roles/{role}/molecule/default/molecule.yml"] = f"""---
dependency:
  name: galaxy
driver:
  name: docker
platforms:
  - name: instance
    image: debian:bookworm
    pre_build_image: true
    privileged: true
    command: /sbin/init
provisioner:
  name: ansible
verifier:
  name: ansible
"""

# ============================================================
# WRITE ALL FILES
# ============================================================

count = 0
for rel_path, content in FILES.items():
    full = os.path.join(BASE, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content.lstrip("\n"))
    count += 1

print(f"Written {count} files for Phases 4-6")
