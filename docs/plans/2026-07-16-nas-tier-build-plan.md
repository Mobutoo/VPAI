# Plan de montage — Tier X58 « home datacenter » (execution-ready)

> **Statut** : plan figé (décisions humaines prises). Matériel : Supermicro **P6X58D-E**, Xeon 55/56xx, **32→48Go DDR3**, 8×8To, **RTX 3060 12Go**. Montage week-end.
> **Archi & rationale** : `docs/2026-07-16-architecture-x58-home-datacenter.md`.
> **Décisions humaines 2026-07-16** : **Option B — ZFS sur l'hôte Proxmox** (pas de HBA/TrueNAS-VM) · **GPU en LXC** (pas de passthrough VM) · **test/dev hybride** (VMs locales X58 au quotidien + Hetzner éphémère pour ce qui exige une IP publique) · zerobyte gardé · embeddings restent sur waza.

## Conséquence des choix : ZÉRO passthrough → 1 seul gate GPU
ZFS sur l'hôte + GPU en LXC ⇒ **aucun VT-d/IOMMU/VFIO requis**. Le seul point matériel restant côté GPU = **Above-4G / ReBAR** (le driver de l'hôte doit voir les 12Go de VRAM).

---

## Phase 0 — Gates matériels (réduits)

- [ ] **G1 — Above 4G Decoding / ReBAR** (BIOS P6X58D-E) : sans ça, la 3060 12Go boote dégradée/invisible pour le driver hôte. Activer l'option BIOS ; sinon patch [`xCuri0/X58Above4G`](https://github.com/xCuri0/X58Above4G) ou DSDT Linux. **Seul gate bloquant pour l'IA.**
- [ ] **G2 — ECC** : Xeon 55/56xx supportent souvent l'ECC unbuffered → activer BIOS avant de monter les 16Go finaux (gratuit, fail-safe anti-corruption ZFS).
- [ ] **G3 — PSU** (watts + connecteur PCIe 8-pin pour la 3060, 170W) + **airflow** (carte grand public en boîtier serveur).
- [ ] **G4 — Disque système** : SSD/NVMe dédié pour Proxmox (JAMAIS un des 8×8To).
> Plus de gate VT-d ni HBA — supprimés par les choix Option B + GPU-LXC.

---

## Phase 1 — Proxmox + ZFS hôte (J1)

- [ ] Installer **Proxmox VE** (dernier stable) sur le SSD système.
- [ ] **Pool ZFS sur l'hôte** : `zpool create tank raidz2 <8 disques by-id>` (par `/dev/disk/by-id`, jamais `sdX`). Datasets : `tank/backups`, `tank/qdrant`, `tank/media`, `tank/vmdata`.
- [ ] ZFS hygiène : `ashift=12`, compression `lz4`, **dedup OFF**, scrub mensuel (cron), snapshots auto **sanoid** sur `tank/backups`.
- [ ] **Partage NAS** : LXC `samba`/Cockpit (ou `cockpit-file-sharing`) exposant `tank/media` (+ SMB/NFS interne). Pas de TrueNAS.
- [ ] Driver **NVIDIA sur l'hôte** Proxmox (headless) + `nvidia-container-toolkit` ; vérifier `nvidia-smi` voit **12Go** (preuve que G1 est OK).

---

## Phase 2 — Backup 3-2-1-1-0 avec zerobyte (LIVRABLE CRITIQUE, indépendant du GPU)

