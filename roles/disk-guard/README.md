# Role: disk-guard

Purge automatique du disque sous pression. Timer systemd toutes les 15 min ; no-op tant que l'usage `/` < 80 %.

## Paliers

| Seuil | Actions |
|-------|---------|
| **≥ 80 %** (SOFT) | `docker builder prune -af` + `docker image prune` (dangling) + suppression des **leases containerd orphelines > 7 j** (uniquement si driver = `overlay2`). **Zéro re-pull.** |
| **≥ 85 %** (MID, après palier SOFT) | ajoute `docker image prune -a --force --filter "until={{ disk_guard_image_max_age_hours }}h"` — supprime les images inutilisées **créées il y a > 7 j** (filtre `until` = date de *build*, pas de dernière utilisation). Les images encore référencées par un conteneur existant restent épargnées (comportement `-a` standard) ; re-pull possible au prochain deploy. |
| **≥ 90 %** (HARD, après palier MID) | ajoute `docker image prune -a --force` **sans filtre d'âge** (re-pull au prochain deploy). |

Origine : incident 2026-06-02 (disque 100 %). Cause racine = leases containerd orphelines épinglant 9.7 G de snapshots d'un image-store mort, invisibles à `docker system df`. Voir mémoire `sese-disk-containerd-leases`.

⚠️ **Zone morte 80-84 %** : entre `SOFT` (80) et `MID` (85), la seule action possible est le palier SÛR — qui ne trouve souvent rien (cache de build vide, aucune image dangling, leases récentes). Le rôle est donc *structurellement impuissant* dans cette plage. C'est connu et assumé : il alerte, il ne libère pas. Constaté sur sese le 2026-07-31 (80 % stable depuis 2 semaines, 20 G libres — état sain).

## Notifications (stateful depuis 2026-07-31)

Un message Telegram part **uniquement** dans ces quatre cas :

| Déclencheur | Message |
|---|---|
| Détection d'un palier différent de l'état enregistré | 🧹 `detection X → Y` |
| Palier redescendu grâce à la purge du run | 🧹 `retour X → Y apres purge` |
| Baisse d'au moins `disk_guard_gain_min_delta` points (défaut 2) | 🧹 `purge effective (−N pt)` |
| Rappel de stagnation — 24 h à SOFT, **1 h à MID/HARD** | 🧹 `rappel (toujours ≥ 80 %)` |
| Retour sous le seuil de sortie (`disk_guard_threshold_clear`, défaut 77) | ✅ `retour a la normale` |

**Trois garde-fous, chacun contre une façon distincte de re-spammer ou de devenir muet :**

1. **Bande morte.** Le seuil de sortie (77) est volontairement inférieur au seuil d'entrée (80). Un disque parqué *pile* sur 80 oscille 79↔80 : sans elle, chaque poll produirait une alternance rouge/vert. Entre 77 et 80, on ne repasse jamais au vert.
2. **Plancher anti-rafale** (`disk_guard_min_notify_sec`, défaut 1 h). Toute notification qui n'est **pas une montée de palier** attend ce délai. Sans lui, le déclencheur « gain de purge » suffit à re-spammer : un seul point d'écart entre les deux mesures d'un même run (rotation de logs, conteneur qui sort) le rallume à chaque poll. Une escalade, elle, n'est **jamais** retardée — et « escalade » se juge par rapport au dernier palier **effectivement notifié** (`LAST_NOTIF_TIER`), pas à l'état courant : sinon un disque oscillant autour d'un seuil (88 → 84 → 88…) redétecterait `MID` à chaque run et contournerait le plancher à chaque fois. La répétition d'un palier déjà annoncé est donc différée d'au plus 1 h ; une aggravation réelle (SOFT déjà notifié → HARD) part tout de suite.
3. **Non-collant vers le haut.** Dans la bande morte, `tier_of` conserve `SOFT` mais **rétrograde `MID`/`HARD` vers `SOFT`** (et persiste la rétrogradation, silencieusement). Garder `HARD` à 78 % rendrait une remontée ultérieure à 95 % totalement silencieuse jusqu'au rappel.

**Deux paliers distincts par run.** `TIER_IN` = ce qui est détecté à l'entrée (`BEFORE`) → gouverne l'escalade. `TIER_OUT` = ce qui reste après purge (`AFTER`) → gouverne l'état persisté. Ne juger que sur `AFTER` rendrait un run 95 % → 78 % silencieux ; ne juger que sur `BEFORE` écrirait un palier que le poll suivant contredirait.

**L'état n'avance que si la notification est partie.** Un échec `curl` transitoire n'efface jamais un franchissement : il sera retenté au poll suivant. Un gain de purge, lui, n'est pas rejouable (au poll d'après `AFTER` n'est plus `< BEFORE`) — il est donc mémorisé dans `PENDING_GAIN` jusqu'à envoi réussi.

