#!/bin/bash
# Banc d'essai de la machine à états de disk-guard, hors production.
# Stubs : df (usage piloté par $FAKE_PCT), docker/ctr (no-op), curl (compte les envois,
# échec forcé par $FAKE_CURL_FAIL). Le script réel est exécuté tel qu'il sera déployé.
set -uo pipefail

ROLE="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Rend le template avec les valeurs de defaults/main.yml. `bool` est un filtre ANSIBLE,
# absent de Jinja2 vanilla : on l'émule ici (le rendu réel passe par Ansible).
SCR="$WORK/disk-guard.rendered.sh"
python3 - "$ROLE" "$SCR" <<'PY'
import sys, pathlib, yaml
from jinja2 import Environment, FileSystemLoader
role, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
d = yaml.safe_load((role / "defaults/main.yml").read_text())
env = Environment(loader=FileSystemLoader(str(role / "templates")))
env.filters["bool"] = lambda v: str(v).lower() in ("true", "yes", "on", "1")
for _ in range(3):
    for k, v in list(d.items()):
        if isinstance(v, str) and "{{" in v:
            d[k] = env.from_string(v).render(**d)
d.setdefault("ansible_managed", "ANSIBLE MANAGED (banc d'essai)")
out.write_text(env.get_template("disk-guard.sh.j2").render(**d))
PY
if [ ! -s "$SCR" ]; then
  echo "ERREUR: rendu du template impossible (jinja2 + pyyaml requis — activer .venv)"
  exit 2
fi

mkdir -p "$WORK/bin" "$WORK/state"
STATE="$WORK/state/state"
SENT="$WORK/sent.log"
: >"$SENT"

# df pilotable : FAKE_PCT pour toutes les mesures, FAKE_PCT_AFTER pour les mesures 2+
# (simule une purge qui libère réellement de l'espace pendant le run). FAKE_DF_FAIL=1 = panne.
cat >"$WORK/bin/df" <<'EOF'
#!/bin/bash
[ "${FAKE_DF_FAIL:-0}" = "1" ] && exit 1
N=0
[ -f "$DFCOUNT" ] && N=$(cat "$DFCOUNT")
N=$((N+1)); echo "$N" >"$DFCOUNT"
echo "Use%"
if [ -n "${FAKE_PCT_AFTER:-}" ] && [ "$N" -gt 1 ]; then
  echo " ${FAKE_PCT_AFTER}%"
else
  echo " ${FAKE_PCT}%"
fi
EOF
cat >"$WORK/bin/docker" <<'EOF'
#!/bin/bash
[ "${1:-}" = "info" ] && { echo "overlay2"; exit 0; }
exit 0
EOF
cat >"$WORK/bin/ctr" <<'EOF'
#!/bin/bash
exit 0
EOF
cat >"$WORK/bin/curl" <<'EOF'
#!/bin/bash
for a in "$@"; do case "$a" in text=*) echo "---${a#text=}" >>"$SENT";; esac; done
[ "${FAKE_CURL_FAIL:-0}" = "1" ] && exit 7
exit 0
EOF
cat >"$WORK/bin/hostname" <<'EOF'
#!/bin/bash
echo testhost
EOF
chmod +x "$WORK"/bin/*

# Version instrumentée : state file + lock hors production, creds bidon.
sed -e "s#^STATE_FILE=.*#STATE_FILE=\"$STATE\"#" \
  -e "s#^ENV_FILE=.*#ENV_FILE=\"/dev/null\"#" \
  -e "s#^TG_BOT=\"\"#TG_BOT=\"x\"#" \
  -e "s#^TG_CHAT=\"\"#TG_CHAT=\"y\"#" \
  -e "s#exec 9>/run/disk-guard.lock#exec 9>$WORK/lock#" \
  "$SCR" >"$WORK/dg.sh"
chmod +x "$WORK/dg.sh"

DFCOUNT="$WORK/dfcount"
export PATH="$WORK/bin:$PATH" SENT DFCOUNT
PASS=0
FAIL=0
LAST_RC=0

run() { # run <pct> [curl_fail]
  : >"$DFCOUNT"
  FAKE_PCT="$1" FAKE_CURL_FAIL="${2:-0}" "$WORK/dg.sh" >>"$WORK/out.log" 2>&1
  LAST_RC=$?
}

run_purge() { # run_purge <pct_avant> <pct_apres>  -> simule une purge qui libere
  : >"$DFCOUNT"
  FAKE_PCT="$1" FAKE_PCT_AFTER="$2" FAKE_CURL_FAIL=0 "$WORK/dg.sh" >>"$WORK/out.log" 2>&1
  LAST_RC=$?
}

expect_rc() { # expect_rc <label> <code>
  if [ "$LAST_RC" = "$2" ]; then
    echo "  PASS  $1 (rc=$LAST_RC)"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $1 — attendu rc=$2, obtenu $LAST_RC"
    FAIL=$((FAIL + 1))
  fi
}

age_state() { # age_state <secondes> : recule LAST_ALERT pour simuler le temps qui passe
  local cur
  cur="$(sed -n 's/^LAST_ALERT=//p' "$STATE" | tail -1)"
  sed -i "s/^LAST_ALERT=.*/LAST_ALERT=$((cur - $1))/" "$STATE"
}

