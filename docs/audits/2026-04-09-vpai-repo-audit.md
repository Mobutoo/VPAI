# Audit du repo VPAI

Date: 2026-04-09
Portee: structure du depot, historique Git local/GitHub, derive du perimetre initial, hygiene des fichiers non commités, recommandations de reorganisation sans casse.

## Resume executif

VPAI a commence comme un projet Ansible de deploiement d'une stack AI self-hosted sur un VPS, puis a evolue tres rapidement vers une plateforme multi-applications, multi-serveurs et multi-workflows pilotee en grande partie par IA.

Le repo fonctionne encore parce que ses points d'entree restent relativement stables:
- `playbooks/site.yml`
- `inventory/hosts.yml`
- `Makefile`

Le principal probleme n'est pas technique mais structurel:
- le repo n'exprime pas clairement ses frontieres
- la taxonomie n'a pas suivi la croissance
- les nouveaux sous-projets et artefacts ont ete absorbes dans le meme espace
- l'IA a optimise pour livrer vite, pas pour urbaniser le depot

Conclusion: le depot n'est pas "mal fait", il est devenu plus ambitieux que son contrat initial. Il faut maintenant le traiter comme un monorepo de platform engineering, pas comme un simple projet Ansible de stack unique.

## Methode

Audit base sur:
- etat Git local (`git status`, `git diff --stat`, `git log`, `git shortlog`)
- lecture des points d'entree du repo
- inspection de l'inventaire et de la structure des dossiers
- verification du repo GitHub `Mobutoo/VPAI`
- revue des fichiers non commités visibles au moment de l'audit

## Etat actuel du repo

## Nature du projet

Le projet est aujourd'hui un monorepo infra/ops qui couvre:
- plusieurs cibles d'inventaire: `prod`, `preprod`, `vpn`, `workstation`, `app_prod`, `story_engine`
- de multiples roles Ansible applicatifs et plateforme
- plusieurs familles de playbooks
- des workflows n8n et des scripts d'exploitation
- de la documentation produit, technique, runbook, REX, design, spec
- des artefacts de validation E2E
- au moins un sous-projet lourd embarque dans `FS/`

## Contrats critiques a preserver

Les contrats suivants sont les plus importants a conserver pendant toute reorganisation:
- `playbooks/site.yml`
- `inventory/hosts.yml`
- `Makefile`
- les commandes `make deploy-*`, `make test*`, `make lint`

Toute reorganisation doit partir du principe que ces interfaces restent stables ou qu'elles sont remplacees par des wrappers compatibilite.

## Constat structurel

### Points forts

- `inventory/` est encore relativement lisible
- l'orchestrateur principal `playbooks/site.yml` reste comprehensible
- le projet a garde une logique Ansible exploitable
- la documentation historique est riche
- le repo contient beaucoup de savoir operationnel utile

### Points de friction

- le `README.md` ne reflete plus le perimetre reel du depot
- la racine du repo contient des fichiers qui devraient etre classes ailleurs
- les roles ont prolifere sans taxonomie assez visible
- `docs/` melange runbooks, specs, plans, preuves, retrospectives et conceptions
- `.planning/` contient des artefacts utiles localement mais pas toujours souhaitables comme patrimoine versionne
- des artefacts Playwright locaux (`.playwright-mcp/`) ne sont pas ignores
- le sous-arbre `FS/flash-studio-complete` brouille la frontiere entre plateforme infra et produit integre

## Historique et evolution du projet

## Ce que montre l'historique Git

L'historique indique une progression tres rapide:

- 2026-02-11: base du projet comme stack Ansible "complete"
- 2026-02-15 a 2026-02-18: durcissement, CI/CD, deploiement, VPN-only, OpenClaw, workflows, observabilite
- 2026-02-18 a 2026-02-20: passage explicite a un modele multi-serveurs avec workstation et nouveaux roles
- 2026-03: explosion du perimetre avec `palais`, `videoref`, `comfyui`, `remotion`, `app-factory`, `story-engine`

Volumes observes:
- 353 commits sur 2026-02
- 396 commits sur 2026-03
- 25 commits sur 2026-04 au moment de l'audit

Contributeurs:
- `Ewutelo`: 588 commits
- `Mobuone`: 164 commits
- `Mobutoo`: 22 commits

Interpretation:
- tres forte velocite
- usage massif d'agents IA
- croissance incrémentale concentree sur la livraison de capacites
- faible urbanisation structurelle en parallele

## Ce que montre GitHub

Depot GitHub detecte:
- `Mobutoo/VPAI`

Observation importante:
- `main` local et `origin/main` sont alignes au meme HEAD au moment de l'audit
- peu de PRs formelles visibles
- la PR #1 date du 2026-02-15 et formalise encore une evolution relativement "cadree"

Interpretation:
- apres la phase initiale, la croissance du projet s'est faite surtout par commits et merges rapides, davantage que par un workflow GitHub structurant
- cela a favorise la vitesse, mais pas la cristallisation d'une architecture de depot explicite

## Fichiers non commités: tri recommande

## A garder et probablement committer

Modifications suivies deja presentes:
- fichiers modifies sous `roles/...`
- ces changements ressemblent a de vraies evolutions produit/deploiement

Nouveaux fichiers a forte valeur:
- `roles/flash-suite/templates/suite-registry.yaml.j2`
- `scripts/index-comfyui-docs.py`
- `scripts/n8n-workflows/af-ci-hook.json`
- `scripts/n8n-workflows/af-deploy.json`
- `scripts/n8n-workflows/af-intake.json`
- certains documents `docs/plans/`, `docs/specs/`, `docs/superpowers/` si le repo reste la source de verite du delivery

