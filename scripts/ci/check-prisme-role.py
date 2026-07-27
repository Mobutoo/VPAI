#!/usr/bin/env python3
from pathlib import Path
import re
import sys

import yaml


ROOT = Path(__file__).resolve().parents[2]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


tasks = yaml.safe_load((ROOT / "roles/postgresql/tasks/main.yml").read_text())
handlers = yaml.safe_load((ROOT / "roles/postgresql/handlers/main.yml").read_text())
hba = (ROOT / "roles/postgresql/templates/pg_hba.conf.j2").read_text()
compose = (ROOT / "roles/prisme/templates/docker-compose.yml.j2").read_text()
docker_vars = (ROOT / "inventory/group_vars/all/docker.yml").read_text()

deploy_hba = next(task for task in tasks if task["name"] == "Deploy pg_hba.conf")
require(deploy_hba["notify"] == "Reload PostgreSQL config", "pg_hba must reload, not restart")
listeners = [handler for handler in handlers if handler.get("listen") == "Reload PostgreSQL config"]
require(len(listeners) == 2, "reload requires probe and reload handlers")
require(any("pg_isready" in str(handler) for handler in listeners), "reload probe missing")
require(any("pg_reload_conf" in str(handler) for handler in listeners), "SQL reload missing")

ordered = [
    "host    prisme          all             {{ prisme_db_proxy_backend_ip }}/32    md5",
    "host    all             all             {{ prisme_db_proxy_backend_ip }}/32    reject",
    "host    prisme          all             {{ docker_network_backend_subnet }}    reject",
    "host    all             all             {{ prisme_service_backend_ip }}/32     reject",
    "host    all             all             {{ docker_network_backend_subnet }}    md5",
]
positions = [hba.index(line) for line in ordered]
require(positions == sorted(positions), "Prisme HBA rules are not before broad backend allow")
require("{% if prisme_enabled | default(false) | bool %}" in hba, "HBA flag guard missing")

service_block = compose.split("\nnetworks:", 1)[0]
services = re.findall(r"^  ([a-z][a-z0-9-]+):$", service_block, flags=re.MULTILINE)
require(
    services
    == [
        "web",
        "outbox",
        "research-worker",
        "browser",
        "connector",
        "indexer",
        "consolidation",
        "sparse-query",
        "db-proxy",
    ],
    f"unexpected Prisme service inventory: {services}",
)
require(compose.count("networks: [prisme_internal, egress]") == 2, "egress must have two consumers")
require("bind {{ prisme_db_proxy_internal_ip }}:5432" in (ROOT / "roles/prisme/templates/haproxy.cfg.j2").read_text(), "proxy bind missing")
require("bind 0.0.0.0" not in (ROOT / "roles/prisme/templates/haproxy.cfg.j2").read_text(), "proxy must not bind all interfaces")

for component in [
    "web",
    "outbox",
    "research",
    "browser",
    "connector",
    "indexer",
    "consolidation",
    "sparse",
    "db_proxy",
]:
    require(f"prisme_{component}_memory_limit:" in docker_vars, f"{component} hard limit missing")
    require(
        f"prisme_{component}_memory_reservation:" in docker_vars,
        f"{component} reservation missing",
    )

print("Prisme Ansible role gate: PASS")
