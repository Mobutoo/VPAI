# Migration secrets config (classe B + consolidation) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sortir tous les secrets en clair des 5 fichiers de config Claude Code (`~/.claude/mcp.json`, `~/.claude/settings.json`, `VPAI/.claude/settings.local.json`, `~/.bashrc`, `~/.profile`) vers un store unique `~/.config/claude/secrets.env` (chmod 600) sourcé avant `claude`, avec refs `${VAR}` dans les configs et retrait des règles allow porteuses de secret — jusqu'à ce que `scripts/secrets-migration-check.sh` retourne 0 violation.

**Architecture:** Store 600 unique sourcé par `~/.bashrc` (que `~/.profile` source déjà → couvre login + interactif → hérité par `claude` au lancement, donc les `${VAR}` de mcp.json résolvent au boot des serveurs MCP). Classe B (vars lues par Claude Code/hooks au démarrage) y vit à demeure ; classe A (tokens de commande NOCODB/MACGYVER/HCLOUD/NAMECHEAP/LITELLM) y vit en **interim** (promue vers Vaultwarden au plan P1b). pg/django PROD = règles allow **retirées** (re-prompt). Le détecteur `secrets-migration-check.sh` (déjà écrit + prouvé non-aveugle : 19 violations sur l'état actuel) est le harnais de test.

**Tech Stack:** bash, python3 (édition JSON sûre), chmod ; détecteur `scripts/secrets-migration-check.sh`.

**Périmètre :** phase **P1a** du spec `docs/superpowers/specs/2026-07-16-coffre-agents-unifie-design.md`. Les phases P0 (fondations Vaultwarden), P1b (classe A → Vaultwarden), P2 (redacteur/guard/scrubber), P3 (Tier 2), P4 (durcissement) = **plans séparés**.

**⚠️ Modifie l'environnement LIVE** (`~/.claude`, `~/.bashrc`, `~/.profile`). Chaque tâche : backup horodaté → changement → détecteur → smoke → commit. Rollback = restaurer le `.bak`. Les changements `.bashrc`/`.env` n'affectent que les **nouveaux** shells ; un smoke MCP complet nécessite une session `claude` fraîche (noté en clôture).

---

## Fichiers touchés

- Create: `~/.config/claude/secrets.env` (600) — store unique des secrets runtime.
- Modify: `~/.bashrc` — source le store ; retire 5 exports en clair.
- Modify: `~/.profile` — retire 5 exports en clair (redondants).
- Modify: `~/.claude/mcp.json` — 4 littéraux → `${VAR}`.
- Modify: `~/.claude/settings.json` — retire 2 clés du bloc `env` + règles allow à secret.
- Modify: `/home/mobuone/work/infra/VPAI/.claude/settings.local.json` — retire règles allow pg/django/litellm.
- Gate: `/home/mobuone/work/infra/VPAI/scripts/secrets-migration-check.sh` (déjà présent).

Note dépôts git : `~/.claude` est un dépôt git local (jamais push) — commits config là. `VPAI` (github-seko) — commit `settings.local.json` **non** (gitignored) ; commit le détecteur/plan/spec seulement. `~/.bashrc`/`~/.profile` = hors git → backups seuls.

---

### Task 0: Pré-vol — backups + baseline détecteur

**Files:**
- Create: `~/.config/claude/` (dir), `*.bak-P1a-<ts>` de chaque fichier.

- [ ] **Step 1: Backups horodatés des 5 fichiers + du dépôt ~/.claude**

```bash
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p ~/.config/claude
for f in ~/.claude/mcp.json ~/.claude/settings.json ~/.bashrc ~/.profile \
         /home/mobuone/work/infra/VPAI/.claude/settings.local.json; do
  cp "$f" "$f.bak-P1a-$TS"
done
echo "backups .bak-P1a-$TS"
```

- [ ] **Step 2: Baseline — le détecteur DOIT trouver des violations (non-aveugle)**

Run: `bash /home/mobuone/work/infra/VPAI/scripts/secrets-migration-check.sh --self-test`
Expected: `SELF-TEST OK : détecteur trouve 19 violation(s)…` exit 0. Noter le compte de départ (19).

- [ ] **Step 3: Commit du point de départ (détecteur + plan + spec, côté VPAI)**

```bash
cd /home/mobuone/work/infra/VPAI
git add scripts/secrets-migration-check.sh docs/superpowers/plans/2026-07-16-migration-secrets-classe-b.md
git commit -m "chore(secrets): gate migration + plan P1a (baseline 19 violations)"
```

---

### Task 1: Store 600 + sourcing, sans encore retirer les clairs

**Files:**
- Create: `~/.config/claude/secrets.env`
- Modify: `~/.bashrc` (ajoute le sourcing en tête)

- [ ] **Step 1: Écrire le store 600 avec TOUS les secrets runtime (depuis les BACKUPS)**

Extraction robuste (corrige revue B1/B2/M1) : lit les **backups** Task 0 (pas les fichiers live → re-run sûr même après Task 2/5) ; **guard idempotent** (n'écrase pas un store peuplé) ; headers ciblés **par nom** (pas last-wins → évite le bug canva `Accept`) ; écriture **quotée** `shlex.quote` (valeurs à espace comme `Bearer …` sourçables sans bug/fuite). Valeurs jamais affichées.

```bash
python3 - <<'PY'
import json, os, re, glob, shlex, sys
home=os.path.expanduser('~')
env=os.path.join(home,'.config','claude','secrets.env')
os.makedirs(os.path.dirname(env), exist_ok=True)
# M1 : guard idempotent — ne JAMAIS écraser un store déjà peuplé (re-run sûr).
if os.path.exists(env) and os.path.getsize(env)>0:
    print("store déjà peuplé — skip (idempotent)"); sys.exit(0)
def newest(pat):
    fs=sorted(glob.glob(pat), key=os.path.getmtime); return fs[-1] if fs else None
mcp_bak=newest(home+'/.claude/mcp.json.bak-P1a-*')
set_bak=newest(home+'/.claude/settings.json.bak-P1a-*')
sh_baks=[b for b in (newest(home+'/.bashrc.bak-P1a-*'), newest(home+'/.profile.bak-P1a-*')) if b]
assert mcp_bak and set_bak, "backups Task 0 introuvables — relancer Task 0"
def lit(v): return isinstance(v,str) and '${' not in v
out={}
# mcp.json : env littéraux (KEY/TOKEN/SECRET) + headers ciblés PAR NOM (B1 fix)
d=json.load(open(mcp_bak)); srv=d.get('mcpServers',{})
for name,c in srv.items():
    for k,v in (c.get('env') or {}).items():
        if lit(v) and re.search(r'KEY|TOKEN|SECRET',k): out[k]=v
HDR={'n8n-docs':('Authorization','N8N_DOCS_AUTHORIZATION'),
     'canva-connect':('x-api-key','CANVA_X_API_KEY')}   # header EXACT, jamais 'Accept'
for name,(hname,vn) in HDR.items():
    h=(srv.get(name,{}).get('headers') or {})
    if hname in h and lit(h[hname]): out[vn]=h[hname]
# settings.json env
s=json.load(open(set_bak))
for k in ('TELEGRAM_BOT_TOKEN','AF_WEBHOOK_SECRET'):
    v=(s.get('env') or {}).get(k)
    if isinstance(v,str) and v: out[k]=v
# exports shell (depuis backups)
SHELL_KEYS={'QDRANT_API_KEY','TELEGRAM_BOT_TOKEN','STITCH_API_KEY','NOCODB_TOKEN',
            'MACGYVER_BOT_TOKEN','HCLOUD_TOKEN','NAMECHEAP_API_KEY'}
for bak in sh_baks:
    for line in open(bak):
        m=re.match(r'\s*export\s+([A-Z0-9_]+)=(.*)',line)
        if not m: continue
        k,v=m.group(1), m.group(2).strip().strip('"').strip("'")
        if k in SHELL_KEYS and k not in out and v: out[k]=v
# B2 fix : écriture QUOTÉE (espaces/spéciaux sûrs au sourcing `. file`)
# Revue : écriture ATOMIQUE (temp + rename) — jamais de store à moitié écrit qui
# passerait le guard/gate en cas de crash mid-write.
os.umask(0o077)
tmp=env+'.tmp'
with open(tmp,'w') as f:
    for k,v in out.items(): f.write(f'{k}={shlex.quote(v)}\n')
os.chmod(tmp,0o600); os.rename(tmp,env)
print(f"{len(out)} secrets écrits (quotés, atomique). clés:", ' '.join(sorted(out)))
PY
```

- [ ] **Step 2: Vérifier perms 600 + n° de clés attendu (≥11 uniques)**

Run: `ls -l ~/.config/claude/secrets.env && grep -c '=' ~/.config/claude/secrets.env`
Expected: `-rw-------` ; compte ≥ 11.

- [ ] **Step 3: Sourcer le store en tête de `~/.bashrc`**

Ajouter (idempotent) au tout début de `~/.bashrc` :

```bash
grep -q 'claude/secrets.env' ~/.bashrc || sed -i '1i # Claude secrets store (600) — sourcé avant tout (MCP boot)\nif [ -f "$HOME/.config/claude/secrets.env" ]; then set -a; . "$HOME/.config/claude/secrets.env"; set +a; fi' ~/.bashrc
head -3 ~/.bashrc
```

- [ ] **Step 4: Smoke — sourcing PROPRE + intégrité des valeurs (fix M2/B2)**

Run (3 assertions ; valeurs jamais affichées) :
```bash
# (a) B2 : sourcing sans erreur (0 "command not found" = pas de valeur à espace mal quotée)
CNF=$(bash -lc 'true' 2>&1 1>/dev/null | grep -c 'command not found' || true)
[ "$CNF" = "0" ] && echo "a) sourcing propre (0 command-not-found)" || { echo "a) ÉCHEC : fuite/parse-bug au sourcing"; exit 1; }
# (b) B2 : la valeur à espace est intègre (commence par 'Bearer ')
bash -lc '[ "${N8N_DOCS_AUTHORIZATION#Bearer }" != "$N8N_DOCS_AUTHORIZATION" ] && echo "b) N8N Authorization = Bearer ... ok" || { echo "b) ÉCHEC : N8N vide/cassé"; exit 1; }'
# (c) toutes les vars résolvent (drapeau :+set, jamais la valeur ; inclut CANVA fix B1)
bash -lc 'for v in QDRANT_API_KEY TELEGRAM_BOT_TOKEN PLANE_API_KEY CANVA_X_API_KEY N8N_DOCS_AUTHORIZATION AF_WEBHOOK_SECRET; do echo "c) $v ${!v:+set}"; done'
```
Expected : `a) sourcing propre` ; `b) N8N Authorization = Bearer ... ok` ; chaque ligne `c) <VAR> set`.
> Note B1 (canva) : l'intégrité de `CANVA_X_API_KEY` (valeur correcte, pas celle d'`Accept`) n'est prouvable qu'en **session `claude` fraîche** (auth canva réelle) — cf Task 6 §validation session fraîche. Le drapeau `set` ne garantit que la présence.

- [ ] **Step 5: Commit (~/.claude n'est pas concerné ici ; .bashrc hors git → backup seul)**

```bash
echo "store créé + sourcing câblé ; backups Task 0 = rollback"
```

---

### Task 2: mcp.json — 4 littéraux → `${VAR}`

**Files:**
- Modify: `~/.claude/mcp.json`

- [ ] **Step 1: Remplacer les littéraux par des refs `${VAR}` (édition JSON sûre)**

```bash
python3 - <<'PY'
import json,os,re
p=os.path.expanduser('~/.claude/mcp.json'); d=json.load(open(p))
srv=d['mcpServers']
def lit(v): return isinstance(v,str) and '${' not in v
for name,c in srv.items():
    for k,v in list((c.get('env') or {}).items()):
        if lit(v) and re.search(r'KEY|TOKEN|SECRET',k): c['env'][k]='${'+k+'}'
    # Le store contient la valeur ENTIÈRE du header (ex. "Bearer xxx") → ref valeur-entière
    # (ne PAS re-préfixer "Bearer", sinon double-Bearer).
    hmap={'n8n-docs':('Authorization','${N8N_DOCS_AUTHORIZATION}'),
          'canva-connect':('x-api-key','${CANVA_X_API_KEY}')}
    if name in hmap and c.get('headers'):
        hk,rep=hmap[name]
        if hk in c['headers'] and '${' not in c['headers'][hk]: c['headers'][hk]=rep
json.dump(d,open(p,'w'),indent=2); print("mcp.json migré")
PY
python3 -c "import json;json.load(open('/home/mobuone/.claude/mcp.json'));print('JSON valide')"
```

- [ ] **Step 2: Détecteur — les 4 violations mcp.json disparaissent**

Run: `bash /home/mobuone/work/infra/VPAI/scripts/secrets-migration-check.sh | grep mcp.json || echo "0 violation mcp.json"`
Expected: `0 violation mcp.json`.

- [ ] **Step 3: Commit dans ~/.claude**

```bash
cd ~/.claude && git add mcp.json && git commit -m "secrets(P1a): mcp.json littéraux -> \${VAR} (4 serveurs)"
```

---

### Task 3: settings.json — retirer clés env + règles allow à secret

**Files:**
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: Supprimer `TELEGRAM_BOT_TOKEN` + `AF_WEBHOOK_SECRET` du bloc `env` (littéral only) et les règles allow portant le secret webhook**

```bash
python3 - <<'PY'
import json,os
p=os.path.expanduser('~/.claude/settings.json'); d=json.load(open(p))
for k in ('TELEGRAM_BOT_TOKEN','AF_WEBHOOK_SECRET'):
    (d.get('env') or {}).pop(k,None)
allow=(d.get('permissions',{}) or {}).get('allow',[])
# n2 fix : discriminant PROPRE (header AF_WEBHOOK), pas un hex large (éviterait un
# éventuel SHA git). Vérifié : exactement 2 règles portent ce header.
kept=[a for a in allow if not (isinstance(a,str) and 'Telegram-Bot-Api-Secret-Token' in a)]
print(f"allow settings.json {len(allow)} -> {len(kept)}")
d['permissions']['allow']=kept
json.dump(d,open(p,'w'),indent=2); print("settings.json nettoyé")
PY
python3 -c "import json;json.load(open('/home/mobuone/.claude/settings.json'));print('JSON valide')"
```

- [ ] **Step 2: Détecteur — plus de violation settings.json**

Run: `bash /home/mobuone/work/infra/VPAI/scripts/secrets-migration-check.sh | grep 'settings.json ' || echo "0 violation settings.json"`
Expected: `0 violation settings.json`.

- [ ] **Step 3: Smoke — le hook Stop voit toujours AF_WEBHOOK_SECRET depuis l'env de session**

Run: `bash -lc 'echo "AF set? ${AF_WEBHOOK_SECRET:+yes}"'`
Expected: `AF set? yes` (fourni par le store, plus par settings.json).

- [ ] **Step 4: Commit**

```bash
cd ~/.claude && git add settings.json && git commit -m "secrets(P1a): settings.json retire 2 clés env + allow à secret"
```

---

### Task 4: settings.local.json — retirer règles allow pg/django/litellm

**Files:**
- Modify: `/home/mobuone/work/infra/VPAI/.claude/settings.local.json`

- [ ] **Step 1: Retirer les règles allow contenant pg PROD / django / LITELLM**

```bash
python3 - <<'PY'
import json,re
p='/home/mobuone/work/infra/VPAI/.claude/settings.local.json'; d=json.load(open(p))
allow=(d.get('permissions',{}) or {}).get('allow',[])
pat=re.compile(r'postgresql://[^:]+:[^@]+@|is_email_verified|DJANGO_SUPERUSER|sk-lm-|LITELLM_API_KEY=|QDRANT_API_KEY=[A-Za-z0-9]')
kept=[a for a in allow if not (isinstance(a,str) and pat.search(a))]
print(f"allow {len(allow)} -> {len(kept)} ({len(allow)-len(kept)} retirées)")
d['permissions']['allow']=kept
json.dump(d,open(p,'w'),indent=2)
PY
python3 -c "import json;json.load(open('/home/mobuone/work/infra/VPAI/.claude/settings.local.json'));print('JSON valide')"
```

- [ ] **Step 2: Détecteur — plus de violation allow retirée**

Run: `bash /home/mobuone/work/infra/VPAI/scripts/secrets-migration-check.sh | grep 'allow' || echo "0 violation allow"`
Expected: `0 violation allow`.

- [ ] **Step 3: Commit — settings.local.json est gitignored → PAS de commit ; backup Task 0 = rollback**

```bash
git -C /home/mobuone/work/infra/VPAI check-ignore .claude/settings.local.json && echo "gitignored: pas de commit (backup seul)"
```

---

### Task 5: Retirer les exports en clair de `.bashrc`/`.profile`

**Files:**
- Modify: `~/.bashrc`, `~/.profile`

- [ ] **Step 1: Commenter/retirer les 7 lignes `export <SECRET>=…` (le store les fournit désormais)**

```bash
for f in ~/.bashrc ~/.profile; do
  for k in QDRANT_API_KEY TELEGRAM_BOT_TOKEN STITCH_API_KEY NOCODB_TOKEN \
           MACGYVER_BOT_TOKEN HCLOUD_TOKEN NAMECHEAP_API_KEY; do
    sed -i -E "s|^\s*export\s+$k=.*|# [migré vers ~/.config/claude/secrets.env — P1a] export $k=…|" "$f"
  done
done
echo "exports en clair commentés"
```

- [ ] **Step 2: Détecteur — 0 violation TOTAL**

Run: `bash /home/mobuone/work/infra/VPAI/scripts/secrets-migration-check.sh; echo "exit=$?"`
Expected: `OK : 0 secret en clair résiduel sur les cibles connues.` exit=0.

- [ ] **Step 3: Smoke — un shell frais résout encore tout depuis le store (pas via les exports retirés)**

Run: `bash -lc 'for v in QDRANT_API_KEY TELEGRAM_BOT_TOKEN NOCODB_TOKEN HCLOUD_TOKEN STITCH_API_KEY; do echo "$v ${!v:+ok}"; done'`
Expected: chaque ligne `… ok`.

- [ ] **Step 4: Commit (fichiers hors git → note seule)**

```bash
echo "P1a terminé : détecteur 0 violation ; rollback = .bak-P1a-<ts>"
```

---

### Task 6: Vérification finale + note de clôture

- [ ] **Step 1: Gate complet vert + self-test toujours non-aveugle**

Run:
```bash
bash /home/mobuone/work/infra/VPAI/scripts/secrets-migration-check.sh; echo "gate exit=$?"
# Contre-preuve : sur le backup pré-migration le plus RÉCENT (n1 : jamais un glob
# multi-source vers un fichier), le détecteur doit ENCORE trouver des violations.
PT=/tmp/pretest; mkdir -p $PT
cp "$(ls -t ~/.claude/mcp.json.bak-P1a-* | head -1)" $PT/mcp.json
CLAUDE_HOME=$PT bash /home/mobuone/work/infra/VPAI/scripts/secrets-migration-check.sh | grep -c VIOLATION
rm -rf $PT
```
Expected: gate exit=0 ; le run sur backup montre ≥1 VIOLATION (détecteur toujours discriminant).

- [ ] **Step 2: Validation SESSION FRAÎCHE (obligatoire) + note reprise P1b**

⚠️ **Suspect n°1 (revue m4)** : aucun `${VAR}` en **header** n'existe dans ce mcp.json aujourd'hui (tous les `${VAR}` actuels sont en `env`) — l'interpolation header est doc-MEDIUM sans précédent local. Donc à la **prochaine session `claude`** (les `${VAR}` se lisent au boot MCP, pas à chaud), valider explicitement que **n8n-docs** et **canva-connect** s'authentifient (les 2 serveurs à header migré, et canva = cible du fix B1). Si l'un échoue → suspecter d'abord l'interpolation header, puis la valeur canva.

Documenter (spec/STATUS) :
- **Classe A en interim (store)** : NOCODB/MACGYVER/HCLOUD/NAMECHEAP (issus des exports shell) vivent temporairement dans `secrets.env` → à **promouvoir vers Vaultwarden + retirer du store + roter** au plan P1b.
- **LITELLM = RETIRÉ (pas stocké)** : `LITELLM_API_KEY` n'existe que dans des règles allow `settings.local` supprimées par Task 4 → il n'entre PAS dans le store (aucun chemin d'extraction). C'est *plus correct* vis-à-vis de la doctrine classe A (ne doit pas vivre dans l'env de session). P1b le récupère depuis le **backup Task 0** (pas depuis le store) pour l'importer dans Vaultwarden + rotation.
- **O4 tranché (m1)** : `claude` est lancé **interactivement** (`/home/mobuone/.local/bin/claude`, chaîne `.profile`→`.bashrc` confirmée) → sourcing `.bashrc` **suffit**, aucun consommateur MCP systemd (`cc-improvement-loop` lance un script sans réseau). `EnvironmentFile=` = **différé** jusqu'à ce qu'un `claude` headless systemd existe (aucun aujourd'hui).

- [ ] **Step 3: Commit final côté VPAI (détecteur + toute doc mise à jour)**

```bash
cd /home/mobuone/work/infra/VPAI
git add -A docs/ scripts/ && git commit -m "docs(secrets): P1a terminé (0 violation) + note reprise P1b"
```

---

## Critères de succès (definition of done)

- `secrets-migration-check.sh` = **0 violation** ET `--self-test` (ou run sur backup) = **≥1** (détecteur non-aveugle).
- `~/.config/claude/secrets.env` = perms **600**, contient tous les secrets runtime.
- `~/.bashrc` source le store avant tout ; 0 export secret en clair dans `.bashrc`/`.profile`.
- mcp.json = `${VAR}` partout ; settings.json = 0 clé secret dans `env` + 0 allow à secret ; settings.local.json = 0 allow pg/django/litellm.
- Un shell frais (`bash -lc`) résout toutes les vars (drapeau `:+yes`, valeur jamais affichée).
- **Reste (hors P1a)** : smoke MCP complet en session fraîche ; P1b promeut classe A → Vaultwarden ; rotation.

## Rollback

Restaurer les `*.bak-P1a-<ts>` (Task 0) ; `git -C ~/.claude revert` des commits mcp.json/settings.json ; `rm ~/.config/claude/secrets.env` ; retirer la ligne de sourcing en tête de `.bashrc`.
