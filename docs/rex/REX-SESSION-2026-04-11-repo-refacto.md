# REX — Refactorisation repo VPAI + Corrections ansible-lint

**Date :** 2026-04-11  
**Durée :** ~1 session complète  
**Déclencheur :** Audit `docs/audits/2026-04-11-vpai-repo-audit-v2.md` — état du repo avant refacto  
**Résultat :** 5 phases de refacto exécutées, 27 violations lint corrigées → `0 failure(s)`

---

## Contexte

Le repo avait accumulé de la dette structurelle depuis le premier déploiement :
- Playbooks tous à plat dans `playbooks/` (18 fichiers sans catégorie)
- Docs sans taxonomie (REX, guides, standards mélangés)
- 60 roles sans classification ni tag de catégorie
- Aucun contrat machine-readable de la structure
- 27 violations `ansible-lint --profile production` jamais corrigées

---

## Phases exécutées

| Phase | Livrable | Commit |
|-------|---------|--------|
| 1 — Audit enrichi Qdrant | `docs/audits/2026-04-11-vpai-repo-audit-v2.md` | — |
| 2 — Checklist création rôle | `docs/standards/ANSIBLE-ROLE-CHECKLIST.md` (12 items) | `f159f0f` |
| 3 — Taxonomie docs | `docs/rex/`, `docs/guides/`, `docs/standards/` | `578c6f1` |
| 4 — Taxonomie playbooks | 18 fichiers → `stacks/`, `hosts/`, `apps/`, `ops/`, `bootstrap/`, `utils/` | `e013530` `aaeec02` `c0a3134` |
| 5 — Taxonomie roles + tags | 60 roles, 3 tags obligatoires, `platform.yaml`, `docs/STRUCTURE.md`, `scripts/generate-structure.py` | `45b5746` `3948189` |
| Lint | 27 violations → 0 | `b2687c5` |

---

## Erreurs documentées et corrections

### E1 — `name[casing]` : noms de tâches en minuscule

**Fichier :** `roles/webhook-relay/tasks/main.yml` (11 occurrences)

**Cause :** Convention de nommage `"<role> | <action>"` appliquée avec le nom du rôle en minuscule.  
Le prefixe `"webhook-relay | ..."` commence par `w` minuscule — ansible-lint exige une majuscule.

```yaml
# ❌ Avant
- name: "webhook-relay | Add Caddy GPG key"

# ✅ Après
- name: "Webhook-relay | Add Caddy GPG key"
```

**Recommandation :** La convention de nommage `"<Role> | <Action>"` doit toujours capitaliser le premier caractère.
Ajouter à la checklist : **le premier caractère du `name:` est toujours une majuscule.**

---

### E2 — `syntax-check[unknown-module]` : collection `ansible.posix` absente

**Fichier :** `roles/obsidian/tasks/main.yml:97`

**Cause :** Utilisation de `ansible.posix.cron` alors que la collection `ansible.posix` n'est pas installée dans le venv du projet. `ansible.builtin.cron` est disponible nativement.

```yaml
# ❌ Avant
- name: "Schedule Obsidian sync"
  ansible.posix.cron:
    name: "obsidian-sync"

# ✅ Après
- name: "Schedule Obsidian sync"
  ansible.builtin.cron:
    name: "obsidian-sync"
```

**Recommandation :** Préférer `ansible.builtin.*` partout où c'est possible. N'utiliser `ansible.posix.*` que si le module n'existe pas dans `builtin` — et vérifier que la collection est dans `requirements.yml`.

---

### E3 — `yaml[line-length]` : liste de rôles sur une seule ligne

**Fichier :** `platform.yaml:22`

**Cause :** La liste des 23 rôles `apps` écrite en inline YAML `[n8n, litellm, ...]` dépassait la limite de 160 caractères.

```yaml
# ❌ Avant
roles: [n8n, litellm, openclaw, nocodb, plane, kitsu, firefly, ...]

# ✅ Après
roles:
  - n8n
  - litellm
  - openclaw
  ...
```