- [ ] **LXC `zerobyte`** : repo restic **local** sur `tank/backups` (= copie « 2 » locale).
- [ ] **Modèle PULL** : zerobyte tire depuis les nœuds via **SSH restreint forced-command** (clé dédiée/nœud) → un nœud compromis ne peut pas effacer le repo NAS.
- [ ] **Sources cohérentes** (jamais copie brute d'une DB) :
  - Sese : `pg_dump`/`pg_dumpall` + snapshot Qdrant + export n8n (dumps `roles/backup-config` à étendre).
  - Seko : Vaultwarden `docker exec vaultwarden /vaultwarden backup` (≥1.32.1) + **Headscale `.backup`/`VACUUM INTO`** (⚠️ WAL depuis 0.23 → **jamais** `stop+cp`).
  - Waza : `~/work` (hors gros caches/binaires) + `~/.claude` (secrets exclus).
- [ ] **Offsite « 1 » immuable** : **nouveau bucket Hetzner Object Storage, Object Lock mode COMPLIANCE à la création** (non rétroactif) + repo restic dédié ; zerobyte réplique NAS→offsite. Seul mécanisme fermant « Seko compromis + creds volés efface tout ».
- [ ] **+0 vérifié** : healthchecks.io (dead-man cron) + `restic check --read-data-subset=5%` mensuel + drill restore trimestriel. Échec vérif = **stop backups vers ce repo** + alerte.
- [ ] Pinner restic + images dans `versions.yml`.

**DoD P2** : `restic restore` prouvé (Vaultwarden + Headscale + pg) **depuis le NAS ET depuis l'offsite**, contenu vérifié (`count(users)` VW/HS). = referme le risque #1.

---

## Phase 3 — Inférence IA en LXC (si G1 Above-4G OK)

- [ ] **LXC `infer`** (unprivileged si possible + device cgroup NVIDIA, sinon privileged) : bind `/dev/nvidia*`, `nvidia-container-toolkit`. **Pas de VT-d.**
- [ ] **llama.cpp compilé from-source** (Ollama précompilé = AVX2 → *illegal instruction* Westmere) + CUDA. `llama-server` OpenAI-compat.
- [ ] Modèles Q4_K_M : Gemma 4 E4B / Qwen3.5-8B (3060 : 7-8B ~40 tok/s, 14B ~20 tok/s).
- [ ] **LiteLLM (Sese) route LOCAL-FIRST** : backend `http://<x58-tailnet>:8080` prioritaire, cloud=fallback → vide moins le cap 5$/j. (Prérequis : X58 sur tailnet, Phase 4.)
- [ ] Whisper (STT) + ComfyUI léger (gen locale légère ; lourd = RunPod).
- [ ] **On-demand** : LXC infer démarré pour batchs/requêtes (hook LiteLLM ou start/stop Proxmox) — pas 24/7.

> **Embeddings = restent sur waza** (données déjà là + 24/7 ; fix = `MemoryMax` en place). Option future : API embedding GPU sur le mesh appelée par le worker waza.

---

## Phase 4 — Mesh & offload Sese (après week-end)

- [ ] **X58 sur le tailnet** (tailscale LXC/hôte → Headscale Seko) — prérequis LiteLLM local-first + pull backups sur 100.64.x. Jamais d'IP publique.
- [ ] **LXC `observ`** : Loki + Grafana (rétention lourde) sur `tank` ; câbler **Alloy→Loki** (aujourd'hui `alloy_loki_url:""`).
- [ ] Décharger **Qdrant** (collection sur `tank/qdrant`) de Sese → allège OVH → downgrade visé.
- [ ] **VMs test-* (hybride)** : templates KVM pour dev/test local (flash-suite/story-engine/fantrad au quotidien) ; garder Hetzner éphémère pour ce qui exige IP publique (CI, ACME public).

---

## IaC — préparable AVANT le matériel (testable à blanc, molecule dry)

- [ ] Rôle Ansible **`x58-proxmox`** : ZFS hôte (datasets), driver NVIDIA + toolkit, LXC (samba, zerobyte, infer, observ), tailscale, sanoid.
- [ ] Étendre **`roles/backup-config`** : sources Vaultwarden/Headscale WAL-safe + Waza ; cible pull NAS + offsite Object-Lock ; healthchecks.io ; `restic check` mensuel.
- [ ] Réviser **`docs/DISASTER-RECOVERY.md`** : Option C mensuel → **copie quotidienne pull-based** + Object Lock + restore-test.
- [ ] `versions.yml` : pinner restic + images tier X58.

## Ordre d'exécution
**J1** : G0 gates → Proxmox + ZFS hôte (P1) → **P2 backup** (livrable critique, sans GPU). **J2** : P3 infer si G1 OK. **Après** : P4 mesh/offload + IaC durci. **Lot 0 Seko** (vaultwarden 1.35.8) dès ban levé.

## Filet
P2 (backup) ne dépend d'AUCUN gate → **garanti** même si Above-4G échoue (dans ce cas : X58 = NAS+backup+VMs test, IA locale reportée jusqu'au fix BIOS/ReBAR).
