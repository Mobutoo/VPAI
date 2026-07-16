# Feuille de route infra — état de l'art juillet 2026

> Réponse à « que peut-on améliorer face au SOTA mi-2026 ? ». Topologie : **Waza** (Pi5 16Go), **Sese-AI** (OVH 8-12Go, no GPU), **Seko-VPN** (Ionos, hub Headscale + coffre), **NAS** (Supermicro P6X58D-E, 8×8To ZFS RAIDZ2 ~48To, 48Go DDR3, X58) **+ RTX 3060 12Go acquise**, montage week-end. Sources SOTA : 2 recherches datées (backup/DR + LLM local), croisées.

## Idée directrice
Aujourd'hui tout le « lourd » (RAM, disque, batch IA) vit soit sur un **Pi bridé** (waza, a OOM) soit sur du **cloud payant contraint** (Sese 8Go, Phase B tombée). Le NAS **+ 3060** devient le **tier « lourd local »** qui : (1) répare le backup (manque #1), (2) rapatrie stockage/observabilité/embeddings hors du cloud exigu, (3) fait de l'inférence GPU locale un **primaire** (pas un fallback). Il allège les deux autres nœuds → permet enfin le downgrade OVH visé (économies).

---

## 🚨 Week-end — chemin critique matériel (À FAIRE EN PREMIER)

