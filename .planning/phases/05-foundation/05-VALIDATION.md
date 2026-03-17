---
phase: 5
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-17
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Ansible + SSH smoke tests (bash scripts) |
| **Config file** | `ansible.cfg` (existing) |
| **Quick run command** | `ansible-playbook playbooks/site.yml --check --diff --tags kitsu` |
| **Full suite command** | `ansible-playbook playbooks/site.yml --tags kitsu,caddy,n8n,backup-config && ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 'bash /opt/vpai/smoke-tests/kitsu-smoke.sh'` |
| **Estimated runtime** | ~120 seconds (deploy) + ~30 seconds (smoke) |

---

## Sampling Rate

- **After every task commit:** Run `make lint` + `ansible-playbook --check --diff` for changed roles
- **After every plan wave:** Full deploy + smoke test suite
- **Before `/gsd:verify-work`:** All smoke tests green, all API endpoints responding
- **Max feedback latency:** 150 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | INFRA-01 | deploy+smoke | `ansible-playbook --tags kitsu --check` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | INFRA-02 | deploy+smoke | `ssh ... 'docker exec postgresql psql -U zou -d kitsu_production -c "SELECT 1"'` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | INFRA-03 | deploy+smoke | `curl -sf https://boss.ewutelo.cloud/ -o /dev/null` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | INFRA-05 | manual+api | Grafana dashboard check for kitsu container metrics | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 1 | INFRA-06 | deploy+smoke | `ssh ... 'grep kitsu_production /opt/vpai/backup/pre-backup.sh'` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | DATA-01 | api | `curl -sf https://hq.ewutelo.cloud/api/v2/meta/tables -H 'xc-token: ...' \| jq '.list[].title' \| grep brands` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | DATA-02 | api | `curl ... \| grep contents` | ❌ W0 | ⬜ pending |
| 05-02-03 | 02 | 2 | DATA-03 | api | `curl ... \| grep scenes` | ❌ W0 | ⬜ pending |
| 05-02-04 | 02 | 2 | DATA-04 | api | `curl -sf https://qd.ewutelo.cloud/collections/brand-voice -H 'api-key: ...'` | ❌ W0 | ⬜ pending |
| 05-02-05 | 02 | 2 | DATA-05 | api | `curl ... brands table rows \| grep "Paul Taff"` | ❌ W0 | ⬜ pending |
| 05-02-06 | 02 | 2 | DATA-06 | api | Zou API `/api/data/projects` returns Paul Taff project with episodes/sequences | ❌ W0 | ⬜ pending |
| 05-02-07 | 02 | 2 | INFRA-04 | api | `ssh ... 'docker exec n8n env \| grep FAL_KEY'` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `roles/kitsu/` — Ansible role directory structure (tasks, handlers, defaults, templates)
- [ ] `inventory/group_vars/all/versions.yml` — `kitsu_version` pinned
- [ ] `inventory/group_vars/all/secrets.yml` — `vault_kitsu_admin_email`, `vault_kitsu_admin_password` added

*Existing infrastructure covers lint, Ansible config, SSH access, and Docker daemon.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Kitsu UI loads with project hierarchy | DATA-06 | Visual check of Vue.js UI | Open `boss.ewutelo.cloud` via VPN, verify Production/Episode/Sequence visible |
| Grafana dashboard shows Kitsu metrics | INFRA-05 | Visual dashboard check | Open `tala.ewutelo.cloud`, verify kitsu container panels |
| Qdrant semantic search returns brand tone | DATA-04 | Semantic quality check | Query `brand-voice` collection with "sarcastic tone" and verify relevant results |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 150s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
