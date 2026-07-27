# Archive Hawkeye — conteneurs supprimés le 2026-07-27

## Contexte

5 conteneurs `hawkeye-*` (+ `hawkeye-flyway`, arrêté) tournaient sur waza depuis
le 2026-05-30 **sans source** : leur label compose pointait vers
`/home/mobuone/projects/saas/hawkeye/docker-compose.yml`, fichier disparu.

Ils consommaient ~1,9 Gio de RAM sans aucune limite mémoire, sur une machine de
16 Go qui s'est fait hard-resetter 4 fois par le watchdog matériel entre le
2026-07-17 et le 2026-07-27 (livelock de reclaim par saturation mémoire).

Supprimés sur décision de l'opérateur. Gain mesuré : **~1,4 Go de RAM rendus**
(used 8893 → 7510 Mo).

## Ce qui est conservé

| Élément | Emplacement | Raison |
|---|---|---|
| Définitions complètes des 6 conteneurs | `docker-inspect.redacted.json` (secrets caviardés ; version complète en 0600 hors dépôt : `/opt/workstation/data/hawkeye-archive/docker-inspect.full.json`) | Seule trace de la configuration (compose disparu) |
| Liste des images | `images.txt` | — |
| Volume PostgreSQL | volume Docker `hawkeye_hawkeye_pgdata` | Données |
| Données Budibase | `/home/mobuone/projects/saas/hawkeye/.data/budibase` (312 K) | Données |
| Images Docker | locales | `hawkeye-api:0.1.0`, `hawkeye-backup:0.1.0`, `hawkeye-postgres:16.14-pgcron` sont des **builds locaux irreconstructibles** (Dockerfile disparu avec le compose) |

## Pour reconstruire

`docker-inspect.redacted.json` (secrets caviardés ; version complète en 0600 hors dépôt : `/opt/workstation/data/hawkeye-archive/docker-inspect.full.json`) contient l'intégralité de la configuration runtime (env,
réseaux, montages, healthchecks, ports). Un `docker-compose.yml` peut en être
dérivé. Les images locales n'étant pas reconstructibles, **ne pas les purger**
(`docker image prune -a`) sans décision explicite.
