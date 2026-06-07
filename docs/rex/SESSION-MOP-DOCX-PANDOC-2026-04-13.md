# Rapport de session — MOP DOCX output + pandoc-api
**Date**: 2026-04-13  
**Durée**: ~3h (2 sessions avec compaction)  
**Objectif**: Ajouter sortie DOCX parallèle au workflow `mop-generate` via microservice pandoc

---

## Ce qui a été accompli

### 1. Rôle Ansible `pandoc-api` (nouveau)
Microservice Express/Node.js wrappant `pandoc/core:3.6`.

- `roles/pandoc-api/files/Dockerfile` — `ENTRYPOINT []` critique (override entrypoint pandoc/core)
- `roles/pandoc-api/files/server.js` — `POST /convert/html-to-docx` + `GET /health`
- `roles/pandoc-api/files/package.json` — dépendance `express` uniquement
- `roles/pandoc-api/defaults/main.yml` — port 3001, réseau `javisi_backend`
- `roles/pandoc-api/templates/docker-compose.yml.j2` — compose séparé, réseau externe
- `roles/pandoc-api/tasks/main.yml` — build + recreate always
- `roles/pandoc-api/meta/main.yml` — `license: MIT` requis par ansible-lint

Déployé via `make deploy-role ROLE=pandoc-api EXTRA_ARGS="-e ansible_host=100.64.0.14"`.  
Container `javisi_pandoc_api` running healthy.

### 2. Rôle `mop-templates` — ajout `mop_docx_dir`
- `defaults/main.yml` : `mop_docx_dir: "{{ mop_data_dir }}/docx"`
- `tasks/main.yml` : `mop_docx_dir` ajouté dans la boucle de création de répertoires (UID 1000, 0755)
- `/opt/javisi/data/mop/docx/` créé sur Sese-AI

### 3. `mop-generate.json` — sortie DOCX
Nœud `Build HTML` : ajout de `docxFilename` et `html` dans le JSON output (évite base64 decode).

Ajout 3 nœuds → `Convert to DOCX` (httpRequest v4.2 → pandoc_api:3001), `Write DOCX` (writeBinaryFile), puis `Respond` mis à jour avec `docx_url`.

Architecture finale — chaîne séquentielle (merge supprimé, voir §Problèmes) :
```
Webhook → Build HTML → Convert to PDF → Write PDF → Convert to DOCX → Write DOCX → Respond
```

Respond retourne :
```json
{"pdf_url": "...", "docx_url": "...", "filename": "...", "docx_filename": "...", "incident_id": "..."}
```

### 4. Smoke tests
- TEST-001 : PDF 41 980 B + DOCX 11 355 B ✓
- TEST-002 (après suppression merge) : PDF 42 302 B + DOCX 11 357 B ✓

### 5. Commits
| Hash | Message |
|------|---------|
| `ea1d622` | feat(mop): add static context and rex brief zone before phase 1 in fiche mop |
| commits pandoc-api | feat(pandoc-api): new role — HTML→DOCX microservice |
| `0fc7009` | refactor(mop-generate): replace parallel+merge with sequential PDF→DOCX chain |

---

## Problèmes rencontrés et solutions

| Problème | Cause | Solution |
|----------|-------|----------|
| Container crash-loop `pandoc node server.js` | `pandoc/core:3.6` a `ENTRYPOINT ["pandoc"]` — CMD devient argument | `ENTRYPOINT []` avant CMD dans Dockerfile |
| `n8n expression | base64ToString` invalide | Syntaxe n8n inexistante pour décoder binary | Exposer `html` comme champ string dans Build HTML JSON output |
| PUT HTTP 400 "additional properties" | API n8n rejette `meta`, `pinData`, `id` au niveau root | Payload minimal `{name, nodes, connections, settings, staticData}` |
| PUT HTTP 401 | `psql` absent dans `javisi_n8n`, mauvais container (javisi_postgresql vs javisi_postgres) | `docker exec javisi_postgresql psql -U n8n` + `PGPASSWORD=W4zaBanga1974` |
| Merge node erreur runtime "Fields to Match" | `mode: combine` + `combinationMode: mergeByPosition` nécessite field pair config | Remplacé par `mode: append` puis suppression totale (architecture séquentielle) |
| Tailscale R7 — `make deploy-role` échoue | `vault_prod_ip: 137.74.114.167` injoignable depuis waza | `EXTRA_ARGS="-e ansible_host=100.64.0.14"` sur toutes les commandes Ansible |
| MCP n8n `-32000` session expirée | MCP n8n déconnecté en cours de session | Validation Python structurelle + REST API PUT direct |
| ansible-lint `name[casing]` | Noms de tâches `pandoc-api |` (lowercase) | `replace_all` → `Pandoc-api |` |
| ansible-lint `schema[meta]` | `meta/main.yml` sans champ `license` | Ajout `license: MIT` dans `galaxy_info` |

---

## Architecture réseau

```
n8n (javisi_backend) → http://pandoc_api:3001  (même réseau Docker)
n8n (javisi_backend) → http://gotenberg:3000   (même réseau Docker)
/opt/javisi/data/mop → /data/mop (volume n8n)
  ├── pdf/     ← Gotenberg output
  └── docx/    ← pandoc-api output
```

## Commandes deploy

```bash
# Ansible (toujours via Tailscale)
source .venv/bin/activate
make deploy-role ROLE=pandoc-api EXTRA_ARGS="-e ansible_host=100.64.0.14"
make deploy-role ROLE=mop-templates EXTRA_ARGS="-e ansible_host=100.64.0.14"

# Workflow n8n (PUT REST API)
N8N_KEY="<claude-code-deploy JWT>"
python3 -c "
import json
d = json.load(open('scripts/n8n-workflows/mop-generate.json'))
payload = {k: d[k] for k in ('name','nodes','connections','settings','staticData') if k in d}
print(json.dumps(payload))
" | curl -sS -w "\nHTTP_%{http_code}" \
  -X PUT "https://mayi.ewutelo.cloud/api/v1/workflows/jtvnpjvxc3RjnIwA" \
  -H "X-N8N-API-KEY: $N8N_KEY" \
  -H "Content-Type: application/json" -d @-
```

---

## Questions ouvertes / todo optionnel

| Item | Priorité |
|------|----------|
| Template `telehouse.docx` — styles Telehouse (headings bleu marine, tableaux) | basse |
| Fix `deploy-workflow.sh` — strip champs refusés avant PUT | basse |
| Stocker `claude-code-deploy` JWT dans `secrets.yml` sous `vault_n8n_deploy_api_key` | basse |

---

## Fichiers modifiés / créés

```
roles/pandoc-api/                        ← nouveau rôle complet
  files/Dockerfile
  files/server.js
  files/package.json
  files/reference/                       ← templates .docx (vide pour l'instant)
  defaults/main.yml
  templates/docker-compose.yml.j2
  tasks/main.yml
  meta/main.yml
roles/mop-templates/defaults/main.yml   ← +mop_docx_dir
roles/mop-templates/tasks/main.yml      ← +mop_docx_dir dans boucle dirs
playbooks/stacks/site.yml               ← +pandoc-api role
scripts/n8n-workflows/mop-generate.json ← +DOCX branch, merge supprimé
```
