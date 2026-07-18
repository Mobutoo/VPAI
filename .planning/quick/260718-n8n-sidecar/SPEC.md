# SPEC — Chantier « n8n fiable » : fix -32000, fallback CLI, upgrade Sidecar

- **Date** : 2026-07-18
- **Repo** : VPAI (`/home/mobuone/work/infra/VPAI`)
- **Sources** : HANDOFF `ops/loops/plans/2026-07-18-HANDOFF-n8n-fiabilite-et-memoire.md` ; recherches `.planning/research/n8n-upgrade/{r1,r2,r3,r4}.md` + `r5-repo-gates.md`/`r6-validator.md` (scratchpad session).
- **Décisions humaines fermes** (non re-débattues) : patch enterprise CONSERVÉ mais découplé de l'image de base (Sidecar) ; ordre Volet A (fix -32000) → fallback validator → upgrade Sidecar ; upgrade PROD = **GATE HUMAIN** (code+runbook livrés, pas exécuté) ; prod Sese=amd64 / waza=arm64 → **le mécanisme ne doit PAS builder d'image sur le Pi** ; doctrine « MCP-preferred, CLI-fallback obligatoire sur le chemin critique ».

---

## 0. Décisions d'architecture (justifiées, verrouillées)

### 0.1 Mécanisme Sidecar du patch enterprise = **init-container + volume overlay** (option (b) de R2 §5, raffinée)

**Décision.** Le service `n8n` utilise désormais l'**image officielle** `n8nio/n8n:2.30.7` (fini `ghcr.io/mobutoo/n8n-enterprise`). Un service Compose **one-shot** `n8n-init` (même image officielle, `user: root`, `restart: "no"`) s'exécute AVANT `n8n` via `depends_on: condition: service_completed_successfully`. Il produit un **arbre n8n patché** dans un répertoire bind persistant, que le service `n8n` **monte par-dessus** `/usr/local/lib/node_modules/n8n`.

**Pourquoi (b) et pas (c) « build CI »** : la contrainte ferme dit « patch découplé de l'**image de base** (pattern Sidecar) ». Une image CI reste un artefact couplé `FROM n8nio/n8n:X` → ce n'est pas « découplé de l'image de base », c'est le même couplage relocalisé. (b) applique le patch au **runtime** sur l'image officielle telle que publiée = vraie décorrélation, bump = 1 variable, zéro build. (c) est conservée comme **chemin de rollback documenté** (runbook §Rollback), pas le chemin nominal.

**Pourquoi pas (a) entrypoint-wrapper** : R2 §5 — pas de `su-exec`/`gosu` dans l'image DHI, `su` busybox fork (mauvaise propagation SIGTERM), remplace `tini` PID 1 → casse la gestion des signaux ; incompatible `read_only`. (b) laisse l'entrypoint stock (`tini -- docker-entrypoint.sh → exec n8n`) et l'utilisateur `node` **intacts** : le patch se joue entièrement dans l'init jetable.

**Preuve empirique déjà faite (2026-07-18, `docker --context local`, arm64)** — de-risque LANE-2 :
- Layout pnpm : `/usr/local/lib/node_modules/n8n/node_modules/.pnpm` (**INSIDE** `n8n/`, pas sibling). `license-state.js` résolu sous `n8n/node_modules/.pnpm/@n8n+backend-common@file+.../dist/`. → copier le seul chemin `/usr/local/lib/node_modules/n8n` capture **tous** les fichiers que `patch-enterprise.sh` atteint via `find "$N8N_ROOT"`.
- Overlay boot : `cp -a /usr/local/lib/node_modules/n8n/. → bind dir` (1.8 G, conforme R2), puis `docker run -v <bind>:/usr/local/lib/node_modules/n8n n8nio/n8n:2.30.7 n8n --version` → **`2.30.7`**. La résolution de modules **survit** à l'overlay. C'est le critère d'acceptation #1 de LANE-2, déjà satisfait pour `--version` ; le boot complet (Postgres + UI) reste un gate staging (runbook).

**FAIL LOUD.** `patch-enterprise.sh` sort en `exit 1` si une étape **critique (1/2/3 uniquement)** rate son propre `grep`. L'init hérite (`set -e`) → l'init sort ≠0 → `service_completed_successfully` non satisfait → `n8n` **ne démarre jamais** (échec visible orchestrateur). ⚠️ **Étapes 4 et 5 restent non-fatales (warn only)** : R2 §3 prouve que l'étape 4 (bundle router minifié) NE PEUT PAS matcher et que l'étape 3 (`showNonProdBanner:false`) l'absorbe fonctionnellement. Rendre 4/5 fatales bricke le boot sur un non-problème.

