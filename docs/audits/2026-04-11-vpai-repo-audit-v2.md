# Audit VPAI repo v2 — 2026-04-11

Date : 2026-04-11
Portee : mise a jour de l'audit v1 (2026-04-09), enrichie par la memoire Qdrant (memory_v1) et l'etat reel du repo au 11/04.

---

## Methode

Sources utilisees :

- Audit v1 : `docs/audits/2026-04-09-vpai-repo-audit.md`
- Memoire Qdrant `memory_v1` : 7 requetes (32 hits pertinents), queries detaillees ci-dessous
- `git status --short` et `git log --oneline -10`
- Lecture directe : `docs/audits/`, `docs/runbooks/`, `.planning/STATE.md`, `.gitignore`, `inventory/group_vars/all/main.yml`
- Audit MOP Ansible compliance : `docs/audits/2026-04-11-mop-generator-execution-audit.md`
- REX session debug 11h : `docs/REX-MOP-AUDIT-2026-04-11.md`, `docs/REX-MOP-DEPLOY-2026-04-11.md`, `docs/REX-SESSION-2026-04-11.md`

Memoire Qdrant — resultats par requete :

| Requete | Hits pertinents VPAI |
|---|---|
| "structure repo VPAI roles organisation" | README.md, TECHNICAL-SPEC.md, CLAUDE.md |
| "refactorisation reorganisation dossiers" | REX-SESSION-2026-02-23.md, .planning/phases/01 |
| "conventions ansible FQCN changed_when" | CLAUDE.md (Conventions Strictes) |
| "docker compose services versions deploiement" | inventory/group_vars/all/versions.yml, roles/docker-stack/ |
| "incidents erreurs n8n litellm caddy" | roles/caddy/tasks/main.yml, PRD.md |
| "documentation runbooks REX architecture" | docs/REX-SESSION-2026-03-04b.md, REX-03-03, REX-03-04 |
| "fichiers non commites git status" | Aucun hit VPAI pertinent (score 0.41 — sujet absent de memory_v1, remplace par lecture directe git status) |

---

## Ce qui a change depuis le 09/04

### Nouveaux fichiers non commites (delta vs audit v1)

Par rapport au `git status` du 09/04 documente dans l'audit v1, les ajouts suivants sont observes au 11/04 :

| Fichier | Nature |
|---|---|
| `scripts/n8n-workflows/mop-ingest-v1.json` | Nouveau workflow n8n (MOP indexation) |
| `scripts/n8n-workflows/mop-search-v1.json` | Nouveau workflow n8n (MOP recherche) |
| `typebot-*.png` (8 captures) | Preuves E2E Typebot (session MOP) |
| `docs/superpowers/plans/2026-04-02-af-phase-complete-status-fix.md` | Plan superpowers non commite |
| `docs/superpowers/specs/2026-04-02-af-phase-complete-status-fix.md` | Spec superpowers non commitee |
| `.planning/research/mop-spec-review-{1,2,3}.md` | Artefacts de recherche session MOP |
| `.planning/phases/09-integration-fixes/.continue-here.md` | Checkpoint de reprise (milestone Content Factory complete) |
| `.planning/phases/09-integration-fixes/09-VERIFICATION.md` | Rapport de verification Phase 9 |

### Nouveaux fichiers commites depuis le 09/04

Les 10 commits recents sont tous tagges `mop:` :
- 31 commits le 11/04 (entre 04:31 et 13:34 UTC)
- Roles Ansible crees : `gotenberg`, `carbone`, `typebot`, `mop-templates`
- Nouveaux docs : `docs/audits/2026-04-11-mop-generator-execution-audit.md`, `docs/audits/qdrant-legacy-migration-map-2026-04-11.md`, `docs/REX-MOP-AUDIT-2026-04-11.md`, `docs/REX-MOP-DEPLOY-2026-04-11.md`, `docs/REX-SESSION-2026-04-11.md`

### Structure roles — evolution

Roles au 11/04 : **60 roles** (vs ~55 au 09/04, estimation).
Nouveaux roles detectes : `carbone`, `gotenberg`, `typebot`, `mop-templates`, `n8n-mcp`, `llamaindex-memory-worker`, `metube`, `openpencil`, `obsidian-collector-pi`.

### Taxonomie docs — etat partiel des recommandations v1

