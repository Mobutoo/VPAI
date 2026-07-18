# RUNBOOK — Upgrade n8n 2.7.3 → 2.30.7 (Sidecar patch enterprise)

**Host prod** : Sese-AI (OVH VPS 8GB) — `100.64.0.14` (Tailscale, R7 — **jamais** `137.74.114.167`)
**Statut** : ✅ **CUTOVER EXÉCUTÉ ET VÉRIFIÉ 2026-07-18** — `javisi_n8n` = `n8nio/n8n:2.30.7`, healthy, HTTP 200 via `mayi.ewutelo.cloud`, migrations 142→219 sans erreur, credentials déchiffrés, 57/125 workflows actifs (baseline), re-run idempotent `ok=41 changed=0`. REX : `docs/rex/REX-N8N-UPGRADE-SIDECAR-2026-07-18.md`. Ce runbook reste la procédure de référence pour un futur bump / le rollback §7.
**Origine** : `ops/loops/plans/2026-07-18-HANDOFF-n8n-fiabilite-et-memoire.md` + `.planning/research/n8n-upgrade/{r1,r2,r3,r4}.md` + `.planning/quick/260718-n8n-sidecar/SPEC.md`.

---

## §1. Contexte & cible

| Composant | Actuel (prod, `javisi_n8n`) | Cible | Delta |
|---|---|---|---|
| n8n | `ghcr.io/mobutoo/n8n-enterprise:2.7.3` | `n8nio/n8n:2.30.7` (image **officielle**, patch enterprise appliqué au runtime) | 23 versions mineures |
| n8n-mcp | `2.40.5` | `2.65.1` | ~4 mois, corrige le défaut `SESSION_TIMEOUT_MINUTES` cassé (5 min → 30 min, R1 §6.1) |

**Mécanisme** : le patch enterprise (`roles/n8n/files/patch-enterprise.sh`) n'est plus buildé dans une image custom (`ghcr.io/mobutoo/n8n-enterprise`). Il est appliqué **au runtime** par un service Compose one-shot `n8n-init` (init-container) qui copie l'arbre `node_modules/n8n` de l'image officielle dans un volume bind persistant (`n8n_patched_dir`), le patche, puis le service `n8n` monte ce volume **en overlay** (`:ro`) par-dessus son propre `node_modules/n8n`. Détail architecture : `SPEC.md` §0.1.

**R7 — accès prod, systématiquement** :
```bash
dig +short mayi.ewutelo.cloud                                          # doit retourner 100.64.0.14
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 'hostname'     # doit répondre 'sese'
```
Jamais `137.74.114.167` (IP publique), jamais `localhost:5678` depuis waza.

---

## §2. Pré-flight (lecture seule, sur prod)

Toutes les commandes de cette section sont des `SELECT`/inspections — **aucune écriture**.

### 2.1 Scopes de la clé API (R3 §2.2 — durcissement post-2.7.3)

Un commit dans la fenêtre 2.7.3→2.30.7 (`58999f030`, *"Enforce API key scope/endpoint parity"*) ajoute `x-required-scope` sur `GET/PUT/DELETE /api/v1/workflows/:id`. La clé API utilisée par `scripts/deploy-workflow.sh` (méthode primaire R11) **doit** porter au minimum `workflow:read` + `workflow:update` (+ `workflow:delete` si un script en dépend), sinon **403 Forbidden après l'upgrade** sur un appel qui fonctionne aujourd'hui.

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "curl -sf -H 'X-N8N-API-KEY: <clé>' https://mayi.ewutelo.cloud/api/v1/workflows | python3 -c \"import sys,json; d=json.load(sys.stdin); print(len(d['data']),'workflows')\""
```
Vérifier/régénérer les scopes via l'UI n8n (Settings → API) **avant** cutover si un doute existe.

### 2.2 Baseline task runners ($env dans les Code nodes — R3 §2.1)

`N8N_RUNNERS_ENABLED` est déjà un no-op en 2.7.3 (champ non lié à une env var côté n8n) — pas un nouveau breaking. Le risque réel : le bug `$env`/`process.env` vide dans le sandbox du Code node (`docs/rex/REX-MOP-TASKRUNNER-2026-04-11.md`) touche potentiellement 2.7.3 **et** 2.30.7 de façon identique (mécanisme runner inchangé). À vérifier AVANT (baseline) et APRÈS (staging §4.3) :

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker exec javisi_n8n printenv N8N_RUNNERS_ENABLED; docker exec javisi_n8n ps aux | grep task-runner"
```

