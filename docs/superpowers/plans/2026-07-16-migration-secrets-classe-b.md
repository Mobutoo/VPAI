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

- [ ] **Step 1: Écrire le store 600 avec TOUS les secrets runtime**

Récupérer chaque valeur depuis sa source actuelle (jamais l'afficher au terminal). Script d'extraction (écrit directement dans le store) :

```bash
umask 077
ENV=~/.config/claude/secrets.env
: > "$ENV"   # part vide, perms 600 via umask
# Depuis mcp.json (env) et .bashrc (valeurs) — extraction programmatique sans echo :
python3 - "$ENV" <<'PY'
import json,sys,re,os
env=sys.argv[1]
out={}
# mcp.json : env littéraux + headers
d=json.load(open(os.path.expanduser('~/.claude/mcp.json')))
srv=d.get('mcpServers',{})
def lit(v): return isinstance(v,str) and '${' not in v
for name,c in srv.items():
    for k,v in (c.get('env') or {}).items():
        if lit(v) and re.search(r'KEY|TOKEN|SECRET',k): out[k]=v
    for hk,hv in (c.get('headers') or {}).items():
        if lit(hv) and len(hv)>=16:
            # nom de var dérivé du serveur (n8n-docs→N8N_DOCS_AUTH, canva→CANVA_X_API_KEY)
            vn={'n8n-docs':'N8N_DOCS_AUTHORIZATION','canva-connect':'CANVA_X_API_KEY'}.get(name)
            if vn: out[vn]=hv
# settings.json env
s=json.load(open(os.path.expanduser('~/.claude/settings.json')))
for k,v in (s.get('env') or {}).items():
    if isinstance(v,str) and re.search(r'TOKEN|SECRET',k): out[k]=v
with open(env,'a') as f:
    for k,v in out.items(): f.write(f'{k}={v}\n')
print(f"{len(out)} secrets config écrits dans le store")
PY
# Ajouter les exports shell (.bashrc/.profile) au store, valeur préservée :
for k in QDRANT_API_KEY TELEGRAM_BOT_TOKEN STITCH_API_KEY NOCODB_TOKEN \
         MACGYVER_BOT_TOKEN HCLOUD_TOKEN NAMECHEAP_API_KEY; do
  grep -q "^$k=" "$ENV" && continue
  val=$(grep -hE "^\s*export\s+$k=" ~/.bashrc ~/.profile 2>/dev/null | head -1 | sed -E "s/^\s*export\s+$k=//; s/^[\"']//; s/[\"']\s*$//")
  [ -n "$val" ] && printf '%s=%s\n' "$k" "$val" >> "$ENV"
done
chmod 600 "$ENV"
echo "clés dans le store (noms only):"; grep -oE '^[A-Z0-9_]+' "$ENV" | sort -u
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

- [ ] **Step 4: Smoke — un shell frais résout les vars depuis le store**

Run: `bash -lc 'echo "QDRANT set? ${QDRANT_API_KEY:+yes}; TELEGRAM set? ${TELEGRAM_BOT_TOKEN:+yes}; PLANE set? ${PLANE_API_KEY:+yes}"'`
Expected: `QDRANT set? yes; TELEGRAM set? yes; PLANE set? yes` (valeurs jamais affichées, juste le drapeau `:+yes`).

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
import json,os,re
p=os.path.expanduser('~/.claude/settings.json'); d=json.load(open(p))
for k in ('TELEGRAM_BOT_TOKEN','AF_WEBHOOK_SECRET'):
    (d.get('env') or {}).pop(k,None)
allow=(d.get('permissions',{}) or {}).get('allow',[])
d['permissions']['allow']=[a for a in allow if not (isinstance(a,str) and re.search(r'[A-Fa-f0-9]{32,}',a))]
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
# Contre-preuve : sur un backup pré-migration, le détecteur doit ENCORE trouver des violations
CLAUDE_HOME=/tmp/pretest; mkdir -p $CLAUDE_HOME
cp ~/.claude/mcp.json.bak-P1a-* $CLAUDE_HOME/mcp.json 2>/dev/null && \
  CLAUDE_HOME=$CLAUDE_HOME bash /home/mobuone/work/infra/VPAI/scripts/secrets-migration-check.sh | grep -c VIOLATION
rm -rf $CLAUDE_HOME
```
Expected: gate exit=0 ; le run sur backup montre ≥1 VIOLATION (détecteur toujours discriminant).

- [ ] **Step 2: Note de reprise pour P1b (classe A → Vaultwarden)**

Documenter dans le spec / STATUS que la classe A (NOCODB/MACGYVER/HCLOUD/NAMECHEAP/LITELLM) vit en **interim** dans `secrets.env` et doit être promue vers Vaultwarden + retirée du store au plan P1b, avec rotation. Smoke MCP complet (qdrant/plane/canva/n8n-docs résolvent) = à la **prochaine session `claude`** (les `${VAR}` se lisent au boot des serveurs MCP, pas rechargeables à chaud).

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
