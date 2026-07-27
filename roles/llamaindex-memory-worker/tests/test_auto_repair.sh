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
    memory_worker_auto_repair_journal_lines=300,
    memory_worker_auto_repair_journal_lookback_max_sec=86400,
    memory_worker_auto_repair_state_file="__STATE_FILE__",
    memory_worker_auto_repair_lock_file="__LOCK_FILE__",
    memory_worker_auto_repair_maintenance_file="__MAINT_FILE__",
    memory_worker_auto_repair_maintenance_frozen_marker="__FROZEN_FILE__",
    memory_worker_auto_repair_env_file="__ENV_FILE__",
    memory_worker_auto_repair_drift_sec=5400,
    memory_worker_auto_repair_cooldown_sec=14400,
    memory_worker_auto_repair_unlock_ticks=8,
    memory_worker_auto_repair_reminder_sec=10800,
    memory_worker_auto_repair_tick_sec=900,
    memory_worker_auto_repair_blind_alert_every=4,
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
# bloc de lignes, pattern test_memctl.sh fake bin dans PATH). L3 fix (revue
# Opus) : notify() envoie desormais le payload (token inclus) via
# `--config -` (stdin), plus comme arguments de ligne de commande -> le mock
# doit aussi capturer stdin (le fichier de config curl, qui contient les
# directives url/data-urlencode dont le texte du message), pas seulement
# "$@". Le mock imprime "200" sur stdout pour simuler un sendMessage reussi
# (notify() lit -w '%{http_code}' -o /dev/null). ---
FAKEBIN="$TMP/bin"
mkdir -p "$FAKEBIN"
CURL_LOG="$TMP/curl_calls.log"
cat > "$FAKEBIN/curl" <<EOF
#!/bin/bash
{
  echo "---CALL---"
  printf '%s\n' "\$@"
  cat
} >> "$CURL_LOG"
printf '200'
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
  # F5/F10 fix (revue Opus 2026-07-27) : la sonde de corruption teste
  # desormais la DERNIERE cle ecrite par write_state (ACTIVATING_TICKS,
  # ajoutee par F10) -- un state seede sans cette cle serait juge corrompu
  # par TOUS les scenarios qui suivent. CONSECUTIVE_BLIND/ACTIVATING_TICKS
  # toujours a 0 ici (aucun scenario seed_state n'en depend).
  cat > "$STATE_FILE" <<EOF
LAST_SUCCESS_EPOCH=$1
DRIFT_TICKS=$2
HEALTHY_TICKS=$3
LAST_REPAIR_EPOCH=$4
REPAIR_ATTEMPTS=$5
ALERTED=$6
LAST_ALERT=$7
CONSECUTIVE_BLIND=0
ACTIVATING_TICKS=0
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
# M6 fix (revue Opus) : `grep -qv X` reussit des qu'AU MOINS UNE LIGNE ne
# contient pas X -- sur une sortie multi-ligne ou X fuit sur une SEULE des
# lignes, l'assertion passait quand meme (faux positif). Remplace par
# `! grep -q X` (echoue seulement si X n'apparait NULLE PART, quel que soit
# le nombre de lignes).
# =====================================================================
echo "== redact() =="
out="$(printf 'API_KEY=abcREDACT1def' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'abcREDACT1def' && echo 1)" "env KEY=v masque"

out="$(printf 'api_key: yamlSECRET2val' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'yamlSECRET2val' && echo 1)" "yaml key: v masque"

out="$(printf '"api_key": "v a l SECRET3"' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'v a l SECRET3' && echo 1)" "JSON quote \"key\": \"v a l\" (espaces) masque en entier"

out="$(printf '%s' "'token':'sekritSECRET4'" | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'sekritSECRET4' && echo 1)" "quote simple 'token':'v' masque"

out="$(printf 'Authorization: Bearer eyJSECRET5.payload' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'eyJSECRET5' && echo 1)" "Authorization: Bearer <token> masque"

out="$(printf 'Authorization: Basic dXNlcjpTRUNSRVQ2' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'dXNlcjpTRUNSRVQ2' && echo 1)" "Authorization: Basic <base64> masque"

out="$(printf 'https://user:hunterSECRET7@example.com/path' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'hunterSECRET7' && echo 1)" "userinfo URL scheme://user:pass@ masque"

out="$(printf 'sk-ABCDEFSECRET8901234567890' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'ABCDEFSECRET8901234567890' && echo 1)" "chaine sk-\\S+ masquee en entier"

# --- C1 fix : les 7 formes qui fuyaient avant la revue Opus (valeur quotee
# avec cle NON quotee -- TOKEN="v", password='v', export KEY='v', espaces
# autour du delimiteur -- + Authorization avec '=' au lieu de ':'). ---
out="$(printf 'TOKEN="quotedSECRET9val"' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'quotedSECRET9val' && echo 1)" "env TOKEN=\"v\" (valeur quotee double, cle non quotee) masque"

