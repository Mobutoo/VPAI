# Plan de montage — Tier NAS (Proxmox + TrueNAS + 3060) & backup 3-2-1-1-0

> **Statut** : plan (design décidé). Matériel : Supermicro **P6X58D-E** (X58, Xeon 55/56xx), **RTX 3060 12Go**, **32Go DDR3 → 48Go** (16Go commandés), 8×8To. Montage week-end.
> **Décisions humaines 2026-07-16** : hyperviseur **Proxmox VE** → **TrueNAS SCALE en VM** ; **garder zerobyte** comme pilote de backup ; **embeddings restent sur waza** (données déjà là + 24/7) ; NAS pour le week-end.
> **Base** : `docs/2026-07-16-feuille-de-route-infra-sota.md` (SOTA) + audit Seko `Seko-VPN/docs/audits/2026-07-16-...`.

## Architecture cible du nœud

```
X58 bare-metal
└─ Proxmox VE (hyperviseur)
   ├─ VM "truenas"    : TrueNAS SCALE — HBA/disques en passthrough → ZFS RAIDZ2 (8×8To ~48To)
   │                     sert NFS/SMB au reste ; datasets: backups/ , media/ , qdrant/
   ├─ LXC/VM "infer"  : Debian + llama.cpp (CUDA) + RTX 3060 en passthrough VT-d
   │                     LLM 7-14B local (LiteLLM local-first) + Whisper + ComfyUI léger
   └─ LXC "zerobyte"  : zerobyte (pilote restic) — repo local sur dataset ZFS truenas (NFS)
                        + offsite Hetzner Object-Lock ; PULL depuis Sese/Seko/Waza
```

> **Pourquoi Proxmox+TrueNAS et pas Debian+ZFS nu** (choix humain, tradeoff assumé) : flexibilité VM/LXC + GUI TrueNAS pour le pool + isolation GPU. Coût : passthrough disques (HBA IT-mode idéal) + passthrough GPU (VT-d) = 2 points durs X58 ; TrueNAS pilotable Ansible via module communautaire (moins first-class que Debian). Overhead virtualisation acceptable sur X58 (VT-x présent).

---

## Phase 0 — Gates matériels (AVANT tout, sinon la stratégie tombe)

- [ ] **G1 — VT-d / IOMMU** (passthrough GPU + HBA) : BIOS P6X58D-E → activer *Intel Virtualization Technology* + *VT-d*. Vérifier après boot Proxmox : `dmesg | grep -e DMAR -e IOMMU` doit montrer l'IOMMU actif ; `find /sys/kernel/iommu_groups/ -type l` non vide. ⚠️ X58 = groupes IOMMU souvent grossiers → la 3060 peut partager un groupe avec d'autres devices (blocage passthrough propre). Plan B si KO : `pcie_acs_override` (moins sûr) OU GPU sur l'hôte Proxmox directement (pas de VM infer, llama.cpp sur l'hôte).
- [ ] **G2 — Above 4G Decoding / ReBAR** (12Go VRAM) : cf feuille de route. Sans ça, 3060 dégradée/invisible même en passthrough. Patch `xCuri0/X58Above4G` si absent.
- [ ] **G3 — HBA / mode disques** : pour ZFS en VM, passer le contrôleur SATA/HBA **entier** en passthrough à la VM TrueNAS (jamais du RDM disque par disque = fragile). Si pas de HBA dédié : envisager ZFS géré par Proxmox hôte + partage, plutôt que TrueNAS-en-VM sur le contrôleur de boot.
- [ ] **G4 — ECC** : Xeon 55/56xx supportent souvent l'ECC unbuffered → activer BIOS avant de recevoir les 16Go (gratuit).
- [ ] **G5 — PSU/PCIe 8-pin/airflow** pour la 3060 (170W).
- [ ] **G6 — RAM interim** : 32Go OK pour démarrer (TrueNAS 8Go+1Go/disque ≈ 16Go, reste pour infer+zerobyte). Les 16Go finaux desserrent le GPU-VM. Dedup ZFS **OFF**.

**Décision de bifurcation** : si G1 (IOMMU propre pour le GPU) échoue → **llama.cpp sur l'hôte Proxmox** (pas de VM infer), TrueNAS reste en VM pour le stockage. Documenter le résultat des gates avant de continuer.

---

## Phase 1 — Socle Proxmox + stockage (week-end J1)

- [ ] Installer Proxmox VE (dernier stable) sur un SSD/disque système (PAS un des 8×8To).
- [ ] IOMMU kernel cmdline : `intel_iommu=on iommu=pt` ; vfio-pci pour la 3060 (`lspci -nn | grep NVIDIA` → bind vendor:device) + blacklist nouveau.
- [ ] VM **truenas** : HBA en passthrough (G3), TrueNAS SCALE, pool **RAIDZ2** (8×8To), datasets `backups`, `qdrant`, `media`. Scrub mensuel planifié. Partage NFS de `backups` (et `qdrant` si besoin) au réseau interne Proxmox.
- [ ] Snapshots ZFS auto (sanoid) sur `backups` — protège la copie locale contre corruption/suppression.

---

## Phase 2 — Backup 3-2-1-1-0 avec zerobyte (PRIORITÉ — répare le manque #1)

> zerobyte **conservé** comme pilote (restic sous le capot). Corrige ses 2 défauts actuels : (a) il ne voyait aucune donnée, (b) offsite non immuable.