1. **Above 4G Decoding / ReBAR** sur le BIOS P6X58D-E : le X58 (PCIe Gen2) n'alloue souvent pas le MMIO >4Go pour une carte 12Go → la 3060 boote dégradée ou invisible. Vérifier l'option BIOS ; sinon patch [`xCuri0/X58Above4G`](https://github.com/xCuri0/X58Above4G) ou patch DSDT Linux. **Bloquant pour toute la stratégie IA locale.**
2. **ECC** : les Xeon 5500/5600 supportent souvent l'ECC unbuffered natif → vérifier le BIOS avant d'acheter la RAM, c'est « gratuit » sur ce matériel (bénéfice = fail-safe anti-corruption silencieuse, pas une garantie ZFS).
3. **PSU + airflow** : watts suffisants + connecteur PCIe 8-pin pour la 3060 (170W) ; refroidissement carte grand public dans un boîtier serveur.
4. **OS = Debian + `zfsutils-linux` + Docker** (PAS TrueNAS/Unraid — appliance GUI que l'IaC Ansible VPAI contourne). RAM ZFS = 8Go + 1Go/disque, **dedup OFF**. Scrubs planifiés (pas d'ECC garanti).

---

## P0 — Backup / DR (le manque critique — cible du week-end)

**État actuel** : zerobyte déployé mais **ne sauvegarde rien** (compose ne monte aucun volume applicatif) ; pas d'offsite immuable prouvé. Un hub VPN + coffre + prod **sans backup fonctionnel**.

**Cible = 3-2-1-1-0** (SOTA 2026 : +1 immuable/air-gap, +0 = restore vérifié) :

| Couche | Action |
|---|---|
| **Copie 1 (source)** | Étendre `roles/backup-config` : Vaultwarden `docker exec vaultwarden /vaultwarden backup` (natif ≥1.32.1) ; **Headscale `.backup`/`VACUUM INTO`** (⚠️ WAL depuis 0.23 → **JAMAIS** le `stop+cp` de la doc officielle, stale) ; Pi `~/work`. + les dumps Sese existants (pg_dump/qdrant snapshot). |
| **Copie 2 (locale) = NAS** | **PULL nocturne** (SSH restreint forced-command, le NAS tire → un nœud compromis n'a pas les creds pour effacer le backup) → restic local sur ZFS. **Promouvoir le NAS en copie QUOTIDIENNE** (le plan actuel `DISASTER-RECOVERY.md` Option C « miroir mensuel » = RPO trop lâche). |
| **Copie 3 (offsite « 1 »)** | Hetzner Object Storage — **nouveau bucket avec Object Lock mode COMPLIANCE activé à la création** (non rétroactif) + ré-init repo restic. Le NAS local ≠ offsite (« un disque à la cave ne compte pas »). |
| **+1 immuable** | L'Object Lock compliance **remplit ce rôle** — seul mécanisme qui ferme le trou « Seko-VPN compromis + creds volés efface tout » (l'append-only restic/kopia NE le ferme PAS : un `forget` légitime avec les vrais creds purge quand même). |
| **+0 vérifié** | healthchecks.io (dead-man switch dédié aux crons — Uptime Kuma seul ne détecte pas un cron qui s'arrête) + `restic check --read-data-subset` mensuel automatisé + drill restore trimestriel (déjà documenté). Un échec de vérif doit **arrêter** les backups vers ce repo, pas juste alerter. |

**Outillage** : rester **restic** (v0.19.1, prod ; Borg 2 encore beta, Kopia n'apporte rien d'unique). ZFS `syncoid` en complément pour protéger la copie locale du NAS (pas un substitut à la cohérence DB). **→ retire zerobyte** (remplacé). DB : `pg_dump` suffit (pas de cluster) ; SQLite toujours via `.backup`/`VACUUM INTO` (WAL).

---

## P1 — Nœud IA local (NAS + 3060) — après vérif Above-4G

- **Stack** : compiler **llama.cpp depuis les sources** (Ollama précompilé = AVX2 → *illegal instruction* sur Westmere) + CUDA 3060.
- **Modèles mi-2026** : Gemma 4 E4B (multimodal, meilleur ratio), Qwen3.5-8B/9B, Phi-4-mini (reasoning). 3060 : **7-8B Q4 ~40 tok/s**, 14B Q4 ~20 tok/s, MoE 30B-A3B via `--n-cpu-moe`.
- **LiteLLM route LOCAL-FIRST** (7-14B) → cloud = **overflow/fallback** (inverse le modèle de coût actuel). Respecte le cap 5$/j en le vidant moins.
- **Rapatrier embeddings + worker Qdrant** du Pi (fragile, a OOM) vers le NAS GPU. Modèle : Qwen3-Embedding-0.6B ou BGE-M3 (multilingue). Garder le `MemoryMax` systemd côté Pi.
- **ComfyUI léger + Whisper** locaux (gen légère content-factory vs RunPod pour le lourd ; STT gratuit).
- **Économie** : X58 idle 80-150W → sous le cap 5$/j, le 24/7 peut coûter plus que les tokens économisés. **Wake-on-LAN / démarrage à la demande** pour batchs + fenêtre de pull, pas 24/7.

---

## P2 — Topologie compute / coût (débloqué par le NAS)

- **Décharger Sese OVH** (goulot 8Go) vers le NAS : Qdrant/mémoire, batch, observabilité → permet le **downgrade OVH** visé (`target_architecture`) = économies récurrentes.
- **Observabilité** : câbler **Alloy→Loki** (aujourd'hui `alloy_loki_url:""` = inerte) ; héberger **Loki/Grafana sur le NAS** (stockage/rétention lourds, courant « gratuit ») au lieu du cloud exigu. Grafana reste sur `tala` en façade si voulu.

---

## P3 — Résilience mesh / VPN

- **Seko sur le tailnet** (aujourd'hui `server_tailscale_ip` = IP publique → admin SSH via net public = surface fail2ban) + bascule **SSH 804** (`playbooks/harden-ssh.yml`, ⚠️ aligner `AllowUsers` ∈ user connecté avant, sinon lock-out).
- **Headscale = SPOF** : sa DB SQLite (WAL) sauvegardée **sur le NAS** + rebuild IaC rapide ; **versionner `config.yaml`** (non versionné → drift, noté `CONCERNS.md`). Upgrade Headscale = séquentiel 8-hop (audit Seko §2), **après** backup DB prouvé.

---

## P4 — Secrets (en cours, déjà SOTA)
Coffre Vaultwarden + `secret-run` (P1a/P1a-bis faits ce jour) — aligné SOTA. Poursuivre P0/P1b coffre. **Fusionner** le backup Vaultwarden du plan coffre (T1/T2) dans P0 ci-dessus (même mécanisme).

## P5 — Hygiène ops
- **Anti-drift versions** : Renovate/dependabot sur `versions.yml` (l'audit Seko a montré des bumps manuels qui dérivent — ex. vaultwarden default inerte). + check drift planifié.
- Traiter les lots de l'audit Seko (`Seko-VPN/docs/audits/2026-07-16-...`) : pin Portainer/Uptime, docs périmées, Caddy 2.11 (rebuild OVH), etc.

---

## Ordre d'exécution recommandé (week-end + après)
1. **Week-end** : chemin critique matériel (Above-4G, ECC, PSU) → OS Debian+ZFS → **P0 backup** (NAS copie locale pull + Object Lock offsite + sources Vaultwarden/Headscale) = referme le risque #1.
2. **Si Above-4G OK** : P1 nœud IA local (llama.cpp+3060, LiteLLM local-first, migration embeddings).
3. **Ensuite** : P2 (décharge Sese + observabilité), P3 (Seko tailnet/804 + Headscale backup), P5 (anti-drift).
4. **Continu** : P4 coffre.

**Règle d'or** : P0 (backup prouvé) **avant** tout upgrade Headscale (migration SQLite du mesh) — jamais migrer sans restore prouvé.

## Fichiers d'implémentation
`VPAI/roles/backup-config/` (étendre) · `VPAI/docs/DISASTER-RECOVERY.md` (Option C → copie quotidienne) · `VPAI/inventory/group_vars/all/versions.yml` (pinner restic + nouveau rôle NAS) · nouveau rôle Ansible `nas` (Debian+ZFS+restic-pull+llama.cpp).
