#!/bin/bash
# Smoke tests for CI/CD pipeline
# Usage: ./scripts/smoke-test.sh [--ci] <domain>
#   --ci    : CI mode — only test public endpoints (skip VPN-only admin UIs)
# Exit code: 0 = all tests passed, 1 = at least one test failed

set -euo pipefail

# Parse --ci flag
CI_MODE=false
if [ "${1:-}" = "--ci" ]; then
  CI_MODE=true
  shift
fi

DOMAIN="${1:?Usage: $0 [--ci] <domain>}"
DOMAIN="${DOMAIN#https://}"   # Strip protocol if provided
DOMAIN="${DOMAIN%%/*}"        # Strip trailing path if any
TIMEOUT=10
FAILURES=0

check() {
  local name="$1" url="$2" expected="${3:-200}"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time "${TIMEOUT}" "$url" 2>/dev/null) || status="000"
  if [ "$status" = "$expected" ]; then
    echo "PASS  $name (HTTP $status)"
  else
    echo "FAIL  $name (HTTP $status, expected $expected)"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "============================================"
echo "  Smoke Tests — CI/CD"
echo "  $(date)"
echo "  Domain: ${DOMAIN}"
if [ "$CI_MODE" = "true" ]; then
  echo "  Mode: CI (public endpoints only)"
else
  echo "  Mode: Full (public + admin endpoints)"
fi
echo "============================================"
echo ""

# --- Caddy / TLS ---
echo "--- HTTPS & TLS ---"
check "Caddy HTTPS health" "https://${DOMAIN}/health"

# TLS certificate check
TLS_EXPIRY=$(echo | openssl s_client -servername "${DOMAIN}" -connect "${DOMAIN}:443" 2>/dev/null | \
  openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2) || TLS_EXPIRY=""
if [ -n "${TLS_EXPIRY}" ]; then
  EXPIRY_EPOCH=$(date -d "${TLS_EXPIRY}" +%s 2>/dev/null) || EXPIRY_EPOCH=0
  NOW_EPOCH=$(date +%s)
  DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
  if [ "${DAYS_LEFT}" -gt 7 ]; then
    echo "PASS  TLS certificate (expires in ${DAYS_LEFT} days)"
  else
    echo "FAIL  TLS certificate (expires in ${DAYS_LEFT} days)"
    FAILURES=$((FAILURES + 1))
  fi
else
  echo "WARN  TLS certificate (could not check — may not be available in CI)"
fi

# DNS check
DNS_RESULT=$(getent hosts "${DOMAIN}" 2>/dev/null | awk '{print $1}' | head -1) || DNS_RESULT=""
if [ -n "${DNS_RESULT}" ]; then
  echo "PASS  DNS resolution (${DOMAIN} -> ${DNS_RESULT})"
else
  echo "FAIL  DNS resolution (${DOMAIN} not resolving)"
  FAILURES=$((FAILURES + 1))
fi

echo ""

# --- VPN-gated endpoints ---
if [ "$CI_MODE" = "true" ]; then
  echo "--- VPN-gated Endpoints (SKIPPED — not reachable from CI runner) ---"
  echo "SKIP  n8n (VPN-only)"
  echo "SKIP  LiteLLM (VPN-only)"
  echo "SKIP  Grafana (VPN-only)"
  echo "SKIP  Qdrant (VPN-only)"
  echo "SKIP  OpenClaw (VPN-only)"
  echo "SKIP  NocoDB (VPN-only)"
  echo "SKIP  Palais (VPN-only)"
  echo "SKIP  Plane (VPN-only)"
else
  echo "--- Admin Endpoints (VPN-only) ---"
  check "n8n healthz"     "https://n8n.${DOMAIN}/healthz"
  check "LiteLLM health"  "https://llm.${DOMAIN}/health"
  check "Grafana health"  "https://tala.${DOMAIN}/api/health"
  check "Qdrant healthz"  "https://qdrant.${DOMAIN}/healthz"
  check "OpenClaw health" "https://oc.${DOMAIN}/health"
  check "NocoDB API"      "https://nocodb.${DOMAIN}/api/v1/db/meta/projects" "401"
  check "Palais health"   "https://palais.${DOMAIN}/health"
  check "Plane API"       "https://plane.${DOMAIN}/api/"
fi

echo ""

# --- LiteLLM API (public check with auth) ---
echo "--- LiteLLM API ---"
MODELS=$(curl -s -H "Authorization: Bearer ${LITELLM_KEY:-test}" \
  "https://llm.${DOMAIN}/v1/models" --max-time "${TIMEOUT}" 2>/dev/null | \
  grep -o '"id"' | wc -l) || MODELS=0
if [ "$CI_MODE" = "true" ]; then
  echo "SKIP  LiteLLM models (VPN-only, not reachable from CI)"
elif [ "${MODELS}" -gt 0 ]; then
  echo "PASS  LiteLLM models (${MODELS} models available)"
else
  echo "FAIL  LiteLLM models (no models found)"
  FAILURES=$((FAILURES + 1))
fi

echo ""

# --- Results ---
echo "============================================"
if [ "${FAILURES}" -eq 0 ]; then
  echo "  ALL TESTS PASSED"
  echo "============================================"
  exit 0
else
  echo "  ${FAILURES} TEST(S) FAILED"
  echo "============================================"
  exit 1
fi
