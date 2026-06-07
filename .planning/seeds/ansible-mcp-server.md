# Spec — ansible-mcp-server

**Statut** : Seed — à implémenter (repo dédié)  
**Priorité** : Moyenne  
**Repo cible** : `git@github-seko:Mobutoo/ansible-mcp-server.git`

---

## Problème résolu

Aucun MCP officiel Ansible n'existe (avril 2026). `ansible-dev-tools` est un LSP VS Code incompatible MCP.  
Sans MCP, Claude Code doit deviner la syntaxe des modules, rate les FQCN, et ne peut pas valider les fichiers en session.  
**Ce MCP fait autorité** : les projets s'y conforment, pas l'inverse.

---

## Périmètre

MCP serveur Python stdio exposant :
1. La documentation officielle des modules installés (`ansible-doc`)
2. La validation lint et YAML en temps réel
3. La recherche sémantique dans la documentation indexée (Qdrant)

**Hors périmètre** :
- Règles projet VPAI → restent dans Qdrant `memory_v1`
- REX et conventions projet → restent dans Qdrant `memory_v1`
- Exécution de playbooks (trop risqué depuis un MCP)
- Modules cloud spécialisés (amazon.aws, azure.azcollection, etc.)

---

## Architecture

```
Claude Code
    └── stdio
         └── ansible-mcp-server (Python)
              ├── get_module()       → ansible-doc --json (live)
              ├── list_modules()     → ansible-doc -l (live)
              ├── lint_path()        → ansible-lint (live)
              ├── validate_yaml()    → yamllint (live)
              ├── syntax_check()     → ansible-playbook --syntax-check (live)
              └── search_docs()      → Qdrant collection ansible_docs
```

### Dépendances runtime

| Dépendance | Version min | Rôle |
|-----------|-------------|------|
| Python | 3.12 | Runtime |
| `mcp` (Anthropic SDK) | latest | Transport stdio |
| `ansible-core` | 2.20+ | ansible-doc, ansible-playbook |
| `ansible-lint` | 26.x | Lint |
| `yamllint` | 1.38+ | YAML validation |
| `qdrant-client` | latest | search_docs |
| `sentence-transformers` ou API embed | — | Indexation |

### Venv

Venv dédié `/opt/workstation/ansible-mcp/.venv` — isolé du venv VPAI pour éviter les conflits de collections.  
Les collections Ansible sont installées dans ce venv via `ansible-galaxy collection install`.

---

## Outils MCP — Spécification détaillée

### `get_module`

```
Input  : fqcn (str) — ex: "community.docker.docker_container"
Output : {
  module: str,
  short_description: str,
  description: str[],
  parameters: [{name, type, required, default, description, choices}],
  examples: str,
  return_values: {...},
  version_added: str
}
Erreur : {"error": "module not found", "suggestions": [...]}
```

Backend : `ansible-doc -t module <fqcn> --json`  
Cache : 1h en mémoire (les docs ne changent pas en cours de session)

---

### `list_modules`

```
Input  : collection (str, optional) — ex: "community.docker" — vide = tous
         query (str, optional) — filtre sur short_description
         limit (int, default 50)
Output : [{fqcn, short_description}]
```

Backend : `ansible-doc -l --json` + filtre Python

---

### `lint_path`

```
Input  : path (str) — fichier .yml ou répertoire de rôle
         profile (str, optional) — "min"|"basic"|"moderate"|"safety"|"shared"|"production"
                                    default: "basic"
Output : {
  passed: bool,
  violations: [{
    rule_id: str,        -- ex: "fqcn[action]"
    severity: str,       -- "error"|"warning"|"info"
    message: str,
    file: str,
    line: int,
    column: int,
    tag: str[]
  }],
  stats: {errors: int, warnings: int}
}
```

Backend : `ansible-lint --format json <path>`  
Note : profile "basic" couvre FQCN, changed_when, no-free-form, risky-shell-pipe

---

### `validate_yaml`

```
Input  : path (str) — fichier .yml ou .yaml ou .j2
Output : {
  valid: bool,
  errors: [{line: int, col: int, level: str, message: str}]
}
```

Backend : `yamllint -f parsable <path>`  
Utilité : couvre les templates Jinja2 `.j2` qu'ansible-lint ne parse pas

---

### `syntax_check`

```
Input  : playbook (str) — chemin vers le playbook
         inventory (str, optional) — chemin inventaire, default: ",localhost,"
Output : {
  valid: bool,
  errors: [{message: str, line: int, file: str}]
}
```

Backend : `ansible-playbook --syntax-check -i <inventory> <playbook>`  
Détecte : variables undefined, modules inexistants, Jinja2 invalide

---

### `search_docs`

```
Input  : query (str) — ex: "docker container env vars restart policy"
         collection (str, optional) — filtrer par collection
         limit (int, default 5)
Output : [{
  fqcn: str,
  short_description: str,
  score: float,
  params_preview: str    -- top 5 paramètres les plus pertinents
}]
```

