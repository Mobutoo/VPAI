# Plan de montage — Tier X58 « home datacenter » (execution-ready)

> ⚠️ **SUPERSÉDÉ (2026-07-18)** : ce plan est archivé. La source de vérité est désormais le repo
> **standalone `~/work/infra/banga`** (design consolidé + 7 rôles Ansible implémentés + runbooks).
> Deux prémisses matérielles de ce plan sont **fausses** et corrigées ci-dessous :
> **(a) gate G1 Above-4G = DISSOUS** (voir `banga/docs/runbooks/RUNBOOK-BANGA-BIOS-ABOVE4G.md`) ;
> **(b) CPU = Core i7-9xx** (pas Xeon), carte **ASUS** P6X58D-E, **ECC caduc**.
> Ne rien exécuter depuis ce fichier — se référer à `banga/.planning/STATE.md`.

> **Statut** : plan figé (décisions humaines prises). Matériel : ASUS **P6X58D-E**, **Core i7-9xx** (x86_64, sans AVX/AVX2), **32→48Go DDR3 non-ECC**, 8×8To, **RTX 3060 12Go**. Montage week-end.
> **Archi & rationale** : `docs/2026-07-16-architecture-x58-home-datacenter.md`.
> **Décisions humaines 2026-07-16** : **Option B — ZFS sur l'hôte Proxmox** (pas de HBA/TrueNAS-VM) · **GPU en LXC** (pas de passthrough VM) · **test/dev hybride** (VMs locales X58 au quotidien + Hetzner éphémère pour ce qui exige une IP publique) · zerobyte gardé · embeddings restent sur waza.

## Conséquence des choix : ZÉRO passthrough → ZÉRO gate GPU
ZFS sur l'hôte + GPU en LXC ⇒ **aucun VT-d/IOMMU/VFIO requis**. ~~Le seul point matériel restant côté GPU = Above-4G / ReBAR.~~
**CORRECTION (2026-07-18)** : le driver NVIDIA hôte voit les **12Go de VRAM SANS Above-4G** (BAR1 256Mio = fenêtre d'accès CPU, pas une limite VRAM ; CUDA charge le modèle par DMA). Above-4G n'est requis que pour ReBAR, dont le gain en inférence llama.cpp ≈ 0. **Plus aucun gate matériel GPU.** Le vrai risque X58↔3060 est le **POST/affichage** (VBIOS legacy), pas la VRAM. Analyse : `banga/docs/runbooks/RUNBOOK-BANGA-BIOS-ABOVE4G.md`.

---

## Phase 0 — Gates matériels (réduits)

- [x] ~~**G1 — Above 4G Decoding / ReBAR**~~ **DISSOUS (2026-07-18)**. Analyse du ROM 0803 réel (AMIBIOS8 legacy, pas d'option Above-4G existante, DSDT 32-bit uniquement) : la 3060 est **pleinement utilisable sans**. `nvidia-smi` affiche 12288 MiB, CUDA charge par DMA. Above-4G/ReBAR = optionnel (hobby, gain inférence ≈0, voie `xCuri0/X58Above4G` runtime sans flash). **Rien à flasher.** Runbook : `banga/docs/runbooks/RUNBOOK-BANGA-BIOS-ABOVE4G.md`.
- [x] ~~**G2 — ECC**~~ **CADUC** : le CPU réel est un **Core i7-9xx grand public** (pas Xeon) → pas de support ECC. RAM non-ECC assumée ; garde-fous ZFS (scrub mensuel, snapshots) inchangés.
- [ ] **G3 — PSU** (watts + connecteur PCIe 8-pin pour la 3060, 170W) + **airflow** (carte grand public en boîtier serveur).
- [ ] **G4 — Disque système** : SSD/NVMe dédié pour Proxmox (JAMAIS un des 8×8To).
> Plus de gate VT-d, HBA, Above-4G (G1) ni ECC (G2) — supprimés par Option B + GPU-LXC + analyse ROM 0803. Restent uniquement G3 (PSU/airflow) et G4 (SSD système).

---

## Phase 1 — Proxmox + ZFS hôte (J1)

- [ ] Installer **Proxmox VE** (dernier stable) sur le SSD système.
- [ ] **Pool ZFS sur l'hôte** : `zpool create tank raidz2 <8 disques by-id>` (par `/dev/disk/by-id`, jamais `sdX`). Datasets : `tank/backups`, `tank/qdrant`, `tank/media`, `tank/vmdata`.
- [ ] ZFS hygiène : `ashift=12`, compression `lz4`, **dedup OFF**, scrub mensuel (cron), snapshots auto **sanoid** sur `tank/backups`.
- [ ] **Partage NAS** : LXC `samba`/Cockpit (ou `cockpit-file-sharing`) exposant `tank/media` (+ SMB/NFS interne). Pas de TrueNAS.
- [ ] Driver **NVIDIA sur l'hôte** Proxmox (headless) + `nvidia-container-toolkit` ; vérifier `nvidia-smi` voit **12288 MiB** (attendu sans Above-4G ; BAR1 256Mio < 4G = normal).

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

## Phase 3 — Inférence IA en LXC (aucun gate — G1 dissous)

- [ ] **LXC `infer`** (unprivileged si possible + device cgroup NVIDIA, sinon privileged) : bind `/dev/nvidia*`, `nvidia-container-toolkit`. **Pas de VT-d.**
- [ ] **llama.cpp compilé from-source** (Ollama précompilé = AVX2 → *illegal instruction* Westmere) + CUDA. `llama-server` OpenAI-compat.
- [ ] Modèles Q4_K_M — **binôme via llama-swap** (1 GPU, 1 modèle chargé, TTL) : Gemma 4 12B (généraliste) + Qwen2.5-Coder 14B (code) + 7B (long-ctx/fallback). Routage LiteLLM par alias+fallback. Build llama.cpp with **AVX/AVX2/FMA/F16C OFF** (SIGILL Nehalem sinon). Détail : `banga/roles/lxc-infer`.
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
**J1** : gates G3/G4 → Proxmox + ZFS hôte (P1) → **P2 backup** (livrable critique, sans GPU). **J2** : P3 infer (aucun gate — G1 dissous). **Après** : P4 mesh/offload + IaC durci. **Lot 0 Seko** (vaultwarden 1.35.8) dès ban levé.

## Filet
P2 (backup) ne dépend d'AUCUN gate → **garanti**. L'IA locale (P3) n'a plus non plus de gate matériel bloquant (G1 dissous). Seul risque résiduel = POST/affichage VBIOS legacy (mitigé : GPU d'affichage temporaire, 3060 en compute headless une fois l'OS booté — cf. runbook BIOS §7).
