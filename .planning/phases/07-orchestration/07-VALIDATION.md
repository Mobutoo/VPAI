---
phase: 7
slug: orchestration
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-17
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Ansible lint + dry-run + manual smoke tests |
| **Config file** | `.yamllint.yml`, `.ansible-lint` |
| **Quick run command** | `source .venv/bin/activate && make lint` |
| **Full suite command** | `source .venv/bin/activate && make lint && ansible-playbook playbooks/site.yml --check --diff --tags n8n-provision` |
| **Estimated runtime** | ~30 seconds (lint) / ~60 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `make lint`
- **After every plan wave:** Run `make lint && ansible-playbook playbooks/site.yml --check --diff --tags n8n-provision`
- **Before `/gsd:verify-work`:** Full deploy + manual smoke test all workflows
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 07-01-01 | 01 | 1 | FLOW-01 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-brief-to-concept.json'))"` | ⬜ pending |
| 07-01-02 | 01 | 1 | FLOW-03 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-script-to-storyboard.json'))"` | ⬜ pending |
| 07-02-01 | 02 | 1 | FLOW-04 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-generate-assets.json'))"` | ⬜ pending |
| 07-02-02 | 02 | 1 | FLOW-05 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-rough-cut.json'))"` | ⬜ pending |
| 07-03-01 | 03 | 1 | FLOW-06 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-invalidation-engine.json'))"` | ⬜ pending |
| 07-03-02 | 03 | 1 | FLOW-02,FLOW-07 | lint+template | `make lint && python3 -c "import re; c=open('roles/n8n-provision/templates/workflows/cf-kitsu-sync.json.j2').read(); assert '{%' in c; import json; json.loads(re.sub(r'\{%.*?%\}','',c).replace('{{ kitsu_subdomain }}','boss').replace('{{ domain_name }}','x.com'))"` | ⬜ pending |
| 07-03-03 | 03 | 1 | FLOW-07 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-kitsu-inbound.json'))"` | ⬜ pending |
| 07-04-01 | 04 | 2 | CAL-01,CAL-02,CAL-03 | lint+json | `make lint && python3 -c "import json; json.load(open('roles/n8n-provision/files/workflows/cf-calendar-sync.json'))"` | ⬜ pending |
| 07-04-02 | 04 | 2 | all | lint | `make lint` (Ansible registration of 8 CF workflows in n8n-provision/tasks/main.yml) | ⬜ pending |
| 07-05-01 | 05 | 2 | all | deploy | `ansible-playbook playbooks/site.yml --check --diff --tags n8n-provision` | ⬜ pending |
| 07-05-02 | 05 | 2 | FLOW-01..07,CAL-01..03 | smoke | Manual: trigger each webhook, verify execution | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements — no new test framework needed. All validation is lint + JSON validity + Ansible dry-run + manual smoke tests after deploy.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Kitsu webhooks fire on task status change | FLOW-07 | Requires Kitsu UI interaction | Change task status in Kitsu UI, verify n8n execution log |
| Calendar visible in Plane | CAL-01 | Visual UI check | Open Plane UI, verify work items with dates |
| Drops as Plane cycles | CAL-02 | Visual UI check | Open Plane UI, verify cycles exist |
| End-to-end /content to rendered video | SC-1 | Full pipeline integration | Send /content in Telegram, follow through all 14 steps |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