### 2.3 Baseline IF v2 (R9 — état réel en prod)

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker exec -i -e PGPASSWORD='<vault>' javisi_postgresql psql -U n8n -d n8n -c \
   \"SELECT n->>'typeVersion' AS tv, w.active, count(*) FROM workflow_entity w, jsonb_array_elements(w.nodes::jsonb) n WHERE n->>'type'='n8n-nodes-base.if' GROUP BY 1,2 ORDER BY 1,2;\""
```
Baseline connue (inventaire R4, 2026-07-18) : **79 IF v2 / 24 IF v1** sur 125 workflows (57 actifs) ; sur les IF en workflows **actifs** : **36 en v2, 4 en v1**. Noter tout écart avant de continuer — ces 36 IF v2 actifs tournent aujourd'hui sans crash malgré R9, ce qui motive la revalidation §8.

### 2.4 Espace disque (R4 §4)

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 "df -h / ; docker system df"
```
Baseline connue : 99G total, **23G disponibles (77% used)**. L'overlay Sidecar ajoute ~**1.8 Go persistant one-time** (arbre `node_modules/n8n` patché, cf `SPEC.md` §0.1 preuve empirique) — largement absorbable. Si le disque est retombé en zone 80-90% (cf mémoire `Sese disque 2026-07-17 zone morte disk-guard`), lancer une purge `disk-guard` préalable plutôt que de cutover à chaud.

---

## §3. Backup (OBLIGATOIRE avant tout, y compris avant §4 staging si restauré depuis prod)

Le `pg_dump` complet est le **seul filet réaliste** : `n8n db:revert` n'annule qu'**une seule** migration à la fois (R3 §3), et 23 versions mineures représentent potentiellement des dizaines de migrations séquentielles (142 déjà appliquées au 2026-07-18, dernière `ExpandSubjectIDColumnLength1769784356000`).

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 << 'EOSSH'
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p /opt/javisi/backups/n8n-upgrade
docker exec -e PGPASSWORD='<vault_postgresql_password>' javisi_postgresql \
  pg_dump -U n8n -d n8n -F c -f /tmp/n8n-pre-upgrade-$STAMP.dump
docker cp javisi_postgresql:/tmp/n8n-pre-upgrade-$STAMP.dump \
  /opt/javisi/backups/n8n-upgrade/n8n-pre-upgrade-$STAMP.dump
