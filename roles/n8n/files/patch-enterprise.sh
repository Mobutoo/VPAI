#!/bin/sh
# patch-enterprise.sh — Patches n8n license checks to enable enterprise features
# Applied at Docker build time on the compiled JS output
# Approach: override LicenseState facade methods (single source of truth for feature checks)
#
# IMPORTANT: n8n 2.7.x compiled JS uses "method(param) {" (with space before brace)
# The sed patterns MUST match this exact format.
set -e

N8N_ROOT="/usr/local/lib/node_modules/n8n"

echo "[patch-enterprise] Patching license checks..."

# --- 1. Patch LicenseState facade (backend-common) ---
# All feature checks go through this class: isSharingLicensed(), getMaxTeamProjects(), etc.
LICENSE_STATE=$(find "$N8N_ROOT" -path "*/backend-common/dist/*" -name "license-state.js" 2>/dev/null | head -1)
if [ -n "$LICENSE_STATE" ]; then
  echo "[patch-enterprise] Patching $LICENSE_STATE"
  # isLicensed(feature) is the central check — make it return true
  # Handles both "isLicensed(feature) {" and "isLicensed(feature){" patterns
  sed -i 's/isLicensed(feature) {/isLicensed(feature) {return true;/g' "$LICENSE_STATE"
  sed -i 's/isLicensed(feature){/isLicensed(feature){return true;/g' "$LICENSE_STATE"
  # getValue(feature) is the central quota check — make it return -1 (unlimited)
  sed -i 's/getValue(feature) {/getValue(feature) {return -1;/g' "$LICENSE_STATE"
  sed -i 's/getValue(feature){/getValue(feature){return -1;/g' "$LICENSE_STATE"
  # Verify patches applied
  if grep -q "return true;" "$LICENSE_STATE"; then
    echo "[patch-enterprise] ✓ license-state.js patched successfully"
  else
    echo "[patch-enterprise] ✗ WARNING: patch may not have applied to license-state.js"
  fi
else
  echo "[patch-enterprise] WARN: license-state.js not found, trying alternative paths"
  # n8n may bundle differently in some versions — try the CLI dist
  LICENSE_STATE=$(find "$N8N_ROOT" -name "license-state.js" 2>/dev/null | head -1)
  if [ -n "$LICENSE_STATE" ]; then
    echo "[patch-enterprise] Found at $LICENSE_STATE"
    sed -i 's/isLicensed(feature) {/isLicensed(feature) {return true;/g' "$LICENSE_STATE"
    sed -i 's/isLicensed(feature){/isLicensed(feature){return true;/g' "$LICENSE_STATE"
    sed -i 's/getValue(feature) {/getValue(feature) {return -1;/g' "$LICENSE_STATE"
    sed -i 's/getValue(feature){/getValue(feature){return -1;/g' "$LICENSE_STATE"
  fi
fi

# --- 2. Patch License service (CLI dist) ---
# In n8n 2.7.x, license.js uses the SAME method names: isLicensed(feature), getValue(feature)
# NOT isFeatureEnabled/getFeatureValue (those are older patterns)
LICENSE_SVC=$(find "$N8N_ROOT" -path "*/cli/dist/*" -name "license.js" 2>/dev/null | head -1)
if [ -z "$LICENSE_SVC" ]; then
  LICENSE_SVC=$(find "$N8N_ROOT/dist" -name "license.js" 2>/dev/null | head -1)
fi
if [ -n "$LICENSE_SVC" ]; then
  echo "[patch-enterprise] Patching $LICENSE_SVC"
  # isLicensed(feature) — return true (both spacing patterns)
  sed -i 's/isLicensed(feature) {/isLicensed(feature) {return true;/g' "$LICENSE_SVC"
  sed -i 's/isLicensed(feature){/isLicensed(feature){return true;/g' "$LICENSE_SVC"
  # getValue(feature) — return -1 unlimited (both spacing patterns)
  sed -i 's/getValue(feature) {/getValue(feature) {return -1;/g' "$LICENSE_SVC"
  sed -i 's/getValue(feature){/getValue(feature){return -1;/g' "$LICENSE_SVC"
  if grep -q "return true;" "$LICENSE_SVC"; then
    echo "[patch-enterprise] ✓ license.js patched successfully"
  else
    echo "[patch-enterprise] ✗ WARNING: patch may not have applied to license.js"
  fi
fi

# --- 3. Patch frontend settings to show enterprise UI ---
SETTINGS_STORE=$(find "$N8N_ROOT" -path "*/editor-ui/*" -name "*.js" -exec grep -l "isEnterpriseFeatureEnabled" {} \; 2>/dev/null | head -1)
if [ -n "$SETTINGS_STORE" ]; then
  echo "[patch-enterprise] Patching frontend: $SETTINGS_STORE"
  # The frontend checks isEnterpriseFeatureEnabled — make it return true (both spacing patterns)
  sed -i 's/isEnterpriseFeatureEnabled(feature) {/isEnterpriseFeatureEnabled(feature) {return true;/g' "$SETTINGS_STORE" 2>/dev/null || true
  sed -i 's/isEnterpriseFeatureEnabled(feature){/isEnterpriseFeatureEnabled(feature){return true;/g' "$SETTINGS_STORE" 2>/dev/null || true
fi

# --- 4. Suppress "not licensed for production" banner ---
NON_PROD_BANNER=$(find "$N8N_ROOT" -path "*/editor-ui/*" -name "*.js" -exec grep -l "not licensed for production" {} \; 2>/dev/null | head -1)
if [ -n "$NON_PROD_BANNER" ]; then
  echo "[patch-enterprise] Suppressing production banner"
  sed -i 's/not licensed for production/licensed/g' "$NON_PROD_BANNER" 2>/dev/null || true
fi

echo "[patch-enterprise] Done. Enterprise features unlocked."
