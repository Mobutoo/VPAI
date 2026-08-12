#!/usr/bin/env bash
set -euo pipefail

# test-extra-body-guard.sh — preuve reproductible post-deploy du fix
# finding CRITIQUE (c), gate technique Optimus B4 2026-08-12
# (docs/ops/gates-journal.md ligne "2026-08-12 après-midi").
#
# Rejoue les DEUX vecteurs de contournement du pin fournisseur/ZDR contre
# le proxy LiteLLM et échoue (exit != 0) si le fournisseur attesté par la
# réponse diffère du pin serveur (litellm_params.extra_body.provider.order
# du modèle testé dans litellm_config.yaml.j2) :
#   (A) top-level  "provider": {...}          — déjà neutralisé par
#       drop_params:true, testé ici en défense-en-profondeur.
#   (B) "extra_body": {"provider": {...}}     — le vecteur CRITIQUE non
#       neutralisé avant le callback guard_extra_body.py (roles/litellm/
#       files/guard_extra_body.py, litellm_settings.callbacks).
#
# Usage:
#   LITELLM_MASTER_KEY=... ./test-extra-body-guard.sh \
#       [-b https://llm.ewutelo.cloud] [-m claude-opus] [-p google-vertex] \
#       [-a openai]
#
#   -b  base URL du proxy (défaut: https://llm.ewutelo.cloud, VPN-only)
#   -m  alias/model_name pinné à tester (défaut: claude-opus)
#   -p  provider attendu (pin serveur — substring insensible à la casse,
#       défaut: google-vertex)
#   -a  provider ATTAQUANT injecté par le client dans les 2 vecteurs
#       (doit être manifestement différent du pin — défaut: openai)
#
# Sortie : 0 = les 2 vecteurs échouent à contourner le pin (PASS guard).
#          1 = au moins un vecteur a réussi à contourner le pin OU
#              l'attestation fournisseur est ABSENTE de la réponse (une
#              attestation manquante n'est PAS un succès du garde-fou —
#              c'est un échec de preuve, traité comme FAIL, cf. revue).
#
# Ne journalise/affiche JAMAIS LITELLM_MASTER_KEY. Nécessite: curl, jq.

: "${LITELLM_MASTER_KEY:?exporter LITELLM_MASTER_KEY avant execution (vault VPAI)}"

BASE_URL="https://llm.ewutelo.cloud"
MODEL="claude-opus"
EXPECTED_PROVIDER="google-vertex"
ATTACKER_PROVIDER="openai"

while getopts "b:m:p:a:h" opt; do
  case "${opt}" in
    b) BASE_URL="${OPTARG}" ;;
    m) MODEL="${OPTARG}" ;;
    p) EXPECTED_PROVIDER="${OPTARG}" ;;
    a) ATTACKER_PROVIDER="${OPTARG}" ;;
    h)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Usage invalide, voir -h" >&2
      exit 2
      ;;
  esac
done

command -v curl >/dev/null || { echo "curl requis" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq requis" >&2; exit 2; }

# Extrait l'attestation fournisseur d'une réponse chat/completions. Aucun
# champ "provider" standard OpenAI n'existe : on tente les emplacements
# documentés/observés côté LiteLLM+OpenRouter (réponse JSON top-level
# "provider", puis les hidden params LiteLLM exposées par certaines
# versions). Retourne chaîne vide si rien trouvé — traité comme échec de
# preuve par l'appelant, PAS comme un pass silencieux.
extract_provider_attestation() {
  local body="$1"
  local val
  val="$(jq -r '.provider // ._hidden_params.custom_llm_provider // .model_extra.provider // empty' <<<"${body}" 2>/dev/null || true)"
  printf '%s' "${val}"
}

run_vector() {
  local label="$1"
  local body_json="$2"
  local http_code response

  response="$(curl -sS -w '\n%{http_code}' \
    -X POST "${BASE_URL}/v1/chat/completions" \
    -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
    -H "Content-Type: application/json" \
    -d "${body_json}")"
  http_code="$(tail -n1 <<<"${response}")"
  response_body="$(sed '$d' <<<"${response}")"

  echo "== Vecteur ${label} == HTTP ${http_code}"

  if [[ "${http_code}" != "200" ]]; then
    echo "FAIL [${label}] : HTTP ${http_code} (attendu 200) — corps: ${response_body}" >&2
    return 1
  fi

  local attested
  attested="$(extract_provider_attestation "${response_body}")"

  if [[ -z "${attested}" ]]; then
    echo "FAIL [${label}] : AUCUNE attestation fournisseur trouvée dans la réponse — preuve non concluante, traité comme échec (pas un pass silencieux)." >&2
    echo "Corps réponse (pour investigation) : ${response_body}" >&2
    return 1
  fi

  local attested_lc expected_lc
  attested_lc="$(tr '[:upper:]' '[:lower:]' <<<"${attested}")"
  expected_lc="$(tr '[:upper:]' '[:lower:]' <<<"${EXPECTED_PROVIDER}")"

  if [[ "${attested_lc}" != *"${expected_lc}"* ]]; then
    echo "FAIL [${label}] : fournisseur attesté='${attested}' != pin serveur attendu='${EXPECTED_PROVIDER}' — le vecteur a CONTOURNÉ le pin." >&2
    return 1
  fi

  echo "PASS [${label}] : fournisseur attesté='${attested}' == pin serveur '${EXPECTED_PROVIDER}' (contournement neutralisé)."
  return 0
}

vector_a_body="$(jq -n --arg model "${MODEL}" --arg atk "${ATTACKER_PROVIDER}" \
  '{model: $model, max_tokens: 1, messages: [{role:"user", content:"1"}],
    provider: {order: [$atk], allow_fallbacks: true, data_collection: "allow"}}')"

vector_b_body="$(jq -n --arg model "${MODEL}" --arg atk "${ATTACKER_PROVIDER}" \
  '{model: $model, max_tokens: 1, messages: [{role:"user", content:"1"}],
    extra_body: {provider: {order: [$atk], allow_fallbacks: true, data_collection: "allow"}}}')"

overall_status=0

run_vector "A top-level provider" "${vector_a_body}" || overall_status=1
run_vector "B extra_body.provider" "${vector_b_body}" || overall_status=1

if [[ "${overall_status}" -eq 0 ]]; then
  echo "RESULTAT: PASS — les 2 vecteurs de contournement échouent, pin serveur '${EXPECTED_PROVIDER}' tenu pour '${MODEL}'."
else
  echo "RESULTAT: FAIL — au moins un vecteur a contourné le pin ou preuve non concluante. Voir détails ci-dessus." >&2
fi

exit "${overall_status}"