tar czf /opt/javisi/backups/n8n-upgrade/n8n-data-$STAMP.tar.gz -C /opt/javisi/data n8n
ls -lh /opt/javisi/backups/n8n-upgrade/
EOSSH
```
Baseline taille (R4) : DB `n8n` = **58 MB**, `/opt/javisi/data/n8n` = **310 MB** — backup trivial en taille et en durée. Horodater (`$STAMP`) et **copier hors du conteneur** (fait ci-dessus, `docker cp`) ; considérer une copie hors-hôte (Seko-VPN / restic) avant cutover si le gate humain valide un délai suffisant.

---

## §4. Validation staging (AVANT prod)

**Contrainte d'architecture (SPEC §0.6, non-négociable)** : prod Sese-AI est **amd64**, waza est **arm64**. Le mécanisme Sidecar ne doit **PAS builder d'image sur le Pi** — et le boot complet (Postgres + UI) doit être validé sur un hôte représentatif de prod. **Ne pas utiliser waza comme host de staging pour ce §4** : l'overlay boot `--version` a déjà été prouvé sur arm64 (image multi-arch, §4.1 ci-dessous), mais le boot UI complet doit être vérifié amd64.

**Hôte staging** : non fixé par ce runbook (aucune instance dédiée n'existe dans l'inventaire à ce jour). Candidat naturel : une instance éphémère **amd64** (Hetzner CX-class, cohérent avec `playbooks/hosts/app-prod.yml` / architecture 3-tiers, mémoire `project_target_architecture`) provisionnée pour la durée de la validation, puis détruite. Provisioning hors scope de ce runbook — paramétrer les commandes ci-dessous par `$STAGING_HOST`/`$STAGING_SSH`.

### 4.1 Overlay boot `--version` (déjà prouvé arm64, 2026-07-18 — reconfirmer sur `$STAGING_HOST` amd64)

```bash
# Exécuté SUR $STAGING_HOST (via SSH dédié à ce host, ou en local si staging = poste courant).
# `docker` nu ici — `--context local` est un idiome waza→waza uniquement (jamais sur un host distant).
docker pull n8nio/n8n:2.30.7
docker run --rm --entrypoint sh n8nio/n8n:2.30.7 -c \
  'cp -a /usr/local/lib/node_modules/n8n/. /tmp/patched/ 2>/dev/null || mkdir -p /tmp/patched && cp -a /usr/local/lib/node_modules/n8n/. /tmp/patched/'
# Ou, pattern init-container réel une fois L2 déployé sur staging :
docker compose -f <compose-staging>.yml run --rm n8n-init
docker logs <staging>_n8n_init   # attendu : "terminé — marqueur=2.30.7:<sha>"
docker run --rm -v <patched_dir>:/usr/local/lib/node_modules/n8n:ro \
  --entrypoint n8n n8nio/n8n:2.30.7 --version   # attendu : 2.30.7
```
Critère : `2.30.7` retourné, aucune erreur de résolution de module (preuve pnpm layout déjà faite arm64, cf `SPEC.md` §0.1).

### 4.2 Boot complet (Postgres + clé de chiffrement) — gate résiduel non fait en recherche

Restaurer le `pg_dump` de §3 sur une DB Postgres staging, déployer le Sidecar complet (L1+L2), démarrer `n8n` avec `N8N_ENCRYPTION_KEY` identique à prod (nécessaire pour déchiffrer les credentials restaurés). Vérifier :
- [ ] UI accessible (`https://<staging-host>:5678` ou domaine staging dédié)
- [ ] **Bannière NON-PROD absente** (preuve fonctionnelle que le patch enterprise a pris — étape 3 `patch-enterprise.sh`, `showNonProdBanner:false`)
- [ ] Features enterprise visibles : Projects, Insights, Variables (menu latéral UI)
- [ ] `docker logs <staging>_n8n` (sur `$STAGING_HOST`) : migrations TypeORM appliquées sans erreur, statut `healthy`

### 4.3 E2E des 3 workflows MOP `$env` (R3 §2.1)

Workflows concernés : `mop-ingest-v1` (`bnokIWFxoydTRbDH`), `mop-search-v1` (`Jot7Djz71QAYxbkY`), `mop-webhook-render-v1` (`Vts5Yid05Qapiwk1`) — tous actifs en prod, tous lisent `$env` dans un Code node.

```bash
# Playwright MCP (R2 — jamais curl pour un flux multi-étapes) OU appel direct webhook si sibling test suffit (R4)
curl -sS -X POST https://<staging-domain>/webhook/mop-ingest-v1 \
  -H 'Content-Type: application/json' -d @tests/fixtures/sample.json
# → vérifier code HTTP 200 + payload non vide (symptôme du bug = 200 + body vide, TROUBLESHOOTING 9.2)
```
Si cassé : tester `N8N_RUNNERS_INSECURE_MODE=true` (var existante depuis avant 2.7.3, désactive les mesures de sécurité du sandbox — PAS la lecture `/proc/*/environ`, écartée explicitement par R3 §2.1 car contredit le guide officiel de durcissement AppArmor task-runners).

