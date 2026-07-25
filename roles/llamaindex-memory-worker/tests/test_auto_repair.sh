#!/bin/bash
# test_auto_repair.sh — harnais bash pour roles/memory-worker-auto-repair
# (script .sh.j2 rendu via jinja2, pattern test_memctl.sh : mocks dans PATH,
# ok()/fail, exit 1 si FAIL). Design normatif :
# docs/design/2026-07-25-memory-worker-auto-repair.md
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$HERE/../../memory-worker-auto-repair/templates/memory-worker-auto-repair.sh.j2"
TMP="$(mktemp -d)"

fail=0
ok() { [ "$1" = 1 ] && echo "  ok: $2" || { echo "  FAIL: $2"; fail=1; }; }

# --- Rendu du template (jinja2 minimal, cf task prompt point 9) — une seule
# fois, contexte fixe pointant vers des chemins tmp. Les scenarios qui suivent
# repartent d'un state propre (rm -f) plutot que de re-rendre a chaque fois. ---
STATE_DIR="$TMP/state"
mkdir -p "$STATE_DIR"
SCRIPT="$TMP/memory-worker-auto-repair.sh"
STATE_FILE="$STATE_DIR/state"
LOCK_FILE="$STATE_DIR/repair-locked"
MAINT_FILE="$STATE_DIR/maintenance"
FROZEN_FILE="$STATE_DIR/maintenance-frozen"
ENV_FILE="$TMP/env"
MEMCTL_PATH="$TMP/memctl.sh"

python3 - "$TEMPLATE" "$SCRIPT" <<'PYEOF'
import sys
import jinja2

template_path, out_path = sys.argv[1], sys.argv[2]
env = jinja2.Environment()
tpl = env.from_string(open(template_path).read())
ctx = dict(
    ansible_managed="Ansible managed (test render)",
    memory_worker_auto_repair_uid=1000,
    memory_worker_auto_repair_target_service="llamaindex-memory-worker.service",
    memory_worker_auto_repair_memctl="__MEMCTL__",
    memory_worker_auto_repair_host_origin="waza",
    memory_worker_auto_repair_journal_since="-6h",
    memory_worker_auto_repair_journal_lines=300,
    memory_worker_auto_repair_state_file="__STATE_FILE__",
    memory_worker_auto_repair_lock_file="__LOCK_FILE__",
    memory_worker_auto_repair_maintenance_file="__MAINT_FILE__",
    memory_worker_auto_repair_maintenance_frozen_marker="__FROZEN_FILE__",
    memory_worker_auto_repair_env_file="__ENV_FILE__",
    memory_worker_auto_repair_drift_sec=5400,
    memory_worker_auto_repair_cooldown_sec=14400,
    memory_worker_auto_repair_unlock_ticks=8,
    memory_worker_auto_repair_reminder_sec=10800,
)
out = tpl.render(**ctx)
open(out_path, "w").write(out)
PYEOF

# Substitution des placeholders (evite de jongler avec l'echappement shell
# dans le heredoc python ci-dessus — chemins tmp injectes apres coup).
sed -i \
  -e "s#__MEMCTL__#$MEMCTL_PATH#" \
  -e "s#__STATE_FILE__#$STATE_FILE#" \
  -e "s#__LOCK_FILE__#$LOCK_FILE#" \
  -e "s#__MAINT_FILE__#$MAINT_FILE#" \
  -e "s#__FROZEN_FILE__#$FROZEN_FILE#" \
  -e "s#__ENV_FILE__#$ENV_FILE#" \
  "$SCRIPT"

bash -n "$SCRIPT"
ok "$([ $? -eq 0 ] && echo 1)" "script rendu: bash -n (syntaxe) OK"

# --- Env Telegram factice (notify() doit appeler curl, pas juste logger
# "creds absentes") — TG_BOT/TG_CHAT non-vides. ---
printf 'TG_BOT=faketoken\nTG_CHAT=fakechat\n' > "$ENV_FILE"

