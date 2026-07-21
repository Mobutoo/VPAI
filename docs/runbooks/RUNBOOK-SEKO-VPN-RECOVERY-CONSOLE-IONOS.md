# RUNBOOK — Récupération Seko-VPN via console Ionos

**Host** : Seko-VPN (Ionos VPS) — `87.106.30.160`
**Rôle** : Headscale (hub coordination VPN mesh), webhook-relay, backup Zerobyte
**Symptôme** : management SSH injoignable depuis waza ; `Permission denied (publickey)` puis `Connection refused` port 22/804.
**Pré-requis** : accès au panel Ionos (DCD / Cloud Panel), credentials login local du VPS — **nécessaire uniquement si les rebonds réseau du §0-bis échouent tous les deux**.
**Origine** : `docs/audits/2026-05-29-infra-audit.md §2.3` (panne connue, non résolue depuis le 29-05) + risque #7 Headscale SPOF.

> **Révision 2026-07-21** — Revue Codex initiale (`~/work/ops/loops/reviews/REVIEW-FILE-RUNBOOK-SEKO-VPN-RECOVERY-CONSOLE-IONOS-20260721-1624.md`), 2 findings HIGH confirmés par escalade Claude, corrigés dans cette version :
> 1. **HIGH #1** — l'ancienne annexe (état daté 2026-06-13) affirmait que Seko n'a pas d'IP tailnet et que la console est l'unique accès. **FAUX depuis le 2026-07-17** : Seko est enrôlé au mesh en tant que *client* (IP `100.64.0.5`), cf. `playbooks/utils/vpn-node-enroll.yml`, VPAI commit `504c97e`, Phase 0 loops T0.5 (`~/work/ops/loops/reports/2026-07-17-phase0.md`). Nouvelle **§0-bis** : épuiser les rebonds réseau avant d'ouvrir la console.
> 2. **HIGH #2** — la commande `ufw allow 22/tcp` (§3) ouvrait SSH à toutes les sources avant toute restriction. Corrigé : règle restreinte dès la première exécution + purge des règles larges préexistantes.
>
> 3 cycles de re-revue Codex/`review-file.sh` ont suivi (16:57 → 2 HIGH résiduels dont un alias SSH `sese-ai` faussement qualifié d'indépendant du tailnet + une règle UFW ajoutée sans purge de l'existant ; 17:01 → 1 HIGH résiduel, contradiction interne §0/§1 sur la preuve de vie du host ; 17:05 → **0 HIGH / 4 MED / 1 LOW**, seuil atteint). Rapports : `REVIEW-FILE-RUNBOOK-SEKO-VPN-RECOVERY-CONSOLE-IONOS-20260721-{1624,1657,1701,1705}.md`. MED intégrés : diagnostic différentiel firewall (host vs cloud, pas de cause unique présumée), nom de service `ssh`/`sshd` à détecter dynamiquement plutôt que codé en dur, statut du relay Tailscale traité comme un signal parmi d'autres (pas une preuve de santé Headscale), notation `nc` de ports combinés invalide, escalade console conditionnée à l'absence d'erreur locale corrigible, fallback headscale natif/Docker.

---

## 0. État constaté (à dater à chaque exécution)

| Test depuis waza | Résultat 2026-06-13 | Lecture |
|---|---|---|
| `nc -zvw4 87.106.30.160 22` | **refused** | host répond (RST) → sshd absent OU reject local. PAS un DROP cloud-firewall à lui seul. |
| `nc -zvw4 87.106.30.160 804` | **refused** | idem |
| `nc -zvw4 87.106.30.160 2222` | **timeout** | port filtré (DROP) |
| `nc -zvw4 87.106.30.160 8022` | **timeout** | idem — deux commandes distinctes, `nc` ne teste pas une notation `2222/8022` combinée |
| `tailscale status` (waza) | relay `"seko"` **actif** | **Signal partiel uniquement** : prouve que le relais DERP embarqué dans Headscale répond, PAS que le control-plane Headscale est sain dans son ensemble. Ne pas conclure « Headscale tourne » sur ce seul test — cf. §5 pour les 3 signaux à croiser. |