- [ ] **LXC zerobyte** sur Proxmox, repo restic **local** sur le dataset NFS `truenas:backups` (= copie « 2 » locale).
- [ ] **Modèle PULL** : zerobyte/restic tire depuis les nœuds via **SSH restreint forced-command** (clé dédiée par nœud, `command="restic serve --append-only"` ou rsync read-only) → un nœud compromis ne peut pas effacer le repo NAS.
- [ ] **Sources cohérentes** (jamais copie brute d'une DB) :
  - Sese-AI : `pg_dump`/`pg_dumpall` + snapshot Qdrant + export n8n (dumps existants `roles/backup-config`, à étendre).
  - Seko-VPN : **Vaultwarden `docker exec vaultwarden /vaultwarden backup`** (natif ≥1.32.1) + **Headscale `.backup`/`VACUUM INTO`** (⚠️ WAL depuis 0.23 → **jamais** `stop+cp`).
  - Waza : `~/work` (hors gros binaires/caches), config `~/.claude` (secrets exclus/redigés).
- [ ] **Offsite « 1 » immuable** : **nouveau bucket Hetzner Object Storage, Object Lock mode COMPLIANCE activé à la création** (non rétroactif) → ré-init repo restic dédié. zerobyte réplique NAS→offsite. Seul mécanisme fermant « Seko compromis + creds volés efface tout » (append-only seul ne suffit pas).
- [ ] **+0 vérifié** : healthchecks.io (dead-man switch cron) + `restic check --read-data-subset=5%` mensuel + drill restore trimestriel (déjà dans `DISASTER-RECOVERY.md`, réviser Option C « miroir mensuel » → **copie quotidienne**). Échec de vérif = **stop backups vers ce repo** + alerte, pas juste log.
- [ ] Pinner les versions dans `versions.yml` (restic, zerobyte, proxmox templates) — anti-drift.

**Definition of done P2** : un `restic restore` prouvé (Vaultwarden + Headscale + pg) depuis le NAS ET depuis l'offsite, contenu vérifié (`count(users)` VW/HS ≥ attendu), heartbeat vert. **C'est le livrable qui referme le risque #1.**

---

## Phase 3 — Nœud d'inférence GPU (si G1/G2 OK)

- [ ] LXC/VM **infer** : Debian + driver NVIDIA + CUDA ; **llama.cpp compilé from-source** (pas Ollama précompilé = AVX2 → crash Westmere ; flags CPU réels + CUDA).
- [ ] Modèles : Gemma 4 E4B / Qwen3.5-8B (Q4_K_M) ; servir en OpenAI-compat (`llama-server`).
- [ ] **LiteLLM (Sese) route local-first** : nouveau backend `http://<nas-tailnet>:8080` prioritaire, cloud en fallback/overflow → vide moins le cap 5$/j. NAS doit être **sur le tailnet** (cf infra mesh).
- [ ] Whisper (STT) + ComfyUI léger (SDXL/Flux-schnell) pour gen locale légère (content-factory : léger local, lourd = RunPod).
- [ ] **Wake-on-LAN / démarrage à la demande** du nœud infer (X58 80-150W idle → pas 24/7 ; démarrer pour batchs + fenêtre de pull).

> **Embeddings = restent sur waza** (décision : données déjà sur waza, 24/7 ; fix racine = `MemoryMax` systemd déjà en place). Option future différée : NAS expose une API d'embedding GPU que le worker waza appelle sur le mesh (les fichiers restent sur waza, seuls les textes transitent) — à évaluer seulement si la vitesse d'embedding devient un problème.

---

## Phase 4 — Intégration mesh & offload (après week-end)

- [ ] **NAS sur le tailnet** (client tailscale → headscale Seko) — prérequis pour LiteLLM local-first + pull backups sur IP 100.64.x.
- [ ] Décharger de Sese vers le NAS (allège OVH → downgrade visé) : héberger la collection **Qdrant** sur dataset ZFS + observabilité **Loki/Grafana** (rétention lourde). Câbler **Alloy→Loki** (aujourd'hui `alloy_loki_url:""`).
- [ ] Headscale : sa DB (WAL) désormais sauvegardée sur NAS (P2) + versionner `config.yaml` → SPOF mitigé.

---

## IaC — ce que je peux préparer AVANT le matériel (testable à blanc)

- [ ] Rôle Ansible **`nas`** (cible : hôte Proxmox / LXC) : IOMMU cmdline, vfio, LXC zerobyte, montages NFS TrueNAS, tailscale. Molecule en dry.
- [ ] Étendre **`roles/backup-config`** : sources Vaultwarden (`/vaultwarden backup`) + Headscale (`.backup` WAL-safe) + Waza ; cible pull NAS + offsite Object-Lock ; healthchecks.io ; `restic check` mensuel.
- [ ] Réviser **`docs/DISASTER-RECOVERY.md`** : Option C mensuel → quotidien pull-based + Object Lock + restore-test.
- [ ] `versions.yml` : pinner restic + images du tier NAS.

## Ordre d'exécution
**J1 week-end** : Gates matériels (Phase 0) → Proxmox + TrueNAS/ZFS (Phase 1) → **Phase 2 backup** (le livrable critique). **J2** : Phase 3 infer si gates GPU OK. **Après** : Phase 4 + IaC durci. **Lot 0 Seko** (vaultwarden 1.35.8, indépendant) dès ban levé.

## Risques / bifurcations
1. **IOMMU X58 grossier** (G1) → GPU sur hôte Proxmox au lieu d'une VM (documenté Phase 0).
2. **Pas de HBA dédié** (G3) → ZFS géré par l'hôte Proxmox, TrueNAS écarté ou en simple front NFS.
3. **Above-4G absent** (G2) → GPU inutilisable → tier NAS = stockage+backup only (Phase 2 reste 100% valable), IA locale reportée.
4. Backup (Phase 2) ne dépend d'AUCUN gate GPU → **livrable garanti** même si tout le volet IA échoue.
