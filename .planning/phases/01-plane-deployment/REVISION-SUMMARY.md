# Phase 01 Plan Revision Summary

**Date**: 2026-02-28
**Mode**: Targeted revision based on checker feedback
**Result**: All blocker issues resolved, warning issues addressed

## Changes Made

### Structure Changes

**Plan 01-01 → Split into 01-01a + 01-01b**
- **Rationale**: Exceeded 5-task blocker threshold (6 tasks)
- **01-01a**: Role + Docker Compose (4 tasks) - Core infrastructure
- **01-01b**: Caddy + Playbook (2 tasks) - Reverse proxy integration
- **Total reduction**: 6 tasks → 4+2 tasks (within threshold)

**Plan 01-02 → Split into 01-02a + 01-02b**
- **Rationale**: Exceeded 5-task blocker threshold (7 tasks)
- **01-02a**: PostgreSQL + Provisioning Role (5 tasks) - Infrastructure and automation
- **01-02b**: Vault + Manual Guide + Checkpoint (3 tasks) - Manual steps with validation
- **Total reduction**: 7 tasks → 5+3 tasks (within threshold)
- **Added**: Manual checkpoint task to ensure AUTH-03 requirement met

**Plan 01-03 → Merged T4+T6**
- **Rationale**: Exceeded 5-task threshold (6 tasks), T6 duplicated scope with T4
- **Before**: 6 tasks (T1-T6)
- **After**: 5 tasks (T1-T5, with T4 incorporating T6 Loki validation)
- **Total reduction**: 6 tasks → 5 tasks (at threshold)

### Blocker Issue Resolutions

#### Issue #1: INFRA-04 Public Webhook Exception Missing
**Plan**: 01-01 (now 01-01b)
**Severity**: blocker
**Fix**: Added public /webhooks/plane handler in Caddy configuration BEFORE VPN-only block
```diff
+ # CRITICAL: Public webhook endpoint for n8n integration (INFRA-04)
+ # Must be BEFORE VPN-only block to avoid 403 on webhook delivery
+ handle /webhooks/plane {
+     reverse_proxy n8n:5678
+ }
```
**Location**: 01-01b-PLAN.md Task T1
**Impact**: n8n webhook delivery will now work (public access) while UI remains VPN-only

#### Issue #2: Plan 01-01 Task Count Exceeds Threshold
**Plan**: 01-01
**Severity**: blocker
**Fix**: Split into 01-01a (4 tasks) and 01-01b (2 tasks)
**Rationale**: Kept role creation and Docker integration together in 01-01a (cohesive unit), separated Caddy config into 01-01b (distinct concern)

#### Issue #3: Plan 01-02 Task Count Exceeds Threshold
**Plan**: 01-02
**Severity**: blocker
**Fix**: Split into 01-02a (5 tasks) and 01-02b (3 tasks)
**Rationale**: 01-02a contains automation (PostgreSQL + provisioning script), 01-02b contains manual steps + checkpoint

#### Issue #4: AUTH-03 Agent Tokens Can Remain Empty
**Plan**: 01-02 (now 01-02b)
**Severity**: blocker
**Fix**: Added checkpoint:manual task (T3) requiring operator confirmation that tokens are populated
**Added validation**:
- Operator must confirm provision script executed
- Operator must verify agent tokens are non-empty using grep commands
- Smoke tests (Plan 01-03) now assert tokens are populated before testing auth
**Location**: 01-02b-PLAN.md Task T3 + 01-03-PLAN.md Task T4 (assertion)
**Impact**: Phase cannot complete until tokens are validated, preventing smoke test failures

### Warning Issue Resolutions

#### Issue #5: INFRA-01 Egress Network Missing
**Plan**: 01-01 (now 01-01a)
**Severity**: warning
**Fix**: Added egress network to plane-api and plane-worker containers
```diff
Service: plane-api
- networks: [backend] (internal only, accessed via plane-web proxy)
+ networks: [backend, egress] (egress for webhook delivery per INFRA-01, backend for internal access)

Service: plane-worker
- networks: [backend] (access to Redis for Celery, PostgreSQL for tasks)
+ networks: [backend, egress] (egress for external API calls and webhook delivery per INFRA-01)
```
**Location**: 01-01a-PLAN.md Task T4
**Impact**: Webhook delivery and external API calls will now work

