# Plan — 3 points restants post-reorg (Phase 3 cleanup)

> Suite vérif Phase 2 (VPAI → `~/work/infra/VPAI`, 2026-06-07). Reorg structurel = OK.
> Ces 3 points sont des **résidus / orthogonaux**, aucun ne bloque le travail courant.
> Repo intact, remote intact, configs vivants propres, memory_v2 interrogeable (R0 session-start OK).

## ✅ STATUT 2026-06-07 (exécuté)
- **P2 FAIT** : `sed` fixtures `~/.claude/hooks/test/*.js` → `~/work/infra/VPAI` ; `run-all.sh` = **ALL TESTS PASS**, 0 résidu.
- **P3 FAIT** : `~/projects/` **supprimé**. `ops`→`~/work/ops`, `mission-control-tui`+`session-analyst(1.7G)`→`~/work/tools`, `writing`→wing `~/work/writing`, `autofix`+parasites `saas/` rm. Placement aligné CLAUDE.md global.
- **P1 RÉSOLU + VÉRIFIÉ** — pin `/etc/hosts` **posé** (`100.64.0.14 qd.ewutelo.cloud`). Client qdrant du worker (env exact) atteint **memory_v2 = 23 692 pts** ; `curl` TLS-vérifié = http 200. Le `qdrant_reachable=False` du `--preflight-only` est **flaky** (contredit par le test autoritatif). Aucun patch `QDRANT_URL`. Détails §P1.

## Triage global

| # | Point | Gravité | Causé par reorg ? | Action |
|---|---|---|---|---|
| P1 | Worker → Qdrant : échec preflight transitoire (config en fait correcte) | 🟢 bas | **NON** (pré-existant) | Pin `/etc/hosts` (robustesse DNS) |
| P2 | Fixtures `~/.claude/hooks/test/*` citent ancien chemin | 🟢 bas | Oui (indirect) | sed fixtures OU laisser |
| P3 | Résidus `~/projects/` (5 dirs + parasites `saas/`) | 🟢 bas | Oui (Phase 1 incomplet) | Classer → move/rm |

---

## P1 — Worker → Qdrant (échec preflight TRANSITOIRE, config correcte)

### Symptôme initial (trompeur)
`index.py --preflight-only` → `ResponseHandlingException: [Errno 111] Connection refused`, `qdrant_reachable: false`.
Mais R0 session-start renvoie des points memory_v2 → Qdrant joignable. → diagnostic plus poussé requis.

### Topologie réelle (confirmée 2026-06-07)
memory_v2 est servi par **`javisi_caddy` sur waza**, extrait Caddyfile :
```
qd.ewutelo.cloud {
    import vpn_only
    reverse_proxy qdrant:6333
}
```
Chemin complet : **`100.64.0.14` (IP tailscale, vpn_only) → `javisi_caddy` → réseau docker `javisi` → service `qdrant:6333`** (conteneur `javisi_qdrant`, bridge 172.20.2.3).

| Élément | Valeur |
|---|---|
| memory_v2 | **23 692 pts, status green** (vérifié `curl -H api-key … https://qd.ewutelo.cloud:443/collections/memory_v2`) |
| Hôte | waza, réseau docker `javisi`, alias service `qdrant` |
| `QDRANT_URL` worker | `https://qd.ewutelo.cloud:443` → **déjà le bon endpoint** |
| Port 6333 direct sur tailscale | **fermé** (qdrant exposé uniquement via Caddy ; pas de subnet docker averti en tailscale) |
| `getent qd.ewutelo.cloud` | `100.64.0.14` (résout déjà, via MagicDNS) |

### Diagnostic
- **La config worker n'a JAMAIS été cassée.** L'échec preflight = blip transitoire (MagicDNS / ACL vpn_only / Caddy momentané).
- Le port 6333 direct étant fermé, l'idée « attaquer l'IP privée:6333 » est **impossible sans deploy sese** ; inutile de toute façon (Caddy fait déjà tailscale → docker).
- Mes `curl 172.20.x:6333` vides = **sandbox du Bash tool** qui bloque les IP bridge docker, pas qdrant down (preuve : via 443 ça répond).

### Action retenue — Option A (pin DNS, robustesse) — ✅ FAIT
Pin posé dans `/etc/hosts` : `100.64.0.14  qd.ewutelo.cloud`. `getent` → `100.64.0.14`. `QDRANT_URL` **inchangé** (SNI/TLS Caddy préservés). Bridge `172.20.2.3:6333` rejeté (IP volatile au recreate).

### Vérification (2026-06-07, env worker exact)
```
curl TLS-vérifié  → http=200, ssl_verify=0, memory_v2 23692 pts green
qdrant_client py  → collections=16, memory_v2 count=23692
```
→ connectivité **prouvée**. `--preflight-only qdrant_reachable=False` = **flag flaky** (transitoire / bug preflight), à investiguer si le worker est ré-armé. Warning version client 1.16.2 vs serveur 1.18.1 (non fatal).