Backend : Qdrant collection `ansible_docs`, recherche vectorielle  
Fallback : si Qdrant indisponible → `list_modules(query=query)` (filtre textuel)

---

## Qdrant — Collection `ansible_docs`

### Schéma document

```json
{
  "id": "community.docker.docker_container",
  "fqcn": "community.docker.docker_container",
  "collection": "community.docker",
  "collection_version": "5.0.6",
  "short_description": "Manage docker containers",
  "description_text": "...",
  "params_summary": "name(str,req) image(str,req) state(str) ports(list) env(dict) etc_hosts(dict) ...",
  "examples": "...",
  "indexed_at": "2026-04-13T00:00:00Z"
}
```

Texte embarqué (pour l'embedding) :  
```
{fqcn} — {short_description}\n{description_text}\nParams: {params_summary}\n{examples[:500]}
```

### Collections indexées

| Collection | Version | Modules | Priorité |
|-----------|---------|---------|----------|
| `ansible.builtin` | 2.20.3 | ~80 | P0 — tous |
| `community.docker` | 5.0.6 | ~30 | P0 — tous |
| `community.general` | 12.4.0 | ~60 subset | P1 — filtré par usage réel VPAI |
| `ansible.posix` | 2.1.0 | ~20 | P1 — tous |

`community.general` subset = modules présents dans au moins un rôle VPAI (grep sur `roles/`).

### Script d'indexation

`scripts/index_docs.py` :
- Lit `COLLECTIONS` depuis `config.yml`
- Pour chaque collection : `ansible-doc -l --json` → filtre → `ansible-doc <fqcn> --json`
- Chunking si doc > 2000 tokens
- Upsert dans Qdrant (idempotent via fqcn comme ID)
- Log : `indexed N modules in Xs`

**Déclencheur** : manuel après `ansible-galaxy collection install --upgrade`

---

## Structure du repo

```
ansible-mcp-server/
├── README.md
├── pyproject.toml
├── config.yml                  # collections à indexer, Qdrant URL, venv path
├── server.py                   # point d'entrée MCP stdio
├── tools/
│   ├── get_module.py
│   ├── list_modules.py
│   ├── lint_path.py
│   ├── validate_yaml.py
│   ├── syntax_check.py
│   └── search_docs.py
├── scripts/
│   ├── index_docs.py           # indexeur Qdrant
│   ├── install.sh              # setup venv + collections + pip
│   └── refresh.sh              # ansible-galaxy upgrade + re-index
├── tests/
│   ├── test_tools.py           # tests unitaires outils
│   └── fixtures/               # exemples YAML valides/invalides
└── .github/
    └── workflows/
        └── test.yml            # pytest sur push
```

---

## Installation (cible Waza Pi)

```bash
git clone git@github-seko:Mobutoo/ansible-mcp-server.git /opt/workstation/ansible-mcp
cd /opt/workstation/ansible-mcp
bash scripts/install.sh         # crée venv, installe pip + collections

# Indexation initiale
bash scripts/refresh.sh         # galaxy upgrade + index Qdrant

# Ajout dans ~/.claude.json
# "ansible": {
#   "type": "stdio",
#   "command": "/opt/workstation/ansible-mcp/.venv/bin/python",
#   "args": ["/opt/workstation/ansible-mcp/server.py"]
# }
```

---

## Versioning et maintenance

### Stratégie de version

`MAJOR.MINOR.PATCH` — aligné sur `ansible-core` major :
- `1.x.x` → ansible-core 2.20.x
- `2.x.x` → ansible-core 2.21.x (breaking changes collections)

### Quand mettre à jour

| Événement | Action |
|-----------|--------|
| `ansible-galaxy collection install --upgrade` | `bash scripts/refresh.sh` |
| Nouvelle version ansible-core | Bump MAJOR, re-tester lint profiles |
| Nouvelle règle ansible-lint | Documenter dans CHANGELOG |
| Nouveau module utilisé dans VPAI | Ajouter dans `config.yml` community.general subset |

### CHANGELOG

Tenir un `CHANGELOG.md` avec :
- collections versions indexées
- règles lint activées/désactivées
- breaking changes outils MCP

---

## Décisions de design

| Décision | Choix | Raison |
|----------|-------|--------|
| Transport | stdio | Cohérent avec autres MCPs locaux |
| Runtime | Python | Même écosystème qu'Ansible |
| Venv | Dédié `/opt/workstation/ansible-mcp/` | Isolation des collections VPAI |
| Cache | Mémoire session uniquement | Simple, docs stables en session |
| Fallback search_docs | list_modules textuel | Résilience si Qdrant down |
| Pas d'exécution playbook | Hors périmètre | Trop risqué depuis un MCP |
| `syntax_check` inventory | `",localhost,"` par défaut | Évite besoin d'accès SSH |
