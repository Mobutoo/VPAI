#!/bin/sh
# patch-enterprise.sh — Patches n8n license checks to enable enterprise features
# Applied at RUNTIME by the Sidecar init-container (roles/n8n/files/n8n-enterprise-init.sh)
# on a disposable copy of the official image's node_modules/n8n tree — N8N_ROOT points at
# that copy, NEVER at the image path directly. See docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md.
# Approach: override LicenseState facade methods (single source of truth for feature checks)
#
# IMPORTANT: n8n compiled JS uses "method(param) {" (with space before brace)
# The sed patterns MUST match this exact format.
#
# CAVEAT: isLicensed() must NOT blindly return true — the feature "feat:showNonProdBanner"
# triggers a full-screen "not licensed for production" overlay that hides the sidebar.
# getValue() must return sensible values for string quotas like 'planName'.
#
# FAIL LOUD: steps 1/2/3 are CRITICAL. If any of them fails to verify its own patch, the
# script exits 1 (CRIT_FAIL) so the init-container never publishes a broken tree and n8n
# never boots on it (fail-loud, visible in `docker logs <project>_n8n_init`).
# Steps 4/5 stay warning-only (non-fatal, cosmetic): step 4 never matches the minified
# router bundle and step 3 already neutralizes the banner functionally (research R2 §3).
set -e

N8N_ROOT="${N8N_ROOT:-/usr/local/lib/node_modules/n8n}"
CRIT_FAIL=0

echo "[patch-enterprise] Patching license checks (N8N_ROOT=$N8N_ROOT)..."

# --- Smart return values ---
# isLicensed: true for everything EXCEPT showNonProdBanner
LICENSED_BODY="if(feature==='feat:showNonProdBanner')return false;if(feature==='feat:apiDisabled')return false;return true;"
# getValue: 'Enterprise' for planName, -1 (unlimited) for everything else
GETVALUE_BODY="if(feature==='planName')return'Enterprise';return -1;"

# --- 1. Patch LicenseState facade (backend-common) — CRITICAL ---
# All feature checks go through this class: isSharingLicensed(), getMaxTeamProjects(), etc.
LICENSE_STATE=$(find "$N8N_ROOT" -path "*/backend-common/dist/*" -name "license-state.js" 2>/dev/null | head -1)
if [ -z "$LICENSE_STATE" ]; then
  echo "[patch-enterprise] WARN: license-state.js not found via primary path, trying alternative paths"
  LICENSE_STATE=$(find "$N8N_ROOT" -name "license-state.js" 2>/dev/null | head -1)
fi
if [ -n "$LICENSE_STATE" ]; then
  echo "[patch-enterprise] Patching $LICENSE_STATE"
  # Handles both "method(feature) {" and "method(feature){" patterns
  sed -i "s/isLicensed(feature) {/isLicensed(feature) {${LICENSED_BODY}/g" "$LICENSE_STATE"
  sed -i "s/isLicensed(feature){/isLicensed(feature){${LICENSED_BODY}/g" "$LICENSE_STATE"
  sed -i "s/getValue(feature) {/getValue(feature) {${GETVALUE_BODY}/g" "$LICENSE_STATE"
  sed -i "s/getValue(feature){/getValue(feature){${GETVALUE_BODY}/g" "$LICENSE_STATE"
fi
if [ -n "$LICENSE_STATE" ] && grep -q "feat:showNonProdBanner" "$LICENSE_STATE"; then
  echo "[patch-enterprise] ✓ license-state.js patched successfully"
else
  echo "[patch-enterprise] ✗ CRITICAL: license-state.js patch verification failed (not found or grep mismatch)" >&2
  CRIT_FAIL=1
fi

# --- 2. Patch License service (CLI dist) — CRITICAL ---
# license.js uses the SAME method names: isLicensed(feature), getValue(feature)
LICENSE_SVC=$(find "$N8N_ROOT" -path "*/cli/dist/*" -name "license.js" 2>/dev/null | head -1)
if [ -z "$LICENSE_SVC" ]; then
  LICENSE_SVC=$(find "$N8N_ROOT/dist" -name "license.js" 2>/dev/null | head -1)
fi
if [ -n "$LICENSE_SVC" ]; then
  echo "[patch-enterprise] Patching $LICENSE_SVC"
  sed -i "s/isLicensed(feature) {/isLicensed(feature) {${LICENSED_BODY}/g" "$LICENSE_SVC"
  sed -i "s/isLicensed(feature){/isLicensed(feature){${LICENSED_BODY}/g" "$LICENSE_SVC"
  sed -i "s/getValue(feature) {/getValue(feature) {${GETVALUE_BODY}/g" "$LICENSE_SVC"
  sed -i "s/getValue(feature){/getValue(feature){${GETVALUE_BODY}/g" "$LICENSE_SVC"