### 4.4 Revalidation R9

Voir §8 ci-dessous — procédure complète.

### 4.5 Vérif scopes clé API sur staging

```bash
curl -sf -H "X-N8N-API-KEY: <clé staging>" https://<staging-domain>/api/v1/workflows \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK —', len(d['data']), 'workflows')"
```
Doit réussir sans 403 (confirme le scope `workflow:read`+`workflow:update` posé en §2.1).

### 4.6 Lecture des warnings de dépréciation au 1er démarrage (R3 §2.4)

```bash
# Sur $STAGING_HOST
docker logs <staging>_n8n 2>&1 | grep -i -A2 deprecat
```
Warnings connus non-bloquants en 2.30.7 (défauts pas encore changés) : `N8N_UNVERIFIED_PACKAGES_ENABLED`, `N8N_RUNNERS_TASK_TIMEOUT`, `N8N_COMPRESSION_NODE_MAX_*`, `N8N_DEFAULT_BINARY_DATA_MODE`. Vérifier absence de `EXECUTIONS_PROCESS=own` (celui-ci **bloque** le démarrage, pas juste un warning) — non trouvé dans `n8n.env.j2` actuel.

**Gate §4 franchi seulement si** : 4.1 OK, 4.2 tous les cocher, 4.3 les 3 workflows répondent, 4.4 statué (corrigé ou R9 confirmée), 4.5 OK, 4.6 lu sans surprise bloquante.

---

## §5. Cutover prod (GATE HUMAIN — ne PAS exécuter sans validation §4 complète)

Les versions cibles sont déjà posées dans `versions.yml` (Lane 1 de la SPEC). **Garde technique** (revue adversariale 2026-07-18, finding CRITICAL) : `roles/n8n/tasks/main.yml` inspecte l'image du conteneur `javisi_n8n` réellement en cours d'exécution ; si elle diffère de `n8n_image` cible, TOUT déploiement touchant `n8n`/`docker-stack` (y compris un déploiement motivé par un autre rôle du même run) échoue en `assert` tant que `-e n8n_upgrade_confirm=yes` n'est pas passé explicitement. **Ne passer ce flag qu'après avoir coché §3 (backup) et §4 (staging) ci-dessus** — il n'y a pas d'autre vérification automatique que la parole de l'opérateur à ce stade.

```bash
source /home/mobuone/work/infra/VPAI/.venv/bin/activate
# le seul tag "n8n" ne recrée pas le conteneur si seule l'image change (R5 §5) — TOUJOURS +docker-stack
# n8n_upgrade_confirm=yes: GATE HUMAIN — n'ajouter qu'après §3 (pg_dump fait) + §4 (staging validé)
# -e prod_ip=100.64.0.14: OBLIGATOIRE depuis waza (R7) — sans lui, vault_prod_ip pointe l'IP publique
#   et le déploiement time-out sur le port 804 (Tailscale). Vérifié cutover 2026-07-18.
ansible-playbook playbooks/stacks/site.yml -e target_env=prod -e prod_ip=100.64.0.14 -e n8n_upgrade_confirm=yes --tags n8n,docker-stack --diff
```
Séquence attendue : `n8n-init` copie (1.8 Go) + patche l'arbre → `service_completed_successfully` → `n8n` démarre avec l'overlay monté → migrations TypeORM s'auto-appliquent au boot (142 déjà appliquées avant cutover, delta = migrations des 23 versions mineures).