## A garder mais deplacer

Captures et preuves:
- `flash-suite-dashboard-full.png`
- `flash-suite-dashboard-loaded.png`
- `flash-suite-dashboard.png`
- `flash-suite-finance-dashboard.png`
- `flash-suite-finance-fixed.png`
- `flash-suite-finance.png`
- `flash-suite-flow.png`
- `project-created-e2e.png`
- `scaffold-review-e2e.png`

Recommendation:
- deplacer vers `docs/evidence/` ou `docs/assets/e2e/`

## A ignorer ou a sortir du versioning

- `.playwright-mcp/`
- `.planning/COMPACT-CHECKPOINT.md`

Cas intermediaire:
- les fichiers `.planning/phases/.../.continue-here.md` et certains fichiers de verification

Recommendation:
- garder `.planning/` seulement si tu assumes explicitement que ce repo versionne aussi la memoire de pilotage IA
- sinon, archiver ou ignorer les checkpoints transitoires et ne conserver que les artefacts de decision utiles

## Diagnostic de fond

Le projet de base etait pense comme:
- un depot de stack Ansible
- une structure de deploiement relativement verticale
- un README de produit deployable

Le projet reel est devenu:
- un depot de platform engineering
- une usine de deploiement et de provisioning multi-apps
- un espace de collaboration humain + IA
- un lieu de documentation vivante, de REX, de specs et de scripts operatoires

Le mismatch principal est donc celui-ci:

Le repo a change de nature, mais pas de contrat d'organisation.

## Risques actuels

- difficulte croissante pour un agent ou un humain de savoir ou ranger un nouveau composant
- augmentation du cout cognitif de navigation
- confusion entre runtime, docs, preuves, prototypage et archives
- fragilite croissante lors d'une reorganisation tardive
- absence de barrières automatiques contre l'etalement du repo

## Plan de reorganisation sans casse

## Principe directeur

Ne jamais casser les interfaces d'entree avant d'avoir introduit des couches de compatibilite.

## Phase 1 - Hygiene et lisibilite

Objectif:
- nettoyer la racine
- mieux ranger docs et preuves
- ignorer les artefacts temporaires

Actions:
- ajouter `.playwright-mcp/` a `.gitignore`
- deplacer les PNG de preuve dans `docs/evidence/`
- clarifier `README.md` pour refleter le caractere multi-hotes/multi-apps
- documenter explicitement le role de `.planning/`

Risque:
- faible

## Phase 2 - Taxonomie documentaire

Objectif:
- distinguer les familles de documentation

Structure cible:
- `docs/audits/`
- `docs/architecture/`
- `docs/runbooks/`
- `docs/specs/`
- `docs/plans/`
- `docs/rex/`
- `docs/standards/`
- `docs/evidence/`
- `docs/archive/`

Risque:
- faible a modere

## Phase 3 - Taxonomie des playbooks

Objectif:
- rendre les points d'execution lisibles sans casser les commandes existantes

Structure cible:
- `playbooks/stacks/`
- `playbooks/apps/`
- `playbooks/hosts/`
- `playbooks/ops/`
- `playbooks/bootstrap/`

Approche:
- deplacer progressivement
- conserver des wrappers a l'emplacement ancien

Risque:
- modere

## Phase 4 - Taxonomie des roles

Objectif:
- classer les roles par responsabilite

Structure cible:
- `roles/core/`
- `roles/platform/`
- `roles/apps/`
- `roles/provision/`
- `roles/workstation/`

Approche:
- ne pas renommer les roles logiques dans les playbooks
- utiliser `roles_path` dans `ansible.cfg` si besoin
- migrer par famille

Risque:
- modere a eleve si fait d'un coup

## Phase 5 - Contrat machine-readable

Objectif:
- rendre la structure interpretable automatiquement par l'IA et les outils

Fichiers a introduire:
- `PROJECT.md`
- `STRUCTURE.md`
- `WORKFLOW.md`
- `platform.yaml`

Risque:
- faible
- tres fort gain organisationnel

## Garde-fous recommandes

Avant chaque phase:
- `ansible-playbook playbooks/site.yml --syntax-check`
- `make lint`
- `make test-role ROLE=<role impacte>`
- verification d'un `make deploy-role ROLE=<x> ENV=<y>`

## Recommandation strategique

La vraie priorite n'est pas de bouger tout de suite les roles.

La vraie priorite est de rendre explicite:
- ce qu'est le repo
- ce qui y a droit de cite
- ou chaque type d'objet doit aller
- ce qu'un agent IA doit faire quand il ajoute une capacite

Autrement dit:
- d'abord le contrat
- ensuite l'urbanisme
- enfin la migration structurelle

## Conclusion

VPAI a prouve qu'il pouvait absorber beaucoup d'evolution fonctionnelle avec une forte aide IA. Le prochain gain de levier n'est plus dans la vitesse de livraison brute, mais dans l'automatisation de l'organisation elle-meme.

Si le repo avait eu des manifests, des generateurs, des conventions obligatoires et des checks de structure des le debut, l'IA aurait nettement mieux range les choses automatiquement.

Le chantier recommande n'est donc pas une simple "reorganisation de dossiers". C'est la mise en place d'un cadre de platform engineering explicite, compatible avec un mode de travail humain + agents.
