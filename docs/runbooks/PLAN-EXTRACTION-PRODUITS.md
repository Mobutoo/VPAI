# Plan d'extraction — produits noyés dans VPAI → repos propres

**Statut** : plan validé, exécution différée (travaux en cours sur les repos cibles au 2026-06-08).
**Origine** : VPAI est le repo **infra** (Ansible). Plusieurs **produits** applicatifs y vivent par accumulation (PRD + skills + workflows n8n + compositions + planning GSD). Ils doivent rejoindre leur wing (`saas/` ou `tools/`) selon `MANIFESTE-CREATION-PROJET.md`.
**Portée** : QUOI migre, QUOI reste, dans QUEL ordre. Ne remplace pas le manifeste (placement/nommage/ingestion) — l'applique.

> **Principe de scission (≠ déplacement bloc)** : chaque produit a deux couches.
> - **Couche infra** (rôle Ansible `*-provision`, templates Jinja2 couplés aux vars inventory) → **reste dans VPAI**.
> - **Couche produit** (PRD, skill métier, workflow n8n logique, composition, code applicatif, planning GSD) → **part dans le repo produit**.
>
> Après scission, le rôle `*-provision` peut `git clone` le repo produit au lieu de vendorer ses `files/`.

---

## 0. Pré-requis communs (avant toute extraction)

1. **Travaux en cours terminés** sur le produit visé (sinon conflit de working tree).
2. **Vérif unicité du nom** (manifeste §2, collision cross-wing = shadow muet) :
   ```bash
   ls -1d ~/work/{infra,saas,tools,refdocs}/* | xargs -n1 basename | sort \
     | grep -ixE 'content-factory|mop-generator|app-factory|palais'
   # zéro ligne attendue par nom = OK
   ```
3. **Placement + git init** au bon wing (manifeste §3) — seul geste requis, l'auto-découverte indexe au prochain run worker.
4. **Préserver l'historique** des fichiers migrés quand c'est possible : `git filter-repo --path <chemin>` (extraction avec histoire) plutôt que `cp`. Sinon `git mv` interne + commit de transition documenté.
5. **Ne JAMAIS hand-edit** le live `sources.yml`/`config.yml` (manifeste §4.2). Exclusion éventuelle via `roles/llamaindex-memory-worker/defaults/main.yml`.

---

## 1. content-factory → `saas/content-factory`

**Maturité** : milestone v2026.3 actif (Phases 5-9). **Extraire APRÈS clôture/stabilisation du milestone.**

### Migre (couche produit)
| Artefact VPAI | Destination repo |
|---|---|
| `docs/PRD-CONTENT-FACTORY.md` | `docs/PRD.md` |
| `roles/openclaw/templates/skills/content-director/` | `skills/content-director/` (le `.j2` redevient skill source ; VPAI garde un pointeur de déploiement) |
| `roles/remotion/files/remotion/Reel*` (ReelMemeSkit, ReelTeaser, ReelFeatureShowcase, ReelMotionText) | `remotion/compositions/` |
| Workflows n8n de production de contenu (`scripts/n8n-workflows/*.json` liés au pipeline 14 étapes) | `n8n-workflows/` |
| `.planning/phases/05-foundation` … `09-integration-fixes` + milestone v2026.3 | `.planning/` (nouveau repo GSD) |

### Reste (couche infra VPAI)
- `roles/content-factory-provision/` (provisionne Qdrant brand-voice + tables NocoDB)
- `roles/kitsu/`, `roles/kitsu-provision/` (déploiement Kitsu/Zou)
- `roles/remotion/` (déploiement du serveur de rendu — cf. aussi extraction `remotion-render-server` ci-dessous)

### Points durs
- Le skill `content-director` est un template `.j2` (rendu avec vars inventory) → extraire la **source** du skill, garder dans VPAI le mécanisme de rendu/déploiement.
- Les workflows n8n : trier `scripts/n8n-workflows/` — seuls les workflows **métier contenu** migrent ; les workflows infra (memory-*, deploy-monitor, session-complete) restent.

---

## 2. mop-generator → `saas/mop-generator`

**Maturité** : produit le plus volumineux/mûr noyé. Empreinte la plus large.

### Migre (couche produit)
| Artefact VPAI | Destination repo |
|---|---|
| `scripts/generate-mop-batch.py`, `generate-mop-wizy.py`, `generate-mop-sop-search.py`, `ingest-mop-kb.py` | `src/` (⚠️ délier le `BASE_DIR` codé en dur — voir points durs) |
| `scripts/mop/` (configs JSON) | `config/` |
| 8 workflows n8n `mop-*` (`scripts/n8n-workflows/mop-*.json`) | `n8n-workflows/` |
| `scripts/typebot/mop-noc-v2.json` | `typebot/` |
| `docs/mop/`, `docs/mop-*.xlsx`, `docs/mop-incidents-alignment.yml` | `docs/` + `data/` |
| REX/sessions MOP (`docs/rex/*MOP*`, `docs/rex/SESSION-MOP-*`) | `docs/rex/` |
| `.planning/research/mop-*`, `.planning/notes/*mop*`, `.planning/seeds/mop-*` | `.planning/` |
| `docs/audits/2026-04-11-mop-generator-execution-audit.md` | `docs/audits/` |