**Recommandation :** Pour toute liste de plus de 3-4 éléments dans un fichier YAML, utiliser le format bloc (un élément par ligne). La limite est 160 caractères (`.yamllint.yml`).

---

### E4 — `yaml[key-duplicates]` : clé dupliquée dans `main.yml`

**Fichier :** `inventory/group_vars/all/main.yml:288`

**Cause :** La variable `kitsu_subdomain` était définie deux fois dans le fichier — probablement suite à un copier-coller lors d'une session précédente. La deuxième occurrence écrasait silencieusement la première.

**Recommandation :** Avant d'ajouter une variable dans `main.yml`, chercher si elle existe déjà :
```bash
grep "kitsu_subdomain" inventory/group_vars/all/main.yml
```
Ajouter cette vérification dans la checklist création rôle.

---

### E5 — `no-relative-paths` : chemin relatif dans `src:` d'un template

**Fichier :** `playbooks/ops/rollback.yml:45`

**Cause :** Lors de la migration des playbooks vers des sous-dossiers (`playbooks/ops/`), un chemin relatif `"../templates/..."` dans un `ansible.builtin.template` n'a pas été ajusté. Ansible résout les templates relativement au rôle, pas au playbook.

```yaml
# ❌ Avant (chemin relatif)
ansible.builtin.template:
  src: "../templates/docker-compose.yml.j2"

# ✅ Après (chemin depuis le rôle)
ansible.builtin.template:
  src: "templates/docker-compose.yml.j2"
```

**Recommandation :** Après toute migration de playbooks, relancer `ansible-lint` immédiatement pour détecter les chemins cassés. Ne pas attendre.

---

### E6 — `command-instead-of-shell` / `command-instead-of-module`

**Fichiers :** `playbooks/utils/openclaw-oauth.yml`, `roles/comfyui/tasks/main.yml`, `roles/story-engine/tasks/main.yml`

**Causes et corrections :**

| Cas | Fichier | Fix |
|-----|---------|-----|
| `docker restart` via `shell` | `openclaw-oauth.yml` | Remplacé par `ansible.builtin.command` (pas de pipe) |
| `git init` + `git remote add` | `comfyui/tasks/main.yml` | `# noqa: command-instead-of-module` — aucun module Ansible équivalent |
| `git describe` | `story-engine/tasks/main.yml` | `# noqa: command-instead-of-module` — lecture seule, pas de module |

**Recommandation :**
- Utiliser `ansible.builtin.command` (pas `shell`) pour les commandes simples sans pipe ni redirection
- Réserver `ansible.builtin.shell` aux commandes avec `|`, `>`, `&&`, ou construits bash
- Pour les opérations `git` sans module équivalent, ajouter `# noqa: command-instead-of-module` explicitement avec un commentaire justificatif

---

### E7 — `load-failure` : script avec encoding UTF-8 cassé

**Fichier :** `scripts/write_phases456.py`

**Cause :** Vieux script de génération de contenu avec des caractères non-UTF-8 (encoding Windows probable). Jamais référencé ailleurs dans le repo, laissé par erreur.

**Fix :** Supprimé via `git rm`.

**Recommandation :** Tout fichier Python doit commencer par `# -*- coding: utf-8 -*-` ou être enregistré en UTF-8 pur. Auditer `scripts/` régulièrement avec `file scripts/*.py` pour détecter les encodings problématiques.

---

### E8 — Projet externe `FS/` inclus dans le scope lint

**Dossier :** `FS/flash-studio-complete/`

**Cause :** Le dossier `FS/` contient un projet Ansible externe (flash-studio) avec ses propres rôles et conventions. Il n'était pas exclu du lint VPAI, générant des faux positifs (`syntax-check[specific]` sur des rôles comme `sd-common` introuvables dans le contexte VPAI).

**Fix :** Ajout dans `.ansible-lint` :
```yaml
exclude_paths:
  - FS/
  - scripts/
```

