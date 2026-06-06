# Batch d'ingestion mémoire bulk — pod CPU x86 → Qdrant `memory_v2`

Ingestion initiale du corpus (~11 390 fichiers / ~78 500 chunks) sur un pod CPU
RunPod, en **parité stricte** avec le worker Waza. Le worker ne fait QUE
l'incrémental ensuite (M4). Le limiteur réel = upsert VPN → Sese Qdrant (pas l'embed).

## Pourquoi un pod CPU (pas GPU)
Coût négligeable (~$0.10–0.20), wall-clock similaire (borné par l'upsert VPN), et
**CPU x86 = parité exacte du stack pure-python** (chunking/tiktoken/nltk identiques
au worker). Le wheel torch x86 ≠ ARM ⇒ vecteurs ~0.99999 cos (accepté, pas bit-exact).

## Contrat de parité (sinon node_id divergent)
1. **Python 3.12.x** + `requirements.lock.txt` (= `pip freeze` du venv worker Waza).
2. **punkt nltk** présent (SentenceSplitter en dépend).
3. `memory_core.py` = celui du repo VPAI cloné (source UNIQUE, identique au worker).
4. Chaque source stagée **exactement** à son root `sources.pod.yml` (pas de double-nesting).
5. `host_origin="waza"` (défaut) — entre dans `ref_doc_id`/tags/node_id.

> `node_id = make_node_id(ref_doc_id(repo, rel), chunk_index, chunk_text)`. Ne dépend
> QUE du texte de chunk + (repo, relative_path). `git_sha` n'y entre PAS (payload only) :
> "" pour DOCS/podpilot rsync non-git est sans effet sur l'identité.

## Procédure

### 0. Gate humain (Step 4 du checkpoint)
- Clé Headscale **éphémère** sur le hub seko-vpn :
  `ssh -i ~/.ssh/seko-vpn-deploy mobuone@87.106.30.160` → `headscale preauthkeys create --ephemeral` (+ ACL nœud).
- Pod CPU RunPod on-demand via `provision_pod.sh` (REST `/v1/pods`, doc R8 2026-06-06 ;
  creds `~/projects/saas/fantrad/.env`) :
  ```bash
  ./provision_pod.sh --check          # dry : montre le payload, aucun appel
  ./provision_pod.sh --create         # crée le pod -> POD_ID
  ./provision_pod.sh --status <id>    # état
  ./provision_pod.sh --terminate <id> # teardown (puis révoquer la clé Headscale)
  ```
  Défaut : `python:3.12-bookworm` 16 vCPU SECURE 60G. Contrôle pod = terminal web RunPod
  (ou sshd si installé). Image overridable via `POD_IMAGE=…` (garder Python 3.12.x).
  Clé deploy `github-seko` à monter sur le pod (6 repos privés ; typebot = https public).

### 1. Venv + deps (sur le pod)
```bash
python3.12 -m venv /opt/ingest && . /opt/ingest/bin/activate
pip install -r requirements.lock.txt
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"
```

### 2. Staging
```bash
# clé deploy github-seko montée sur le pod
bash stage_sources.sh           # clone les 7 repos git -> /staging/<name>
# DEPUIS WAZA (mesh) : rsync DOCS + podpilot (cf bas de stage_sources.sh)
```

### 3. Preflight (aucun upsert)
```bash
set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a   # QDRANT_URL/API_KEY
python pod_ingest.py --sources sources.pod.yml --preflight
```
Attendu : 9 sources, `files=` > 0 partout, tout `OK`.

### 4. ⭐ Spot-check parité node_id (DISCRIMINANT — fait l'objet de la décision parité)
Sur un fichier présent des **deux** côtés (ex. VPAI/CLAUDE.md). Exécuter le MÊME
script avec le **venv worker** sur Waza ET sur le pod, puis diff :
```bash
# --- sur WAZA (venv worker, qui A llama-index) ---
/opt/workstation/ai-memory-worker/.venv/bin/python pod_ingest.py \
  --sources <sources-waza.yml> --verify-sample /home/mobuone/VPAI/CLAUDE.md > /tmp/waza.json
# (sources-waza.yml = même mapping mais roots Waza : /home/mobuone/VPAI, etc.)

# --- sur POD ---
python pod_ingest.py --sources sources.pod.yml --verify-sample /staging/VPAI/CLAUDE.md > /tmp/pod.json

# --- diff (doit être VIDE) ---
diff <(jq '{repo,relative_path,chunk_count,nodes:[.nodes[]|{node_id,chunk_text_sha256}]}' /tmp/waza.json) \
     <(jq '{repo,relative_path,chunk_count,nodes:[.nodes[]|{node_id,chunk_text_sha256}]}' /tmp/pod.json)
```
`node_id` + `chunk_text_sha256` + `chunk_count` identiques ⇒ chunking + attribution
prouvés. (Les vecteurs ne sont volontairement PAS comparés : ARM≠x86.)

**Confirmer aussi le mécanisme point-id** : après un `--dry-run` puis un petit run réel
(`--limit 5`), vérifier dans Qdrant que les points portent bien les `node_id` calculés
(QdrantVectorStore doit utiliser `node.id_` comme id de point). Si absent → STOP.

### 5. Dry-run borné puis bulk
```bash
python pod_ingest.py --sources sources.pod.yml --dry-run --limit 200   # sanity
python pod_ingest.py --sources sources.pod.yml                          # BULK
```

### 6. Teardown
- Terminer le pod RunPod.
- **Révoquer** la clé Headscale éphémère sur le hub.

## Fichiers
| Fichier | Rôle |
|---|---|
| `pod_ingest.py` | Batch (importe `memory_core`) — preflight / verify-sample / dry-run / bulk |
| `sources.pod.yml` | Mapping staging root → wing/name (parité defaults worker) |
| `stage_sources.sh` | Clone git + doc rsync DOCS/podpilot |
| `requirements.lock.txt` | Pins exacts du venv worker (parité) |