| Sous-dossier | Etat au 11/04 |
|---|---|
| `docs/audits/` | Cree et utilise (3 fichiers) |
| `docs/runbooks/` | Cree (4 fichiers : AI-MEMORY, LOI-OPERATIONNELLE, HUGGINGFACE, AI-MEMORY-OPERATIONS) |
| `docs/specs/` | Cree (1 fichier : SPEC-MONTAGE-BRIDGE) |
| `docs/standards/` | Cree (1 fichier : AI-PLATFORM-STARTER-KIT) |
| `docs/plans/` | Existait deja, contenu enrichi |
| `docs/superpowers/` | Cree (plans/ + specs/ — non commite) |
| `docs/rex/` | Non cree — les 21 REX-SESSION-*.md restent a la racine de docs/ |
| `docs/evidence/` | Non cree — PNG de preuve restent a la racine du repo |
| `docs/archive/` | Non cree |

### Sous-arbre FS/ — toujours present

`FS/flash-studio-complete` et `FS/domain-strategy.md` existent toujours a la racine du repo. La recommandation v1 ("brouille la frontiere entre plateforme infra et produit integre") n'a pas ete traitee. Ce sous-arbre ne contient aucun role Ansible ni playbook — il s'agit d'artefacts produit embarques dans un repo infra.

### Recommendations v1 non implementees

- `FS/` toujours present (voir ci-dessus)
- `.playwright-mcp/` toujours absent de `.gitignore`
- `.planning/COMPACT-CHECKPOINT.md` toujours non ignore
- PNG de preuve (flash-suite-*.png, project-created-e2e.png, etc.) toujours a la racine du repo
- 21 fichiers REX-SESSION-*.md toujours a la racine de `docs/`
- 6 fichiers SPEC-*.md toujours a la racine de `docs/` (1 seulement migre dans `docs/specs/`)
- 6 fichiers GUIDE-*.md toujours a la racine de `docs/`

---

## Apports de la memoire Qdrant

### Convention critique : `postgresql_password` unique partage

Source : `CLAUDE.md` section "PostgreSQL — Convention critique" via memory_v1.

Tous les users DB (n8n, litellm, nocodb, sure, zou/kitsu) utilisent `{{ postgresql_password }}`. Creer un `postgresql_xxx_password` separe = crash-loop garanti (`password authentication failed`). Toute reorganisation de roles impliquant postgresql doit preserver ce contrat.

### Piege handlers env_file (Docker Compose)

Source : `CLAUDE.md` section "Docker" via memory_v1.

`state: restarted` ne recharge PAS l'env_file. Utiliser `state: present` + `recreate: always` pour tout service avec `env_file` (n8n, litellm, openclaw, nocodb, palais). Violation = mise a jour silencieuse sans rechargement des secrets.

### Violations Ansible MOP detectees en audit

Source : `docs/audits/2026-04-11-mop-generator-execution-audit.md`.

Les 4 nouveaux roles MOP ont ete deployes avec des violations systémiques :

| Violation | Roles concernes | Impact |
|---|---|---|
| V1 — Phase tags manquants | gotenberg, carbone, typebot, mop-templates | `--tags phase3` ne les deploie pas |
| V2 — Logging Docker absent | gotenberg, carbone, mailhog, typebot-builder, typebot-viewer | Logs illimites sur VPS 8 GB |
| V3 — URL hardcodee dans workflow n8n | mop-webhook-render-v1.json | Non-portable entre prod/preprod |

Ces violations ont ete corrigees en session (commit `c21e844`), mais elles documentent un pattern recurrent : les nouveaux roles sont crees rapidement sans checklist de conformite.

### Pattern de friction documente : 0 MCP en 11h de debug

Source : `docs/audits/2026-04-11-mop-generator-execution-audit.md`, metriques session `840f3397`.

806 appels Bash, 0 appel MCP, 23 auto-compacts pour une session de debug qui n'a pas abouti. La session suivante qui a utilise les MCP (n8n-docs) a reussi. Ce pattern — optimiser pour livrer vite sans utiliser les outils de validation disponibles — est exactement ce qui produit l'etalement du repo et les violations de convention.

Regle institutionnalisee suite a cet incident : `LOI-OPERATIONNELLE-MCP-FIRST.md` dans `docs/runbooks/`.
Source : `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` via memory_v1.

### REX sessions — pièges Caddy VPN ACL

Source : `docs/REX-SESSION-2026-02-18.md` via memory_v1.

Toute regle `not client_ip` doit inclure les 2 CIDRs : `{{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }}`. L'oubli du second CIDR produit un 403 sous VPN via HTTP/3 QUIC. Ce piège est maintenu dans `CLAUDE.md` et `docs/GUIDE-CADDY-VPN-ONLY.md` mais il n'est pas encode en test automatique.