**Idempotence (résout R2 §4.3).** Marqueur `<patched_dir>/.enterprise-patched` = `"<version>:<sha256(patch-enterprise.sh)>"`. L'init : si marqueur == cible → `exit 0` immédiat (aucune copie). Sinon → **`rm -rf` de la copie + `cp -a` FRAÎCHE depuis l'image pristine + patch + réécriture marqueur**. Ne repatch JAMAIS un arbre déjà patché (pas d'accumulation de blocs `LICENSED_BODY`). Coût 1.8 G = one-time **par version** (bind persistant), pas par restart.

### 0.2 Versions cibles (R1, digests vérifiés)

| Composant | Cible | Justification |
|---|---|---|
| **n8n** | `n8nio/n8n:2.30.7` | stable == `:latest` Docker Hub (digest `sha256:23a26975…`) ; node-DB de n8n-mcp 2.65.1 bâtie sur 2.30.x → désync schéma quasi nulle. |
| **n8n-mcp** | `2.65.1` | dernière release ; corrige le défaut `SESSION_TIMEOUT_MINUTES` cassé (5 min) de notre pin `2.40.5` — **le bump SEUL corrige la cause -32000 la plus probable** (R1 §6.1) ; embarque le validateur v2.63.0. |

### 0.3 Validateur CLI fallback (R6 = pivot obligatoire)

R6 a **disqualifié `yigitkonur/n8n-workflow-validator`** : il renvoie `VALID` sur un workflow avec connexion orpheline ET IF v2 type-mismatch (faux négatifs), + pénalité 10-52 s npx sur ARM. **Décision** : l'autorité du fallback R1 = un **validateur structurel Python** (celui déjà dans `deploy-workflow.sh`, extrait dans `scripts/n8n-validate-fallback.sh` et enrichi) qui attrape exactement ce que yigitkonur rate (connexions orphelines des deux côtés, doublons de noms, détection IF v2). L'appel HTTP **stateless** vers le n8n-mcp local 2.65.1 est **best-effort informatif uniquement** — jamais il ne fait passer un PASS structurel à FAIL, jamais il ne bloque si injoignable (R6 n'a pas pu le tester sous 2.40.5, et « single-shot HTTP évite l'expiration de session » est une hypothèse non prouvée). Le gate R1 doit être satisfiable par le seul check Python.

### 0.4 Sort de R9 (IF v2)

R3 §2.3 : ni prouvé corrigé, ni cassé (schéma IF passé à 2.3 + `builderHint`, aucun commit de fix identifié). R4 : **79 IF v2 déjà en prod 2.7.3, dont 36 dans des workflows ACTIFS qui tournent healthy** → contredit empiriquement « crashe sur TOUTES les conditions ». Décisions :
- **Maintenant (LANE-3)** : le chemin de **déploiement** tolère les IF v2 EXISTANTS (warning bruyant, jamais blocage) — R9 interdit d'ÉCRIRE des IF v2, pas de DÉPLOYER un workflow qui en contient. Défendable même pré-upgrade (prod en exécute déjà 36 sans crash).
- **L'advisory d'AUTORING R9** (hook `loi-op-enforcer.js` sur Write/Edit) **reste en place** jusqu'à revalidation staging.
- **Runbook (LANE-4)** : procédure de revalidation isolée sur staging 2.30.7 (rejouer le cas exact de `docs/rex/REX-SESSION-2026-04-12b.md`). Si corrigé → retrait de R9 (follow-up : CLAUDE.md R9, advisory hook, NOTE fallback). Si non → garder R9 scopé au pattern précis.

### 0.5 Carte de disjonction des fichiers (4 agents, zéro coordination)

| Fichier | Lane |
|---|---|
| `inventory/group_vars/all/versions.yml` | **L1 (exclusif)** |
| `roles/n8n-mcp/tasks/main.yml`, `roles/n8n-mcp/defaults/main.yml` | L1 |
| `roles/n8n/files/patch-enterprise.sh`, `roles/n8n/files/n8n-enterprise-init.sh` (new), `roles/n8n/files/Dockerfile` | L2 |
| `roles/n8n/tasks/main.yml`, `roles/n8n/defaults/main.yml`, `roles/n8n/handlers/main.yml` | L2 |
| `roles/docker-stack/templates/compose/apps-core.yml.j2` | L2 |
| `templates/docker-compose.yml.j2` (legacy rollback) | L2 |
| `scripts/n8n-validate-fallback.sh` (new), `scripts/deploy-workflow.sh` | L3 |
| `~/.claude/hooks/n8n-validate-cli-marker.js` (new), `~/.claude/hooks/loi-op-enforcer.js`, `~/.claude/settings.json` | L3 |
| `~/.claude/hooks/test/test-validate-cli-marker.js` (new), `test-enforcer-gates.js`, `harness.js` | L3 |
| `docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md` (new), `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md`, `docs/TROUBLESHOOTING.md`, `CLAUDE.md` | L4 |

**Aucun fichier n'apparaît dans deux lanes.** Seule **dépendance runtime** (pas fichier) : le chemin HTTP best-effort de L3 ne fonctionne qu'une fois le n8n-mcp 2.65.1 de L1 déployé ; jusque-là L3 = structurel-Python seul. Les fichiers ne collisionnent pas → travail parallèle OK.

---

## LANE-1 — n8n-mcp : fix -32000 + bumps de version

**Fichiers** (3) : `inventory/group_vars/all/versions.yml`, `roles/n8n-mcp/tasks/main.yml`, `roles/n8n-mcp/defaults/main.yml`.
**But** : débloquer le -32000 sans toucher n8n (victoire court terme, R1 §6.1) + porter les cibles de version (n8n ET n8n-mcp).

### 1.1 `inventory/group_vars/all/versions.yml`

Remplacer le bloc n8n (lignes ~19-23) :
```yaml
# n8n: image OFFICIELLE — patch enterprise appliqué au runtime (Sidecar init-container).
# Voir roles/n8n/files/n8n-enterprise-init.sh + patch-enterprise.sh. PLUS de build custom.
# Bump = changer ces deux lignes ensemble (image = officielle, version = tag sémantique).
n8n_image: "n8nio/n8n:2.30.7"
n8n_upstream_version: "2.30.7"  # doit == le tag de n8n_image
```
Modifier le pin n8n-mcp (ligne ~130) :
```yaml
n8n_mcp_image_version_pinned: "2.65.1"  # bump 2026-07-18: corrige SESSION_TIMEOUT défaut cassé (5min) de 2.40.5 → -32000 (R1 §6.1) + validateur v2.63.0
```

### 1.2 `roles/n8n-mcp/defaults/main.yml`

- Bumper le fallback de secours : `n8n_mcp_image_version: "{{ n8n_mcp_image_version_pinned | default('2.65.1') }}"`.
- Ajouter (avec commentaires) :
```yaml
# --- Fix -32000 (session HTTP) — R1 §3/§6.1 ---
n8n_mcp_session_timeout_minutes: "30"     # défaut sain rétabli (2.40.5 tournait à 5 = cassé)
n8n_mcp_max_sessions: "50"                 # plafond explicite (défaut upstream 100)
n8n_mcp_auth_rate_limit_max: "1000"        # tentatives auth/IP/fenêtre (défaut upstream 20)
n8n_mcp_trust_proxy: "1"                    # R1 §6.3: NO-OP en topologie actuelle (accès direct Tailscale, pas de route Caddy vers :3001) — posé par directive, sans effet ni risque tant que pas derrière proxy
n8n_mcp_allow_concurrent_sessions: "true"  # R1 §6.1: 2e cause -32000 = éviction éager de session au reconnect
```

### 1.3 `roles/n8n-mcp/tasks/main.yml`

Dans la task `Run n8n-mcp container`, bloc `env:`, ajouter APRÈS `NODE_ENV: "production"` :
```yaml
      SESSION_TIMEOUT_MINUTES: "{{ n8n_mcp_session_timeout_minutes }}"
      N8N_MCP_MAX_SESSIONS: "{{ n8n_mcp_max_sessions }}"
      AUTH_RATE_LIMIT_MAX: "{{ n8n_mcp_auth_rate_limit_max }}"
      TRUST_PROXY: "{{ n8n_mcp_trust_proxy }}"
      MULTI_TENANT_ALLOW_CONCURRENT_SESSIONS: "{{ n8n_mcp_allow_concurrent_sessions }}"
```
(env est un dict → les valeurs doivent être des **strings** ; conserver les guillemets. Ne rien changer d'autre : `state: started` + handler `recreate: true` déjà présents.)

### 1.4 Critères d'acceptation L1

1. `source .venv/bin/activate && make lint` (ansible-lint) passe : FQCN OK, aucun `command`/`shell` ajouté.
2. `grep -c 'n8nio/n8n:2.30.7' inventory/group_vars/all/versions.yml` == 1 ; `n8n_mcp_image_version_pinned` == `2.65.1` ; plus aucune occurrence de `mobutoo/n8n-enterprise` dans versions.yml.
3. Rendu dry-run : `ansible-playbook playbooks/hosts/workstation.yml --tags n8n-mcp --check --diff` montre le conteneur `n8n-mcp` recréé avec les 5 nouvelles env vars et l'image `:2.65.1`.
4. (Déploiement waza = hors gate, autorisé) après `make deploy-n8n-mcp` : `docker --context local inspect n8n-mcp` liste les 5 env vars ; `docker --context local exec n8n-mcp printenv SESSION_TIMEOUT_MINUTES` → `30`.

---

## LANE-2 — roles/n8n : refactor Sidecar (init-container + overlay)

**Fichiers** (8) : `roles/n8n/files/patch-enterprise.sh`, `roles/n8n/files/n8n-enterprise-init.sh` (**new**), `roles/n8n/files/Dockerfile`, `roles/n8n/tasks/main.yml`, `roles/n8n/defaults/main.yml`, `roles/n8n/handlers/main.yml`, `roles/docker-stack/templates/compose/apps-core.yml.j2`, `templates/docker-compose.yml.j2`.
**Interdit** : ne PAS toucher `versions.yml` (référencer `{{ n8n_image }}` / `{{ n8n_upstream_version }}` posés par L1).

### 2.1 `roles/n8n/defaults/main.yml` (ajouts)

```yaml
# --- Sidecar patch enterprise (init-container + overlay volume) ---
n8n_enterprise_dir: "/opt/{{ project_name }}/configs/n8n/enterprise"   # scripts init+patch (RO côté init)
n8n_patched_dir: "/opt/{{ project_name }}/data/n8n-patched"            # arbre node_modules/n8n patché (persistant)
```

### 2.2 `roles/n8n/files/patch-enterprise.sh` (MODIFIER — fail-loud + N8N_ROOT paramétrable + boucle router)

Trois changements chirurgicaux :

**(a) N8N_ROOT paramétrable** (l'init patche une COPIE, pas le chemin image). Ligne 14 :
```sh
N8N_ROOT="${N8N_ROOT:-/usr/local/lib/node_modules/n8n}"
```

**(b) Fail-loud sur étapes critiques 1/2/3 uniquement.** Introduire un flag et faire échouer le script si un des trois `grep` de vérification échoue. Patron :
```sh
CRIT_FAIL=0
# ... étape 1 (license-state.js): dans le else du grep → CRIT_FAIL=1 (au lieu de simple echo WARNING)
# ... étape 2 (license.js):      idem
# ... étape 3 (frontend.service.js): idem
# étapes 4 (router bundle) et 5 (texte i18n): rester en WARNING pur, NE PAS toucher CRIT_FAIL
# ... fin de script:
if [ "$CRIT_FAIL" -ne 0 ]; then
  echo "[patch-enterprise] ✗ FATAL: une étape critique (license-state/license/frontend.service) n'a pas matché — arbre NON déployable" >&2
  exit 1
fi
echo "[patch-enterprise] Done. Enterprise features unlocked."
```
⚠️ Ne PAS transformer les WARNING des étapes 4/5 en fatals (R2 §3 : étape 4 ne matche jamais le bundle minifié, absorbée par l'étape 3).

**(c) Boucle sur tous les `router-*.js`** (R2 §4.2 : deux bundles `router-dp_*` + `router-legacy-*`, `head -1` non déterministe). Étape 4, remplacer le `find … | head -1` par :
```sh
for ROUTER_FILE in $(find "$N8N_ROOT" -name "router-*.js" -path "*/assets/*" 2>/dev/null); do
  sed -i 's/settingsStore\.isEnterpriseFeatureEnabled\.showNonProdBanner/false/g' "$ROUTER_FILE"
done   # non fatal — cosmétique
```

### 2.3 `roles/n8n/files/n8n-enterprise-init.sh` (**NOUVEAU** — entrypoint de l'init-container)

```sh
#!/bin/sh
# n8n-enterprise-init.sh — Sidecar init: produit un arbre n8n patché dans un volume overlay.
# Exécuté en root, restart:no, AVANT le service n8n (depends_on service_completed_successfully).
# Idempotent: skip si le marqueur == (version:hash-du-patch). FAIL LOUD si le patch échoue.
set -eu

SRC="/usr/local/lib/node_modules/n8n"        # arbre pristine de l'image officielle
DST="/patched"                                # bind persistant monté ici (= n8n_patched_dir)
PATCH="/enterprise/patch-enterprise.sh"       # monté RO
MARKER="$DST/.enterprise-patched"

VER="${N8N_TARGET_VERSION:-$(n8n --version 2>/dev/null || echo unknown)}"
PHASH="$(sha256sum "$PATCH" | cut -d' ' -f1)"
WANT="${VER}:${PHASH}"

if [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$WANT" ]; then
  echo "[n8n-init] déjà patché ($WANT) — skip"
  exit 0
fi

echo "[n8n-init] (re)construction de l'arbre patché pour $WANT"
rm -rf "$DST"/..?* "$DST"/.[!.]* "$DST"/* 2>/dev/null || true
cp -a "$SRC"/. "$DST"/
N8N_ROOT="$DST" sh "$PATCH"        # exit≠0 ici (set -e) => init échoue => n8n ne démarre pas (FAIL LOUD)

# garde-fou: refuser un arbre où les cibles critiques ne portent pas la valeur licensed
if ! grep -rq "feat:showNonProdBanner" "$DST"/node_modules/.pnpm/*/node_modules/@n8n/backend-common/dist/license-state.js 2>/dev/null; then
  echo "[n8n-init] ✗ FATAL: license-state.js patché introuvable dans la copie" >&2
  exit 1
fi

printf '%s' "$WANT" > "$MARKER"
echo "[n8n-init] terminé — marqueur=$WANT"
```
Notes :
- `N8N_TARGET_VERSION` est injecté par Compose (= `{{ n8n_upstream_version }}`) pour un marqueur déterministe ; fallback `n8n --version` si absent.
- `n8n --version` fonctionne dans l'init (binaire sur PATH, entrypoint surchargé) — vérifié empiriquement.

### 2.4 `roles/docker-stack/templates/compose/apps-core.yml.j2` (MODIFIER — service init + overlay + depends_on)

**Ajouter le service `n8n-init` juste avant `n8n:`** (garder l'indentation 2 espaces du fichier) :
```yaml
  n8n-init:
    image: {{ n8n_image }}
    container_name: {{ project_name }}_n8n_init
    user: root
    restart: "no"
    entrypoint: ["/bin/sh", "/enterprise/n8n-enterprise-init.sh"]
    environment:
      N8N_TARGET_VERSION: "{{ n8n_upstream_version }}"
    volumes:
      - {{ n8n_enterprise_dir }}:/enterprise:ro
      - {{ n8n_patched_dir }}:/patched
    networks:
      - backend
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```
**Modifier le service `n8n:`** — ajouter `depends_on` et le mount overlay (en tête des volumes, RO) :
```yaml
  n8n:
    image: {{ n8n_image }}
    container_name: {{ project_name }}_n8n
    depends_on:
      n8n-init:
        condition: service_completed_successfully
    # ... (extra_hosts, restart, security_opt, cap_* inchangés) ...
    volumes:
      - {{ n8n_patched_dir }}:/usr/local/lib/node_modules/n8n:ro   # overlay: arbre patché
      - /opt/{{ project_name }}/data/n8n:/home/node/.n8n
      # ... (openclaw ro, mop, carbone inchangés) ...
```
Notes :
- `:ro` sur l'overlay : n8n n'écrit rien dans son propre `node_modules` (les community packages vont dans `~/.n8n/nodes`). **Gate staging** : confirmer au boot complet qu'aucune écriture runtime n'est requise ; si un cas surgit, retirer `:ro`.
- L'utilisateur du service `n8n` reste **stock (`node`)** — pas de `user:` ajouté. `tini` PID 1 et gestion des signaux **intacts**.
- `logging` json-file 10m/3 déjà standard sur le fichier — l'ajouter à `n8n-init` (fait ci-dessus).

### 2.5 `roles/n8n/tasks/main.yml` (MODIFIER — déployer scripts + créer patched_dir)

Ajouter AVANT la task « Deploy n8n environment file » (toutes en `become: true`, tags `[n8n, phase3, apps]`) :
```yaml
- name: Create n8n enterprise scripts directory
  ansible.builtin.file:
    path: "{{ n8n_enterprise_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true
  tags: [n8n, phase3, apps]

- name: Deploy n8n enterprise patch + init scripts
  ansible.builtin.copy:
    src: "{{ item }}"
    dest: "{{ n8n_enterprise_dir }}/{{ item }}"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  loop:
    - patch-enterprise.sh
    - n8n-enterprise-init.sh
  become: true
  notify: Restart n8n stack
  tags: [n8n, phase3, apps]

- name: Create n8n patched-tree directory (overlay volume target)
  ansible.builtin.file:
    path: "{{ n8n_patched_dir }}"
    state: directory
    owner: "root"
    group: "root"
    mode: "0755"
  become: true
  tags: [n8n, phase3, apps]
```
(La task assert HMAC, config dir, data dir, env file restent inchangées. `ansible.builtin.copy` = idempotent ; le `mode: "0755"` sur les `.sh` évite un `chmod` shell.)

### 2.6 `roles/n8n/handlers/main.yml` (MODIFIER — inclure n8n-init dans le restart)

Dans le handler `Restart n8n stack`, changer `services` pour forcer la re-exécution de l'init (sinon un bump de version ne re-patche jamais — R2/advisor) :
```yaml
    services:
      - n8n-init
      - n8n
    state: present
    recreate: always
```
(recreate: always déjà présent — REX TROUBLESHOOTING 11.18. En version inchangée l'init re-tourne mais skip via marqueur = quasi-instantané.)

### 2.7 `roles/n8n/files/Dockerfile` (MODIFIER — en-tête de dépréciation)

Ajouter en tête, sans supprimer le contenu (chemin de rollback (c) du runbook) :
```dockerfile
# DEPRECATED 2026-07-18 — n'est plus le chemin de déploiement nominal.
# Le patch enterprise est désormais appliqué au RUNTIME (Sidecar init-container,
# voir roles/n8n/files/n8n-enterprise-init.sh). Ce Dockerfile n'est conservé que
# comme chemin de rollback (c) « build CI hors Pi » documenté dans
# docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md. NON référencé par versions.yml.
```

### 2.8 `templates/docker-compose.yml.j2` (legacy, rollback only — MODIFIER le bloc n8n)

R5 §1bis + advisor : ce template (utilisé par `playbooks/ops/rollback.yml`) déploierait un n8n **non patché** (bannière revient, features verrouillées) contre une DB migrée. Aligner son bloc `n8n` sur le pattern Sidecar : ajouter le service `n8n-init` et le mount overlay + `depends_on` **identiques** à §2.4 (mêmes variables). Si l'alignement complet est jugé hors périmètre par l'agent, **a minima** insérer un commentaire bloquant en tête du service n8n :
```yaml
      # ⚠️ NE PAS utiliser ce template pour n8n post-Sidecar (2026-07-18): il déploie un
      # n8n NON patché. Rollback n8n = suivre docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md.
```
(La voie complète — dupliquer §2.4 ici — est préférée ; le commentaire est le minimum non négociable. LANE-4 documente aussi cette incompatibilité.)

### 2.9 Critères d'acceptation L2

1. **Overlay boot (déjà prouvé pour `--version`)** : sur waza, `cp -a` de l'arbre `n8nio/n8n:2.30.7` + `N8N_ROOT=<copie> sh patch-enterprise.sh` → `exit 0` ; `grep -rq feat:showNonProdBanner <copie>/.../license-state.js` OK ; `docker --context local run -v <copie>:/usr/local/lib/node_modules/n8n --entrypoint n8n n8nio/n8n:2.30.7 --version` → `2.30.7`.
2. **Fail-loud** : injecter une faute (renommer une méthode dans une copie de license-state.js) → `patch-enterprise.sh` sort `exit 1` avec `FATAL`. Une étape 4/5 en échec ne fait PAS échouer le script (`exit 0`).
3. **Idempotence** : 2e run de l'init avec marqueur inchangé → `skip` + `exit 0`, aucune re-copie. Changement de `N8N_TARGET_VERSION` → re-copie + re-patch + nouveau marqueur.
4. `make lint` : YAML compose valide, FQCN OK, `copy`/`file` idempotents (pas de `command`/`shell`).
5. `ansible-playbook playbooks/stacks/site.yml -e target_env=prod --tags n8n,docker-stack --check --diff` : montre le service `n8n-init`, le `depends_on`, le mount overlay ; **aucun** déploiement réel (gate humain).
6. Handler `Restart n8n stack` recrée `n8n-init` + `n8n`.

---

## LANE-3 — Validateur CLI fallback + durcissement deploy + gate R1

**Fichiers** (7) : `scripts/n8n-validate-fallback.sh` (**new**), `scripts/deploy-workflow.sh`, `~/.claude/hooks/n8n-validate-cli-marker.js` (**new**), `~/.claude/hooks/loi-op-enforcer.js`, `~/.claude/settings.json`, `~/.claude/hooks/test/test-validate-cli-marker.js` (**new**), `~/.claude/hooks/test/{test-enforcer-gates.js,harness.js}`.

### 3.1 `scripts/n8n-validate-fallback.sh` (**NOUVEAU** — autorité structurelle)

```bash
#!/usr/bin/env bash
# n8n-validate-fallback.sh — Validateur R1 fallback, INDÉPENDANT de la session MCP.
# Autorité = check structurel Python (R6: yigitkonur rate connexions orphelines + IF v2).
# HTTP n8n-mcp local = best-effort informatif, ne flippe jamais un PASS→FAIL, ne bloque pas.
# Émet le sentinel "[N8N-VALIDATE-CLI] PASS" sur stdout SEULEMENT si succès.
set -euo pipefail
WF="${1:?usage: n8n-validate-fallback.sh <workflow.json>}"
[ -f "$WF" ] || { echo "[N8N-VALIDATE-CLI] FAIL: fichier introuvable: $WF" >&2; exit 1; }

python3 - "$WF" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"[N8N-VALIDATE-CLI] FAIL: JSON invalide: {e}", file=sys.stderr); sys.exit(1)
names = [n.get('name') for n in d.get('nodes', [])]
nameset = set(names)
errs = []
dupes = sorted({n for n in nameset if names.count(n) > 1})
if dupes: errs.append(f"noms de nodes dupliqués: {dupes}")
missing_src = sorted(set(d.get('connections', {}).keys()) - nameset)
if missing_src: errs.append(f"connexions depuis nodes inconnus: {missing_src}")
for src, outs in d.get('connections', {}).items():
    for branch in (outs.get('main', []) or []):
        for c in (branch or []):
            t = c.get('node')
            if t and t not in nameset:
                errs.append(f"cible de connexion inconnue: {t} (depuis {src})")
ifv2 = [n['name'] for n in d.get('nodes', [])
        if n.get('type') == 'n8n-nodes-base.if' and n.get('typeVersion', 1) >= 2]
if ifv2:
    # R9 = garde-fou d'AUTORING, pas de déploiement (prod exécute déjà 79 IF v2). NOTE, jamais FAIL.
    print(f"[N8N-VALIDATE-CLI] NOTE: IF v2 présents (R9 authoring guard; déploiement toléré): {ifv2}", file=sys.stderr)
if errs:
    print("[N8N-VALIDATE-CLI] FAIL: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
print(f"  structurel OK — {len(names)} nodes, {len(d.get('connections', {}))} sources de connexion", file=sys.stderr)
PY

# best-effort: n8n-mcp local stateless (informatif). N'affecte JAMAIS le code de sortie.
MCP_URL="${N8N_MCP_URL:-http://localhost:3001}"
MCP_TOKEN="${N8N_MCP_AUTH_TOKEN:-}"
if [ -n "$MCP_TOKEN" ]; then
  if timeout 8 curl -sf -o /dev/null "$MCP_URL/health" -H "Authorization: Bearer $MCP_TOKEN" 2>/dev/null; then
    echo "[N8N-VALIDATE-CLI] info: n8n-mcp local joignable ($MCP_URL) — validation sémantique disponible via MCP session" >&2
  else
    echo "[N8N-VALIDATE-CLI] info: n8n-mcp local injoignable — structurel seul (non bloquant)" >&2
  fi
fi

echo "[N8N-VALIDATE-CLI] PASS: $WF"
```
(Chmod 0755 à la création. `set -euo pipefail` + guillemets. Le sentinel PASS n'est atteint que si le heredoc Python sort 0.)

### 3.2 `scripts/deploy-workflow.sh` (MODIFIER — by-id + délégation validateur + IF v2 toléré)

**(a) Mode by-id.** Après lecture des params, autoriser un override d'ID :
```bash
# --id <ID> ou env WF_ID override l'id du fichier (workflow sans id embarqué, ou re-ciblage)
WF_ID_OVERRIDE="${WF_ID:-}"
if [[ "${2:-}" == "--id" && -n "${3:-}" ]]; then WF_ID_OVERRIDE="$3"; fi
```
Puis dans l'étape 1, si `WF_ID_OVERRIDE` non vide, l'utiliser au lieu d'exiger `id` dans le JSON :
```bash
if [[ -n "$WF_ID_OVERRIDE" ]]; then WF_ID="$WF_ID_OVERRIDE"; fi
if [[ -z "$WF_ID" ]]; then echo "Error: 'id' absent du JSON et --id non fourni." >&2; exit 1; fi
```

**(b) Déléguer la validation structurelle** au nouveau script (DRY + IF v2 toléré). Remplacer tout le heredoc Python de l'étape 2 par :
```bash
echo "→ Structural validation (fallback CLI)..."
"$(dirname "$0")/n8n-validate-fallback.sh" "$WF_FILE"   # exit≠0 => set -e stoppe le deploy
```
→ conséquence : les IF v2 EXISTANTS ne bloquent plus le déploiement (le fallback émet NOTE, pas FAIL), les connexions orphelines/doublons bloquent toujours. Retirer l'ancien bloc R9 `sys.exit(1)`.

**(c) Commentaire de tête** clarifiant que le tolérance IF v2 n'est PAS « R9 résolue » (advisor) :
```bash
# NOTE R9: ce script DÉPLOIE des workflows existants; il tolère les IF v2 déjà présents
# (prod 2.7.3 en exécute 79, dont 36 actifs, sans crash — R4). R9 reste un garde-fou
# d'AUTORING (ne pas ÉCRIRE de nouveaux IF v2) tant que la revalidation staging n'a pas
# statué (RUNBOOK-N8N-UPGRADE-SIDECAR.md §R9).
```

### 3.3 `~/.claude/hooks/n8n-validate-cli-marker.js` (**NOUVEAU** — PostToolUse, imite `n8n-validate-marker.js`)

```js
#!/usr/bin/env node
// PostToolUse (Bash). Écrit /tmp/claude-validate-cli-done SEULEMENT si le validateur
// CLI a effectivement RÉUSSI (sentinel présent dans la sortie). Fail-open total.
const fs = require('fs');
const MARKER = '/tmp/claude-validate-cli-done';
let raw = '';
try { raw = fs.readFileSync(0, 'utf8'); } catch (_) { process.exit(0); }
let data = {}; try { data = JSON.parse(raw || '{}'); } catch (_) { process.exit(0); }
const cmd = ((data.tool_input && (data.tool_input.command || '')) || '').toString();
// tool_response peut être string ou objet — on stringifie pour chercher le sentinel
const resp = (() => { try { return JSON.stringify(data.tool_response || ''); } catch (_) { return ''; } })();
const ranValidator = /n8n-validate-fallback\.sh/.test(cmd);
const passed = /\[N8N-VALIDATE-CLI\]\s+PASS/.test(resp) || /\[N8N-VALIDATE-CLI\]\s+PASS/.test(raw);
if (ranValidator && passed) {
  try { fs.writeFileSync(MARKER, new Date().toISOString()); } catch (_) {}
  process.stdout.write('[VALIDATE-CLI-MARKER] validation CLI réussie — import:workflow autorisé 30 min.');
}
process.exit(0);
```

### 3.4 `~/.claude/settings.json` (MODIFIER — enregistrer le hook PostToolUse)

Dans `hooks.PostToolUse`, ajouter une entrée matcher `Bash` pointant vers `n8n-validate-cli-marker.js` (à côté de l'existant `r0-marker.js` sur Bash, ne pas écraser). Forme :
```json
{ "matcher": "Bash", "hooks": [ { "type": "command", "command": "node $HOME/.claude/hooks/n8n-validate-cli-marker.js" } ] }
```
(Respecter la syntaxe exacte des entrées voisines ; si un matcher `Bash` existe déjà, **ajouter** le hook à son tableau `hooks` plutôt que de dupliquer le matcher.)

### 3.5 `~/.claude/hooks/loi-op-enforcer.js` (MODIFIER — gate R1 accepte MCP OU CLI)

Bloc R1-GATE (~lignes 207-240), remplacer `validateFresh()` :
```js
const VALIDATE_MARKER = '/tmp/claude-validate-done';       // MCP (n8n-validate-marker.js)
const VALIDATE_MARKER_CLI = '/tmp/claude-validate-cli-done'; // CLI (n8n-validate-cli-marker.js)
const VALIDATE_MAX_AGE_MS = 30 * 60 * 1000;
function validateFresh() {
  const fs = require('fs');
  for (const m of [VALIDATE_MARKER, VALIDATE_MARKER_CLI]) {
    try { if ((Date.now() - fs.statSync(m).mtimeMs) < VALIDATE_MAX_AGE_MS) return true; } catch (_) {}
  }
  return false;
}
```
(Optionnel : dans `logGateEvent`, indiquer quel marqueur a satisfait — champ additionnel, non bloquant. Ne PAS ajouter de garde `isSubagent` : le comportement actuel est conservé.)

### 3.6 Tests (`~/.claude/hooks/test/`)

- **`harness.js`** : dans `cleanMarkers()`, ajouter la suppression de `/tmp/claude-validate-cli-done`.
- **`test-validate-cli-marker.js`** (new) : (1) tool_response contenant `[N8N-VALIDATE-CLI] PASS` + cmd `n8n-validate-fallback.sh` → marqueur écrit ; (2) tool_response `[N8N-VALIDATE-CLI] FAIL …` → marqueur **NON** écrit ; (3) cmd sans rapport (`ls`) → non écrit ; (4) hook jamais bloquant (`code !== 2`).
- **`test-enforcer-gates.js`** : ajouter au bloc R1 un cas « marqueur CLI frais (+ ledger R0 satisfait) → `n8n import:workflow` autorisé (`code !== 2`) » ; conserver les cas existants (sans marqueur → bloqué).

### 3.7 Critères d'acceptation L3

1. `bash scripts/n8n-validate-fallback.sh scripts/n8n-workflows/memory-healthcheck.json` → sortie contient `[N8N-VALIDATE-CLI] PASS`, exit 0.
2. Sur le `test-broken.json` de R6 (connexion vers `nonexistent-node`) → `[N8N-VALIDATE-CLI] FAIL`, exit 1 (**là où yigitkonur renvoyait VALID**).
3. Un workflow avec IF v2 mais structure saine → `NOTE` IF v2 + `PASS` exit 0 (déploiement toléré).
4. `~/.claude/hooks/test/run-all.sh` → « ALL TESTS PASS » (dont les nouveaux cas CLI-marker + R1 CLI).
5. Simulation gate : `touch /tmp/claude-validate-cli-done` récent → un `n8n import:workflow` (ledger R0 pré-rempli) n'est PAS bloqué par R1-GATE ; sans aucun marqueur → bloqué exit 2 `[R1-GATE]`.
6. `deploy-workflow.sh` : `--id <ID>` override fonctionne ; validation déléguée ; `shellcheck` propre (`set -euo pipefail`).

---

## LANE-4 — Runbook upgrade prod + mise à jour des références

**Fichiers** (4) : `docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md` (**new**), `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md`, `docs/TROUBLESHOOTING.md`, `CLAUDE.md`.
**Interdit** : ne PAS toucher versions.yml, roles/*, scripts/*, hooks/* (uniquement docs).

### 4.1 `docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md` (**NOUVEAU**)

Structure imposée (procédure PROD complète — exécution = GATE HUMAIN) :

**§1 Contexte & cible.** 2.7.3 → 2.30.7 (23 mineures), n8n-mcp 2.40.5 → 2.65.1. Mécanisme Sidecar (§0.1 de cette SPEC). Rappel R7 (`ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14`, jamais l'IP publique).

**§2 Pré-flight (lecture seule, sur prod).**
- Scopes clé API (R3 §2.2) : la clé de `deploy-workflow.sh` DOIT avoir `workflow:read`+`workflow:update` (+`workflow:delete` si utilisé) sinon 403 post-upgrade. Vérifier / régénérer.
- Baseline task runner : `docker exec javisi_n8n printenv N8N_RUNNERS_ENABLED; docker exec javisi_n8n ps aux | grep task-runner`.
- Baseline IF v2 : requête R4 (`jsonb_array_elements`) → noter 79 IF v2 / 36 actifs.
- Espace disque (R4 §4) : 23 G libres ; l'overlay ajoute ~1.8 G persistant (one-time). OK, mais viser une purge disk-guard préalable si zone 80-90.

**§3 Backup (OBLIGATOIRE avant tout).**
- `pg_dump` **complet** de la base `n8n` (58 MB) — c'est le SEUL filet réaliste (R3 §3 : migrations séquentielles auto, `db:revert` n'annule qu'UNE migration).
- `tar` de `/opt/javisi/data/n8n` (310 MB).
- Horodater, stocker hors conteneur.

**§4 Validation staging (AVANT prod).**
- Restaurer le `pg_dump` sur une instance staging + déployer le Sidecar 2.30.7.
- Overlay boot `--version` (**déjà prouvé** 2026-07-18) ; puis **boot complet** avec Postgres + clé de chiffrement : UI accessible, **bannière NON-PROD absente**, features enterprise (Projects/Insights/Variables) visibles (gate résiduel R2 §6 : le boot UI réel n'a pas été fait en recherche).
- E2E des 3 workflows MOP qui lisent `$env` dans un Code node (`mop-ingest-v1`, `mop-search-v1`, `mop-webhook-render-v1`) — bug task runner R3 §2.1. Fallback si cassé : `N8N_RUNNERS_INSECURE_MODE=true` (à tester, PAS lecture `/proc/environ`).
- **Revalidation R9** (§R9 ci-dessous).
- Vérif scopes clé API sur staging (`GET /api/v1/workflows`).
- Lecture des warnings de dépréciation au 1er démarrage (R3 §2.4).

**§5 Cutover prod (GATE HUMAIN — ne PAS exécuter sans validation §4).**
- Les versions sont déjà dans versions.yml (L1) ; le déclencheur = déploiement.
- `make deploy-role ROLE=n8n ENV=prod` **+** tag `docker-stack` (le seul `n8n` ne recrée pas le conteneur si seule l'image change — R5 §5). Ex. `ansible-playbook playbooks/stacks/site.yml -e target_env=prod --tags n8n,docker-stack --diff`.
- L'init copie+patche (1.8 G, one-time) puis n8n démarre → migrations TypeORM s'auto-appliquent au boot (142 déjà appliquées).
- Surveiller : `docker logs javisi_n8n_init` (patch OK), `docker logs javisi_n8n` (migrations, healthy), bannière absente.

**§6 Post-upgrade.**
- Ré-ingérer les docs n8n 2.x dans le RAG (nos docs RAG = 1.115/1.117 pré-2.0, R1/HANDOFF).
- Le n8n-mcp natif de l'instance (dispo dès 2.30.7, `N8N_MCP_MANAGED_BY_ENV=true`+`N8N_MCP_ACCESS_ENABLED=true`, Community, R1 §4) devient activable → simplifie le Volet B harness (schéma = instance). Follow-up séparé.

**§7 Rollback (ORDRE CRITIQUE).**
1. **RESTAURER le `pg_dump` D'ABORD** — les migrations 2.30.7 sont one-way ; revenir à l'image 2.7.3 sur un schéma migré = n8n cassé. Ne PAS commencer par le tag.
2. Ensuite seulement : revenir `n8n_image`/`n8n_upstream_version` à 2.7.3 dans versions.yml (via l'image (c) `ghcr.io/mobutoo/n8n-enterprise:2.7.3` si conservée, sinon rebuild CI hors Pi — Dockerfile déprécié gardé exprès).
3. **NE PAS utiliser `playbooks/ops/rollback.yml`** pour n8n (template legacy `templates/docker-compose.yml.j2` = n8n non patché ; cf. L2 §2.8). Suivre ce runbook.

**§8 R9 — disposition.** Procédure de revalidation isolée : recréer sur staging le cas exact de `docs/rex/REX-SESSION-2026-04-12b.md` (IF `typeVersion:2`, conditions mixtes booléen+string) → exécuter → observer si le crash `Cannot read properties of undefined (reading 'caseSensitive')` se reproduit. **Si corrigé** : retirer R9 (follow-up : CLAUDE.md R9, advisory `loi-op-enforcer.js`, NOTE de `n8n-validate-fallback.sh`). **Si non** : scoper R9 au pattern précis. Rappel : `deploy-workflow.sh` tolère déjà les IF v2 existants (L3) — c'est indépendant de cette décision.

### 4.2 `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` (MODIFIER)

- **R1** : documenter le fallback CLI accepté — le gate R1 est satisfait par MCP `validate_workflow` **OU** `scripts/n8n-validate-fallback.sh` (marqueur `/tmp/claude-validate-cli-done`). Doctrine « MCP-preferred, CLI-fallback obligatoire sur le chemin critique ».
- **R9** : ajouter « ⏳ EN REVALIDATION post-2.30.7 (RUNBOOK-N8N-UPGRADE-SIDECAR §8) — le déploiement tolère les IF v2 EXISTANTS ; l'interdiction d'AUTORING reste jusqu'à statut ».

### 4.3 `docs/TROUBLESHOOTING.md` (MODIFIER)

- Section n8n-mcp `-32000` : cause = défaut `SESSION_TIMEOUT_MINUTES` 5 min de 2.40.5 (R1 §6.1) ; fix = bump 2.65.1 + les 5 env vars (L1). Réinit session MCP décrite en R1-bis inchangée.
- Nouvelle section « n8n Sidecar (patch enterprise runtime) » : init-container, overlay `n8n_patched_dir`, marqueur idempotent, fail-loud 1/2/3 only, `docker logs javisi_n8n_init` pour diag.

### 4.4 `CLAUDE.md` (MODIFIER — R9 uniquement)

Sur la ligne R9, ajouter le pointeur : « ⏳ En revalidation post-upgrade 2.30.7 (docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md §8). Déploiement d'IF v2 existants toléré ; ne pas ÉCRIRE de nouveaux IF v2 tant que non statué. » Ne toucher AUCUNE autre règle.

### 4.5 Critères d'acceptation L4

1. `RUNBOOK-N8N-UPGRADE-SIDECAR.md` couvre les 8 sections ; le §7 Rollback mène par « restaurer pg_dump » (pas le tag) ; interdit explicitement `ops/rollback.yml` pour n8n.
2. Les 3 gates staging (boot UI/bannière, E2E `$env` MOP, revalidation R9) sont des étapes cochables avec commandes exactes (SSH R7).
3. LOI-OP R1 mentionne le double marqueur ; R9 marquée « en revalidation » dans LOI-OP **et** CLAUDE.md.
4. Aucune modif hors des 4 fichiers docs (zéro collision avec L1/L2/L3).
5. `make lint` non impacté (docs pures).

---

## Ordre d'exécution recommandé (parallélisable, mais si séquencé)

1. **L1** (débloque -32000 immédiatement, déployable sur waza hors gate).
2. **L3** (fallback + gate ; le chemin HTTP best-effort profite de L1 déployé, mais fonctionne en structurel-seul sans lui).
3. **L2** (refactor Sidecar ; overlay boot déjà prouvé — reste le boot complet = gate staging du runbook).
4. **L4** (runbook + refs ; consomme les décisions de L1/L2/L3).

Les 4 lanes ont des fichiers disjoints → peuvent être menées par 4 agents en parallèle. L'**upgrade prod n8n lui-même reste un GATE HUMAIN** : cette SPEC livre code + runbook, elle ne déploie pas la prod Sese.
