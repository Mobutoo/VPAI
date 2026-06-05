# REX Session — Panne SSH waza : OOM worker → bail DHCP eth0 perdu (2026-06-05)

## Objectif

Perte totale d'accès SSH à **waza** (Workstation Pi, RPi5 16G) pendant ~6h30. Symptôme côté utilisateur : SSH-via-Tailscale mort, waza disparu du mesh — **mais** `ewutelo` (autre machine derrière la **même box**) toujours en ligne. Investiguer la cause réelle après reboot manuel (19:08), puis durcir contre la récurrence.

État initial au diagnostic : waza rebooté 15 min plus tôt, connectivité revenue (gateway + Internet + Tailscale OK).

---

## Diagnostic — fausses pistes écartées

| Hypothèse | Verdict | Preuve |
|---|---|---|
| Crash / reboot du Pi | ❌ | `last reboot` : up depuis May 31 14:05 jusqu'au reboot **manuel** 19:08. `sshd Received signal 15` (arrêt propre) à 19:07:36 |
| Panne box / ISP (WAN down) | ❌ | `ewutelo` (même box) resté sur le mesh → WAN sain. La box répond au ping maintenant |
| Câble / lien eth0 | ❌ | Aucun `eth0: Lost carrier` kernel pendant la fenêtre — lien physique up |
| UFW bloque le DHCP | ❌ | `grep "UFW BLOCK" ... DPT=67/68` → vide |
| Tailscale (reconnexion ratée) | ⚠️ Symptôme, pas cause | tailscaled victime : `Rebind defIf="" ips=[]` ×3314, aucune route possible sous lui |

---

## Root cause — chaîne causale (logs `journalctl -b -1`)

1. **Worker mémoire non-borné** : `llamaindex-memory-worker` (user unit, oneshot, `embeddinggemma-300m` + sentence-transformers) → pic **~3,2 Go RSS**, `total-vm` 16 Go. Aucune limite cgroup (`Nice=19`/`IOSchedulingClass=idle` seulement).
2. **OOM global répété** : Jun04 20:20, 21:53, **Jun05 00:39** (`oom-kill ... cpuset=systemd-networkd.service` → c'est networkd qui déclenche l'oom-killer, preuve qu'il était lui-même affamé), 00:52 (+chrome).
3. **Bail DHCP perdu** : bail eth0 acquis Jun04 06:34, jamais renouvelé sous la pression mémoire. **Jun05 12:36:35** : `avahi: Withdrawing address record for 192.168.1.8 on eth0` + `tailscaled monitor: RTM_DELROUTE ... gw=192.168.1.254` → eth0 perd son IPv4 **et la route par défaut**.
4. **Aucune récupération** : `systemd-networkd` **silence total** sur eth0 de 12:36 à 19:07 — pas un seul DISCOVER/REQUEST/retry. eth0 sans IPv4 pendant 6h30.
5. **Effet tailscale** : plus de route → `magicsock: ... sendto: network is unreachable` (ENETUNREACH), `Rebind defIf="" ips=[]` ×3314 → tunnel down → SSH (`100.64.0.x`) mort.
6. **Reboot** : networkd neuf → DHCP ACK immédiat **19:08:30** → tout revient (prouve que la box répond à un DISCOVER frais ; seul le **renouvellement** avait échoué).

**Insight clé** : `network is unreachable` (ENETUNREACH) = route locale perdue **sur l'hôte**, pas une panne amont. Le diagnostic se joue sur `ip route show default` + corrélation `journalctl | grep oom-kill` avec la fenêtre de renouvellement DHCP. Un hôte sain derrière la même box (ewutelo) qui reste en ligne = la cause est **locale**.

---

## Fix appliqué

### A — Immédiat (live)
- Stop du run worker bloqué (1h12, 2,9 Go).
- Drop-in `~/.config/systemd/user/llamaindex-memory-worker.service.d/10-resource-limits.conf` : `MemoryHigh=3G`, `MemoryMax=4G`, `MemorySwapMax=512M`, `OOMScoreAdjust=1000`. → le worker est OOM-killed **dans son cgroup** avant d'affamer le système. Mémoire libérée 9,2→7,2 Go.

### B — Ansible (idempotent, validé lint + dry-run `failed=0`)
- **Caps worker** codifiés : `roles/llamaindex-memory-worker` (`defaults/main.yml` + `templates/memory-worker.service.user.j2`).
- **P1 — OOM-shield** : `roles/workstation-common` pose `OOMScoreAdjust=-900` en drop-in `/etc/systemd/system/{systemd-networkd,tailscaled}.service.d/10-oom-protect.conf` → le stack réseau n'est jamais 1ère victime de l'OOM-killer.
- **P3 — watchdog passerelle** : `/opt/workstation/bin/net-watchdog.sh` + `net-watchdog.timer` (2 min). Si gateway injoignable (confirmé par 2e cible `1.1.1.1`, anti-flap) → `networkctl reconfigure eth0` (relance DHCP) puis restart `tailscaled` ; escalade restart networkd ; `reboot` optionnel (OFF par défaut). Idempotent : n'agit que si réellement down.
- **Handler reload-only** (pas de restart networkd/tailscaled pendant un play) → anti-lockout (cohérent avec I4/UFW). `OOMScoreAdjust=-900` prend effet au **prochain restart/reboot**.

Déploiement réel : `ansible-playbook playbooks/hosts/workstation.yml --tags net_resilience`.

---

## Leçons

1. **ENETUNREACH ≠ panne amont** : c'est une route locale perdue. Toujours croiser avec un autre hôte du même LAN (ewutelo ici) avant d'accuser la box/ISP.
2. **Un process user en vrille peut tuer le réseau** : sans `OOMScoreAdjust` bas sur networkd/tailscaled, l'OOM-killer global emporte le stack réseau. Tout service réseau critique doit être OOM-shield.
3. **Type=oneshot non-borné = bombe mémoire** : tout worker ML user (embeddings) doit avoir `MemoryMax` cgroup.
4. **systemd-networkd ne re-DISCOVER pas toujours après expiration de bail** sous stress → un watchdog `networkctl reconfigure` est la filet de sécurité pour un Pi headless/remote.
5. **Tailscale est souvent la victime, pas le coupable** : `Rebind defIf="" ips=[]` = il n'a aucune interface/route à binder. Remonter d'un cran (route/DHCP/lien).

Réf : mémoire `project_waza_ssh_dhcp_oom_2026_06_05`. À indexer dans `docs/TROUBLESHOOTING.md` §0 (Workstation Pi) + §12 (Réseau & VPN).