out="$(printf "password='quotedSECRET10val'" | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'quotedSECRET10val' && echo 1)" "env password='v' (valeur quotee simple, cle non quotee) masque"

out="$(printf "export QDRANT_API_KEY='exportSECRET11val'" | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'exportSECRET11val' && echo 1)" "export QDRANT_API_KEY='v' masque"

out="$(printf 'qdrant_api_key = "spacedSECRET12val"' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'spacedSECRET12val' && echo 1)" "qdrant_api_key = \"v\" (espaces autour du delimiteur) masque"

out="$(printf 'Authorization=Bearer eqSECRET13token' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'eqSECRET13token' && echo 1)" "Authorization=Bearer <token> (delimiteur '=' au lieu de ':') masque"

out="$(printf '"secret": "jsonSECRET14 with spaces"' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'jsonSECRET14' && echo 1)" "JSON quote \"secret\": \"v a l\" masque"

out="$(printf "'password':'quotedBothSECRET15'" | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'quotedBothSECRET15' && echo 1)" "'password':'v' (quotes simples cle+valeur) masque"

# --- M6 fix : test multi-ligne -- une seule des lignes contient le secret,
# ! grep -q doit echouer sur TOUTE la sortie (pas juste la 1ere ligne
# matchee), verifiant qu'aucun fragment ne survit sur aucune ligne. ---
out="$(printf 'first line, nothing secret\napi_key: multiSECRET16line\nlast line, clean' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'multiSECRET16line' && echo 1)" "redact multi-ligne: secret sur la ligne du milieu masque"
ok "$([ "$(echo "$out" | wc -l)" -ge 3 ] && echo 1)" "redact multi-ligne: les lignes non sensibles survivent (pas de troncature globale)"

# --- F11 fix : private[-_]?key ajoute aux mots-cles. ---
out="$(printf 'private_key: pemSECRET17val' | bash "$SCRIPT" __redact_test)"
ok "$(! echo "$out" | grep -q 'pemSECRET17val' && echo 1)" "private_key: v (F11 -- mot-cle ajoute) masque"

# =====================================================================
# 1b) F1/F12 : html_escape() isolee -- point d'entree cache
#     __html_escape_test (meme pattern que __redact_test). ORDRE STRICT :
#     '&' doit etre traite EN PREMIER (verifie que les '&' injectes par
#     &lt;/&gt; ne sont pas re-echappes en &amp;lt;/&amp;gt;).
# =====================================================================
echo "== html_escape() =="
out="$(printf '%s' 'a < b > c & d' | bash "$SCRIPT" __html_escape_test)"
ok "$([ "$out" = 'a &lt; b &gt; c &amp; d' ] && echo 1)" "html_escape: '<'/'>'/'&' echappes dans le bon ordre (F1)"
out="$(printf '%s' '<script>alert(1)</script>' | bash "$SCRIPT" __html_escape_test)"
ok "$([ "$out" = '&lt;script&gt;alert(1)&lt;/script&gt;' ] && echo 1)" "html_escape: balises completes echappees"

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
# M1 fix : le predicat d'echec post-reparation exige NOW-LAST_REPAIR_EPOCH >
# TICK_SEC (900s, cf script) -- le run declenche peut prendre plusieurs
# minutes, un jugement trop precoce serait premature. 1000s > 900s et reste
# tres en-deca du cooldown (14400s), donc la branche testee est bien
# POST_REPAIR_FAILED, pas COOLDOWN_ACTIVE.
REPAIR_EPOCH=$((NOW - 1000))     # reparation il y a >TICK_SEC (900s), < cooldown
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
# 10) H1 : state file corrompu -> notif + survie (PAS de mort silencieuse
#     sous set -e). L'ancien code faisait `. "$STATE_FILE"` (source) -- un
#     contenu non-shell tuait le script AVANT le premier notify() possible.
#     Desormais : detection (grep de la 1ere cle attendue), notif dediee,
#     rm + reinitialisation, le tick continue normalement et re-ecrit un
#     state valide.
# =====================================================================
echo "== H1: state file corrompu -> notif + survie =="
reset_state
printf '\x00\x01 ceci n'"'"'est pas du KEY=VALUE shell valide {{{\n' > "$STATE_FILE"
OUT="$(AUTOREPAIR_FAKE_ACTIVE_STATE=inactive AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=0 AUTOREPAIR_FAKE_RESULT=success \
  bash "$SCRIPT" 2>&1)"