### Migration Qdrant legacy

Source : `docs/audits/qdrant-legacy-migration-map-2026-04-11.md`.

28 collections Qdrant legacy, 23 a migrer vers `memory_v1` (1105 points, dimension 768). Ce travail de migration est initie mais non termine. Il ne bloque pas le repo mais constitue une dette operationnelle qui croit avec chaque session IA.

---

## Constats mis a jour

### Points forts (actualises)

- `inventory/`, `playbooks/site.yml`, `Makefile` : toujours stables, contrats preserves
- `docs/audits/` cree et actif : 3 audits dont 1 avec metriques detaillees (sessions IA, appels outils)
- `docs/runbooks/` cree avec des documents de haute valeur operationnelle (`LOI-OPERATIONNELLE-MCP-FIRST.md`, `AI-MEMORY-AGENT-PROTOCOL.md`)
- `versions.yml` : source de verite unique pour les images Docker pinned — respecte
- Patterns de provisioning robustes : postgresql_password unique, handlers env_file corriges
- `.planning/STATE.md` confirme milestone "Content Factory" a 100% (Phase 9, 15/15 plans)
- `docs/superpowers/` cree pour les plans/specs de skills Superpowers — bonne initiative de taxonomie

### Points de friction (actualises + enrichis)

1. **Racine repo encombrée** : 16 PNG de preuve non deplaces, toujours a la racine (recommande depuis le 09/04, non fait)
2. **`docs/` partiellement reorganise** : les sous-dossiers crees (`audits/`, `runbooks/`, `specs/`, `standards/`) ne contiennent que les nouveaux fichiers. Les 21 REX-SESSION-*.md, 6 GUIDE-*.md, 6 SPEC-*.md restent a la racine de `docs/`. Migration non initiee.
3. **`.gitignore` incomplet** : `.playwright-mcp/` et `.planning/COMPACT-CHECKPOINT.md` non ajoutes. Ces artefacts restent trackables.
4. **Pattern violations MOP** : les 4 nouveaux roles ont ete deployes sans phase tags ni logging Docker. Signe qu'il n'existe pas de checklist de creation de role automatiquement appliquee.
5. **`docs/plans/`** accumule des fichiers heterogenes : plans GSD (`2026-02-24-palais-phase*.md`), scripts Python (`apply_fixes.py`, `fix_log.py`), fichier shell (`jarvis-cli.sh`), settings JSON (`jarvis-executor-settings.json`), PRD speciaux. Ce n'est plus un dossier de plans.
6. **`scripts/n8n-workflows/`** : 12 workflows non commites ou partiellement commites. Pas de convention de nommage unifiee (af-*, mop-*, memory-*).
7. **`docs/superpowers/`** non commite : la structure est bonne mais le contenu reste hors versioning.

### Risques reels identifies par la memoire

1. **Risque conformite Ansible** : le pattern "role livre vite sans checklist" produit des violations systematiques (V1 phase tags, V2 logging). Sans garde-fou automatique, chaque nouveau role repete ces violations.

2. **Risque env_file / handlers** : le piege `state: restarted` vs `state: present + recreate: always` est documente mais non encode en test Molecule. Un nouveau deploiement d'un role avec env_file peut silencieusement rater le rechargement des secrets.

3. **Risque debt Qdrant** : 23 collections legacy non migrees. Chaque session IA alimente `memory_v1` mais le corpus legacy reste non accessible. La memoire est fragmentee.

4. **Risque LOI-OPERATIONNELLE** : mesuree a 0 appel MCP sur 806 Bash en une session. La loi est posee dans `CLAUDE.md` et `docs/runbooks/` mais elle n'est pas enforcee par les hooks de facon bloquante (seul `loi-op-enforcer.js` injecte des rappels, non-bloquant).

5. **Risque documentation proliferation** : 21 REX-SESSION a la racine de `docs/` + une nouvelle session cree 2-3 fichiers. Sans migration, la navigation deviendra inoperante pour les agents comme pour les humains dans 2-3 mois.

---

## Plan de reorganisation en 5 phases (revise)

### Principe directeur (inchange)

Ne jamais casser les interfaces d'entree avant d'avoir introduit des couches de compatibilite.

Ordre de priorite ajuste : les violations de conformite Ansible et les gardes-fous de creation de role passent avant la reorganisation des dossiers, parce qu'ils empechent l'accumulation de dette future.

