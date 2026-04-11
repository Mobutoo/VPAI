# Starter Kit - Projet IA / Infra auto-organise

Date: 2026-04-09
But: definir le cadre minimum qu'un projet similaire doit avoir des le jour 1 pour que des agents comme Codex ou Claude Code organisent automatiquement le depot au lieu de l'etaler.

## Objectif

Ce starter kit sert aux projets qui vont probablement devenir:
- multi-applications
- multi-serveurs
- infra + provisioning + automation
- operes par humains et agents IA

L'idee centrale:

L'IA s'organise bien si le repo expose ses regles sous forme executable:
- manifests
- generateurs
- conventions
- validations automatiques

Sans cela, l'IA privilegie la livraison locale la plus rapide.

## Les 7 piliers

1. Un contrat de repo explicite
2. Une arborescence stricte
3. Un manifeste machine-readable
4. Des generateurs obligatoires
5. Une CI de structure
6. Un workflow Git/PR impose
7. Des hooks IA qui rappellent les obligations de classement

## Structure cible recommandee

```text
.
├── PROJECT.md
├── STRUCTURE.md
├── WORKFLOW.md
├── platform.yaml
├── Makefile
├── ansible.cfg
├── inventory/
│   ├── hosts.yml
│   ├── group_vars/
│   └── host_vars/
├── playbooks/
│   ├── stacks/
│   ├── apps/
│   ├── hosts/
│   ├── ops/
│   └── bootstrap/
├── roles/
│   ├── core/
│   ├── platform/
│   ├── apps/
│   ├── provision/
│   └── workstation/
├── scripts/
│   ├── scaffolds/
│   ├── ci/
│   ├── ops/
│   └── tests/
├── docs/
│   ├── audits/
│   ├── architecture/
│   ├── runbooks/
│   ├── specs/
│   ├── plans/
│   ├── rex/
│   ├── standards/
│   ├── evidence/
│   └── archive/
├── .github/
│   ├── pull_request_template.md
│   └── workflows/
└── archive/
```

## Ce que chaque fichier racine doit contenir

## `PROJECT.md`

Contient:
- mission du repo
- ce qui appartient au repo
- ce qui n'appartient pas au repo
- definition des environnements
- definition des livrables

Question a laquelle il doit repondre:
- "Ce depot est-il un produit, une plateforme, une usine de deploiement, ou un peu tout cela ?"

## `STRUCTURE.md`

Contient:
- ou ranger chaque type de fichier
- conventions de nommage
- exemples obligatoires
- regles de placement pour docs, preuves, scripts, roles, playbooks

Question a laquelle il doit repondre:
- "Si un agent cree X, dans quel dossier doit-il aller ?"

## `WORKFLOW.md`

Contient:
- processus standard humain + IA
- definition of done
- checklists avant PR / avant merge
- regles de branchement
- quand creer une spec, un ADR, un runbook, un smoke test

Question a laquelle il doit repondre:
- "Quelle sequence d'actions un agent doit-il suivre avant de coder ?"

## `platform.yaml`

Contient:
- environnements
- groupes d'inventaire
- apps
- roles
- dependances
- playbooks
- ownership
- smoke tests
- docs obligatoires associees

Question a laquelle il doit repondre:
- "Quelle est la verite structurelle du projet, lisible par machine ?"

## Manifeste `platform.yaml` minimal

```yaml
project:
  name: vpai
  type: ai-platform-factory
  repo_scope:
    includes:
      - ansible_roles
      - playbooks
      - deployment_scripts
      - runbooks
      - specs
      - smoke_tests
    excludes:
      - large_product_source_repos
      - local_test_artifacts
      - screenshots_at_repo_root

environments:
  - name: prod
  - name: preprod
  - name: vpn
  - name: workstation

host_groups:
  - name: prod
    purpose: main production stack
  - name: workstation
    purpose: local creative tooling

role_families:
  - name: core
  - name: platform
  - name: apps
  - name: provision
  - name: workstation

apps:
  - id: story-engine
    owner: platform
    host_group: story_engine
    role: story-engine
    playbook: playbooks/apps/story-engine.yml
    smoke_test: scripts/tests/story-engine-smoke.sh
    docs:
      runbook: docs/runbooks/story-engine.md
      spec: docs/specs/story-engine.md

rules:
  evidence_dir: docs/evidence
  plans_dir: docs/plans
  specs_dir: docs/specs
  allow_root_files:
    - PROJECT.md
    - STRUCTURE.md
    - WORKFLOW.md
    - platform.yaml
    - README.md
    - Makefile
    - ansible.cfg
```

## Generateurs obligatoires

Le principe:
- on ne cree presque rien a la main
- on scaffold
- ensuite on remplit

## Commandes a fournir