rc=$?
ok "$([ "$rc" -eq 0 ] && echo 1)" "state corrompu: le script survit (exit 0, pas de mort silencieuse sous set -e)"
ok "$(curl_log_contains 'corrompu' && echo 1)" "state corrompu: notification dediee envoyee"
ok "$([ -s "$STATE_FILE" ] && grep -q '^LAST_SUCCESS_EPOCH=' "$STATE_FILE" && echo 1)" "state corrompu: nouveau state valide reecrit (write_state du tick courant)"

# =====================================================================
# 11) H2 : ActiveState=activating -> suspension de jugement, ni sain ni
#     drift. Aucun compteur (DRIFT_TICKS/HEALTHY_TICKS/ALERTED) ne bouge, et
#     aucune notification n'est envoyee -- un run EN COURS ne prouve rien.
# =====================================================================
echo "== H2: activating -> suspension de jugement (ni sain ni drift) =="
reset_state
seed_state "$OLD_DRIFT" 3 0 0 0 1 "$((NOW - 100))"
AUTOREPAIR_FAKE_ACTIVE_STATE=activating AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=0 AUTOREPAIR_FAKE_RESULT=success \
  bash "$SCRIPT" >/dev/null
ok "$([ "$(state_get DRIFT_TICKS)" = 3 ] && echo 1)" "activating: DRIFT_TICKS inchange (ni remis a zero -- faux all-clear --, ni incremente)"
ok "$([ "$(state_get HEALTHY_TICKS)" = 0 ] && echo 1)" "activating: HEALTHY_TICKS inchange (pas de degel REPAIR_LOCKED sans run reussi)"
ok "$([ "$(state_get ALERTED)" = 1 ] && echo 1)" "activating: ALERTED inchange (pas de faux retablissement)"
ok "$([ "$(curl_call_count)" = 0 ] && echo 1)" "activating: aucune notification envoyee (tick suspendu)"

# =====================================================================
# 12) H3 : notification de resultat verifie post-reparation. L'action
#     (classe A ici) pose ALERTED=1 -- sans ce fix, le tick suivant qui
#     constate le retour a la sante ne notifiait JAMAIS le resultat de la
#     reparation (branche "healthy" conditionnee a ALERTED=1, jamais posee).
# =====================================================================
echo "== H3: notif de resultat verifie post-reparation =="
reset_state
seed_state "$OLD_DRIFT" 5 0 0 0 0 0
AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  AUTOREPAIR_FAKE_STATUS_JSON='{"lock_pid":"555","lock_alive":false,"timer_enabled":"enabled","timer_active":"active","qdrant_reachable":true}' \
  AUTOREPAIR_FAKE_JOURNAL='nothing special' \
  AUTOREPAIR_FAKE_ACTIONS_LOG="$ACTIONS_LOG" \
  bash "$SCRIPT" >/dev/null
ok "$([ "$(state_get ALERTED)" = 1 ] && echo 1)" "H3: action classe A pose ALERTED=1 (prealable a la notif de resultat)"
: > "$CURL_LOG"
NEWSUCC="$(date +%s)"
AUTOREPAIR_FAKE_ACTIVE_STATE=inactive AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=0 AUTOREPAIR_FAKE_RESULT=success \
  AUTOREPAIR_FAKE_EXEC_MAIN_EXIT_EPOCH="$NEWSUCC" \
  bash "$SCRIPT" >/dev/null
ok "$(curl_log_contains 'retour a la sante' && echo 1)" "H3: notification de resultat verifie emise au tick suivant (run reussi apres reparation)"
ok "$([ "$(state_get ALERTED)" = 0 ] && echo 1)" "H3: ALERTED remis a zero apres confirmation du resultat"

# =====================================================================
# 13) Sonde aveugle (systemctl injoignable) -> exit 2, log fort, jamais
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
# 14) F12/M8 : alerte sonde aveugle emise EXACTEMENT au 4e tick consecutif
#     (BLIND_ALERT_EVERY=4 dans le contexte de rendu du harnais) -- jamais
#     avant (1-3), jamais re-emise au 5e (5 % 4 != 0).
# =====================================================================
echo "== F12: alerte M8 exactement au 4e tick aveugle =="
reset_state
for _i in 1 2 3; do
  : > "$CURL_LOG"
  PATH="$FAKEBIN2:$PATH" bash "$SCRIPT" >/dev/null 2>&1 || true
  ok "$([ "$(curl_call_count)" = 0 ] && echo 1)" "sonde aveugle tick ${_i}/4: pas d'alerte (avant le seuil)"