**Recommandation :** Tout sous-projet ou dossier externe copié/cloné dans le repo doit être exclu immédiatement de `.ansible-lint`, `.yamllint.yml` et `.github/workflows/ci.yml`.

---

### E9 — Tags à 2 niveaux insuffisants (constaté à l'audit)

**Cause :** Les roles n'avaient que 2 tags `[<role_name>, phase<N>]`. Impossible de déployer "toutes les applications" ou "seulement les outils Pi" sans lister chaque role individuellement.

**Fix :** Ajout d'un 3ème tag de catégorie (`core`, `platform`, `apps`, `provision`, `monitoring`, `workstation`, `ops`) et d'un 4ème tag de sous-catégorie pour workstation (`tools`, `creative`, `services`, `infra`, `monitoring`).

```yaml
# ❌ Avant
- role: n8n
  tags: [n8n, phase3]

# ✅ Après
- role: n8n
  tags: [n8n, phase3, apps]

# ✅ Workstation
- role: comfyui
  tags: [comfyui, workstation, creative]
```

**Recommandation :** La règle des 3 tags est maintenant dans `docs/standards/ANSIBLE-ROLE-CHECKLIST.md` (item 1) et dans `CLAUDE.md`. Tout nouveau rôle doit respecter ce pattern dès sa création.

---

## Recommandations générales

### R1 — Lancer `ansible-lint` après chaque session de code

Le lint n'avait pas été lancé depuis des mois. 27 violations accumulées.  
**Ajouter dans le workflow habituel :**
```bash
source .venv/bin/activate && make lint   # avant tout git push
```

### R2 — Committer `platform.yaml` + `docs/STRUCTURE.md` ensemble

Ces deux fichiers sont liés : `platform.yaml` est la source de vérité, `docs/STRUCTURE.md` est généré.  
Workflow obligatoire lors d'un ajout de rôle :
```bash
vim platform.yaml                                  # 1. modifier
vim scripts/generate-structure.py                  # 2. ajouter description
python scripts/generate-structure.py               # 3. régénérer
git add platform.yaml scripts/generate-structure.py docs/STRUCTURE.md
```

### R3 — Exclure les projets externes immédiatement

Dès qu'un sous-dossier externe est ajouté (clone, copie), l'exclure dans `.ansible-lint` et `.yamllint.yml`.

### R4 — Majuscule sur le premier caractère des noms de tâches

Convention : `name: "Role-name | Action description"` — **toujours une majuscule en premier**.

### R5 — Préférer `ansible.builtin.*` à `ansible.posix.*`

Avant d'utiliser un module `ansible.posix.*`, vérifier s'il existe un équivalent dans `ansible.builtin.*`.  
Si `ansible.posix` est nécessaire, l'ajouter dans `requirements.yml` et vérifier qu'il est installé dans le venv.

### R6 — Relancer le lint après toute migration de fichiers

Toute migration de playbooks ou de rôles peut casser des chemins relatifs. Le lint le détecte via `no-relative-paths` et `syntax-check`. **Toujours lancer `ansible-lint` immédiatement après une migration.**

---

## État final du repo après session

```
ansible-lint --profile production
→ 0 failure(s), 12 warning(s)
   (12 warnings = role-name avec tirets, intentionnel, dans warn_list)
```

| Artefact | Statut |
|----------|--------|
| `docs/standards/ANSIBLE-ROLE-CHECKLIST.md` | ✅ 12 items, mis à jour (3 tags, item 12 taxonomie) |
| `docs/STRUCTURE.md` | ✅ Généré automatiquement depuis `platform.yaml` |
| `platform.yaml` | ✅ Source de vérité taxonomie — 60 rôles en 7 catégories |
| `scripts/generate-structure.py` | ✅ `--check` mode disponible pour CI |
| `playbooks/` | ✅ 6 sous-dossiers (`stacks/`, `hosts/`, `apps/`, `ops/`, `bootstrap/`, `utils/`) |
| `.ansible-lint` | ✅ `FS/` et `scripts/` exclus, `role-name` en warn_list |
| Lint | ✅ `0 failure(s)` |
