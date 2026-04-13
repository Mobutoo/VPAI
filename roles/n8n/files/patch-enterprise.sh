#!/bin/sh
# patch-enterprise.sh — Patches n8n license checks to enable enterprise features
# Applied at Docker build time on the compiled JS output
# Approach: override LicenseState facade methods (single source of truth for feature checks)
#
# IMPORTANT: n8n 2.7.x compiled JS uses "method(param) {" (with space before brace)
# The sed patterns MUST match this exact format.
#
# CAVEAT: isLicensed() must NOT blindly return true — the feature "feat:showNonProdBanner"
# triggers a full-screen "not licensed for production" overlay that hides the sidebar.
# getValue() must return sensible values for string quotas like 'planName'.
set -e

N8N_ROOT="/usr/local/lib/node_modules/n8n"

echo "[patch-enterprise] Patching license checks..."

# --- Smart return values ---
# isLicensed: true for everything EXCEPT showNonProdBanner
LICENSED_BODY="if(feature==='feat:showNonProdBanner')return false;if(feature==='feat:apiDisabled')return false;return true;"
# getValue: 'Enterprise' for planName, -1 (unlimited) for everything else
GETVALUE_BODY="if(feature==='planName')return'Enterprise';return -1;"

# --- 1. Patch LicenseState facade (backend-common) ---
# All feature checks go through this class: isSharingLicensed(), getMaxTeamProjects(), etc.
LICENSE_STATE=$(find "$N8N_ROOT" -path "*/backend-common/dist/*" -name "license-state.js" 2>/dev/null | head -1)
if [ -n "$LICENSE_STATE" ]; then
  echo "[patch-enterprise] Patching $LICENSE_STATE"
  # Handles both "method(feature) {" and "method(feature){" patterns
  sed -i "s/isLicensed(feature) {/isLicensed(feature) {${LICENSED_BODY}/g" "$LICENSE_STATE"
  sed -i "s/isLicensed(feature){/isLicensed(feature){${LICENSED_BODY}/g" "$LICENSE_STATE"
  sed -i "s/getValue(feature) {/getValue(feature) {${GETVALUE_BODY}/g" "$LICENSE_STATE"
  sed -i "s/getValue(feature){/getValue(feature){${GETVALUE_BODY}/g" "$LICENSE_STATE"
  if grep -q "feat:showNonProdBanner" "$LICENSE_STATE"; then
    echo "[patch-enterprise] ✓ license-state.js patched successfully"
  else
    echo "[patch-enterprise] ✗ WARNING: patch may not have applied to license-state.js"
  fi
else
  echo "[patch-enterprise] WARN: license-state.js not found, trying alternative paths"
  LICENSE_STATE=$(find "$N8N_ROOT" -name "license-state.js" 2>/dev/null | head -1)
  if [ -n "$LICENSE_STATE" ]; then
    echo "[patch-enterprise] Found at $LICENSE_STATE"
    sed -i "s/isLicensed(feature) {/isLicensed(feature) {${LICENSED_BODY}/g" "$LICENSE_STATE"
    sed -i "s/isLicensed(feature){/isLicensed(feature){${LICENSED_BODY}/g" "$LICENSE_STATE"
    sed -i "s/getValue(feature) {/getValue(feature) {${GETVALUE_BODY}/g" "$LICENSE_STATE"
    sed -i "s/getValue(feature){/getValue(feature){${GETVALUE_BODY}/g" "$LICENSE_STATE"
  fi
fi

# --- 2. Patch License service (CLI dist) ---
# In n8n 2.7.x, license.js uses the SAME method names: isLicensed(feature), getValue(feature)
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
  if grep -q "feat:showNonProdBanner" "$LICENSE_SVC"; then
    echo "[patch-enterprise] ✓ license.js patched successfully"
  else
    echo "[patch-enterprise] ✗ WARNING: patch may not have applied to license.js"
  fi
fi

# --- 3. Patch frontend.service.js — hardcode showNonProdBanner: false ---
# Belt-and-suspenders: even if isLicensed was somehow not patched, force this to false
FRONTEND_SVC=$(find "$N8N_ROOT/dist" -name "frontend.service.js" 2>/dev/null | head -1)
if [ -n "$FRONTEND_SVC" ]; then
  echo "[patch-enterprise] Patching $FRONTEND_SVC (showNonProdBanner → false)"
  sed -i 's/showNonProdBanner: this\.license\.isLicensed([^)]*)/showNonProdBanner: false/g' "$FRONTEND_SVC"
  if grep -q "showNonProdBanner: false" "$FRONTEND_SVC"; then
    echo "[patch-enterprise] ✓ frontend.service.js patched successfully"
  else
    echo "[patch-enterprise] ✗ WARNING: showNonProdBanner patch may not have applied"
  fi
fi

# --- 4. Patch frontend router — neutralize banner push ---
# The router checks settingsStore.isEnterpriseFeatureEnabled.showNonProdBanner and pushes
# NON_PRODUCTION_LICENSE banner. Replace the condition with false directly in the bundle.
ROUTER_FILE=$(find "$N8N_ROOT" -name "router-*.js" -path "*/assets/*" 2>/dev/null | head -1)
if [ -n "$ROUTER_FILE" ]; then
  echo "[patch-enterprise] Patching $ROUTER_FILE (banner push → disabled)"
  sed -i 's/settingsStore\.isEnterpriseFeatureEnabled\.showNonProdBanner/false/g' "$ROUTER_FILE"
  if grep -q "if (false) bannersStore.pushBannerToStack" "$ROUTER_FILE"; then
    echo "[patch-enterprise] ✓ router banner push neutralized"
  else
    echo "[patch-enterprise] ✗ WARNING: router banner patch may not have applied"
  fi
fi

# --- 5. Suppress "not licensed for production" i18n text (editor-ui) ---
BANNER_FILE=$(find "$N8N_ROOT" -type f -name "*.js" -exec grep -l "not licensed for production" {} \; 2>/dev/null | head -1)
if [ -n "$BANNER_FILE" ]; then
  echo "[patch-enterprise] Suppressing production banner text in $BANNER_FILE"
  sed -i 's/not licensed for production/licensed for production/g' "$BANNER_FILE" 2>/dev/null || true
fi

# --- 6. Prevent license SDK phone-home ---
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

echo "[patch-enterprise] Done. Enterprise features unlocked."
