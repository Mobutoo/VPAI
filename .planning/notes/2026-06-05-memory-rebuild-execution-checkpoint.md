# Checkpoint — Exécution refonte mémoire (Plan A) — 2026-06-05 soir

**Pourquoi** : user redémarre Ewutelo (canal SSH → Waza). Reprise propre ici.
**Session Claude** : tourne SUR Waza. Reconnecter via SSH Ewutelo→Waza.

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