done
: > "$CURL_LOG"
PATH="$FAKEBIN2:$PATH" bash "$SCRIPT" >/dev/null 2>&1 || true
ok "$([ "$(curl_call_count)" = 1 ] && echo 1)" "sonde aveugle tick 4/4: alerte emise (exactement au seuil)"
ok "$(curl_log_contains 'aveugle' && echo 1)" "sonde aveugle tick 4/4: message d'alerte correct"
: > "$CURL_LOG"
PATH="$FAKEBIN2:$PATH" bash "$SCRIPT" >/dev/null 2>&1 || true
ok "$([ "$(curl_call_count)" = 0 ] && echo 1)" "sonde aveugle tick 5/4: pas de re-emission (5 % 4 != 0)"

# =====================================================================
# 15) F12/F5 : state tronque APRES la 1ere ligne (LAST_SUCCESS_EPOCH= seul
#     present, cle DERNIERE ecrite -- ACTIVATING_TICKS -- absente) -> detecte
#     comme corrompu, notification dediee. L'ancienne sonde (teste la 1ere
#     cle) aurait laisse passer ce cas sans le voir.
# =====================================================================
echo "== F12/F5: state tronque apres la 1ere ligne -> notif corruption =="
reset_state
printf 'LAST_SUCCESS_EPOCH=%s\n' "$OLD_DRIFT" > "$STATE_FILE"
OUT="$(AUTOREPAIR_FAKE_ACTIVE_STATE=inactive AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=0 AUTOREPAIR_FAKE_RESULT=success \
  bash "$SCRIPT" 2>&1)"
rc=$?
ok "$([ "$rc" -eq 0 ] && echo 1)" "state tronque (1ere ligne seule): le script survit (exit 0)"
ok "$(curl_log_contains 'corrompu' && echo 1)" "state tronque (1ere ligne seule): notification de corruption emise (F5 -- sonde sur la DERNIERE cle)"

# =====================================================================
# 16) F12/F6 : valeur DRIFT_TICKS=- (non numerique, mais compatible avec
#     l'ancien filtre bugue) retombe sur le defaut (0) sans casser
#     l'arithmetique `$(( DRIFT_TICKS + 1 ))` en aval.
# =====================================================================
echo "== F12/F6: DRIFT_TICKS=- retombe sur le defaut sans casser l'arithmetique =="
reset_state
cat > "$STATE_FILE" <<EOF
LAST_SUCCESS_EPOCH=$OLD_DRIFT
DRIFT_TICKS=-
HEALTHY_TICKS=0
LAST_REPAIR_EPOCH=0
REPAIR_ATTEMPTS=0
ALERTED=0
LAST_ALERT=0
CONSECUTIVE_BLIND=0
ACTIVATING_TICKS=0
EOF
OUT="$(AUTOREPAIR_FAKE_ACTIVE_STATE=failed AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=1 AUTOREPAIR_FAKE_RESULT=failed \
  bash "$SCRIPT" 2>&1)"
rc=$?
ok "$([ "$rc" -eq 0 ] && echo 1)" "DRIFT_TICKS=- : le script survit, pas d'erreur arithmetique (exit 0)"
ok "$([ "$(state_get DRIFT_TICKS)" = 1 ] && echo 1)" "DRIFT_TICKS=- : retombe sur le defaut (0) puis incremente normalement (1)"

# =====================================================================
# 17) F12/F10 : ACTIVATING_TICKS -> alerte exactement au 4e tick consecutif
#     en ActiveState=activating (meme cadence BLIND_ALERT_EVERY=4).
# =====================================================================
echo "== F12/F10: alerte ACTIVATING_TICKS au 4e tick =="
reset_state
for _i in 1 2 3; do
  : > "$CURL_LOG"
  AUTOREPAIR_FAKE_ACTIVE_STATE=activating AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=0 AUTOREPAIR_FAKE_RESULT=success \
    bash "$SCRIPT" >/dev/null
  ok "$([ "$(curl_call_count)" = 0 ] && echo 1)" "activating tick ${_i}/4: pas d'alerte (avant le seuil)"
done
: > "$CURL_LOG"
AUTOREPAIR_FAKE_ACTIVE_STATE=activating AUTOREPAIR_FAKE_EXEC_MAIN_STATUS=0 AUTOREPAIR_FAKE_RESULT=success \
  bash "$SCRIPT" >/dev/null
ok "$([ "$(curl_call_count)" = 1 ] && echo 1)" "activating tick 4/4: alerte emise (exactement au seuil, F10)"
ok "$(curl_log_contains 'activating' && echo 1)" "activating tick 4/4: message d'alerte mentionne le run fige"
ok "$([ "$(state_get DRIFT_TICKS)" = 0 ] && echo 1)" "activating tick 4/4: DRIFT_TICKS toujours inchange (H2 preserve)"

# =====================================================================
rm -rf "$TMP"
[ "$fail" = 0 ] && echo "test_auto_repair PASS" || { echo "test_auto_repair FAIL"; exit 1; }
