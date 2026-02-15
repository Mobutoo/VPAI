#!/bin/bash
# Smoke tests for CI/CD pipeline
# Usage: ./scripts/smoke-test.sh [--ci] <base_url> [admin_url]
#   --ci    : CI mode — only test public endpoints (skip VPN-only admin UIs)
# Exit code: 0 = all tests passed, 1 = at least one test failed

set -euo pipefail

# Parse --ci flag
CI_MODE=false
if [ "${1:-}" = "--ci" ]; then
  CI_MODE=true
  shift
fi

BASE_URL="${1:?Usage: $0 [--ci] <base_url> [admin_url]}"
ADMIN_URL="${2:-${BASE_URL/preprod/admin.preprod}}"
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
echo "  Target: ${BASE_URL}"
if [ "$CI_MODE" = "true" ]; then
  echo "  Mode: CI (public endpoints only)"
else
  echo "  Mode: Full (public + admin endpoints)"
fi
echo "============================================"
echo ""

# --- Caddy / TLS ---
echo "--- HTTPS & TLS ---"
check "Caddy HTTPS health" "${BASE_URL}/health"

# TLS certificate check
DOMAIN=$(echo "${BASE_URL}" | sed 's|https://||; s|/.*||')
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
DNS_RESULT=$(dig +short "${DOMAIN}" 2>/dev/null | head -1) || DNS_RESULT=""
if [ -n "${DNS_RESULT}" ]; then
  echo "PASS  DNS resolution (${DOMAIN} -> ${DNS_RESULT})"
else
  echo "FAIL  DNS resolution (${DOMAIN} not resolving)"
  FAILURES=$((FAILURES + 1))
fi

echo ""

# --- Public Application Endpoints ---
echo "--- Public Endpoints ---"
check "LiteLLM health" "${BASE_URL}/litellm/health"

echo ""

# --- LiteLLM API ---
echo "--- LiteLLM API ---"
MODELS=$(curl -s -H "Authorization: Bearer ${LITELLM_KEY:-test}" \
  "${BASE_URL}/litellm/v1/models" --max-time "${TIMEOUT}" 2>/dev/null | \
  grep -o '"id"' | wc -l) || MODELS=0
if [ "${MODELS}" -gt 0 ]; then
  echo "PASS  LiteLLM models (${MODELS} models available)"
else
  echo "FAIL  LiteLLM models (no models found)"
  FAILURES=$((FAILURES + 1))
fi

echo ""

# --- Admin Endpoints (VPN-only, skipped in CI mode) ---
if [ "$CI_MODE" = "true" ]; then
  echo "--- Admin Endpoints (SKIPPED — VPN-only, not reachable from CI) ---"
  echo "SKIP  n8n healthz (VPN-only)"
  echo "SKIP  Grafana health (VPN-only)"
  echo "SKIP  OpenClaw health (VPN-only)"
else
  echo "--- Admin Endpoints (VPN-only) ---"
  check "n8n healthz" "${ADMIN_URL}/n8n/healthz"
  check "Grafana health" "${ADMIN_URL}/grafana/api/health"
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