### Reste (couche infra VPAI)
- `roles/mop-templates/` (assets de rendu DOCX/templates déployés) — **ou** migre aussi si le repo produit prend en charge son propre rendu. À trancher à l'extraction.

### Points durs
- Les scripts encodent `BASE_DIR = dirname(dirname(__file__))` puis lisent `docs/`, `roles/` de VPAI → **refacto chemins** (config/env) obligatoire avant qu'ils tournent hors VPAI.
- Workflows `mop-*` : appliquer R1 (`validate_workflow`) + R3 (file-first) après migration, re-déployer via `scripts/deploy-workflow.sh`.

---

## 3. app-factory → `tools/app-factory`

**Maturité** : outillage interne (méta-factory intake→ci→deploy). Wing `tools/` (pas un produit vendable).

### Migre (couche produit)
| Artefact VPAI | Destination repo |
|---|---|
| `docs/superpowers/specs/2026-04-01-app-factory-design.md` | `docs/specs/` |
| `docs/superpowers/plans/2026-04-01-app-factory.md` | `docs/plans/` |
| 5 workflows n8n `af-*` (`af-intake`, `af-ci-hook`, `af-deploy`, `af-phase-complete`, `af-rex-indexer`) | `n8n-workflows/` |

### Reste (couche infra VPAI)
- `roles/app-factory-provision/`

### Points durs
- Les `af-*` orchestrent le cycle de vie GSD/CI → vérifier qu'aucun webhook n'est en dur sur un chemin VPAI avant déplacement (R3-bis : `import:workflow` strippe `webhookId`).

---

## 4. palais → `saas/palais`

**Maturité** : code SvelteKit prêt, vendored, repo pas encore créé. **Cas le plus simple** (faible couplage Ansible).

### Migre (couche produit)
| Artefact VPAI | Destination repo |
|---|---|
| `roles/palais/files/app/` (148 fichiers TS/Svelte) | racine du repo |
| `docs/PRD-PALAIS.md` + `docs/plans/PRD-PALAIS-V2.md` | `docs/` |

### Reste (couche infra VPAI)
- `roles/palais/` (tasks : clone + `pnpm install` + build + serve). Après extraction, le rôle pointe vers `git@github-seko:Mobutoo/palais.git` au lieu de `files/app/`.

### Points durs
- Aucun template Jinja2 dans le code app → extraction quasi mécanique. Vérifier qu'aucune var inventory n'est injectée dans `files/app/` avant de couper.

---

## 5. Cas distinct — PRD-KOODIA-V2 égaré

`docs/plans/PRD-KOODIA-V2.md` vit dans VPAI alors que **`saas/koodia` existe déjà**.
→ Simple déplacement de doc (pas une extraction produit) : `mv` vers `~/work/saas/koodia/docs/`, commit dans les deux repos.

---

## 6. Ordre d'exécution recommandé

| Ordre | Produit | Raison |
|---|---|---|
| 1 | **PRD-KOODIA-V2** | trivial, zéro risque, valide le rituel |
| 2 | **palais** | faible couplage, code autonome, repo à créer |
| 3 | **app-factory** | périmètre net (spec + 5 workflows) |
| 4 | **mop-generator** | gros périmètre + refacto chemins, bloc indépendant |
| 5 | **content-factory** | **en dernier** — milestone actif, attendre clôture |

---

## 7. Checklist par extraction

- [ ] Travaux en cours du produit terminés (working tree propre)
- [ ] Nom validé unique (`ls | grep -ix`, manifeste §2)
- [ ] Wing correct (`saas/` produit vendable, `tools/` outillage) — manifeste §1
- [ ] `mkdir` + `git init` + remote `git@github-seko:Mobutoo/<name>.git`
- [ ] Artefacts produit migrés (avec histoire si possible — `git filter-repo`)
- [ ] Couplages durs traités (BASE_DIR, vars Jinja2, webhooks n8n)
- [ ] Rôle `*-provision` repointé (clone repo) au lieu de vendoring `files/`
- [ ] Workflows n8n migrés : R1 `validate_workflow` + R3 file-first + redeploy
- [ ] Arbo docs/ conforme manifeste §5 (rex/specs/audits/runbooks)
- [ ] `index.py --list-sources` confirme le nouveau repo vu par l'auto-découverte
- [ ] `sources.pod.yml` MAJ seulement si remote git-clonable + inclusion rebuild GPU voulue (manifeste §4.3)

---

## 8. Liens

- `docs/runbooks/MANIFESTE-CREATION-PROJET.md` — placement/nommage/ingestion (autorité)
- `docs/runbooks/MEMORY-TAXONOMY-MANIFEST.md` — dérivation wing/room/doc_kind
- `docs/PRD-CONTENT-FACTORY.md` — produit content-factory
- `docs/superpowers/specs/2026-04-01-app-factory-design.md` — produit app-factory
- `roles/llamaindex-memory-worker/defaults/main.yml` — exclusions/overrides découverte