**Le script sort en code ≠ 0** quand l'état n'est pas écrivable (`ENOSPC` — précisément le moment où le rôle sert), quand `df` échoue, ou quand une notification est perdue. Une unité systemd en échec est un signal ; une unité verte et muette est un mensonge.

État persistant : `/opt/disk-guard/state` (0600 root), clés `LAST_TIER` / `PENDING_GAIN` / `LAST_ALERT`. Écriture par `mv` (rename(2), réellement atomique — **pas** `install`, qui détruit la cible avant de la recréer). `LAST_ALERT` est écrite en dernier et sert de sentinelle de troncature : si elle manque, l'état est réinitialisé.

**Avant 2026-07-31** : `notify()` était appelé sans condition dès l'usage ≥ 80 %. Sur un disque stable, cela donnait **96 messages identiques par jour** (`Disque / : 80% → 80%`). Le commentaire du script prétendait « notif uniquement si une action a eu lieu » — rien ne gardait l'appel.

## Sécurité / prudence

- **Lock `flock`** : pas de run concurrent.
- **Garde d'âge leases** (`disk_guard_lease_min_age_days`, défaut 7) : ne touche jamais une lease fraîche d'une opération en cours.
- **Garde driver** : nettoyage leases uniquement si Docker tourne sur `overlay2` (image-store containerd inactif).
- **Jamais de restart containerd** (rebooterait les shims). On passe par `ctr leases delete --sync` qui déclenche le GC.
- `image prune -a --filter until=...` réservé au palier MID (85 %) — le filtre porte sur la date de **création** de l'image, pas sa dernière utilisation ; une image encore référencée par un conteneur existant reste épargnée quel que soit son âge.
- `image prune -a` sans filtre réservé au palier HARD (90 %).

## Variables clés (`defaults/main.yml`)

| Variable | Défaut | Rôle |
|----------|--------|------|
| `disk_guard_threshold_soft` | `80` | Seuil palier sûr |
| `disk_guard_threshold_mid` | `85` | Seuil palier intermédiaire (images anciennes) |
| `disk_guard_threshold_hard` | `90` | Seuil palier agressif |
| `disk_guard_lease_min_age_days` | `7` | Âge min lease orpheline |
| `disk_guard_image_max_age_hours` | `168` | Âge min (h) image inutilisée au palier MID |
| `disk_guard_threshold_clear` | `77` | Seuil de **sortie** d'alerte (bande morte anti-clignotement) |
| `disk_guard_reminder_sec` | `86400` | Rappel de stagnation au palier SOFT |
| `disk_guard_reminder_critical_sec` | `3600` | Rappel aux paliers MID/HARD (un disque à 90 % ne peut pas attendre 24 h) |
| `disk_guard_min_notify_sec` | `3600` | Plancher entre deux notifications non escaladantes |
| `disk_guard_gain_min_delta` | `2` | Baisse minimale (points) comptée comme « purge effective » |
| `disk_guard_timeout_start_sec` | `10min` | Borne de durée d'un run (`Type=oneshot` → `TimeoutStartSec`) |
| `disk_guard_state_file` | `/opt/disk-guard/state` | État persistant (jamais templaté) |
| `disk_guard_timer_on_unit_active_sec` | `15min` | Cadence |
| `disk_guard_notify_telegram` | `true` | Notif (réutilise `telegram_monitoring_*`) — réellement câblé depuis 2026-07-31 |

## Déploiement

```bash
make deploy-role ROLE=disk-guard ENV=prod
# Vérif — `sudo` OBLIGATOIRE sur journalctl : l'utilisateur de déploiement n'est ni dans
# `adm` ni dans `systemd-journal`, donc sans sudo le journal des units système paraît VIDE
# (piège rencontré le 2026-07-31 : « le service ne loggue rien » était faux).
ssh sese 'systemctl list-timers disk-guard.timer; sudo journalctl -u disk-guard -n 20'
# Test manuel (force un run immédiat)
ssh sese 'sudo systemctl start disk-guard.service && sudo journalctl -u disk-guard -n 30'
# État courant de la machine à états
ssh sese 'sudo cat /opt/disk-guard/state'
```

## Tests

```bash
source .venv/bin/activate
roles/disk-guard/tests/test-notification-state-machine.sh
```

Banc d'essai autoportant (46 cas) : il rend le template avec les valeurs de `defaults/main.yml`, puis exécute le script réel avec `df`/`docker`/`ctr`/`curl` bouchonnés. Couvre le scénario de l'incident (80 % stable × 5 polls → 1 notif), l'oscillation 79↔80, l'oscillation autour de MID, la ré-escalade HARD après bande morte, l'échec `curl`, l'état non écrivable, la panne `df`, l'horloge qui recule, l'état tronqué.

**Aucune modification du script ne doit être poussée sans que ce banc passe** — les trois défauts les plus graves de la première version (spam par gain non borné, mutisme sur ré-escalade, spam à disque plein) sont précisément ceux qu'une première rédaction du banc, écrite par l'auteur du correctif, ne testait pas.

## Tags

`[disk-guard, phase5]`
