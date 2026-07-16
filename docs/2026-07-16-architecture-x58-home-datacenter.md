# Architecture X58 — « home datacenter » (NAS + IA + VMs de test)

> Objectif : sur le seul X58 (P6X58D-E, Xeon 55/56xx, 48Go DDR3, 8×8To, RTX 3060 12Go), obtenir **NAS + inférence IA + VMs de test** (décharger Sese) — robuste malgré les limites X58, et cohérent avec l'estate Sese/Seko/Waza.
> Remplace l'approche « GPU passthrough en VM » du plan précédent, fragile sur X58.

## 1. L'estate à 4 tiers (rôles clairs)

| Nœud | Surnom | Rôle | Toujours-on ? |
|---|---|---|---|
| **Waza** (Pi5) | *Cockpit* | edge, mission-control (Claude Code), worker RAG/embeddings (données déjà là), nœud tailnet | oui (bas conso) |
| **Sese** (OVH) | *Cerveau public* | front internet minimal : n8n, **LiteLLM (routeur)**, OpenClaw, services publics. Downgrade après offload | oui (payé) |
| **Seko** (Ionos) | *Portier* | hub Headscale (contrôle mesh) + coffre Vaultwarden. À durcir + mettre sur tailnet | oui (petit) |
| **X58** (neuf) | *L'atelier / datacenter maison* | **stockage 48To + IA GPU + VMs de test + backup + observabilité**. Jamais exposé au net (derrière Tailscale) | baseline 24/7 + lourd on-demand |

**Bascule stratégique** : le X58 devient le tier « lourd local » → Sese rétrécit à un front public minimal, l'IA passe **local-first** (cloud = overflow), le dev/test quitte le cloud éphémère pour du **local gratuit**.

## 2. L'insight clé — LXC pour le GPU, pas une VM

Le passthrough GPU **vers une VM** exige VT-d + un **groupe IOMMU propre** → sur X58 les groupes sont grossiers (la 3060 partage souvent son groupe) = galère, patchs ACS risqués, parfois impossible.

**Solution : mettre l'inférence dans un LXC, pas une VM.** Un conteneur LXC **partage le noyau + le driver NVIDIA de l'hôte** (bind-mount `/dev/nvidia*` + nvidia-container-toolkit) → **aucun VT-d, aucun VFIO, aucun groupe IOMMU** requis pour le GPU. On élimine le point de fragilité #1 du X58, et plusieurs LXC peuvent même se partager le GPU.

> VT-d n'est alors requis que si on veut passer le **HBA disque** à une VM TrueNAS (§3, optionnel) — un passthrough bien plus simple/stable que celui d'un GPU.

## 3. Architecture cible

```
X58 bare-metal ── Proxmox VE (Debian-based → 100% Ansible)
│
├─ HÔTE : driver NVIDIA 3060 installé sur l'hôte (pas de VFIO)
│         ZFS natif Proxmox si pas de HBA dédié
│
├─ 💾 STOCKAGE  ┌ Option A (recommandée, +HBA LSI 9211-8i IT ~40€) :
│               │   VM TrueNAS SCALE ← HBA passthrough (VT-d, simple) → 8×8To ZFS RAIDZ2
│               │   = GUI + snapshots + réplication + SMB/NFS. Autorité stockage.
│               └ Option B (sans HBA) : ZFS sur l'hôte Proxmox + LXC Cockpit/Samba.
│                   Perd la GUI TrueNAS, évite tout passthrough disque.
│
├─ 🧠 LXC "infer"  : Debian + CUDA + llama.cpp (from-source, GPU partagé de l'hôte)
│                    llama-server 7-14B (OpenAI-compat) + Whisper + ComfyUI léger
│                    → LiteLLM (Sese) route LOCAL-FIRST vers ce endpoint via tailnet
│
├─ 🗄 LXC "zerobyte" : pilote restic (gardé) — pull nœuds → dataset ZFS (copie 2)
│                     → offsite Hetzner Object-Lock (immuable, copie 1)
│
├─ 📊 LXC "observ"  : Loki + Grafana (rétention lourde, décharge Sese) ; Alloy→Loki câblé
│
├─ 🧪 VMs "test-*"  : KVM éphémères (templates/clones/snapshots) = dev/test local
│                     GRATUIT → remplace/complète le tier « Hetzner éphémère »
│                     (décharge Sese des flash-suite/story-engine/fantrad)
│
└─ 🔗 tailscale (LXC ou hôte) : X58 rejoint le mesh Headscale → LiteLLM + pull backups
                                 sur 100.64.x. JAMAIS d'IP publique exposée.
```