---

### Phase 1 — Hygiene et lisibilite (priorite haute)

Objectif : nettoyer la racine, completer `.gitignore`, creer `docs/evidence/`.

Actions concretes :

1. Ajouter a `.gitignore` :
   ```
   .playwright-mcp/
   .planning/COMPACT-CHECKPOINT.md
   .planning/research/
   ```

2. Creer `docs/evidence/` et y deplacer :
   - `flash-suite-*.png` (7 fichiers)
   - `project-created-e2e.png`
   - `scaffold-review-e2e.png`
   - `typebot-*.png` (8 fichiers)
   Ces fichiers n'ont aucune raison d'etre a la racine du repo.

3. Committer `docs/audits/2026-04-09-vpai-repo-audit.md` et le present audit.

4. Committer les fichiers de valeur non encore commites :
   - `roles/flash-suite/templates/suite-registry.yaml.j2`
   - `scripts/index-comfyui-docs.py`
   - `scripts/n8n-workflows/` (tous les JSON apres validation `mcp__n8n-docs__validate_workflow`)
   - `docs/plans/PLAN-MONTAGE-BRIDGE-v0.7.0.md`
   - `docs/specs/SPEC-MONTAGE-BRIDGE-v0.7.0.md` (deja dans le bon sous-dossier)
   - `docs/standards/AI-PLATFORM-STARTER-KIT.md`
   - `docs/superpowers/` (plans/ + specs/)

Garde-fous :
- `ansible-playbook playbooks/site.yml --syntax-check` avant et apres
- `make lint` avant commit
- Les deplacement de fichiers dans `docs/` ne touchent pas `roles/` ni `playbooks/`

Risque : faible.

---

### Phase 2 — Taxonomie documentaire (priorite haute)

Objectif : terminer la migration `docs/` initiee le 09/04 — deplacer les 30+ fichiers encore a la racine.

Structure cible (completee) :

```
docs/
  audits/           (existe — 3 fichiers)
  runbooks/         (existe — 4 fichiers)
  specs/            (existe — 1 fichier)
  standards/        (existe — 1 fichier)
  plans/            (existe — a nettoyer)
  superpowers/      (existe — plans/ + specs/)
  evidence/         (a creer — voir Phase 1)
  rex/              (a creer)
  guides/           (a creer)
  archive/          (a creer)
```

Migrations a faire :

| Dossier source | Dossier cible | Fichiers concernes |
|---|---|---|
| `docs/REX-SESSION-*.md` (21) | `docs/rex/` | Tous les REX-SESSION |
| `docs/REX-FIRST-DEPLOY-*.md` | `docs/rex/` | 1 fichier |
| `docs/REX-MISSION-CONTROL-*.md` | `docs/rex/` | 1 fichier |
| `docs/REX-PALAIS-*.md` | `docs/rex/` | 1 fichier |
| `docs/REX-MOP-*.md` | `docs/rex/` | 2 fichiers |
| `docs/GUIDE-*.md` (6) | `docs/guides/` | Tous les GUIDE |
| `docs/SPEC-*.md` (2) racine | `docs/specs/` | SPEC-GITEA, SPEC-PLANE |
| `docs/PLAN-MIGRATION-*.md` | `docs/plans/` | 1 fichier |
| `docs/TROUBLESHOOTING.md` | Garder a `docs/` racine — exception justifiee (voir ci-dessous) |
| `docs/RUNBOOK.md` | Garder a `docs/` racine — exception justifiee (voir ci-dessous) |
| `docs/ARCHITECTURE.md` | `docs/` racine — garder visible |

**Exception critique — TROUBLESHOOTING.md et RUNBOOK.md :** `CLAUDE.md` (project, charge a chaque session) reference `docs/TROUBLESHOOTING.md` par chemin exact a 6 reprises (sections LiteLLM, Docker healthchecks, Caddy, REX sessions 11 et 12). Idem `docs/RUNBOOK.md` reference dans `CLAUDE.md` et Makefile. Un deplacement avec symlink git ne survit pas a un clone sur une machine vierge (symlink non suivi par git sur certains systemes). Recommandation : garder ces deux fichiers a `docs/` racine comme exceptions permanentes documentees, et mettre a jour `CLAUDE.md` uniquement si un deplacement est decide apres verification exhaustive des references. Commande de verification : `grep -rn 'docs/TROUBLESHOOTING\|docs/RUNBOOK' CLAUDE.md Makefile .github/ docs/GOLDEN-PROMPT.md`.

