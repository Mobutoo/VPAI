---
phase: 9
slug: integration-fixes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-18
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Manual E2E (curl + SSH + ansible --check --diff) |
| **Config file** | none |
| **Quick run command** | `ansible-playbook playbooks/site.yml --check --diff -t kitsu,n8n` |
| **Full suite command** | Run 3 E2E flows manually (Kitsu events, Remotion render, CRUD webhooks) |
| **Estimated runtime** | ~120 seconds (deploy + smoke tests) |

---

## Sampling Rate

- **After every task commit:** `ansible-playbook playbooks/site.yml --check --diff` for template changes
- **After every plan wave:** Deploy + 3 E2E flows on Sese-AI
- **Before `/gsd:verify-work`:** All 8 SCs verified on Sese-AI
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | SC# | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-----|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | SC-1 | smoke | `ansible-playbook --check --diff -t kitsu` + grep rendered template | N/A | pending |
| 09-01-02 | 01 | 1 | SC-2 | smoke | `curl -X POST https://remotion.ewutelo.cloud/renders -H 'Content-Type: application/json' -d '{"compositionId":"HelloWorld"}'` | N/A | pending |
| 09-01-03 | 01 | 1 | SC-3 | smoke | SSH + `docker exec n8n env \| grep -E 'REMOTION_API_KEY\|BYTEPLUS_API_KEY'` | N/A | pending |
| 09-01-04 | 01 | 1 | SC-4 | code review | Verify JSON contains `action` field in body | N/A | pending |
| 09-01-05 | 01 | 1 | SC-5 | code review | Verify JSON contains `locked` key in STATUS_MAP | N/A | pending |
| 09-02-01 | 02 | 2 | SC-6 | smoke | `curl -X POST http://kitsu:80/api/auth/login -d '{"email":"javisi.bot@gmail.com",...}'` via SSH | N/A | pending |
| 09-02-02 | 02 | 2 | SC-7 | smoke | `curl http://kitsu:80/api/data/projects` via SSH | N/A | pending |
| 09-02-03 | 02 | 2 | SC-8 | manual | `ansible-vault view secrets.yml \| grep kitsu_admin` | N/A | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test framework needed — all verification is curl/SSH-based smoke tests against deployed services.

---

## Manual-Only Verifications

| Behavior | SC# | Why Manual | Test Instructions |
|----------|-----|------------|-------------------|
| Vault creds match server | SC-8 | Encrypted vault, requires ansible-vault | `ansible-vault view secrets.yml \| grep kitsu_admin` |
| Bot account login | SC-6 | Requires SSH to Sese-AI + curl inside container | SSH + `docker exec kitsu-zou curl -s http://localhost/api/auth/login -d '...'` |
| Project exists in Kitsu | SC-7 | Requires SSH to Sese-AI + Kitsu API | SSH + `docker exec kitsu-zou curl -s http://localhost/api/data/projects` |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
