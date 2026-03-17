---
phase: 8
slug: data-layer-glue
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-17
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Ansible lint + JSON validity + dry-run |
| **Config file** | `.yamllint.yml`, `.ansible-lint` |
| **Quick run command** | `source .venv/bin/activate && make lint` |
| **Full suite command** | `source .venv/bin/activate && make lint && ansible-playbook playbooks/site.yml --check --diff --tags n8n-provision` |
| **Estimated runtime** | ~30 seconds (lint) / ~60 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `make lint`
- **After every plan wave:** Run `make lint && ansible-playbook playbooks/site.yml --check --diff --tags n8n-provision`
- **Before `/gsd:verify-work`:** Full deploy + manual smoke test all webhooks
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 08-01-01 | 01 | 1 | BLOCKER-1 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-create-content.json'))"` | ⬜ pending |
| 08-01-02 | 01 | 1 | BLOCKER-1 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-update-content.json'))"` | ⬜ pending |
| 08-01-03 | 01 | 1 | BLOCKER-1 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-read-content.json'))"` | ⬜ pending |
| 08-01-04 | 01 | 1 | BLOCKER-1 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-scene.json'))"` | ⬜ pending |
| 08-02-01 | 02 | 1 | BLOCKER-1 | lint | `make lint` (Ansible registration + env vars) | ⬜ pending |
| 08-03-01 | 03 | 2 | DATA-06 | ssh | `ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 'test -f /opt/kitsu/provisioned && echo OK'` | ⬜ pending |
| 08-04-01 | 04 | 2 | all | deploy | `ansible-playbook playbooks/site.yml --check --diff --tags n8n-provision` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements — no new test framework needed. All validation is lint + JSON validity + Ansible dry-run + manual smoke tests after deploy.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| cf-create-content creates NocoDB row | BLOCKER-1 | Requires live n8n + NocoDB | POST to webhook, verify row in NocoDB UI |
| cf-scene handles all 4 actions | BLOCKER-1 | Requires live services | Test create, list, update, invalidate via webhook |
| DATA-06 Kitsu project structure | DATA-06 | Requires Kitsu UI check | Verify hierarchy in boss.ewutelo.cloud |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
