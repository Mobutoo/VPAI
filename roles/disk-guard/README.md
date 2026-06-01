# Role: disk-guard

Purge automatique du disque sous pression. Timer systemd toutes les 15 min ; no-op tant que l'usage `/` < 80 %.

## Paliers

| Seuil | Actions |
|-------|---------|
| **≥ 80 %** (SOFT) | `docker builder prune -af` + `docker image prune` (dangling) + suppression des **leases containerd orphelines > 7 j** (uniquement si driver = `overlay2`). **Zéro re-pull.** |
| **≥ 90 %** (HARD, après palier SOFT) | ajoute `docker image prune -a --force` (re-pull au prochain deploy). |

Origine : incident 2026-06-02 (disque 100 %). Cause racine = leases containerd orphelines épinglant 9.7 G de snapshots d'un image-store mort, invisibles à `docker system df`. Voir mémoire `sese-disk-containerd-leases`.

## Sécurité / prudence

- **Lock `flock`** : pas de run concurrent.
- **Garde d'âge leases** (`disk_guard_lease_min_age_days`, défaut 7) : ne touche jamais une lease fraîche d'une opération en cours.
- **Garde driver** : nettoyage leases uniquement si Docker tourne sur `overlay2` (image-store containerd inactif).
- **Jamais de restart containerd** (rebooterait les shims). On passe par `ctr leases delete --sync` qui déclenche le GC.
- `image prune -a` réservé au palier HARD (90 %).

## Variables clés (`defaults/main.yml`)

| Variable | Défaut | Rôle |
|----------|--------|------|
| `disk_guard_threshold_soft` | `80` | Seuil palier sûr |
| `disk_guard_threshold_hard` | `90` | Seuil palier agressif |
| `disk_guard_lease_min_age_days` | `7` | Âge min lease orpheline |
| `disk_guard_timer_on_unit_active_sec` | `15min` | Cadence |
| `disk_guard_notify_telegram` | `true` | Notif (réutilise `telegram_monitoring_*`) |

## Déploiement

```bash
make deploy-role ROLE=disk-guard ENV=prod
# Vérif
ssh sese 'systemctl list-timers disk-guard.timer; journalctl -u disk-guard -n 20'
# Test manuel (force un run immédiat)
ssh sese 'sudo systemctl start disk-guard.service && journalctl -u disk-guard -n 30'
```

## Tags

`[disk-guard, phase5]`