```bash
make new-role TYPE=apps NAME=story-engine
make new-playbook TYPE=apps NAME=story-engine
make new-host-group NAME=story_engine
make new-app APP=story-engine HOST_GROUP=story_engine
make new-spec NAME=story-engine-v1
make new-runbook NAME=story-engine
make new-adr NAME=dedicated-story-engine-server
```

## Ce que `make new-app` doit faire

Creer automatiquement:
- role Ansible dans la bonne famille
- defaults/tasks/templates/handlers/README
- playbook applicatif
- entree `platform.yaml`
- squelette `group_vars` si necessaire
- spec et runbook minimaux
- smoke test
- eventuellement workflow CI/CD dedie

## CI de structure

Ajouter un job `structure-lint` qui echoue si:
- un binaire ou screenshot apparait a la racine
- un nouveau dossier top-level non autorise apparait
- un role est cree hors des familles autorisees
- un nouveau playbook n'est pas reference dans `platform.yaml`
- une app n'a pas `spec + runbook + smoke test`
- `.playwright-mcp/`, `tmp/`, captures locales ou logs ne sont pas ignores
- du code source lourd de produit est embarque alors qu'il devrait vivre dans un repo dedie

## Regles de Git et PR

Meme en solo, utiliser un workflow de plateforme:

- une branche par capability
- une PR par capability
- pas de push direct sur `main` pour les gros chantiers
- les PRs doivent expliciter:
  - type de changement
  - hotes impactes
  - roles impactes
  - migration requise ou non
  - smoke tests
  - rollback

## Template de PR recommande

```md
## Scope
- Type: infra | app | provision | docs | ops
- Capability:
- Host groups impacted:
- Roles impacted:

## Why

## What changed

## Required docs updated
- [ ] platform.yaml
- [ ] spec
- [ ] runbook
- [ ] architecture

## Validation
- [ ] syntax-check
- [ ] lint
- [ ] targeted tests
- [ ] smoke test

## Rollback
```

## Hooks IA recommandes

Apres toute modification importante, l'agent doit verifier:

1. Ai-je ajoute une nouvelle app, un nouveau role, un nouvel host group ou un nouveau playbook ?
2. Si oui, ai-je mis a jour `platform.yaml` ?
3. Ai-je cree ou mis a jour la spec, le runbook et le smoke test ?
4. Ai-je depose un artefact dans un mauvais dossier ?
5. Ai-je produit une preuve E2E qui doit aller dans `docs/evidence/` ?
6. Suis-je en train d'etendre ce repo au-dela de son scope defini dans `PROJECT.md` ?

## Workflow IA standard

Sequence obligatoire:

1. Lire `PROJECT.md`, `STRUCTURE.md`, `WORKFLOW.md`, `platform.yaml`
2. Determiner s'il s'agit d'une app, d'un role, d'un host, d'une operation ou d'une doc
3. Creer les squelettes via `make new-*`
4. Mettre a jour le manifeste
5. Implementer
6. Ajouter ou mettre a jour tests + smoke test
7. Ajouter ou mettre a jour docs
8. Verifier la structure
9. Ouvrir une PR avec checklist complete

## Regles de frontiere du repo

Definir des le depart:

- ce repo contient l'infra, le packaging, le deploiement, les scripts d'exploitation et la documentation operationnelle
- les gros produits autonomes vivent dans leurs propres repos
- on n'embarque pas des sous-projets complets dans des dossiers ad hoc
- les preuves et captures ne vivent pas a la racine
- les archives sont deplacees dans `archive/` ou `docs/archive/`

## Ce qu'il faut automatiser des le jour 1

Minimum vital:
- scaffold des roles/apps/playbooks/docs
- mise a jour du manifeste
- linter de structure
- template de PR
- checklist IA
- smoke test minimal par app

Ideal:
- bot qui detecte tout nouveau fichier racine anormal
- bot qui ouvre une PR de rangement si un dossier grossit sans taxonomie
- generation automatique d'un index d'architecture a partir de `platform.yaml`
- verification automatique que chaque host group a ses variables et ses playbooks

## Checklist de lancement d'un nouveau projet

- [ ] Definir le scope dans `PROJECT.md`
- [ ] Definir la taxonomie dans `STRUCTURE.md`
- [ ] Definir le process dans `WORKFLOW.md`
- [ ] Creer `platform.yaml`
- [ ] Installer le scaffold `make new-*`
- [ ] Installer le job `structure-lint`
- [ ] Installer le template de PR
- [ ] Definir les regles d'archives et de preuves
- [ ] Definir les limites du repo et les criteres d'extraction vers un sous-repo
- [ ] Ecrire les premiers runbooks

## Conclusion

Le bon levier n'est pas de demander a l'IA d'etre plus rangee "dans l'absolu".

Le bon levier est de donner a l'IA:
- une carte du territoire
- des generateurs
- des interdits
- des checks automatiques

Si ces quatre choses existent, l'organisation emerge presque toute seule.