**Surveillance immédiate** :
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker logs javisi_n8n_init --tail 50 ; echo --- ; docker logs javisi_n8n --tail 80 ; echo --- ; docker inspect javisi_n8n --format '{{.State.Health.Status}}'"
```
- `docker logs javisi_n8n_init` → doit finir sur `terminé — marqueur=2.30.7:<sha>` (jamais `FATAL`)
- `docker logs javisi_n8n` → migrations appliquées, `healthy`, bannière non-prod absente
- `docker inspect javisi_n8n --format '{{.State.Health.Status}}'` → `healthy`

---

## §6. Post-upgrade

- **Nettoyage disque (`n8n_patched_dir` scopé par version)** : depuis la revue adversariale 2026-07-18 (finding HIGH #3), `n8n_patched_dir` = `/opt/javisi/data/n8n-patched/<version>` — un répertoire **par version** (jamais réutilisé/écrasé par `rm -rf` pendant qu'une autre version tourne encore, ce qui évacue la course ancien-conteneur/nouvel-init). Conséquence : les anciens répertoires (`.../n8n-patched/2.7.3`, etc.) restent sur disque après un cutover réussi — purger manuellement une fois `javisi_n8n` confirmé `healthy` sur la nouvelle version : `ssh ... "rm -rf /opt/javisi/data/n8n-patched/<ancienne-version>"`. ~1.8 Go par version laissée.
- **Ré-ingérer les docs n8n 2.x dans le RAG** : nos docs locales (`/home/mobuone/DOCS/n8n-docs/`) sont pré-2.0 (1.115/1.117 sur 1.117 total, cf HANDOFF) — déclencher une ré-ingestion pour couvrir 2.x.
- **n8n-mcp natif de l'instance** (`N8N_MCP_MANAGED_BY_ENV=true` + `N8N_MCP_ACCESS_ENABLED=true`, disponible dès 2.30.7, Community, pas de gate license — R1 §4) devient activable. Simplifie potentiellement le Volet B harness (le schéma de nœuds vient alors directement de l'instance, plus de désync). **Follow-up séparé, pas dans ce cutover.**

---

## §7. Rollback (ORDRE CRITIQUE — ne pas inverser)

1. **RESTAURER le `pg_dump` D'ABORD.** Les migrations 2.30.7 sont one-way (`n8n db:revert` ne défait qu'une migration à la fois, R3 §3). Redémarrer l'image 2.7.3 sur un schéma déjà migré par 2.30.7 = n8n cassé au boot. **Ne jamais commencer par le tag d'image.**
   ```bash
   ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 << 'EOSSH'
   set -euo pipefail
   docker stop javisi_n8n
   docker cp /opt/javisi/backups/n8n-upgrade/n8n-pre-upgrade-<STAMP>.dump javisi_postgresql:/tmp/restore.dump
   docker exec -e PGPASSWORD='<vault>' javisi_postgresql \
     pg_restore -U n8n -d n8n --clean --if-exists /tmp/restore.dump
   EOSSH
   ```
2. **Ensuite seulement** : revenir `n8n_image`/`n8n_upstream_version` à `2.7.3` dans `versions.yml`. Deux voies : (a) réutiliser `ghcr.io/mobutoo/n8n-enterprise:2.7.3` si l'image existe encore en registre, (b) rebuild via le `Dockerfile` **déprécié mais conservé exprès** (`roles/n8n/files/Dockerfile`, chemin (c) de `SPEC.md` §0.1) — **build hors Pi** (registre CI, jamais waza arm64).
3. **NE PAS utiliser `playbooks/ops/rollback.yml`** pour n8n : le template legacy `templates/docker-compose.yml.j2` déploie un n8n **non patché** (bannière NON-PROD revient, features enterprise reverrouillées) contre une DB potentiellement déjà migrée. Suivre exclusivement ce runbook pour tout rollback n8n.

---

## §8. R9 — disposition (IF node v2)

**État actuel (2026-07-18, post-staging run 3)** : **`fixed` prouvé sur le pattern string exact du REX** (revalidation staging 2.30.7). Workflow `r9-probe` : IF `typeVersion: 2`, comparaison string `$json.headers['x-r9-secret'] === $env.TEST_ENV_PROBE`, schéma canonique `options: { caseSensitive: true, typeValidation: strict }` → 2 exécutions réelles (200 branche match / 403 branche nomatch), **aucun crash `Cannot read properties of undefined (reading 'caseSensitive')`**, vérification R10 sur `workflow_history` (le node exécuté est bien `typeVersion 2`, non downgradé silencieusement). **Portée à ne PAS sur-généraliser** : seul le cas *comparaison string avec résolution d'expression sur `options`* a été retesté ; le cas **boolean IF v2** n'a PAS été rejoué. Ne pas retirer R9 en bloc — laisser la règle d'autoring en place, scopée. Empiriquement, 79 IF v2 tournaient déjà en prod 2.7.3 (36 en workflows actifs healthy), ce qui contredisait déjà "crashe sur TOUTES les conditions" comme énoncé absolu.

**Cas de repro exact** (`docs/rex/REX-SESSION-2026-04-12b.md`, session 2026-04-12) :
- Workflow `deploy-monitor` (id `q2w7nVrVNP7KNtyj`), node **"Validate Secret"** — `n8n-nodes-base.if` `typeVersion: 2`, comparaison string `$json.headers['x-af-secret'] === $env.AF_WEBHOOK_SECRET`.
- Symptôme : `Cannot read properties of undefined (reading 'caseSensitive')`.
- Cause identifiée dans le code : `filter-parameter.js:198` — `const ignoreCase = !filterOptions.caseSensitive` crashe quand `filterOptions` (résolu depuis `typeOptions.filter.caseSensitive`) est `undefined`. Toutes les conditions (boolean ET string) passent par cette ligne.
- Fix appliqué à l'époque : downgrade `typeVersion: 2 → 1` + schéma `fixedCollection`, commit `527f0e4`.

**Procédure de revalidation isolée (sur `$STAGING_HOST` §4, post-boot complet 4.2)** :
1. Recréer un workflow minimal avec un IF `typeVersion: 2` reproduisant exactement le node "Validate Secret" (comparaison string `$json.x === $env.Y`, schéma canonique `options: { caseSensitive: true, typeValidation: "strict" }`).
2. L'importer sur staging (`n8n-validate-fallback.sh` NOTE sur l'IF v2 mais PASS — L3), l'activer, déclencher une exécution réelle (webhook ou manuel).
3. Observer : le crash `Cannot read properties of undefined (reading 'caseSensitive')` se reproduit-il ?

**Décision** :
- **Si corrigé** (pas de crash) → retirer R9. Follow-up à ouvrir séparément : `CLAUDE.md` (retirer la ligne R9), `~/.claude/hooks/loi-op-enforcer.js` (retirer l'advisory d'autoring R9), `scripts/n8n-validate-fallback.sh` (retirer la `NOTE` IF v2 — devient non pertinente).
- **Si non corrigé** → garder R9 scopé précisément au pattern reproduit (comparaison string avec résolution d'expression sur `options`), pas comme interdiction générale si le cas boolean simple s'avère sain.
- Dans les deux cas, **indépendant** de la tolérance déjà en place côté déploiement (Lane 3) : `scripts/deploy-workflow.sh` tolère déjà les IF v2 **existants** au déploiement (R9 = garde-fou d'autoring, pas de déploiement) — cette décision R9 ne change que la règle d'ÉCRITURE de nouveaux IF v2.

### §8bis — État chantier A « harness autoring » (2026-07-18) — R9 boolean, livrable 4

**Verdict : reporté — staging indisponible.** Vérifié ce jour (`grep -rln "stg_n8n"` sur
tout le repo, aucun compose file ; le staging éphémère `stg_n8n`/`stg_n8n_pg` ayant
servi au cutover `REX-N8N-UPGRADE-SIDECAR-2026-07-18.md` a été **entièrement
démantelé** après le cutover). Aucune instance `$STAGING_HOST` amd64 disponible.
Ne pas en reprovisionner un pour ce chantier ponctuel : l'incident staging du
cutover (§Incident staging ci-dessus — fausse alerte Telegram réelle via
`hawktrade-killswitch`, causée par un boot avec la clé de chiffrement prod réelle)
montre que reconstituer ce type de staging est une opération à risque non
négligeable, hors périmètre d'un chantier « quick » mono-agent sans gate humain
dédié.

**Commande exacte à rejouer** (dès qu'un `$STAGING_HOST` amd64 est provisionné,
suivre §4.2 boot complet AVANT ceci) :
```bash
# Sur $STAGING_HOST, workflow minimal reproduisant "Validate Secret" en boolean
# (au lieu du pattern string déjà statué fixed) :
#   IF typeVersion 2, operator: { type: 'boolean', operation: 'true', singleValue: true }
#   comparaison sur un champ boolean simple issu d'un Code node amont, PAS une
#   résolution d'expression sur $env (le pattern déjà testé porte sur $env, isoler
#   la variable "type de comparaison" ici : boolean, pas string).
# Importer, activer, déclencher une exécution réelle, observer si
# "Cannot read properties of undefined (reading 'caseSensitive')" se reproduit.
# Procédure complète : §8 ci-dessus, étapes 1-3.
```

**Corroboration indirecte obtenue (read-only, sans staging)** : le workflow prod
`memory-healthcheck` (id `NZZ9Ke6DXJTlkasa`) contient un IF v2 boolean réel
(`Needs Alert?`, `operator: {type:'boolean', operation:'true', singleValue:true}`,
`$json.needs_alert` en entrée). Vérifié via `execution_entity` (lecture seule,
SSH+psql §2.3) : 5 exécutions consécutives `mode=trigger, status=success` le
2026-07-18 (12h, 13h, 14h, 17h, 18h) sur prod 2.30.7. Le nœud IF traverse
nécessairement le même chemin de code (`filter-parameter.js`) que le cas string
déjà statué — un crash y aurait produit `status=error`/`crashed`, pas `success`.
**Ce n'est pas une preuve substitutive** à la procédure isolée du §8 (pas de
schéma `options` identique reconstitué à l'identique, pas d'environnement
contrôlé) — voir `docs/runbooks/GOTCHAS-N8N-2.30.md` §1 pour la nuance complète.
Faisceau d'indices qui penche vers "corrigé" mais ne tranche pas formellement.

**Diff proposés, NON appliqués (édition LOI = gate humain, SPEC non-buts)** —
préparés pour éviter de re-dériver le diff une fois le test staging effectivement
rejoué :

*Branche A — si la revalidation isolée confirme `fixed` sur le cas boolean aussi*
(R9 devient obsolète en bloc, alignée sur le cas string déjà statué) :
```diff
--- a/CLAUDE.md
-**R9** IF node v2 bug (n8n 2.7.3): ALWAYS use `typeVersion: 1` + `fixedCollection` schema. `typeVersion: 2` crashes on ALL conditions (boolean + string). Detect: `python3 -c "import json; [print(n['name']) for n in json.load(open('wf.json'))['nodes'] if n.get('type')=='n8n-nodes-base.if' and n.get('typeVersion',1)>=2]"` ⏳ En revalidation post-upgrade 2.30.7 (docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md §8). Déploiement d'IF v2 existants toléré ; ne pas ÉCRIRE de nouveaux IF v2 tant que non statué.
+**R9 — RETIRÉE 2.30.7** (historique : bug filter-parameter.js corrigé en amont entre 2.7.3 et 2.30.7, string ET boolean confirmés `fixed` sur staging, REX-SESSION-2026-04-12b.md + RUNBOOK-N8N-UPGRADE-SIDECAR.md §8/§8bis). IF v2 est de nouveau le schéma standard d'autoring.