> **Diagnostic différentiel — hypothèses, pas certitudes** :
> - `refused` (RST) sur 22 → sshd arrêté/crashé **ou** firewall *host* en `REJECT`. Piste probable : **local au host**.
> - `timeout` → un DROP quelque part sur le chemin. Ça **peut** être le cloud-firewall Ionos (§4), mais ça peut aussi être un DROP `nftables`/`iptables` local (§3) ou un équipement réseau intermédiaire. **Ne pas présumer la cause avant d'avoir vérifié §3 ET §4** — l'audit 29-05 voyait `timeout`, on voit maintenant `refused` : l'état a changé, donc les hypothèses aussi doivent être reconfirmées à chaque exécution.

---

## 0-bis. Épuiser les accès distants AVANT la console (2026-07-21)

La console Ionos (VNC) est un dernier recours coûteux (pas de copier-coller aisé, session isolée du reste de la stack). **Avant de l'ouvrir**, tester dans cet ordre :

### (a) SSH direct via le mesh Tailscale — `100.64.0.5`

Depuis le **2026-07-17**, Seko est enrôlé comme **client** du tailnet qu'il coordonne (pas seulement comme control-plane) — cf. `playbooks/utils/vpn-node-enroll.yml`, commit VPAI `504c97e`. Ce chemin couvre le cas « firewall public cassé / port filtré côté cloud » alors que sshd est vivant sur l'interface `tailscale0` :

```bash
ssh -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.5              # port 22
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.5        # si hardening SSH déjà actif (cf §6)
```

> ⚠️ IP mesh brute → **toujours `-i` explicite**. Aucun alias `Host` dédié pour `100.64.0.5` dans `~/.ssh/config` de waza → pas d'`IdentityFile` implicite (même piège que la « cause A » documentée en §6 pour l'IP publique).

**Limite connue, à VÉRIFIER au moment T (ne pas présumer)** : Headscale (le control-plane du mesh) tourne *sur* Seko lui-même. Si le service Headscale est down (pas juste sshd), le nœud client Seko peut potentiellement décrocher du mesh (perte de netmap/DERP) — dans ce cas (a) peut échouer indépendamment de l'état de sshd. Si (a) échoue, ne pas conclure que sshd est mort : passer à (b), qui est indépendant de Headscale.

### (b) Rebond réseau via Sese (IP source ≠ waza)

Rebondir via Sese fait arriver la connexion sur le port public 22/804 de Seko avec une **IP source différente de waza** — couvre un blocage par IP source ou un souci réseau spécifique à waza :

```bash
ssh -J sese seko 'echo OK $(hostname)'
```

> ⚠️ **Piège alias `~/.ssh/config`** : deux alias distincts existent pour Sese-AI — `sese-ai` (résout vers l'IP **tailnet** `100.64.0.14`, dépend donc du mesh/control-plane Headscale) et `sese`/`sese-ai` combiné plus bas dans le fichier (résout vers l'IP **publique** `137.74.114.167`, premier `Host` déclaré qui gagne pour chaque paramètre). Utiliser **`sese`** (pas `sese-ai`) comme jump-host ici pour un chemin réellement indépendant du tailnet de bout en bout — vérifier `ssh -G sese | grep -i hostname` avant usage si le fichier a pu changer.
>
> Pattern de rebond validé en usage réel (anti-ban) — cf. `.planning/seeds/2026-07-16-seko-vpn-reinstall-handoff.md` (« secours anti-ban prouvé : `ssh -J sese-ai seko`, jamais de clé copiée en clair sur le hop » — alias historique, à revalider avec `sese` pour ce runbook). Le `ProxyJump` tunnelise depuis waza, aucune clé privée n'a besoin d'être présente sur Sese.

### (c) Console Ionos — seulement si (a) ET (b) échouent pour une raison RÉSEAU, pas une erreur locale corrigible

Si (a) ou (b) échoue avec `Permission denied (publickey)`, une erreur d'alias `~/.ssh/config`, une clé absente/mauvaise ou un host-key mismatch — ce sont des **erreurs locales côté waza**, pas des preuves que Seko est injoignable. **Corriger et rejouer** avant d'escalader (vérifier `-i`, l'alias exact — cf piège §0-bis b —, `ssh -v` pour le détail de l'échec).

