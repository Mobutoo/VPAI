# Audit — rôle `llamaindex-memory-worker`

**Date** : 2026-04-09
**Auditeur** : Claude Opus 4.6
**Scope** : Code ajouté par Codex dans `roles/llamaindex-memory-worker/`
**Verdict** : 4 critiques à corriger avant deploy, 5 importants avant production

---

## Résumé

| Sévérité | Count | Action |
|---|---|---|
| Critique | 4 | Corriger avant deploy |
| Important | 5 | Corriger avant usage en production |
| Mineur | 5 | Backlog |

---

## CRITIQUE (bugs / crashes)

### C1 — `py_compile` ne prend qu'un fichier à la fois

**Fichier** : `roles/llamaindex-memory-worker/tasks/main.yml:117`

`python -m py_compile file1 file2` échoue. `py_compile` n'accepte qu'un seul argument.

```yaml
# Actuel (cassé)
cmd: "{{ memory_worker_venv_dir }}/bin/python -m py_compile {{ memory_worker_index_script }} {{ memory_worker_search_script }}"

# Fix: boucle sur les deux scripts
- name: Verify memory worker script syntax
  ansible.builtin.command:
    cmd: "{{ memory_worker_venv_dir }}/bin/python -m py_compile {{ item }}"
  loop:
    - "{{ memory_worker_index_script }}"
    - "{{ memory_worker_search_script }}"
  changed_when: false
  become: true
```

### C2 — `lstrip("# ")` mange les caractères du titre

**Fichier** : `roles/llamaindex-memory-worker/templates/index.py.j2:223`

`first_line.lstrip("# ")` supprime TOUS les caractères `#`, ` ` du début, **dans n'importe quel ordre**. `"## Configuration"` → `"onfiguration"` (le `C` est mangé car `lstrip` traite un **set** de caractères, pas un préfixe).

```python
# Actuel (bug)
section_title = first_line.lstrip("# ").strip()

# Fix
section_title = re.sub(r'^#+\s*', '', first_line).strip()
```

### C3 — Lock file non atomique (race condition)

**Fichier** : `roles/llamaindex-memory-worker/templates/index.py.j2:100-103`

`if exists → raise, else write` est une TOCTOU race. Deux timers pourraient passer le check simultanément.

```python
# Fix: création atomique via O_EXCL
def ensure_lock(lock_path: Path) -> None:
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError as exc:
        raise RuntimeError(f"lock file exists: {lock_path}") from exc
```

### C4 — `changed_when: false` sur création du venv

**Fichier** : `roles/llamaindex-memory-worker/tasks/main.yml:33`

`creates:` rend la tâche idempotente, mais `changed_when: false` masque le changement réel au premier run. Ansible-lint `profile: production` le flaguera. Retirer `changed_when: false` — le `creates:` suffit.

---

## IMPORTANT (fonctionnel dégradé)

### I1 — `batch_size` config inutilisée

**Fichier** : `config.yml.j2:22` vs `index.py.j2:629`

Le code appelle `encoder.encode_documents()` sur TOUS les chunks d'un fichier d'un coup. Un fichier avec 200 chunks va envoyer les 200 au modèle en une seule passe. Sur le Pi avec EmbeddingGemma (~280ms/chunk), ça représente ~56 secondes sans yield + pic RAM. Le `batch_size: 8` dans la config est ignoré.

**Fix** : boucler sur des batches de `config["limits"]["batch_size"]` chunks dans `process_file`.

### I2 — GC ne nettoie pas les repos retirés de la config

**Fichier** : `index.py.j2:667-668`

`gc_missing_entries` skip les entrées dont le `repo_name` n'est plus dans `existing_roots`. Si on retire un repo de la config, ses vecteurs Qdrant et ses entrées d'état restent orphelins pour toujours.

**Fix** : traiter les repos inconnus comme des entrées à supprimer (ou au minimum les logger en warning).

### I3 — `repo_name_for` est un no-op

**Fichier** : `index.py.j2:301-304`

Les deux branches retournent `repo_root.name`. La fonction ne fait rien d'utile. Probable stub oublié.

```python
# Actuel
def repo_name_for(path: Path, repo_root: Path) -> str:
    if path == repo_root:
        return repo_root.name
    return repo_root.name  # <- identique
```

### I4 — Pas de batching Qdrant

**Fichier** : `index.py.j2:651`

`vector_store.add(nodes)` envoie tous les chunks en un seul upsert. Pour 200 chunks × 768 dim × float32 = ~600 Ko de payload par requête réseau. Acceptable pour la majorité des fichiers, mais à surveiller pour les gros fichiers.

### I5 — `sentence-transformers>=5.1,<5.2` — version probablement inexistante

**Fichier** : `defaults/main.yml:31`

En avril 2026, sentence-transformers est probablement en v4.x. Le pin `>=5.1,<5.2` va faire échouer `pip install`. À vérifier contre PyPI et ajuster.

---

## MINEUR (qualité / UX)

### M1 — Pas de rotation de logs

**Fichier** : `index.py.j2:491`

`FileHandler` sans rotation → le fichier log grossit indéfiniment. Utiliser `RotatingFileHandler` ou déployer une config logrotate.

### M2 — `search_memory.py` inutilisable manuellement sans sourcer l'env

**Fichier** : `search_memory.py.j2:37`

`QDRANT_API_KEY` n'a pas de fallback dans la config YAML. L'utilisation manuelle requiert `source memory-worker.env` avant, ce qui n'est documenté nulle part. Ajouter un `--api-key` ou documenter.

### M3 — `ensure_ascii=True` dans les dumps JSON

**Fichier** : `index.py.j2:97`

Rend les fichiers d'état illisibles pour les chemins non-ASCII. Préférer `ensure_ascii=False`.

### M4 — Spool retry ne re-vérifie pas le loadavg

**Fichier** : `index.py.j2:525`

Le check loadavg se fait une seule fois au début. Le retry du spool se fait après, même si le load a augmenté entre-temps.

### M5 — Collection auto-créée sans dimension explicite

La collection `memory_v1` sera créée automatiquement par `QdrantVectorStore` à partir de la dimension du premier vecteur inséré. Fonctionnel, mais fragile si le premier run plante avant insertion. Mieux vaut pré-créer explicitement avec la bonne dimension.

---

## Ce qui est bien fait

- Structure Ansible propre : FQCN partout, `become: true` explicite, handlers corrects avec `listen`
- Variables Qdrant via le domaine VPN-only (`qdrant_subdomain.domain_name`) — pas d'IP Docker inventée
- `EnvironmentFile` en `0600` pour les secrets
- `Nice=19` + `IOSchedulingClass=idle` — bonne citoyenneté sur le Pi
- `Persistent=true` sur le timer — rattrape les exécutions manquées
- Détection de changements par mtime+size avec fallback hash — pragmatique
- Spool pour retry des fichiers échoués — résilient
- `--dry-run` présent dès le départ
- Chunking différencié par type (markdown/code/config) — meilleur que du sliding window aveugle
- Payload riche avec `schema_version`, `embedding_model`, `git_commit_sha` — facilite les migrations futures