expect() { # expect <label> <nb_notifs_attendues_depuis_le_dernier_reset>
  local label="$1" want="$2" got
  got="$(grep -c '^---' "$SENT" || true)"
  if [ "$got" = "$want" ]; then
    echo "  PASS  $label (notifs=$got)"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $label — attendu $want notif(s), obtenu $got"
    sed 's/^/        /' "$SENT"
    FAIL=$((FAIL + 1))
  fi
  : >"$SENT"
}

expect_state() { # expect_state <label> <cle=valeur>
  local label="$1" want="$2"
  if grep -qx "$want" "$STATE" 2>/dev/null; then
    echo "  PASS  $label ($want)"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $label — '$want' absent de l'etat : $(tr '\n' ' ' <"$STATE" 2>/dev/null)"
    FAIL=$((FAIL + 1))
  fi
}

echo "== 1. Le scenario de l'incident : 80% stable, 5 polls =="
run 80
expect "1er run = franchissement OK->SOFT" 1
expect_state "etat persiste" "LAST_TIER=SOFT"
run 80
run 80
run 80
run 80
expect "4 polls suivants = SILENCE (avant le fix : 4 notifs)" 0

echo "== 2. Bande morte : 78% (entre CLEAR=77 et SOFT=80) =="
run 78
expect "78% ne declenche PAS de retour au vert" 0
expect_state "palier conserve dans la bande morte" "LAST_TIER=SOFT"
run 80
expect "retour a 80% depuis la bande morte = toujours silence" 0

echo "== 3. Anti-clignotement 79<->80 (le piege du seuil pile dessus) =="
run 79
run 80
run 79
run 80
run 79
run 80
expect "6 oscillations = 0 notif" 0

echo "== 4. Retour a la normale sous CLEAR =="
run 70
expect "70% < 77% = 1 notif verte" 1
expect_state "etat remis a OK" "LAST_TIER=OK"
run 70
run 75
expect "sous le seuil = silence (75% dans la bande, etat deja OK)" 0

echo "== 5. Rappel de stagnation =="
run 80
expect "re-franchissement" 1
age_state 90000 # > 86400 (REMINDER_SEC a SOFT)
run 80
expect "rappel echu = 1 notif" 1
run 80
expect "juste apres le rappel = silence" 0

echo "== 5b. Rappel CRITIQUE : 1h a MID/HARD, pas 24h =="
run 95
expect "escalade SOFT->HARD" 1
age_state 5000 # > 3600 mais << 86400
run 95
expect "rappel critique echu apres ~1h30 (pas 24h)" 1

echo "== H1. Gain de purge repete : le piege du finding HIGH n1 =="
run 70 >/dev/null
: >"$SENT" # remise a OK
run_purge 80 79
expect "1er run : escalade OK->SOFT (delta 1 < 2 = pas un gain)" 1
run_purge 80 79
run_purge 80 79
run_purge 80 79
run_purge 80 79
expect "4 runs 80->79 supplementaires = SILENCE (avant fix : 4 notifs)" 0

echo "== H1b. Gain SIGNIFICATIF : notifie, mais une seule fois par heure =="
run 70 >/dev/null
: >"$SENT"
run_purge 80 76 # escalade OK->SOFT + purge de 4 pts
expect "1re detection + gain = 1 notif" 1
run_purge 80 76
run_purge 80 76
run_purge 80 76
expect "3 repetitions dans l'heure = differees (plancher)" 0
age_state 4000
run_purge 80 76
expect "apres expiration du plancher = 1 notif" 1