### Options écartées
- **B — ouvrir 6333 sur tailscale sese + `http://100.64.0.14:6333`** : nécessite deploy gaté (ufw + publish container), plaintext. Inutile tant que Caddy marche.
- **C — ne rien faire** : acceptable (Caddy OK, worker disabled), mais le pin /etc/hosts coûte 1 ligne et supprime la cause transitoire.

### Note
Aucun lien avec le déplacement VPAI. Ré-activation timer worker = **gate humain séparé** (cf [[project_memory_worker_control]]). **Ne PAS ré-ingérer** : node_id path-indépendant.

---

## P2 — Fixtures hooks/test (ancien chemin `/home/mobuone/VPAI`)

### Faits
- `~/.claude/hooks/test/` : 14 tests + `harness.js` + `run-all.sh`.
- **Jamais référencés dans `settings.json`** → suite de test **dev manuelle**, pas exécutée par un hook actif.
- Fixtures en dur : `/home/mobuone/VPAI/...` (paths morts depuis Phase 2).
- Hooks **PROD** (hors `test/`) = 0 ancien chemin (déjà vérifié).

### Impact
Nul en runtime. Seul effet : `run-all.sh` échouerait sur les tests qui touchent de vrais chemins (`test-sources.js` surtout — `sources.yml` a changé).

### Options
- **A (reco)** : `sed -i 's#/home/mobuone/VPAI#/home/mobuone/work/infra/VPAI#g' ~/.claude/hooks/test/*.js` puis `bash run-all.sh` → suite revalidée. ~5 min.
- **B** : laisser tel quel (dette test, à corriger au prochain run de la suite).

### Hors-scope assumé
Fichiers `memory/*.md` contenant d'anciens chemins absolus = **contenu historique**, path-indépendant pour l'indexation memory_v2 → **ne pas toucher**.

---

## P3 — Résidus `~/projects/` (Phase 1 incomplet)

### Inventaire (aucun = repo git, aucun référencé en config prod → libres)

| Dir | Taille | Contenu | Reco |
|---|---|---|---|
| `autofix/` | 4K | **vide** (0 entrée) | `rmdir` |
| `writing/` | 4K | **vide** (0 entrée) | `rmdir` (recréer `~/work/writing/` si besoin créatif) |
| `mission-control-tui/` | 36K | 1 entrée | → `~/work/tools/` |
| `ops/` | 24K | 2 entrées | → `~/work/ops/` (nouveau wing) OU fusion docs VPAI — **à trancher** |
| `session-analyst/` | **1.7G** | 5 entrées | → `~/work/tools/` mais **inspecter d'abord** (1.7G = data/cache régénérable ?) |
| `saas/` (résiduel) | — | `.claude/`, `.playwright-mcp/`, `hawkeye-budibase-builder-task2.png`, `story-engine-specs-tmp/` | **parasites → rm** |

### Procédure (idempotente, `cd ~` avant tout `mv`)
```bash
cd ~
# 1. Vides
rmdir ~/projects/autofix ~/projects/writing
# 2. Parasites saas/
rm -rf ~/projects/saas/.claude ~/projects/saas/.playwright-mcp \
       ~/projects/saas/hawkeye-budibase-builder-task2.png \
       ~/projects/saas/story-engine-specs-tmp
rmdir ~/projects/saas
# 3. session-analyst : INSPECTER avant (du -sh sous-dirs ; purger cache si régénérable)
du -sh ~/projects/session-analyst/* | sort -h
# puis : mv ~/projects/session-analyst ~/work/tools/session-analyst
# 4. tools
mv ~/projects/mission-control-tui ~/work/tools/mission-control-tui
# 5. ops : décision wing (voir §décisions)
# mv ~/projects/ops ~/work/ops    OU    intégrer dans VPAI/docs/runbooks/
# 6. ~/projects/ vide → rmdir ~/projects (fin de l'ancien layout)
 rmdir ~/projects 2>/dev/null && echo "ancien layout supprimé"
```

### Décisions ouvertes (gate humain)
1. **`ops/`** : wing `~/work/ops/` dédié, OU absorber dans `VPAI/docs/` ? (2 entrées seulement).
2. **`session-analyst/` 1.7G** : déplacer tel quel, OU purger le cache avant (gain disque) ?
3. **`writing/`** : supprimer définitif, ou recréer `~/work/writing/` (le CLAUDE.md global liste `writing/` comme workspace) ?

### Post
- Maj `~/.claude/CLAUDE.md` global §Workspace si `ops/`/`writing/` changent d'emplacement.
- `rmdir ~/projects` clôt la migration → plus aucun chemin `~/projects` vivant.

---

## Ordre d'exécution recommandé
1. **P3** (rapide, sans risque, clôt le reorg) — sauf décisions ouvertes.
2. **P2 option A** (5 min, revalide la suite test).
3. **P1** (diagnostic à part, gate worker — quand on rouvre le chantier mémoire).

## Rollback
- P3 : `mv` inverse (dirs intacts). Parasites supprimés = irréversibles → vérifier avant `rm`.
- P2 : `git`/file-history des fixtures, ou re-sed inverse.
- P1 : 1 ligne config, diff trivial.
