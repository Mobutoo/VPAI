#!/bin/bash
# Smoke tests for CI/CD pipeline
# Usage: ./scripts/smoke-test.sh <base_url> [admin_url]
# Exit code: 0 = all tests passed, 1 = at least one test failed

set -euo pipefail

BASE_URL="${1:?Usage: $0 <base_url> [admin_url]}"
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

# --- Application Endpoints ---
echo "--- Application Endpoints ---"
check "n8n healthz" "${ADMIN_URL}/n8n/healthz"
check "Grafana health" "${ADMIN_URL}/grafana/api/health"
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