Ouvrir la console KVM (§1) seulement quand (a) ET (b) échouent tous les deux pour une cause **réseau** (refused/timeout, pas d'erreur d'authentification). Noter dans le rapport d'incident **lequel des deux chemins a échoué et comment** (refused/timeout/erreur clé) — ça oriente le diagnostic une fois en console.

---

## 1. Ouvrir la console KVM (pas de rescue — le host tourne)

*Uniquement si §0-bis (a) et (b) ont échoué.*

Le mode rescue a un coût réel (perte de l'état runtime) — ne l'utiliser QUE si le host semble totalement injoignable au niveau réseau. Le signal `tailscale status` seul (§0) est **insuffisant** pour trancher (cf §0/§5 — ne prouve que le relay DERP, pas la santé globale). Avant de choisir, croiser au moins deux signaux indépendants :
- `nc` en §0 renvoie `refused` (RST) plutôt que `timeout` sur au moins un port → le host répond au niveau TCP, donc vivant.
- HTTPS via Caddy répond sur un vhost connu (`curl -sf https://<vhost connu>/` — ex. Vaultwarden `/alive`, cf. précédent réel du 2026-07-16 : host down présumé mais HTTPS 200 constaté).

Si ces signaux confirment un host qui répond (même partiellement), **ne pas** booter en mode rescue → utiliser la console KVM/VNC standard. Si TOUS les ports/services testés sont en `timeout` et qu'aucun HTTPS ne répond, documenter ce constat avant de considérer le rescue (hors périmètre standard de ce runbook — évaluer l'impact avec un humain avant de trancher).

1. Panel Ionos → **Servers & Cloud** (DCD) ou **Cloud Panel** selon le compte.
2. Sélectionner le VPS `87.106.30.160`.
3. **Remote Console** / **KVM Console** → ouvre un terminal VNC dans le navigateur.
4. Login local : user `mobuone` (sudo) — credentials hors-bande (gestionnaire de mots de passe / Vault). PAS de clé SSH ici, c'est un login console.

---

## 2. Diagnostic sshd (cause #1 probable — `refused`)

```bash
sudo systemctl status ssh sshd 2>&1 | head -20      # service actif ? lequel des deux noms existe ?
sudo systemctl list-unit-files | grep -E '^(ssh|sshd)\.(service|socket)'   # nom réel chargé sur CE système
sudo ss -tlnp | grep -E ':(22|804)\b'               # sshd écoute-t-il ?
sudo sshd -T 2>&1 | grep -E '^port|listenaddress|passwordauthentication'
sudo journalctl -u ssh -u sshd --since "-7d" --no-pager | tail -40
```

Décision :
- **service `inactive`/`failed`** → identifier le nom réellement chargé (sortie de `list-unit-files` ci-dessus — Debian/Ubuntu récents peuvent exposer `ssh.service` ET/OU `ssh.socket` en activation socket) puis agir sur CE nom précis : `sudo systemctl restart <nom> && sudo systemctl enable <nom>`. Ne pas redémarrer `ssh` par réflexe si c'est `sshd` qui est chargé (et inversement) — un restart sur un nom inexistant échoue silencieusement (« Unit not found ») sans toucher au vrai service.
- **erreur de config** (journal) → corriger `/etc/ssh/sshd_config(.d/*)`, puis `sudo sshd -t` (test syntaxe) avant restart.
- **écoute sur autre port** (pas 22) → noter le port réel, ajuster `~/.ssh/config` côté waza (cf §6).

---

## 3. Diagnostic firewall HOST (cause #1bis)

```bash
sudo ufw status verbose                              # si ufw
sudo iptables -S | grep -E '22|804|REJECT|DROP'      # règles brutes
sudo nft list ruleset 2>/dev/null | grep -E '22|reject|drop'
```

Réparer (ufw — adapter au port réel) — **restreindre la source dès la première commande, jamais d'ouverture large même « temporaire »**, et **purger toute règle large déjà présente** (ufw empile les règles ALLOW : une ancienne règle ouverte reste active même après l'ajout de règles restreintes) :

