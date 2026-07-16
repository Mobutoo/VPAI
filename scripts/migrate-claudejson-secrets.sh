#!/usr/bin/env bash
# migrate-claudejson-secrets.sh — P1a-bis : sort les 9 littéraux de ~/.claude.json
# vers ~/.config/claude/secrets.env (600) et remplace par des refs ${VAR}.
#
# RÉEXÉCUTABLE (parade au hazard clobber : le CLI Claude Code réécrit ~/.claude.json
# depuis sa copie mémoire → une édition in-session peut être écrasée ; relancer ce
# script sessions fermées si le re-run post-boot du détecteur retrouve des littéraux).
# Idempotent : n'ajoute au store que les clés absentes ; ne touche que les valeurs
# encore littérales. Valeurs JAMAIS affichées. Écritures atomiques.
# Gate : scripts/secrets-migration-check.sh (le run DÉFINITIF = post-boot).
set -euo pipefail

python3 - <<'PY'
import json, os, re, shlex, sys, tempfile

home = os.path.expanduser('~')
cj_path = os.path.join(home, '.claude.json')
env_path = os.path.join(home, '.config', 'claude', 'secrets.env')

d = json.load(open(cj_path))
srv = d.get('mcpServers', {}) or {}

def lit(v): return isinstance(v, str) and '${' not in v

# (serveur, section, clé config) -> nom de var store
MAP = [
    ('qdrant',        'env',     'QDRANT_API_KEY',               'QDRANT_API_KEY'),
    ('plane',         'env',     'PLANE_API_KEY',                'PLANE_API_KEY'),
    ('stitch',        'env',     'STITCH_API_KEY',               'STITCH_API_KEY'),
    ('nocodb',        'env',     'NOCODB_API_TOKEN',             'NOCODB_TOKEN'),
    ('github',        'env',     'GITHUB_PERSONAL_ACCESS_TOKEN', 'GITHUB_PERSONAL_ACCESS_TOKEN'),
    ('postgres',      'env',     'POSTGRES_CONNECTION_STRING',   'POSTGRES_CONNECTION_STRING'),
    ('canva-connect', 'headers', 'x-api-key',                    'CANVA_X_API_KEY'),
    ('n8n-docs',      'headers', 'Authorization',                'N8N_DOCS_AUTHORIZATION'),
    ('trek',          'headers', 'Authorization',                'TREK_AUTHORIZATION'),
]

# 1) Charger le store existant (clés seulement).
store = {}
if os.path.exists(env_path):
    for line in open(env_path):
        m = re.match(r'([A-Z0-9_]+)=', line)
        if m: store[m.group(1)] = True

# 2) Extraire vers le store les valeurs littérales dont la clé store est absente.
additions = {}
for server, section, ckey, vname in MAP:
    c = srv.get(server, {})
    val = (c.get(section) or {}).get(ckey)
    if lit(val) and vname not in store and vname not in additions:
        additions[vname] = val

if additions:
    os.umask(0o077)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(env_path))
    with os.fdopen(fd, 'w') as f:
        if os.path.exists(env_path):
            f.write(open(env_path).read())
        for k, v in additions.items():
            f.write(f'{k}={shlex.quote(v)}\n')
    os.chmod(tmp, 0o600); os.replace(tmp, env_path)
print(f"store: +{len(additions)} clé(s) : {' '.join(sorted(additions)) or '(aucune)'}")

# 3) Remplacer les littéraux par des refs ${VAR} dans ~/.claude.json (atomique).
changed = 0
for server, section, ckey, vname in MAP:
    c = srv.get(server, {})
    sec = c.get(section)
    if sec and lit(sec.get(ckey)):
        sec[ckey] = '${' + vname + '}'
        changed += 1
if changed:
    fd, tmp = tempfile.mkstemp(dir=home)
    with os.fdopen(fd, 'w') as f:
        json.dump(d, f, indent=2)
    os.chmod(tmp, 0o600); os.replace(tmp, cj_path)
print(f"~/.claude.json : {changed} entrée(s) -> ${{VAR}}")
PY
