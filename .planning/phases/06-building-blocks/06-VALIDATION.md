---
phase: 6
slug: building-blocks
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-17
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Ansible check mode + SSH smoke tests (skill), Remotion `npx remotion render` (compositions) |
| **Config file** | `ansible.cfg` (Ansible), `remotion.config.ts` (Remotion) |
| **Quick run command** | `ansible-playbook playbooks/site.yml --check --diff --tags openclaw` |
| **Full suite command** | `make lint && ansible-playbook playbooks/site.yml --check --diff --tags openclaw,remotion` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `make lint`
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green + manual Telegram command test
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | RMTN-01..05 | type-check+lint | `cd roles/remotion/files && npx tsc --noEmit` | ✅ | ⬜ pending |
| 06-01-02 | 01 | 1 | RMTN-01..05 | type-check+lint | `npx tsc --noEmit && make lint` | ✅ | ⬜ pending |
| 06-02-01 | 02 | 1 | SKILL-01..09 | lint+check | `make lint` | ✅ | ⬜ pending |
| 06-02-02 | 02 | 1 | SKILL-01,02 | lint+check | `make lint` | ✅ | ⬜ pending |
| 06-03-01 | 03 | 2 | RMTN-01..05, SKILL-01,02 | deploy+smoke | `curl localhost:3200/health + ssh skill check` | ✅ | ⬜ pending |
| 06-03-02 | 03 | 2 | ALL | manual | Telegram + Remotion UI verification | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Ansible lint config already exists (`ansible.cfg`, `.yamllint.yml`, `.ansible-lint`)
- [ ] Remotion TypeScript check requires existing `tsconfig.json` in Remotion project

*Existing infrastructure covers Ansible-side requirements. Remotion test setup is part of existing role.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `/content reel-motion-text "test"` creates content | SKILL-03 | Requires live OpenClaw + Telegram | Send command in topic 7, verify NocoDB row created |
| `/ok` advances step | SKILL-04 | Requires live pipeline state | Create content, send `/ok`, verify step increment |
| `/adjust` modifies step | SKILL-05 | Requires live pipeline | Send `/adjust "change tone"`, verify new version |
| `/back` with impact analysis | SKILL-06 | Requires live pipeline | Send `/back 2`, verify impact shown |
| `/preview` shows status | SKILL-07 | Requires live pipeline | Send `/preview`, verify formatted response |
| `/impact` shows invalidation | SKILL-08 | Requires live pipeline | Send `/impact`, verify matrix display |
| Gate commands advance gates | SKILL-09 | Requires live pipeline + completed steps | Complete steps, send `/lock-preprod`, verify gate locked |
| Composition renders 9:16 video | RMTN-01..04 | Requires Waza + Remotion server | `curl localhost:3200/render` with test props, verify output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