```bash
# 0. Purger toute règle SSH large PRÉEXISTANTE (ex: '22/tcp ALLOW Anywhere', '804/tcp ALLOW Anywhere')
#    AVANT de considérer le firewall comme corrigé — sinon le port reste exposé en parallèle.
sudo ufw status numbered
# Pour CHAQUE ligne large trouvée (Anywhere / Anywhere (v6) sur 22 ou 804) :
#   sudo ufw delete <numéro>          # confirmer 'y' — répéter jusqu'à ce que 'status numbered' n'en montre plus

# 1. Ajouter les règles restreintes :
# Mesh tailnet (couvre §0-bis a et toute admin future via VPN) :
sudo ufw allow in on tailscale0 to any port 22 proto tcp comment 'ssh via mesh tailnet'
# Rebond connu via Sese (couvre §0-bis b) :
sudo ufw allow from 137.74.114.167 to any port 22 proto tcp comment 'ssh rebond sese'
# Optionnel : SEULEMENT si l'IP publique de waza à cet instant est connue et stable :
# sudo ufw allow from <ip_waza_connue_a_cet_instant> to any port 22 proto tcp comment 'ssh waza direct'
sudo ufw reload

# 2. Revérifier qu'il ne reste AUCUNE règle large :
sudo ufw status numbered
```