echo "== H1c. Oscillation autour du palier MID (le 4e canal de spam) =="
# 88% -> purge -> 84% -> se remplit -> 88% ... Chaque run REDETECTE MID. Si l'escalade se
# jugeait sur l'etat courant et non sur le dernier palier NOTIFIE, chaque run contournerait
# le plancher = 96 msg/jour par un 4e chemin.
run 70 >/dev/null
: >"$SENT"
run_purge 88 84
expect "1er run : detection MID = 1 notif" 1
run_purge 88 84
run_purge 88 84
run_purge 88 84
run_purge 88 84
expect "4 oscillations MID<->SOFT suivantes = SILENCE" 0
run 95
expect "une VRAIE aggravation (HARD) passe immediatement malgre le plancher" 1

echo "== H2. Re-escalade HARD apres passage en bande morte (finding HIGH n2) =="
run 70 >/dev/null
: >"$SENT"
run 95
expect "montee a 95% = 1 notif HARD" 1
expect_state "etat HARD" "LAST_TIER=HARD"
run 78
expect "78% (bande morte) = silence" 0
expect_state "RETROGRADE a SOFT (sinon la remontee serait muette)" "LAST_TIER=SOFT"
# Compromis assume : HARD ayant deja ete notifie il y a moins de MIN_NOTIFY_SEC, la
# remontee est DIFFEREE, pas perdue. Le finding HIGH n2 denoncait 24h de silence ; la
# borne est ici le plancher (1h), et REMINDER_CRITICAL_SEC (1h) la garantit aussi.
run 95
expect "remontee a 95% dans l'heure = differee (anti-rafale)" 0
age_state 4000
run 95
expect "et elle part bien a l'expiration du plancher (borne : 1h, pas 24h)" 1
expect_state "etat HARD retabli" "LAST_TIER=HARD"

echo "== H2b. Un run qui purge 95% -> 78% ne doit pas etre silencieux =="
run 70 >/dev/null
: >"$SENT"
run_purge 95 78
expect "detection HARD malgre l'atterrissage en bande morte = 1 notif" 1
expect_state "etat persiste = SOFT (ce qui reste)" "LAST_TIER=SOFT"

echo "== H3. Etat non ecrivable (disque plein) : signal, pas spam silencieux =="
run 70 >/dev/null
: >"$SENT"
chmod 0500 "$WORK/state"
run 95
expect_rc "echec d'ecriture = code de sortie non nul" 1
chmod 0700 "$WORK/state"

echo "== 6. Echec curl : l'etat ne doit PAS avancer, et l'unite doit echouer =="
run 70
: >"$SENT" # remise a OK
run 92 1
expect "notif tentee malgre l'echec" 1
expect_rc "echec de notif = code de sortie non nul" 1
expect_state "palier NON avance apres echec" "LAST_TIER=OK"
run 92
expect "retente au poll suivant = 1 notif" 1
expect_rc "succes = rc 0" 0
expect_state "palier avance apres succes" "LAST_TIER=HARD"

echo "== 7. State file tronque =="
echo "LAST_TIER=HARD" >"$STATE" # LAST_ALERT manquante = sentinelle absente
run 80
expect "etat corrompu = reinit + notif de franchissement" 1
expect_state "reinitialise proprement" "LAST_TIER=SOFT"

echo "== 8. Mesure df impossible =="
: >"$SENT"
FAKE_DF_FAIL=1 run 80
expect "df en echec = aucune notif (pas de faux retour au vert)" 0
expect_rc "df en echec = code de sortie non nul (avant : exit 0 muet)" 1
expect_state "etat intact" "LAST_TIER=SOFT"

echo "== 9. Horloge qui recule (LAST_ALERT dans le futur) =="
run 70 >/dev/null
: >"$SENT"
run 95
: >"$SENT"
sed -i "s/^LAST_ALERT=.*/LAST_ALERT=$(($(date +%s) + 999999))/" "$STATE"
run 95
expect "LAST_ALERT futur remis a zero = le rappel peut echoir" 1

echo "== 10. Reliquat .tmp d'un run tue =="
run 70 >/dev/null
touch "${STATE}.tmp.99999"
run 80 >/dev/null
if [ -z "$(find "$WORK/state" -name 'state.tmp.*' -print -quit)" ]; then
  echo "  PASS  reliquat .tmp nettoye au demarrage"
  PASS=$((PASS + 1))
else
  echo "  FAIL  reliquat .tmp non nettoye"
  FAIL=$((FAIL + 1))
fi

echo
echo "TOTAL : $PASS pass, $FAIL fail"
[ "$FAIL" -eq 0 ]