## 4. Pourquoi c'est robuste (vs le plan VM-passthrough)

| Fragilité X58 | Ce design |
|---|---|
| GPU passthrough VM (IOMMU grossier) | **contourné** — GPU en LXC, pas de VT-d |
| Above-4G / ReBAR (12Go VRAM) | **reste à vérifier** (le driver hôte doit voir les 12Go) — seul gate GPU restant |
| HBA passthrough | **simple** (VT-d sur un HBA dédié) OU évité (ZFS hôte, Option B) |
| NAS fiable vs bidouille GPU | **séparés** : le stockage (VM/host stable) n'est pas perturbé par les reboots du LXC infer |

Le GPU n'est plus qu'un **service parmi d'autres sur l'hôte**, pas une pièce virtualisée capricieuse.

## 5. Puissance & fiabilité (X58 = 80-150W idle)

- **Baseline 24/7** : Proxmox + stockage/NAS + zerobyte + observ + tailnet (le NAS doit être là pour le pull + servir Qdrant/Loki).
- **On-demand** : LXC infer (GPU) démarré pour les batchs/requêtes + VMs de test au besoin. Proxmox start/stop (ou hook LiteLLM qui réveille l'infer).
- **Bilan** : le coût électrique (~130€/an) est compensé par le downgrade OVH (Sese minimal) + les tokens cloud économisés (local-first) + le dev/test gratuit. Net probablement positif.
- Si on veut optimiser plus tard : séparer un **petit nœud always-on** (mini-PC 10W pour NAS-front/tailnet/backup) du **gros X58 on-demand** (GPU+VMs). Pas nécessaire au départ.

## 6. Cohérence avec le reste

- **Backup 3-2-1-1-0** (le livrable critique, §plan NAS) tourne **indépendamment du GPU** → garanti même si Above-4G échoue.
- **Décharge Sese** = double : services always-on (Qdrant/Loki/observ) en LXC + dev/test en VMs éphémères → Sese rétréci = économies OVH.
- **IA locale** routée par le LiteLLM existant (juste un backend de plus, prioritaire) → zéro changement côté n8n/OpenClaw.
- **Mesh** : X58 sur tailnet = prérequis commun (LiteLLM local-first + pull backups).

## 7. Gates matériels restants (réduits à 3)

1. **Above-4G / ReBAR** (BIOS P6X58D-E) — seul gate GPU restant (driver hôte doit voir 12Go). Patch `xCuri0/X58Above4G` si absent.
2. **VT-d** — requis **seulement** pour l'Option A (HBA→TrueNAS VM). Option B s'en passe totalement.
3. **ECC** (Xeon 55/56xx souvent OK) + PSU/PCIe-8pin + airflow.

## 8. Décisions à trancher
- **HBA LSI 9211-8i IT-mode (~40€)** pour la voie TrueNAS propre (Option A), ou ZFS-sur-hôte (Option B) ? *(Reco : A si tu veux la GUI/réplication TrueNAS ; B si tu veux zéro passthrough.)*
- **VMs de test** : les projets Hetzner-éphémères (flash-suite/story-engine/fantrad) migrent-ils vers des VMs X58 locales ?
- **Toujours-on** : quels services justifient le 24/7 (Qdrant/Loki oui ; infer non) ?