> ⚠️ Ne **JAMAIS** exécuter `ufw allow 22/tcp` sans restriction de source — c'est exactement le risque signalé par la revue Codex (HIGH #2). Ne pas se contenter d'AJOUTER des règles restreintes : **vérifier et supprimer explicitement** toute règle large préexistante (étape 0 ci-dessus), sinon elle reste active en parallèle et le port demeure exposé à toutes les sources (2e HIGH confirmé en re-revue). Si le port réel diffère (804 post-hardening, cf §2), adapter les règles ci-dessus en conséquence. Hardening SSH normalisé absent sur seko (audit risque #9) — cette règle restreinte manuelle est un correctif d'urgence, à codifier ensuite dans le rôle `security` du repo `Seko-VPN` (cf §7).

---

## 4. Diagnostic cloud-firewall Ionos (hypothèse à vérifier, PAS la cause unique)

> Le firewall réseau Ionos (séparé du host) **peut** expliquer les ports `timeout`, mais ce n'est qu'une hypothèse parmi d'autres (cf §0). Vérifier ce point même si §2/§3 semblent déjà expliquer le symptôme — les deux causes peuvent coexister (ex : sshd down ET règle cloud manquante).

1. Panel → VPS → onglet **Network** / **Firewall Policies**.
2. Vérifier une règle **inbound TCP 22** (et 804 si conservé) depuis la source admin.
3. Ajouter/activer la règle si absente. Appliquer.

---

## 5. Validation sur le host (avant de quitter la console)

```bash
sudo systemctl is-active <nom_detecte_en_2>           # → active — RÉUTILISER le nom réellement détecté en §2 (ssh, sshd, ou ssh.socket si activation socket), pas 'ssh' en dur
sudo ss -tlnp | grep ':22'                           # → LISTEN
sudo sshd -t && echo "config OK"

# Santé Headscale — 3 signaux DISTINCTS, ne pas les confondre (MED corrigé, cf revue) :
sudo systemctl is-active headscale 2>/dev/null                       # (1) le service tourne sur le host
# (2) le control-plane répond réellement — Seko-VPN déploie tout en Docker Compose
#     (community.docker.docker_compose_v2, cf Seko-VPN/CLAUDE.md) : le conteneur
#     s'appelle 'headscale' en usage normal. Si absent (installation native/systemd
#     hors du pattern habituel), adapter :
sudo docker exec headscale headscale nodes list 2>/dev/null | head \
  || sudo headscale nodes list 2>/dev/null | head              # fallback binaire natif hors conteneur
# (3) depuis WAZA une fois sorti de console : curl -sf https://singa.ewutelo.cloud/health
#     → {"status":"pass"} attendu ; passe par Caddy, indépendant de sshd
```

> Un `tailscale status` "actif" côté waza (cf §0) ne prouve QUE la joignabilité DERP — pas la santé globale du control-plane Headscale. Croiser les 3 signaux ci-dessus avant de conclure.

---

## 6. Validation depuis waza (sortie de console)

```bash
nc -zvw4 87.106.30.160 22                            # → succeeded
ssh seko 'echo OK $(hostname)'                        # alias ~/.ssh/config (clé seko-vpn-deploy)
ssh -i ~/.ssh/seko-vpn-deploy mobuone@100.64.0.5 'echo OK mesh'   # bonus : confirme aussi le chemin §0-bis (a)
```

> **Rappel cause A** : toujours `ssh seko`, **jamais** `ssh mobuone@87.106.30.160`. L'IP brute ne matche que `Host *` → la clé `seko-vpn-deploy` n'est pas présentée → `publickey denied`. Même piège pour l'IP mesh `100.64.0.5` (§0-bis a) : toujours `-i` explicite.
> Si sshd a changé de port en §2, mettre à jour le bloc `Host seko seko-vpn` de `~/.ssh/config` (`Port <n>`).

---

## 7. Durcissement post-récupération (dette à clôturer)

Une fois l'accès rétabli — ces points sont la **vraie cause racine** (host nu + SPOF) :

| Action | Réf audit |
|---|---|
| Sauvegarder la **DB Headscale** (SPOF, non sauvegardée) → restic offsite | risque #7 |
| Appliquer le rôle **hardening**/`security` (Seko-VPN) pour codifier la règle UFW restreinte appliquée en §3 (actuellement manuelle, hors IaC) | risque #9 + revue 2026-07-21 |
| Versionner la config Headscale dans le repo Ansible | REX 2026-02-20 |
| Mettre seko sous **monitoring** (collecteur + alerting) | risque #5 |
| Documenter le port SSH réel + restreindre la source inbound | §3/§4 |

---

## Annexe — accès distants disponibles (état 2026-07-21, corrige HIGH #1 de la revue)

- **SSH via mesh Tailscale** (§0-bis a) : disponible depuis le **2026-07-17**. Seko est enrôlé comme **client** du tailnet qu'il coordonne, IP `100.64.0.5` (`playbooks/utils/vpn-node-enroll.yml`, commit `504c97e`). Dépend de la santé du control-plane Headscale (tourne sur Seko lui-même) — à vérifier au moment T (§5), pas à présumer disponible.
- **Rebond réseau via Sese** (§0-bis b) : `ssh -J sese seko` (alias `sese`, IP publique — pas `sese-ai`, cf piège §0-bis b), transite par le réseau public OVH→Ionos avec une IP source différente de waza.
- **Console Ionos** : reste nécessaire dès que (a) ET (b) échouent tous les deux **pour une cause réseau confirmée** (refused/timeout, PAS une erreur locale corrigible côté waza — publickey/alias/clé, cf §0-bis c) — **quelle que soit la cause réseau présumée** (sshd mort/crashé, firewall host ou cloud en DROP reproduit sur les deux chemins, panne réseau côté waza ou côté Seko, Headscale down affectant (a) sans affecter (b), etc.). Ne pas présumer une cause réseau unique avant d'avoir diagnostiqué en console (§2-§4) — l'échec conjoint réseau de (a) et (b) est le critère déclencheur, pas une hypothèse sur *pourquoi* ils échouent.
- webhook-relay/Zerobyte n'exposent pas de shell (inchangé).

→ **Ordre d'escalade** : §0-bis (a) mesh → (corriger/rejouer toute erreur locale) → §0-bis (b) rebond Sese → (idem) → §1 console Ionos (seulement après deux échecs réseau confirmés, sans présumer laquelle des causes du §0 en est responsable).

**Historique, PÉRIMÉ depuis le 2026-07-17** (état daté 2026-06-13, conservé pour traçabilité de la revue Codex, ne plus utiliser comme référence opérationnelle) : *« seko ≠ node tailnet (c'est le serveur de coordination) → pas d'IP `100.64.0.x` → pas de SSH via mesh. Console Ionos = seule voie. »*
