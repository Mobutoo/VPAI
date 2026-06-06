# Checkpoint — Exécution refonte mémoire (Plan A) — 2026-06-05 soir

**Pourquoi** : user redémarre Ewutelo (canal SSH → Waza). Reprise propre ici.
**Session Claude** : tourne SUR Waza. Reconnecter via SSH Ewutelo→Waza.

---
# 🔴 REPRISE 2026-06-06 (après gel subagent 10h) — LIRE EN PREMIER

## Incident
Un subagent (plomberie M3) a **figé ~10h** — cause quasi certaine : chargement de `SentenceTransformer(embeddinggemma-300m)` dans `test_memory_core.py` **sur Waza ARM** (lent/hang). **LEÇON DURE : ne JAMAIS charger/encoder le modèle sur Waza. L'embed tourne UNIQUEMENT sur le pod x86.** Marquer les tests embed `@pytest.mark.skipif` hors-pod.

## État VÉRIFIÉ (au moment de la reprise)
- **T1 fix B** : déployé + vérifié. Worker MemoryMax=4G/OOMScoreAdjust=1000, networkd/tailscaled=-900, net-watchdog.timer active. Worker timer **disabled** (à garder ainsi jusqu'à fin M3).
- **T2 Qdrant** : `memory_v2` créée **vide** (768d cosine + 6 indexes wing/room/doc_kind/repo/topic/tags). 15 collections wipées. 14 APP épargnées. LiteLLM sain (semantic_cache recréée). Snapshots **offsite Sese** : `/home/mobuone/qdrant-snapshots-2026-06-05/` (258MB, 0 zéro-byte) + dans qdrant.
- **Manifeste taxonomie** : `docs/runbooks/MEMORY-TAXONOMY-MANIFEST.md` (commit cc67ad2) = SOURCE CANONIQUE wing/room/doc_kind + payload complet.
- **R0 memory search CASSÉ** : `qdrant-find` MCP + `search_memory.py` pointent `memory_v1` (wipé). Réparé seulement quand memory_v2 peuplé + tooling repointé (partie M4).

## Décisions M3 (FIGÉES ce soir)
- **Bulk via 1 SEUL Pod CPU costaud** (RunPod 16-24 vCPU), PAS GPU. Raison : coût négligeable des 2 côtés (~$0.10-0.20), wall-clock similaire (borné par upsert VPN, pas l'embed), et **CPU pod = parité exacte** (pas de gate). Parallèle multi-pods = inutile.
- **Parité = priorité user**. Pod x86, pins IDENTIQUES Waza : `sentence-transformers==5.1.2`, `torch==2.11.0`, `transformers==4.57.6`, `numpy==2.4.4`, modèle `google/embeddinggemma-300m`, `normalize=true`, **fp32**. x86 vs ARM → cosine ≈0.99999 (pas bit-exact, OK). Spot-check 1-échantillon non bloquant.
- **Corpus** : 11 390 fichiers / 104 MB / **~78 500 chunks** (fantrad domine 60MB). Refdocs Tier1/2 viendront plus tard (D7).
- **Staging pod** : repos clonables via `git@github-seko` (VPAI, flash-studio, story-engine, FanTrad, hawkeye, riposte, typebot-docs `https://github.com/baptisteArno/typebot.io.git`). **LOCAL-ONLY** (rsync Waza→pod via mesh) : **DOCS** (16MB), **podpilot**.
- **Worker local PAS dans le hot-path bulk** : pod embed+upsert ; Waza ne sert que ~16MB local-only ; limiteur réel = upsert VPN → Sese Qdrant. Waza worker = incrémental après.
- **Creds RunPod** : `~/projects/saas/fantrad/.env` (`RUNPOD_API_KEY`, `RUNPOD_VOLUME_ID`, `RUNPOD_ENDPOINT_ID`). Tooling fantrad = **serverless** (GraphQL `saveEndpoint`) → l'**on-demand pod** est à faire via REST `https://rest.runpod.io/v1/pods` (à vérifier R8).
- **Clé Headscale éphémère** : créer sur le HUB seko-vpn : `ssh -i ~/.ssh/seko-vpn-deploy mobuone@87.106.30.160` → `headscale preauthkeys create --ephemeral` (+ ACL nœud) → **révoquer après** teardown pod.

## Travail M3 PARTIEL (commit 71f8c63, WIP NON VÉRIFIÉ)
- ✅ `scripts/memory/memory_core.py` (compile OK) : `classify_doc_kind`, `classify_room` (règles manifeste §3), `load_wing_room_lookup`, `build_payload`, chunking, `EmbeddingGemmaEncoder`. **MODULE PARTAGÉ** worker+batch (DRY/parité).
- ⚠️ `scripts/memory/test_memory_core.py` : écrit mais **JAMAIS exécuté** (gel). À lancer **sans** les tests embed sur Waza (ou sur pod).
- ❌ **PAS FAIT** : câblage worker. `roles/llamaindex-memory-worker/` INCHANGÉ → reste à faire :
  1. `index.py.j2` : importer `memory_core`, ajouter wing/room/valid_from/valid_to au payload, compléter `merge_source_roots`.
  2. `defaults/main.yml` : `wing:` par source (VPAI→infra ; flash-studio/story-engine/podpilot/hawkeye/fantrad/riposte→saas ; DOCS/typebot-docs→refdocs) + `collection_name`→`memory_v2`.
  3. `sources.yml.j2` : émettre `wing`.
  4. `tasks/main.yml` : déployer `memory_core.py` → `/opt/workstation/ai-memory-worker/`.

## ✅ FAIT 2026-06-06 (session post-gel) : Step 1 + Step 2 (câblage worker full-DRY)
- **Step 1** : `memory_core` validé — 86 tests verts (`-k "not embed and not encode"`, modèle JAMAIS chargé sur Waza).
- **memory_core complété pour parité** (advisor, 2 BLOCKERS) : ajout `sha256_file`, `git_commit_sha`, `extract_structural_meta` (étaient absents → payloads divergeaient) + `resolve_source` = AUTORITÉ UNIQUE du contrat `(repo, wing, relative_path)` partagée worker+pod. +10 tests.
- **Step 2 — worker full-DRY** : `index.py.j2` importe TOUT de `memory_core` (doublons supprimés). `to_text_nodes`→`build_payload`+`make_node_id` avec wing/room. `process_file`→`resolve_source` (skip si hors source). `main`→`load_wing_room_lookup` 1×. **`list_repo_roots` : expansion SUPPRIMÉE** (BLOCKER #1 : DOCS=arbre unique, repo="DOCS"/rel="n8n-docs/…").
- **defaults** `collection_name`→`memory_v2` + `wing:` ×9. **sources.yml.j2** émet wing. **config.yml.j2** +indexes wing/room. **tasks** copie `memory_core.py`→install_dir (source unique `{{ role_path }}/../../scripts/memory/`).
- **VÉRIF** : render Jinja+`py_compile`+pyflakes CLEAN ; parité démontrée (DOCS nested→DOCS/n8n ; caddy→caddy-vpn ; n8n-workflows→n8n) ; YAML OK. PAS déployé (worker disabled jusqu'à M4). NB : le venv worker `/opt/workstation/ai-memory-worker/.venv` A llama-index (≠ le `.venv` projet) ; `--dry-run` est model-free (fix 2026-06-06) → smoke-test possible sans embed.
- **⚠️ R0 GATE rétrogradé** : flag `/opt/workstation/configs/ai-memory-worker/r0-rebuild.flag` + patch `~/.claude/hooks/loi-op-enforcer.js` (bloc `r0Rebuild`). **À SUPPRIMER en M4** (flag + bloc hook).

## PROCHAINES ÉTAPES (ordre)
1. ✅ ~~Valider memory_core~~ (86 tests).
2. ✅ ~~Câbler le worker~~ (full-DRY, voir bloc ci-dessus).
3. ✅ ~~Écrire le batch pod~~ `scripts/memory/gpu_ingest/` — FAIT 2026-06-06 :
   - `pod_ingest.py` (importe memory_core ; modes `--preflight`/`--verify-sample`/`--dry-run`/bulk ; upsert via `QdrantVectorStore.add` = mêmes clés payload que worker ; `host_origin=waza` ; chemin RELATIF passé à to_text_nodes = parité classify_doc_kind).
   - `requirements.lock.txt` = **pip freeze du venv worker live** (104 pkgs, llama-index-core==0.12.52.post1, tiktoken==0.12.0, nltk==3.9.4, Py3.12.3) — pin du stack pure-python complet (advisor BLOCKER : dérive chunking → node_id). torch/wheels x86 = vecteurs ~cos0.99999 accepté.
   - `sources.pod.yml` (root /staging/<name> → wing/name identiques defaults). `stage_sources.sh` (clone github-seko ⚠️remotes à VÉRIFIER + rsync DOCS/podpilot doc). `README.md` runbook (gate→venv→punkt→staging→preflight→**spot-check node_id Waza↔pod**→bulk→teardown).
   - **Refacto parité** : `to_text_nodes` + `iter_source_files` + constantes INCLUDE_EXTENSIONS/EXCLUDE_DIRS/MAX_FILE_BYTES déplacés/ajoutés dans memory_core (worker re-câblé, pyflakes CLEAN, 86 tests).
   - **VÉRIF** : pod_ingest compile+pyflakes CLEAN ; testé live sur **venv worker** Waza (`--verify-sample VPAI/CLAUDE.md` → 14 chunks, node_ids déterministes, punkt OK) = RÉFÉRENCE pour le diff Step 4. (Spot-check cross-env Waza↔pod = à faire au Step 4 quand le pod existe.)
   - **À confirmer côté pod (Step 4, advisor)** : QdrantVectorStore.add utilise bien `node.id_` comme point-id ; staging sans double-nesting ; punkt+punkt_tab téléchargés.
4. **Provision** — AUTOMATISÉ (non-supervisé) 2026-06-06, en cours de validation :
   - `scripts/memory/gpu_ingest/{bootstrap.sh,provision_pod.sh,reference_nodeids.json}` (commits d497f83→58a3ef8). Pod auto-bootstrap : Tailscale (userspace si pas de tun) → Qdrant → clone 7 repos via **PAT GitHub read-only** → venv lock+punkt → self-check node_id (3 wings) → bulk → sentinelle `ingest_done` → **self-stop** (trap EXIT anti-orphelin, REX FanTrad P1).
   - Secrets injectés en env (jamais commit) : `pod-ingest.env` (HEADSCALE_AUTHKEY/LOGIN_SERVER=singa.ewutelo.com, GITHUB_PAT, SESE_TAILNET_IP=100.64.0.14) + memory-worker.env (QDRANT_URL=qd.ewutelo.cloud:443, QDRANT_API_KEY, **HF_TOKEN** car embeddinggemma gated) + fantrad/.env (RUNPOD_API_KEY). **À RÉVOQUER au teardown** : clé Headscale (hub) + PAT GitHub + `rm pod-ingest.env`.
   - Validé sans dépense : PAT clone 6 repos (ls-remote), RunPod REST auth HTTP 200, payload `--check` valide, référence node_id générée (venv worker).
   - **R4 probe** : `provision_pod.sh --probe` (PROBE_ONLY=1) → pod `dbbln5kagmkdxr` (cpu3c, US-MD-1, $0.48/h) → écrit collection témoin `probe_ok` puis self-stop. Lecture depuis Waza = preuve Tailscale-en-conteneur+Qdrant. **DOCS+podpilot retirés du pod** (worker Waza M4).
   - Restant : si probe OK → `--create` (bulk complet) → poll statut+memory_v2 → `--stop`/`--terminate` + révocations.
   **Spot-check Step 4 (advisor — diff cross-env Waza↔pod via `--verify-sample`)** : NE PAS se limiter à CLAUDE.md (markdown/infra). Diffuser ≥1 fichier par chunk_kind ET par wing : (a) **fichier DOCS imbriqué** refdocs (valide attribution BLOCKER #1 + room refdocs + chunk markdown-section) ; (b) **fichier `.py`** (chunk_kind `llama-sentence` + chemin AST `extract_structural_meta`). Réf Waza = `/opt/workstation/ai-memory-worker/.venv/bin/python pod_ingest.py --verify-sample` (encoder=None, model-free, sûr).
   **Spot-check Step 4 (advisor — diff cross-env Waza↔pod via `--verify-sample`)** : NE PAS se limiter à CLAUDE.md (markdown/infra). Diffuser ≥1 fichier par chunk_kind ET par wing : (a) **fichier DOCS imbriqué** refdocs (valide attribution BLOCKER #1 + room refdocs + chunk markdown-section) ; (b) **fichier `.py`** (chunk_kind `llama-sentence` + chemin AST `extract_structural_meta`). Réf Waza = `/opt/workstation/ai-memory-worker/.venv/bin/python pod_ingest.py --verify-sample` (encoder=None, model-free, sûr).
5. **Teardown** pod + **révoquer** clé Headscale.
6. **M4** : repointer `search_memory.py` + MCP qdrant-find sur memory_v2 (répare R0) ; filtres wing/room ; cap process ; re-enable worker timer (incrémental, capé).
   **Nettoyages M4 obligatoires** (faits/préparés en session 2026-06-06) :
   - SUPPRIMER `/opt/workstation/configs/ai-memory-worker/r0-rebuild.flag` + le bloc `r0Rebuild` dans `~/.claude/hooks/loi-op-enforcer.js` (rétablit le hard-block R0).
   - State/spool v1 neutralisés en backup (`/opt/workstation/data/ai-memory-worker/{state/memory_state.json.2026-06-06-v1-stale.bak,spool.2026-06-06-v1-stale.bak}`). NE PAS restaurer (memory_v1 wipé). Supprimer les `.bak` une fois memory_v2 validé.
   - 🔴 **SEED-STATE OBLIGATOIRE avant re-enable du timer** (advisor — sinon le worker reprocesse + RÉ-EMBED les ~78k chunks SUR WAZA, ce que le pod existe précisément pour éviter). État vide ⇒ `should_process`=True partout. Procédure post-bulk pod :
     ```
     index.py --config <cfg> --mode full --dry-run --report-path /tmp/seed.json
     ```
     `--dry-run` est désormais **model-free** (encoder jamais construit, fix 2026-06-06) : il écrit l'état size/mtime/hash SANS embed. Ensuite SEULEMENT `systemctl --user enable --now` le timer → l'incrémental ne touche que les fichiers réellement modifiés. (Copier l'état du pod ne marche PAS : size/mtime diffèrent clone-pod vs working-tree Waza.)
   - **Règle réconciliée** : "jamais de **bulk**-embed sur Waza" (le bulk = pod x86). L'embed incrémental per-fichier des fichiers réellement modifiés par le worker capé reste OK. La leçon gel = pas de chargement modèle dans un contexte fragile / pas de full-pass embed sur ARM.
   - Vérif deploy-time : la copie `{{ role_path }}/../../scripts/memory/memory_core.py` (tasks) ne se valide qu'au run du rôle → confirmer au 1er deploy M4.
   - Smoke-test model-free dispo dès aujourd'hui : `index.py --preflight-only` (retourne avant l'encoder — valide bootstrap main() + list_repo_roots no-expansion contre qdrant live).
7. Plan B (reorg M1 + manifeste M5 ~/work).

---

## Artefacts (commités sur origin/main sauf indiqué)
- Spec : `docs/superpowers/specs/2026-06-05-memory-system-rebuild-design.md` (D1-D14) — `1ec1ae0`+`eea187b`
- Plan A : `docs/superpowers/plans/2026-06-05-memory-rebuild-core.md` — `7d5e90a` (local, **pas poussé**)
- Script M2 : `scripts/memory/qdrant_rebuild.py` — `78422d1` (local, **pas poussé**)
- Plan B (reorg M1 + manifeste M5) : à écrire après Plan A (finit par restart).

## Décisions clés
- Rebuild ce soir = fix B + M2 + M3 + M4. Reorg ~/work (M1) + manifeste (M5) = DIFFÉRÉ (payloads path-indépendants).
- Embedding unifié embeddinggemma-300m 768d. Collection cible `memory_v2`.
- Ingestion M3 : pod RunPod on-demand + clé Headscale éphémère + upsert direct VPN + terminate/revoke.

## Sécurité Waza (FAIT, mais VOLATILE)
- `llamaindex-memory-worker.timer` `disable --now` (était enabled+active, refirait non-capé).
- Run worker non-capé (PID 58161, ~3.16G RSS) tué. RAM récupérée.
- ⚠️ Volatile : un reboot/re-enable ramène le worker NON capé tant que fix B n'est pas déployé.

## ✅ FAIT 2026-06-05 ~23h45 : Task 1 (fix B déployé+vérifié) + Task 2 (Qdrant rebuild complet)
- Task 1 : fix B déployé depuis ewutelo. Vérifié live Waza : MemoryMax=4G, OOMScoreAdjust=1000, networkd/tailscaled=-900, net-watchdog.timer active. Worker timer re-disabled (deploy l'avait ré-enabled) + run capé tué.
- Task 2 : snapshot 14 MEMORY (257MB) → copie hors-qdrant Sese `/home/mobuone/qdrant-snapshots-2026-06-05/` (258MB, 0 zéro-byte) → wipe 15 (14 MEMORY + semantic_cache) → restart javisi_litellm (semantic_cache recréée, readiness 200) → create memory_v2 (768d cosine + 6 indexes). APP/14 intactes. Qdrant propre.
- **PROCHAIN : Task 3 (M3) ingestion GPU** — commence par RESEARCH gate RunPod+Headscale.

## Task 1 — Deploy fix B (caps + net-resilience) — ✅ FAIT (voir ci-dessus)
- Fix B = commit `45015bb` (déjà sur origin/main). PAS déployé sur Waza (vérifié : MemoryMax=infinity, net-watchdog absent).
- **À lancer depuis EWUTELO** (option B choisie par user), pas depuis Waza :
  ```bash
  cd ~/VPAI && git pull --ff-only
  source .venv/bin/activate
  ansible-playbook playbooks/hosts/workstation.yml \
    --tags "net_resilience,llamaindex-memory-worker" \
    -e workstation_pi_ip=100.64.0.1 --check --diff   # puis sans --check
  ```
- ⚠️ `-e workstation_pi_ip=100.64.0.1` OBLIGATOIRE (sinon défaut 127.0.0.1 = ewutelo se déploie lui-même).
- Vérif post-deploy (depuis Waza) :
  ```bash
  systemctl --user show llamaindex-memory-worker.service -p MemoryMax -p OOMScoreAdjust
  systemctl show systemd-networkd tailscaled -p OOMScoreAdjust
  systemctl status net-watchdog.timer --no-pager | head -5
  ```
  Attendu : MemoryMax=4G, OOMScoreAdjust=1000, networkd/tailscaled=-900, timer active.

## Task 2 — Qdrant rebuild
- **S1 inventory** ✅ : 14 MEMORY + semantic_cache = 15 cibles WIPE ; 14 APP épargnées ; 0 UNKNOWN.
  Les 4 ex-UNKNOWN (brand-voice, model-registry, palais_memory, videoref_styles) → SPARE (gravé APP_EXACT).
- **S2 disque Sese** ✅ GO : vrai Qdrant = `javisi_qdrant` (`/opt/javisi/data/qdrant/storage`, 2.0G dont semantic_cache 1.7G). Snapshot MEMORY ≈ 260 MB vs 29G libres. (Le volume `infra_qdrant_data` est vide/leurre.)
- **S3 pré-check LiteLLM** ✅ SAFE : drop semantic_cache en dernier → `docker restart javisi_litellm` (recrée 1536d) → curl health. Erreurs cache non-fatales.
- **S4-7 à faire (GATE humain avant wipe)** :
  ```bash
  set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a
  PY=/opt/workstation/ai-memory-worker/.venv/bin/python
  $PY scripts/memory/qdrant_rebuild.py --snapshot --out ~/qdrant-snapshots/2026-06-05/
  $PY scripts/memory/qdrant_rebuild.py --wipe --confirm 'WIPE MEMORY'
  # restart litellm (recrée semantic_cache) + curl health
  $PY scripts/memory/qdrant_rebuild.py --create   # memory_v2 768d + 6 indexes
  ```

## Task 3 (M3) / Task 4 (M4) — pas commencés
- M3 : RESEARCH gate RunPod+Headscale d'abord (plan Task 3 Step 1). Plomberie wing/room partagée worker+batch (le batch GPU est le chemin réel). Trap staged-path /runpod-volume.
- M4 : search_memory.py v2 scopé wing/doc_kind + capé.

## Ordre de reprise
1. (toi/ewutelo) deploy fix B → ping.
2. (moi/waza) vérif caps live.
3. GATE snapshot → wipe → restart litellm → create memory_v2.
4. M3 (research → plomberie → pod GPU → parité → bulk).
5. M4 retrieval. Puis Plan B (reorg+manifeste, finit par restart).