# --- Fake curl (capture les appels notify() -> $CURL_LOG, un appel = un
# bloc de lignes, pattern test_memctl.sh fake bin dans PATH). ---
FAKEBIN="$TMP/bin"
mkdir -p "$FAKEBIN"
CURL_LOG="$TMP/curl_calls.log"
cat > "$FAKEBIN/curl" <<EOF
#!/bin/bash
{
  echo "---CALL---"
  printf '%s\n' "\$@"
} >> "$CURL_LOG"
exit 0
EOF
chmod +x "$FAKEBIN/curl"
export PATH="$FAKEBIN:$PATH"

ACTIONS_LOG="$TMP/actions.log"

reset_state() {
  rm -f "$STATE_FILE" "$LOCK_FILE" "$MAINT_FILE" "$FROZEN_FILE" "$ACTIONS_LOG" "$CURL_LOG"
}

seed_state() {
  # $1=LAST_SUCCESS_EPOCH $2=DRIFT_TICKS $3=HEALTHY_TICKS $4=LAST_REPAIR_EPOCH
  # $5=REPAIR_ATTEMPTS $6=ALERTED $7=LAST_ALERT
  cat > "$STATE_FILE" <<EOF
LAST_SUCCESS_EPOCH=$1
DRIFT_TICKS=$2
HEALTHY_TICKS=$3
LAST_REPAIR_EPOCH=$4
REPAIR_ATTEMPTS=$5
ALERTED=$6
LAST_ALERT=$7
EOF
}

state_get() {
  # $1=KEY -> valeur courante du state file
  sed -n "s/^$1=//p" "$STATE_FILE" 2>/dev/null | tail -1
}

curl_log_contains() { grep -q -- "$1" "$CURL_LOG" 2>/dev/null; }
curl_call_count() {
  # NB: `grep -c` avec 0 match imprime deja "0" ET sort en rc=1 -> un
  # `|| echo 0` supplementaire produirait un DOUBLE "0" (deux lignes) et
  # casserait toute comparaison "= 0" en aval. Un seul chemin d'impression.
  if [ -f "$CURL_LOG" ]; then
    grep -c -- '^---CALL---$' "$CURL_LOG" 2>/dev/null
  else
    echo 0
  fi
}

NOW="$(date +%s)"
OLD_DRIFT=$((NOW - 6000))   # > AUTOREPAIR_DRIFT_SEC (5400) dans le passe

# =====================================================================
# 1) redact() — toutes les formes du §6, credentials factices distincts.
# =====================================================================
echo "== redact() =="
out="$(printf 'API_KEY=abcREDACT1def' | bash "$SCRIPT" __redact_test)"
ok "$(echo "$out" | grep -qv 'abcREDACT1def' && echo 1)" "env KEY=v masque"

out="$(printf 'api_key: yamlSECRET2val' | bash "$SCRIPT" __redact_test)"
ok "$(echo "$out" | grep -qv 'yamlSECRET2val' && echo 1)" "yaml key: v masque"

out="$(printf '"api_key": "v a l SECRET3"' | bash "$SCRIPT" __redact_test)"
ok "$(echo "$out" | grep -qv 'v a l SECRET3' && echo 1)" "JSON quote \"key\": \"v a l\" (espaces) masque en entier"

out="$(printf '%s' "'token':'sekritSECRET4'" | bash "$SCRIPT" __redact_test)"
ok "$(echo "$out" | grep -qv 'sekritSECRET4' && echo 1)" "quote simple 'token':'v' masque"

out="$(printf 'Authorization: Bearer eyJSECRET5.payload' | bash "$SCRIPT" __redact_test)"
ok "$(echo "$out" | grep -qv 'eyJSECRET5' && echo 1)" "Authorization: Bearer <token> masque"

out="$(printf 'Authorization: Basic dXNlcjpTRUNSRVQ2' | bash "$SCRIPT" __redact_test)"
ok "$(echo "$out" | grep -qv 'dXNlcjpTRUNSRVQ2' && echo 1)" "Authorization: Basic <base64> masque"

out="$(printf 'https://user:hunterSECRET7@example.com/path' | bash "$SCRIPT" __redact_test)"
ok "$(echo "$out" | grep -qv 'hunterSECRET7' && echo 1)" "userinfo URL scheme://user:pass@ masque"

