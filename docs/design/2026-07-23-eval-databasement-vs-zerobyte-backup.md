# Évaluation — databasement (David-Crty) pour nos backups + apport upstream zerobyte

> **Date** : 2026-07-23 · **Méthode** : lecture du **code source** des 2 repos (clone, pas README).
> **Contexte** : design backup v3 approuvé (`2026-07-23-refonte-backup-zerobyte-orchestrateur-seko.md`, restic-based).
> **Verdict court** : **databasement n'améliore PAS nos backups tels que conçus**. Seul apport = **référence des
> commandes de dump cohérent par moteur** (à cribler dans notre Couche 1 / piste A). Rien de portable en PR zerobyte à
> faible coût.

## 1. Ce que databasement est (source-vérifié)

| Point | Constat (chemin:ligne) |
|---|---|
| Stack | PHP 8.5 / Laravel + Livewire, ~26,5k LOC PHP, config **DB-backed** (pas YAML), **MIT** |
| Multi-arch | ARM64 confirmé (CI `docker.yml` `linux/amd64,linux/arm64`) |
| Dumps par moteur | SQLite `.backup` **WAL-safe** (`SqliteDatabase.php:48-59`) ; SQLite/SFTP = **best-effort NON atomique** (`:66-106`) ; Redis `--rdb` (`RedisDatabase.php:30-45`, **restore non supporté**) ; `pg_dump` (`PostgresqlDatabase.php:63-90`) |
| Remote agents | poll **REST sortant** + Bearer (`AgentRunCommand.php:43-79`) ; dump+compress+checksum **sur l'agent** |
| Notifications | 3 canaux (Discord/Gotify/Webhook) |

## 2. Les 3 raisons pour lesquelles il ne s'intègre PAS à notre design

| # | Finding source-vérifié | Conséquence |
|---|---|---|
| **A** | **Aucune sortie plain** : compression gzip/zstd/AES **toujours** appliquée (`CompressionType.php:5-9` = 3 cas, pas de `NONE` ; `CompressorFactory.php:24-33` match exhaustif), réglage **global** (`AppConfigService.php:19`), et le **dump brut est supprimé** après (`BaseCompressor.php:32-34`) | Chaîner databasement→restic = **contre-productif** : flux compressé **différent à chaque run → restic ne dédup pas** ; + **double compression** (restic compresse déjà nativement). **Invalide l'idée « databasement = Couche 1 »**. |
| **B** | **Vérification faible** : sha256 calculé une fois **jamais relu** (`BackupTask.php:116`) ; cron de « vérif » = **existence du fichier seulement** (`SnapshotVerificationService.php:61-99`) ; **aucun restore-drill**, aucun `restic check`-équivalent | Ne fournit **pas** notre H2 (« le 0 »). |
| **C** | **Immuabilité absente** : S3 = PUT simple Flysystem (`Awss3Filesystem.php:19-27`), **aucun Object-Lock/WORM/versioning** | Ne fournit **pas** notre « +1 immuable » anti-ransomware. |

+ **DB-only** : ne couvre pas Qdrant/n8n/Grafana/`~/work`/`~/.claude`/configs.

## 3. Comparaison sur les axes qui comptent

| Capacité | databasement | zerobyte (source-vérifié) | Gagnant |
|---|---|---|---|
| Dump-par-moteur cohérent | ✅ 7 moteurs | ❌ **aucun** (schéma = volumes/chemins seulement, `schema.ts:238-427` ; backup-hooks = webhooks HTTP, pas d'exec local) | **databasement** |
| SQLite WAL-safe | ✅ `.backup` | ❌ copie fichier live via volume `directory` | **databasement** |
| Intégrité dépôt | checksum jamais relu + existence-only | ✅ `restic check` natif + périodique + doctor (`check.ts`, `repository-healthchecks.ts`) | **zerobyte** |
| Restore-drill applicatif réel | ❌ | ❌ | **aucun** (gap commun, notre design l'ajoute) |
| Notifications | 3 canaux | ✅ **9 canaux** | **zerobyte** |
| Remote agents | poll REST sortant | WebSocket bidirectionnel sortant | équivalent |
| Sortie plain (pour restic) | ❌ jamais | ✅ `compressionMode off/auto/max` au repo (`agent-protocol.ts:22`, `schema.ts:286`) | **zerobyte** |

## 4. Réponse à « améliorer zerobyte en upstream avec le meilleur de databasement »

- **Le seul vrai gap de zerobyte que databasement révèle** = **pas de dump-par-moteur cohérent natif** (zerobyte
  snapshotte des chemins ; le dump DB doit être produit en amont — exactement le rôle de notre Couche 1 / piste A).
- **Mais ce n'est PAS une PR bon marché** : ce serait une réécriture **PHP → TypeScript** multi-moteurs (Bun/Hono/Effect),
  à l'opposé des micro-PR ~10 lignes que ce mainteneur merge vite (#305). Classé **« inspirant, pas faisable »** à court
  terme. Licence MIT→AGPL OK, mais il n'y a **quasi rien à copier** (stack différente) — c'est de l'inspiration, pas du
  code réutilisable.
- Sur **tous les autres axes** (verify, notif, remote-agents, sortie plain), **zerobyte est déjà égal ou supérieur** →
  **rien à porter**.
- **Nos PR upstream restent Brique A (#305) + Brique B** (design v3 §3) — petites, ciblées, mergeables. Une éventuelle
  « fonctionnalité dump-cohérent-par-moteur émettant du plain » dans zerobyte serait précieuse à long terme mais reste un
  **gros chantier**, pas un quick win.

## 5. Recommandation actionnable

1. **Ne PAS adopter databasement** pour nos backups (incompatible restic : findings A/B/C).
2. **Cribler sa source MIT** comme **référence de commandes de dump** dans notre **Couche 1 (piste A)** — flags exacts
   utiles, à réimplémenter dans nos scripts qui émettent du **plain** pour restic :
   - `sqlite3 <db> '.backup <out>'` (WAL-safe) pour Vaultwarden/Headscale/Gitea — **mieux que `VACUUM INTO`** sur bases actives.
   - `pg_dump --clean --if-exists --no-owner --no-privileges --quote-all-identifiers --format=custom`.
   - `redis-cli --rdb --no-auth-warning` (attention : databasement **ne restaure pas** Redis — notre drill doit le couvrir).
   - Piège confirmé : SQLite **sur SFTP** = non atomique → toujours `.backup` **local** côté source (jamais copie main+wal+shm à distance).
3. **Upstream zerobyte** : garder Brique A/B ; le dump-par-moteur natif reste « nice-to-have gros chantier », pas une PR à lancer maintenant.

> **Correction de l'analyse README initiale** : l'idée « databasement produit des dumps plain consommés par restic » est
> **fausse** (finding A, source) — databasement n'émet jamais de plain. Retirée.