Cas particuliers dans `docs/plans/` a regler :
- `apply_fixes.py`, `fix_log.py`, `jarvis-cli.sh`, `jarvis-executor-settings.json` → `scripts/` (pas leur place dans plans)
- `jarvis-CLAUDE.md` → `docs/` racine ou supprimer si obsolete
- `PRD-KOODIA-V2.md`, `PRD-PALAIS-V2.md` → creer `docs/prd/` ou garder dans `docs/plans/`

Garde-fous :
- Verifier que `CLAUDE.md` (project) ne reference pas de chemins de fichiers hardcodes qui seraient casses
- `grep -r 'docs/REX\|docs/GUIDE\|docs/SPEC' CLAUDE.md Makefile` avant migration
- Committer par famille (tous les REX, puis tous les GUIDE, etc.), pas en masse

Risque : faible a modere — CLAUDE.md et docs ci-dessus referent certains fichiers par chemin.

---

### Phase 3 — Garde-fou creation de role (priorite haute — ajout vs v1)

Objectif : empecher la repetition des violations V1/V2/V3 sur chaque nouveau role, sans bloquer la velocite.

Cette phase est absente de l'audit v1 mais justifiee par les mesures du 11/04.

Actions concretes :

1. Creer `docs/standards/ANSIBLE-ROLE-CHECKLIST.md` avec la checklist minimale :
   - Phase tags : `[<role_name>, phase<N>]` dans chaque `tasks/main.yml`
   - Logging Docker : bloc `logging: driver: json-file options: max-size: "10m" max-file: "3"` sur chaque service
   - FQCN obligatoire (`ansible.builtin.xxx`)
   - `changed_when` / `failed_when` sur `command` et `shell`
   - `set -euo pipefail` + `executable: /bin/bash` sur les blocs `shell`
   - Images pinnees dans `versions.yml` (jamais `:latest`)
   - Healthcheck sur chaque container

2. Ajouter dans `CLAUDE.md` project une section "Checklist creation de role" pointant vers ce fichier.

3. Optionnel (priorite plus basse) : ajouter un check `make lint` qui valide la presence de phase tags dans les roles modifies (via un script Python ou ansible-lint custom rule).

Garde-fous :
- La checklist ne doit pas modifier les roles existants — elle s'applique aux creations futures
- Respecter FQCN dans le document lui-meme (exemples de code)

Risque : faible.

---

### Phase 4 — Taxonomie playbooks (priorite moderee)

Objectif : rendre les points d'execution lisibles. Reprend Phase 3 de l'audit v1.

Structure cible (inchangee) :
- `playbooks/stacks/` — site.yml et variantes (principal)
- `playbooks/apps/` — story-engine.yml, flash-suite.yml, obsidian.yml
- `playbooks/ops/` — rollback.yml, rotate-secrets.yml, safety-check.yml, seed-preprod.yml
- `playbooks/hosts/` — app-prod.yml, workstation.yml
- `playbooks/bootstrap/` — provision-hetzner.yml, penpot-up.yml, penpot-down.yml
- `playbooks/utils/` — ovh-dns-add.yml, vpn-toggle.yml, vpn-dns.yml, openclaw-oauth.yml, backup-restore.yml

Approche :
- Creer les sous-dossiers
- Deplacer progressivement par famille
- Conserver des wrappers `include_playbook` a l'ancien emplacement pour les 90 jours suivants (compatibilite CI/CD et `make deploy-*`)
- `Makefile` mis a jour en parallele pour pointer sur les nouveaux chemins

Garde-fous :
- `ansible-playbook playbooks/site.yml --syntax-check` a chaque deplacement
- `make deploy-prod --check` apres refactoring du Makefile
- Verifier tous les workflows GitHub Actions (`ci.yml`, `deploy-prod.yml`, etc.) qui referent des chemins hardcodes

Risque : modere — CI/CD reference des chemins de playbooks.

---

### Phase 5 — Taxonomie roles et contrat machine-readable (priorite basse a moyen terme)

Objectif : regrouper les 60 roles par famille, rendre la structure interpretable par les agents.