#### Issue #6: PROV-04 Project ID Not Captured
**Plan**: 01-02 (now 01-02a)
**Severity**: warning
**Fix**: Added project_id capture in provision script with explicit instructions
```diff
+ # CRITICAL (PROV-04): When creating Onboarding project, capture the project_id from the API response:
+ PROJECT_ID=$(curl ... | jq -r '.id')
+ # Then pass $PROJECT_ID to create_custom_field function calls:
+ create_custom_field "agent_id" "text" "$PROJECT_ID" "$TYPE_ID"
```
**Location**: 01-02a-PLAN.md Task T3
**Impact**: Custom field creation will use correct project_id, preventing API 404 errors

#### Issue #7: Must-Haves Are Implementation-Focused
**Plan**: 01-01 (now 01-01a, 01-01b, 01-03)
**Severity**: warning
**Fix**: Reframed must-haves to user-observable outcomes
**Examples**:
- Before: "Ansible role deployable (lint passes)"
- After: "UI accessible from VPN (HTTP 200), all 3 container healthchecks green"
- Before: "VPN-only configuration complete"
- After: "Public access blocked (403 without VPN), webhook endpoint public (200)"
**Location**: All plan files (Must-Haves section)
**Impact**: Verification criteria now match user expectations, easier to validate success

#### Issue #8: Task Completeness - Missing XML Structure
**Plan**: 01-02 (now 01-02a, 01-02b)
**Severity**: warning
**Status**: DEFERRED
**Rationale**: VPAI plan format uses prose within <task> tags, not structured <files>/<action>/<verify>/<done> sub-elements. Checker expected a different schema. Current format is consistent with existing VPAI plans and executor expectations.
**Impact**: None - executors understand current format

#### Issue #9: Plan 01-03 Task Count + Duplication
**Plan**: 01-03
**Severity**: warning
**Fix**: Merged T6 (Loki validation) into T4 (smoke tests)
**Rationale**: Both tasks modify smoke-tests.yml, Loki validation is part of smoke testing
**Result**: 6 tasks → 5 tasks (at threshold)
**Location**: 01-03-PLAN.md Task T4 (now includes Loki checks from old T6)

## Dependency Graph (Updated)

```
Wave 1:
  01-01a (Role + Docker)
  ├─> 01-01b (Caddy + Playbook)

Wave 2:
  01-01a + 01-01b
  ├─> 01-02a (PostgreSQL + Provision Role)
      ├─> 01-02b (Vault + Manual Checkpoint) [MANUAL CHECKPOINT]

Wave 3:
  01-01a + 01-01b + 01-02a + 01-02b
  ├─> 01-03 (Monitoring + Backup + Smoke Tests)
```

## Task Count Summary

| Plan | Before | After | Status |
|------|--------|-------|--------|
| 01-01 | 6 tasks | SPLIT | - |
| 01-01a | - | 4 tasks | ✓ Under threshold |
| 01-01b | - | 2 tasks | ✓ Under threshold |
| 01-02 | 7 tasks | SPLIT | - |
| 01-02a | - | 5 tasks | ✓ At threshold |
| 01-02b | - | 3 tasks (1 checkpoint) | ✓ Under threshold |
| 01-03 | 6 tasks | 5 tasks | ✓ At threshold |
| **Total** | **19 tasks** | **19 tasks** | Scope preserved |

## Files Modified Summary

**Added files**:
- `.planning/phases/01-plane-deployment/01-01a-PLAN.md` (new)
- `.planning/phases/01-plane-deployment/01-01b-PLAN.md` (new)
- `.planning/phases/01-plane-deployment/01-02a-PLAN.md` (new)
- `.planning/phases/01-plane-deployment/01-02b-PLAN.md` (new)

**Updated files**:
- `.planning/phases/01-plane-deployment/01-03-PLAN.md` (merged T4+T6)

**Removed files**:
- `.planning/phases/01-plane-deployment/01-01-PLAN.md` (replaced by 01-01a + 01-01b)
- `.planning/phases/01-plane-deployment/01-02-PLAN.md` (replaced by 01-02a + 01-02b)