out="$(printf 'sk-ABCDEFSECRET8901234567890' | bash "$SCRIPT" __redact_test)"
ok "$(echo "$out" | grep -qv 'ABCDEFSECRET8901234567890' && echo 1)" "chaine sk-\\S+ masquee en entier"

# =====================================================================
# 2) Garde timer-disabled -> notif unique, aucune action.
# =====================================================================
echo "== garde timer disabled =="
reset_state
seed_state "$OLD_DRIFT" 1 0 0 0 0 0
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  AUTOREPAIR_FAKE_STATUS_JSON='{"lock_pid":"","lock_alive":false,"timer_enabled":"disabled","timer_active":"inactive","qdrant_reachable":true}' \
  AUTOREPAIR_FAKE_ACTIONS_LOG="$ACTIONS_LOG" \
  bash "$SCRIPT" >/dev/null
ok "$([ "$(state_get DRIFT_TICKS)" = 2 ] && echo 1)" "timer disabled: DRIFT_TICKS avance normalement (2)"
ok "$([ ! -s "$ACTIONS_LOG" ] && echo 1)" "timer disabled: aucune action tentee"
ok "$(curl_log_contains 'desactive' && echo 1)" "timer disabled: notif unique envoyee"
ok "$([ "$(curl_call_count)" = 1 ] && echo 1)" "timer disabled: exactement 1 notif (pas de rappel)"

echo "== garde timer disabled: re-tick, silence (episode deja notifie) =="
: > "$CURL_LOG"
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  AUTOREPAIR_FAKE_STATUS_JSON='{"lock_pid":"","lock_alive":false,"timer_enabled":"disabled","timer_active":"inactive","qdrant_reachable":true}' \
  bash "$SCRIPT" >/dev/null
ok "$([ "$(curl_call_count)" = 0 ] && echo 1)" "timer disabled: pas de rappel au tick suivant (episode unique)"

# =====================================================================
# 3) Sentinelle maintenance -> gel + reprise, DRIFT_TICKS remis a zero.
# =====================================================================
echo "== sentinelle maintenance =="
reset_state
seed_state "$OLD_DRIFT" 1 0 0 0 0 0
touch "$MAINT_FILE"
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  bash "$SCRIPT" >/dev/null
ok "$([ -e "$FROZEN_FILE" ] && echo 1)" "sentinelle: marqueur de gel pose"
ok "$(curl_log_contains 'sentinelle' && echo 1)" "sentinelle: notif de gel envoyee"

: > "$CURL_LOG"
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  bash "$SCRIPT" >/dev/null
ok "$([ "$(curl_call_count)" = 0 ] && echo 1)" "sentinelle: silence au 2e tick gele (anti-spam < 3h)"

rm -f "$MAINT_FILE"
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  bash "$SCRIPT" >/dev/null
ok "$([ ! -e "$FROZEN_FILE" ] && echo 1)" "sentinelle levee: marqueur de gel retire"
ok "$(curl_log_contains 'levee' && echo 1)" "sentinelle levee: notif de reprise envoyee"
ok "$([ "$(state_get DRIFT_TICKS)" = 1 ] && echo 1)" "sentinelle levee: fenetre de drift repart de zero (1, pas 2+)"

# =====================================================================
# 4) Classification des 6 classes (A/B/C/D/E/F), DRIFT_TICKS pre-arme (5).
# =====================================================================
echo "== classification: 6 classes =="

classify_with() {
  # $1=status_json $2=journal -> ecrit CLASS_RESULT via grep du log
  reset_state
  seed_state "$OLD_DRIFT" 5 0 0 0 0 0
  AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
    AUTOREPAIR_FAKE_STATUS_JSON="$1" \
    AUTOREPAIR_FAKE_JOURNAL="$2" \
    AUTOREPAIR_FAKE_ACTIONS_LOG="$ACTIONS_LOG" \
    bash "$SCRIPT" 2>&1
}