--- a/docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md
# Section "R9 — IF node v2" : remplacer le corps de règle par un renvoi historique
# vers RUNBOOK-N8N-UPGRADE-SIDECAR.md §8/§8bis, retirer la contrainte d'autoring.

--- a/scripts/n8n-validate-fallback.sh
# Retirer le bloc NOTE IF v2 (devenu non pertinent) — lignes du check `ifv2`.

--- a/~/.claude/hooks/loi-op-enforcer.js
# Retirer l'advisory d'autoring R9 (le hook n'a pas à re-signaler une règle retirée).
```

*Branche B — si la revalidation isolée confirme le crash aussi en boolean*
(R9 reste, texte déjà scopé correctement — pas de retrait, juste lever
l'ambiguïté "non testé" → "testé, confirmé cassé") :
```diff
--- a/CLAUDE.md
 **R9** IF node v2 bug (n8n 2.7.3): ALWAYS use `typeVersion: 1` + `fixedCollection` schema. `typeVersion: 2` crashes on ALL conditions (boolean + string). Detect: ... ⏳ En revalidation post-upgrade 2.30.7 (docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md §8). Déploiement d'IF v2 existants toléré ; ne pas ÉCRIRE de nouveaux IF v2 tant que non statué.
-⏳ En revalidation post-upgrade 2.30.7 (docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md §8). Déploiement d'IF v2 existants toléré ; ne pas ÉCRIRE de nouveaux IF v2 tant que non statué.
+String comparison confirmée `fixed` sur 2.30.7 (staging run 3) ; comparaison
+boolean confirmée TOUJOURS cassée sur 2.30.7 (staging §8bis) — règle maintenue
+dans son intégralité pour tout nouveau IF v2, quel que soit le type de
+comparaison, jusqu'à correction upstream n8n.
# LOI-OP.md, hook enforcer, n8n-validate-fallback.sh : aucun changement.
```

Aucune de ces deux branches n'est appliquée par ce chantier — gate humain requis
avant toute édition de `CLAUDE.md`/`LOI-OPERATIONNELLE-MCP-FIRST.md`/hook enforcer,
et avant cela, exécution effective de la commande de revalidation ci-dessus.

---

## Références

- `SPEC.md` (`.planning/quick/260718-n8n-sidecar/`) — décisions d'architecture verrouillées (§0.1 à §0.5)
- `.planning/research/n8n-upgrade/r1-versions.md` — versions cibles, corrections vs HANDOFF
- `.planning/research/n8n-upgrade/r2-patch-sidecar.md` — mécanisme Sidecar, layout pnpm
- `.planning/research/n8n-upgrade/r3-breaking.md` — breaking changes réels (scopes API, task runners, IF v2, migrations)
- `.planning/research/n8n-upgrade/r4-prod-inventory.md` — inventaire lecture-seule prod (125 workflows, 79 IF v2, 58 MB DB, 23G disque libre)
- `docs/rex/REX-SESSION-2026-04-12b.md` — repro exact du crash IF v2 (`deploy-monitor`, commit `527f0e4`)
- `docs/rex/REX-MOP-TASKRUNNER-2026-04-11.md` — bug `$env` vide dans les Code nodes
- `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` — R1 (double marqueur MCP/CLI), R9 (statut en revalidation)
- `docs/TROUBLESHOOTING.md` §9 (n8n), §57/§58 (n8n-mcp -32000, Sidecar patch enterprise)
- `roles/n8n/files/n8n-enterprise-init.sh`, `roles/n8n/files/patch-enterprise.sh` — implémentation Sidecar (Lane 2)
- `scripts/n8n-validate-fallback.sh`, `scripts/deploy-workflow.sh` — validateur fallback + déploiement (Lane 3)