## Key Technical Changes

### 1. Caddy Handle Ordering (CRITICAL)
- Public webhook endpoint MUST appear BEFORE VPN-only matcher
- Order matters: Caddy processes handles sequentially
- Impact: Prevents 403 on n8n webhook delivery

### 2. Docker Network Configuration
- plane-api: [backend, egress] (was [backend])
- plane-worker: [backend, egress] (was [backend])
- Impact: Enables webhook delivery and external API calls

### 3. Project ID Capture in Provision Script
- Added: `PROJECT_ID=$(curl ... | jq -r '.id')`
- Usage: `create_custom_field "field_name" "type" "$PROJECT_ID" "$TYPE_ID"`
- Impact: Custom fields will create correctly (no 404 errors)

### 4. Manual Checkpoint for Token Validation
- Plan 01-02b Task T3: Blocks until operator confirms tokens populated
- Verification commands provided for programmatic validation
- Smoke tests (01-03) assert tokens non-empty before auth testing
- Impact: Guarantees AUTH-03 requirement met before phase completion

### 5. Must-Haves Reframed
- Focus: User-observable outcomes (UI accessible, containers green, auth working)
- Examples: "HTTP 200 from VPN", "3/3 healthchecks green", "agent auth validated"
- Impact: Clear success criteria, easier to verify deployment

## Checker Issue Status

| Issue | Severity | Plan | Status | Resolution |
|-------|----------|------|--------|------------|
| #1 Webhook exception missing | blocker | 01-01 | ✅ FIXED | Added /webhooks/plane handle in 01-01b T1 |
| #2 Task count (6 tasks) | blocker | 01-01 | ✅ FIXED | Split into 01-01a (4) + 01-01b (2) |
| #3 Task count (7 tasks) | blocker | 01-02 | ✅ FIXED | Split into 01-02a (5) + 01-02b (3) |
| #4 Agent tokens empty | blocker | 01-02 | ✅ FIXED | Added checkpoint in 01-02b T3 + assertion in 01-03 T4 |
| #5 Egress network missing | warning | 01-01 | ✅ FIXED | Added egress to plane-api/worker in 01-01a T4 |
| #6 Project ID not captured | warning | 01-02 | ✅ FIXED | Added jq capture in 01-02a T3 |
| #7 Implementation-focused must-haves | warning | 01-01 | ✅ FIXED | Reframed all must-haves to user-observable outcomes |
| #8 Task XML structure | warning | 01-02 | ⚠️ DEFERRED | Current format matches VPAI conventions |
| #9 Task count + duplication | warning | 01-03 | ✅ FIXED | Merged T6 into T4, reduced to 5 tasks |

**Blocker resolution**: 4/4 (100%)
**Warning resolution**: 4/5 (80%, 1 deferred as format convention)

## Validation Checklist

Before execution, verify:
- [ ] All plan files reference correct dependencies (01-01a → 01-01b → 01-02a → 01-02b → 01-03)
- [ ] Caddy webhook handle appears BEFORE VPN matcher in 01-01b T1
- [ ] Egress network added to plane-api and plane-worker in 01-01a T4
- [ ] Project ID capture logic present in 01-02a T3 provision script
- [ ] Manual checkpoint task exists in 01-02b T3 with verification commands
- [ ] Agent token assertion exists in 01-03 T4 smoke tests
- [ ] Must-haves use user-observable language in all plans
- [ ] Task counts: 4, 2, 5, 3, 5 (all at or under threshold)

## Next Steps

1. **Executor**: Review updated plans for implementation readiness
2. **Operator**: Prepare for manual checkpoint in 01-02b (admin token creation)
3. **Verification**: Run smoke tests after phase completion to validate all requirements
4. **Documentation**: Ensure GUIDE-PLANE-PROVISIONING.md is accessible to operators

## Notes

- Total scope preserved: 19 tasks before and after revision
- All blocker issues resolved with minimal disruption
- Manual checkpoint ensures AUTH-03 compliance without automation gaps
- User-observable must-haves improve verification clarity
- Caddy handle ordering documented as CRITICAL (common pitfall)