OUT="$(classify_with '{"lock_pid":"","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":true}' 'Traceback: discover_sources found 31 repos > max_repos=30')"
ok "$(echo "$OUT" | grep -q 'CLASS=D' && echo 1)" "classe D (discovery max_repos) detectee"
ok "$([ ! -s "$ACTIONS_LOG" ] && echo 1)" "classe D: alerte seule, aucune action"

OUT="$(classify_with '{"lock_pid":"","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":false}' 'nothing special')"
ok "$(echo "$OUT" | grep -q 'CLASS=E' && echo 1)" "classe E (qdrant injoignable) detectee"
ok "$([ ! -s "$ACTIONS_LOG" ] && echo 1)" "classe E: alerte seule, aucune action"

OUT="$(classify_with '{"lock_pid":"4242","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":true}' 'nothing special')"
ok "$(echo "$OUT" | grep -q 'CLASS=A' && echo 1)" "classe A (lock zombie) detectee"
ok "$([ "$(cat "$ACTIONS_LOG" 2>/dev/null)" = "fix" ] && echo 1)" "classe A: memctl fix declenche"

OUT="$(classify_with '{"lock_pid":"","lock_alive":false,"timer_enabled":"enabled","timer_active":"inactive","qdrant_reachable":true}' 'nothing special')"
ok "$(echo "$OUT" | grep -q 'CLASS=B' && echo 1)" "classe B (timer arrete par accident) detectee"
ok "$(grep -q '^start$' "$ACTIONS_LOG" 2>/dev/null && echo 1)" "classe B: memctl start declenche"

OUT="$(classify_with '{"lock_pid":"","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":true}' 'nothing special')"
ok "$(echo "$OUT" | grep -q 'CLASS=C' && echo 1)" "classe C (echec inconnu) detectee"
ok "$([ "$(cat "$ACTIONS_LOG" 2>/dev/null)" = "run" ] && echo 1)" "classe C: memctl run (relance unique) declenche"

# Classe F : aucune signature D/E/A/B/C ne doit matcher. RESULT=success +
# EXEC_MAIN_STATUS=0 neutralise SIG_C (sinon C gagnerait), MAIS sans fournir
# AUTOREPAIR_FAKE_EXEC_MAIN_EXIT_EPOCH (defaut 0) le "succes" ne met PAS a
# jour LAST_SUCCESS_EPOCH (garde EXIT_EPOCH>0 dans le script) -> le drift
# seede (OLD_DRIFT) reste actif malgre ce faux "succes" sans date exploitable.
reset_state
seed_state "$OLD_DRIFT" 5 0 0 0 0 0
OUT="$(AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=0 AUTOREPAIR_FAKE_RESULT=success \
  AUTOREPAIR_FAKE_STATUS_JSON='{"lock_pid":"","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":true}' \
  AUTOREPAIR_FAKE_JOURNAL='nothing special' \
  AUTOREPAIR_FAKE_ACTIONS_LOG="$ACTIONS_LOG" \
  bash "$SCRIPT" 2>&1)"
ok "$(echo "$OUT" | grep -q 'CLASS=F' && echo 1)" "classe F (inclassable) detectee"
ok "$([ ! -s "$ACTIONS_LOG" ] && echo 1)" "classe F: alerte seule, aucune action"

# =====================================================================
# 5) Collisions D+A et E+B -> la classe alerte-seule (D, E) gagne toujours.
# =====================================================================
echo "== collisions D+A, E+B =="
OUT="$(classify_with '{"lock_pid":"999","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":true}' 'Traceback: discover_sources found 31 repos > max_repos=30')"
ok "$(echo "$OUT" | grep -q 'CLASS=D' && echo 1)" "collision D+A: classe D gagne"
ok "$([ ! -s "$ACTIONS_LOG" ] && echo 1)" "collision D+A: aucune action (A masque, pas reparee)"
# La signature secondaire est mentionnee dans le MESSAGE Telegram (notify()),
# pas dans les lignes log() -> verifier CURL_LOG, pas $OUT (stdout du script).
ok "$(curl_log_contains 'lock zombie present egalement' && echo 1)" "collision D+A: signature secondaire A mentionnee (notif)"