Structure cible (inchangee) :
- `roles/core/` : common, docker, hardening, headscale-node
- `roles/platform/` : caddy, postgresql, redis, qdrant, docker-stack
- `roles/apps/` : n8n, litellm, openclaw, nocodb, plane, kitsu, firefly, zimboo, mealie, grocy, koodia, palais, metube, carbone, gotenberg, typebot, videoref-engine, story-engine, flash-suite, app-scaffold, opencut, openpencil, obsidian, remotion, comfyui
- `roles/provision/` : n8n-provision, plane-provision, kitsu-provision, content-factory-provision, app-factory-provision, mop-templates
- `roles/monitoring/` : monitoring, diun, obsidian-collector, obsidian-collector-pi
- `roles/workstation/` : claude-code, codex-cli, gemini-cli, opencode, workstation-caddy, workstation-common, workstation-monitoring, llamaindex-memory, llamaindex-memory-worker, n8n-mcp
- `roles/ops/` : backup-config, smoke-tests, uptime-config, webhook-relay, vpn-dns

Approche :
- `ansible.cfg` definit actuellement `roles_path = roles` (chemin unique, plat). Avant tout deplacement, modifier cette ligne pour inclure les sous-dossiers cibles :
  ```ini
  roles_path = roles:roles/core:roles/platform:roles/apps:roles/provision:roles/monitoring:roles/workstation:roles/ops
  ```
  Cela permet de referencer les roles par leur nom court (`n8n`, `caddy`...) sans modifier `playbooks/site.yml`.
- Migrer par famille en commencant par les roles sans dependance (`workstation/`, puis `ops/`, puis `provision/`)
- Garder les roles `core/` et `platform/` pour la fin (plus risque)
- `roles/` racine doit rester dans `roles_path` pendant toute la migration pour les roles non encore deplaces

Contrat machine-readable (Phase 5b) :
- `PROJECT.md` : ce qu'est le repo, ses frontieres, ses interfaces d'entree
- `STRUCTURE.md` : carte des dossiers avec semantique de chaque famille
- `platform.yaml` : manifest YAML listant les services, leurs roles, leurs phases, leurs tags

Garde-fous :
- `ansible-playbook playbooks/site.yml --syntax-check` apres chaque deplacement de famille
- `make lint` obligatoire
- `make test-role ROLE=<role>` pour les roles avec molecule
- Phase 5 roles ne doit jamais preceder Phase 3 garde-fous

Risque : modere a eleve si fait en une seule fois — migrer par petits lots de 5-10 roles.

---

## Garde-fous transversaux

A executer avant chaque phase :

```bash
# Activation venv obligatoire
source /home/mobuone/seko/VPAI/.venv/bin/activate

# Verification syntaxe Ansible
ansible-playbook playbooks/site.yml --syntax-check

# Linting complet
make lint

# Verification chemins references dans les fichiers critiques
grep -r 'docs/REX\|docs/GUIDE\|docs/SPEC\|playbooks/' CLAUDE.md Makefile .github/

# Test role impacte (si applicable)
make test-role ROLE=<role_concerne>
```

A eviter absolument :
- Renommer un role logique reference dans `playbooks/site.yml` sans wrapper de compatibilite
- Modifier `inventory/hosts.yml` pendant une phase de reorganisation
- Deplacer `Makefile`, `ansible.cfg`, `inventory/` — ces fichiers ne bougent pas

---

## Recommandation strategique actualisee

L'audit v1 identifiait le probleme principal comme structurel : le repo a change de nature sans changer de contrat d'organisation.

L'audit v2 ajoute une dimension operationnelle mesurable : **la velocite de livraison IA produit des violations de convention regulieres** (V1 phase tags, V2 logging, V3 URL hardcodee — toutes corrigees a posteriori, pas preventivement).

Le levier le plus rentable n'est pas de tout reorganiser maintenant, mais de rendre impossible l'ajout d'un role non-conforme. La Phase 3 (garde-fou creation de role) a donc ete ajoutee et priorisee avant la taxonomie des playbooks, parce qu'elle casse le cycle de dette.

Ordre de priorite recommande :
1. **Phase 1** (hygiene racine + .gitignore) — 1h, risque minimal, benefice immediat
2. **Phase 3** (checklist creation de role) — 2h, protege toutes les sessions futures
3. **Phase 2** (taxonomie documentaire) — 2-3h, ameliore la navigation humaine et IA
4. **Phase 4** (taxonomie playbooks) — a planifier avec un slot dedié, CI/CD a verifier
5. **Phase 5** (taxonomie roles + contrat machine-readable) — apres Phase 4, par lots

La vraie question strategique en 2026-04-11 n'est plus "comment reorganiser" mais "comment empecher la prochaine session IA de recreer le meme desordre". Le contrat machine-readable (Phase 5b) et la checklist (Phase 3) sont les seules reponses durables a cette question.