fi
if [ -n "$LICENSE_SVC" ] && grep -q "feat:showNonProdBanner" "$LICENSE_SVC"; then
  echo "[patch-enterprise] ✓ license.js patched successfully"
else
  echo "[patch-enterprise] ✗ CRITICAL: license.js patch verification failed (not found or grep mismatch)" >&2
  CRIT_FAIL=1
fi

# --- 3. Patch frontend.service.js — hardcode showNonProdBanner: false — CRITICAL ---
# Belt-and-suspenders: even if isLicensed was somehow not patched, force this to false
FRONTEND_SVC=$(find "$N8N_ROOT/dist" -name "frontend.service.js" 2>/dev/null | head -1)
if [ -n "$FRONTEND_SVC" ]; then
  echo "[patch-enterprise] Patching $FRONTEND_SVC (showNonProdBanner → false)"
  sed -i 's/showNonProdBanner: this\.license\.isLicensed([^)]*)/showNonProdBanner: false/g' "$FRONTEND_SVC"
fi
if [ -n "$FRONTEND_SVC" ] && grep -q "showNonProdBanner: false" "$FRONTEND_SVC"; then
  echo "[patch-enterprise] ✓ frontend.service.js patched successfully"
else
  echo "[patch-enterprise] ✗ CRITICAL: frontend.service.js patch verification failed (not found or grep mismatch)" >&2
  CRIT_FAIL=1
fi

# --- 4. Patch frontend router — neutralize banner push (non-fatal, cosmetic) ---
# The router checks settingsStore.isEnterpriseFeatureEnabled.showNonProdBanner and pushes
# NON_PRODUCTION_LICENSE banner. Replace the condition with false directly in the bundle.
# Loop over ALL router-*.js bundles (router-dp_* AND router-legacy-*) — a single `head -1`
# is non-deterministic across the two bundle families (research R2 §4.2).
ROUTER_MATCHED=0
for ROUTER_FILE in $(find "$N8N_ROOT" -name "router-*.js" -path "*/assets/*" 2>/dev/null); do
  echo "[patch-enterprise] Patching $ROUTER_FILE (banner push → disabled)"
  sed -i 's/settingsStore\.isEnterpriseFeatureEnabled\.showNonProdBanner/false/g' "$ROUTER_FILE"
  ROUTER_MATCHED=1
done
if [ "$ROUTER_MATCHED" -eq 1 ]; then
  echo "[patch-enterprise] router bundle(s) patched (non-fatal check only — see R2 §3)"
else
  echo "[patch-enterprise] WARNING: no router-*.js bundle found (non-fatal, cosmetic — absorbed by step 3)"
fi

# --- 5. Suppress "not licensed for production" i18n text (editor-ui) — non-fatal ---
BANNER_FILE=$(find "$N8N_ROOT" -type f -name "*.js" -exec grep -l "not licensed for production" {} \; 2>/dev/null | head -1)
if [ -n "$BANNER_FILE" ]; then
  echo "[patch-enterprise] Suppressing production banner text in $BANNER_FILE"
  sed -i 's/not licensed for production/licensed for production/g' "$BANNER_FILE" 2>/dev/null || true
fi

# --- 6. Prevent license SDK phone-home (non-fatal — best-effort, not part of R2 fail-loud scope) ---
# Patch LicenseManager initialization to force offlineMode and disable auto-renewal.
# This prevents n8n from contacting the official license server (license.n8n.io).
if [ -n "$LICENSE_SVC" ]; then
  echo "[patch-enterprise] Patching license init (offline mode + no auto-renew)"
  # Force offlineMode = true regardless of instance type
  sed -i 's/const offlineMode = !isMainInstance;/const offlineMode = true;/g' "$LICENSE_SVC"
  # Force autoRenew to false
  sed -i 's/autoRenewEnabled: shouldRenew/autoRenewEnabled: false/g' "$LICENSE_SVC"
  sed -i 's/renewOnInit: shouldRenew/renewOnInit: false/g' "$LICENSE_SVC"
  if grep -q "offlineMode = true" "$LICENSE_SVC"; then
    echo "[patch-enterprise] ✓ license phone-home disabled (offline mode)"
  else
    echo "[patch-enterprise] ✗ WARNING: offline mode patch may not have applied"
  fi
fi

if [ "$CRIT_FAIL" -ne 0 ]; then
  echo "[patch-enterprise] ✗ FATAL: une étape critique (license-state/license/frontend.service) n'a pas matché — arbre NON déployable" >&2
  exit 1
fi
echo "[patch-enterprise] Done. Enterprise features unlocked."