OUT="$(classify_with '{"lock_pid":"","lock_alive":false,"timer_enabled":"enabled","timer_active":"inactive","qdrant_reachable":false}' 'nothing special')"
ok "$(echo "$OUT" | grep -q 'CLASS=E' && echo 1)" "collision E+B: classe E gagne"
ok "$([ ! -s "$ACTIONS_LOG" ] && echo 1)" "collision E+B: aucune action (B masque, pas reparee)"
ok "$(curl_log_contains 'timer arrete par accident egalement' && echo 1)" "collision E+B: signature secondaire B mentionnee (notif)"

# =====================================================================
# 6) Cooldown : 2e action refusee dans la fenetre, y compris apres retour
#    transitoire a la sante (LAST_REPAIR_EPOCH survit, pas d'escalade car un
#    succes a bien eu lieu depuis).
# =====================================================================
echo "== cooldown, incluant retour transitoire =="
reset_state
REPAIR_EPOCH=$((NOW - 7200))     # reparation il y a 2h (< cooldown 4h)
SUCCESS_EPOCH=$((NOW - 6000))    # succes transitoire APRES la reparation, mais deja re-stale (>5400s)
seed_state "$SUCCESS_EPOCH" 5 0 "$REPAIR_EPOCH" 1 0 0
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  AUTOREPAIR_FAKE_STATUS_JSON='{"lock_pid":"777","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":true}' \
  AUTOREPAIR_FAKE_JOURNAL='nothing special' \
  AUTOREPAIR_FAKE_ACTIONS_LOG="$ACTIONS_LOG" \
  bash "$SCRIPT" >/dev/null
ok "$([ ! -s "$ACTIONS_LOG" ] && echo 1)" "cooldown actif: aucune 2e action declenchee"
ok "$([ "$(state_get REPAIR_ATTEMPTS)" = 1 ] && echo 1)" "cooldown actif: REPAIR_ATTEMPTS inchange (budget non reconsomme)"
ok "$([ ! -e "$LOCK_FILE" ] && echo 1)" "cooldown actif + succes transitoire: PAS d'escalade REPAIR_LOCKED"

# =====================================================================
# 7) Echec post-reparation (aucun succes depuis la reparation) -> escalade +
#    REPAIR_LOCKED.
# =====================================================================
echo "== echec post-reparation -> REPAIR_LOCKED =="
reset_state
REPAIR_EPOCH=$((NOW - 60))       # reparation il y a 1 min (largement < cooldown)
seed_state "$OLD_DRIFT" 3 0 "$REPAIR_EPOCH" 1 0 0   # LAST_SUCCESS_EPOCH <= LAST_REPAIR_EPOCH
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  AUTOREPAIR_FAKE_STATUS_JSON='{"lock_pid":"777","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":true}' \
  AUTOREPAIR_FAKE_JOURNAL='nothing special' \
  AUTOREPAIR_FAKE_ACTIONS_LOG="$ACTIONS_LOG" \
  bash "$SCRIPT" >/dev/null
ok "$([ -e "$LOCK_FILE" ] && echo 1)" "drift persiste apres reparation: REPAIR_LOCKED pose"
ok "$(curl_log_contains 'REPAIR_LOCKED' && echo 1)" "drift persiste: notif escalade envoyee"
ok "$([ ! -s "$ACTIONS_LOG" ] && echo 1)" "drift persiste: aucune nouvelle action tentee ce tick"

echo "== REPAIR_LOCKED actif: bloque toute action ulterieure ="
: > "$ACTIONS_LOG"; : > "$CURL_LOG"
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  AUTOREPAIR_FAKE_STATUS_JSON='{"lock_pid":"777","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":true}' \
  AUTOREPAIR_FAKE_ACTIONS_LOG="$ACTIONS_LOG" \
  bash "$SCRIPT" >/dev/null
ok "$([ ! -s "$ACTIONS_LOG" ] && echo 1)" "REPAIR_LOCKED: aucune action, meme classe actionnable"

# =====================================================================
# 8) Degel par HEALTHY_TICKS (sante soutenue >= AUTOREPAIR_UNLOCK_TICKS=8).
# =====================================================================
echo "== degel automatique REPAIR_LOCKED (HEALTHY_TICKS) =="
for _i in $(seq 1 8); do
  T="$(date +%s)"
  AUTOREPAIR_FAKE_ACTIVE_STATE=inactive AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=0 AUTOREPAIR_FAKE_RESULT=success \
    AUTOREPAIR_FAKE_EXEC_MAIN_EXIT_EPOCH="$T" \
    bash "$SCRIPT" >/dev/null
done
ok "$([ ! -e "$LOCK_FILE" ] && echo 1)" "8 ticks sains consecutifs -> REPAIR_LOCKED leve automatiquement"
ok "$(curl_log_contains 'degel automatique' && echo 1)" "notif de degel automatique envoyee"

# =====================================================================
# 9) Anti-course classe B : `memctl run` seulement si aucun run n'a demarre
#    entre le start et le recheck (InactiveExitTimestamp avant/apres).
# =====================================================================
echo "== anti-course classe B =="
reset_state
seed_state "$OLD_DRIFT" 5 0 0 0 0 0
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  AUTOREPAIR_FAKE_STATUS_JSON='{"lock_pid":"","lock_alive":false,"timer_enabled":"enabled","timer_active":"inactive","qdrant_reachable":true}' \
  AUTOREPAIR_FAKE_JOURNAL='nothing special' \
  AUTOREPAIR_FAKE_ACTIONS_LOG="$ACTIONS_LOG" \
  AUTOREPAIR_ANTI_COURSE_SLEEP_SEC=0 \
  AUTOREPAIR_FAKE_INACTIVE_EXIT_BEFORE=1000 AUTOREPAIR_FAKE_INACTIVE_EXIT_AFTER=1000 \
  bash "$SCRIPT" >/dev/null
ok "$(printf '%s\n%s\n' start run | diff -q - "$ACTIONS_LOG" >/dev/null 2>&1 && echo 1)" "pas de run concurrent: start PUIS run declenches"

reset_state
seed_state "$OLD_DRIFT" 5 0 0 0 0 0
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  AUTOREPAIR_FAKE_STATUS_JSON='{"lock_pid":"","lock_alive":false,"timer_enabled":"enabled","timer_active":"inactive","qdrant_reachable":true}' \
  AUTOREPAIR_FAKE_JOURNAL='nothing special' \
  AUTOREPAIR_FAKE_ACTIONS_LOG="$ACTIONS_LOG" \
  AUTOREPAIR_ANTI_COURSE_SLEEP_SEC=0 \
  AUTOREPAIR_FAKE_INACTIVE_EXIT_BEFORE=1000 AUTOREPAIR_FAKE_INACTIVE_EXIT_AFTER=2000 \
  bash "$SCRIPT" >/dev/null
ok "$([ "$(cat "$ACTIONS_LOG")" = "start" ] && echo 1)" "run concurrent detecte (Persistent catch-up): PAS de 2e memctl run"

# =====================================================================
# 10) Sonde aveugle (systemctl injoignable) -> exit 2, log fort, jamais
#     silencieux.
# =====================================================================
echo "== sonde aveugle =="
reset_state
FAKEBIN2="$TMP/bin2"
mkdir -p "$FAKEBIN2"
printf '#!/bin/bash\nexit 1\n' > "$FAKEBIN2/systemctl"
chmod +x "$FAKEBIN2/systemctl"
OUT="$(PATH="$FAKEBIN2:$PATH" bash "$SCRIPT" 2>&1)"
rc=$?
ok "$([ "$rc" -eq 2 ] && echo 1)" "systemctl injoignable: exit code 2"
ok "$(echo "$OUT" | grep -qi 'sonde aveugle' && echo 1)" "systemctl injoignable: log fort explicite (pas de silence)"

# =====================================================================
rm -rf "$TMP"
[ "$fail" = 0 ] && echo "test_auto_repair PASS" || { echo "test_auto_repair FAIL"; exit 1; }
