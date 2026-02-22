# Creative Studio — Fixes & Release Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Corriger les bugs critiques du AI Creative Studio, supprimer mission-control, gérer les branches CC, créer un tag v1.6.0 et merger.

**Architecture:** Les fixes touchent 3 fichiers principaux (creative-pipeline.json, asset-register.json, docker-compose-creative.yml.j2) + suppression du role mission-control. Les branches CC/* sont toutes en retard sur main (aucun commit unique à merger). Le tag v1.6.0 sera créé sur main après les fixes.

**Tech Stack:** Ansible/Jinja2, JSON (n8n workflows), Docker Compose, git

---

## Contexte branches

| Branche | État vs main | Action |
|---------|-------------|--------|
| `CC/gifted-lichterman` | **Identique** à main (SHA 30550e1) | Rien à faire |
| `CC/nostalgic-dubinsky` | **En retard** — diverge à `8db2294` (avant Creative Studio) | Dead — pas de commits uniques |
| `CC/confident-hertz` | **En retard** — diverge à `6e54f83` (bien avant) | Dead — pas de commits uniques |

Toutes les branches CC sont des worktrees Claude Code sans commits supplémentaires → **rien à merger, rien à rebaser**.

## Situation main

- 11 commits non pushés vers `origin/main`
- 2 fichiers non commités : `bootstrap.sh` (CRLF only), `docs/REX-MISSION-CONTROL-OPENCLAW-2026-02-20.md` (nouveau)
- Dernier tag : `v1.5.0` (6 commits en arrière)
- Prochain tag : `v1.6.0` — AI Creative Studio complet + fixes

---

## Task 1 : Corriger le DNS cross-host dans creative-pipeline.json

**Problème :** Le workflow n8n appelle `http://comfyui:8188` et `http://remotion:3200` — noms Docker DNS du RPi 5, invisibles depuis le VPS.

**Solution :** Remplacer par les URLs Caddy du workstation : `https://studio.{{ domain_name }}` et `https://cut.{{ domain_name }}`. Mais comme c'est un fichier JSON statique (pas un template Jinja2), on utilise une variable de substitution fixe issue du vault. La vraie solution propre est de convertir ce fichier en template `.j2`.

**Approche choisie :** Convertir `creative-pipeline.json` en template `creative-pipeline.json.j2` dans `roles/n8n-provision/templates/` et référencer les variables Ansible.

**Files:**
- Rename: `roles/n8n-provision/files/workflows/creative-pipeline.json` → supprimé
- Create: `roles/n8n-provision/templates/workflows/creative-pipeline.json.j2`
- Modify: `roles/n8n-provision/tasks/main.yml` — utiliser `template` au lieu de `copy` pour ce workflow

**Step 1 : Lire le tasks/main.yml de n8n-provision**

Vérifier comment les workflows sont copiés.

**Step 2 : Créer le template creative-pipeline.json.j2**

Remplacer dans le JSON :
- `"http://comfyui:8188/prompt"` → `"https://{{ comfyui_subdomain }}.{{ domain_name }}/prompt"`
- `"http://remotion:3200/render"` → `"https://{{ remotion_subdomain }}.{{ domain_name }}/render"`
- `"http://comfyui:8188/view?filename=` → `"https://{{ comfyui_subdomain }}.{{ domain_name }}/view?filename=`
- `"http://remotion:3200/output/` → `"https://{{ remotion_subdomain }}.{{ domain_name }}/output/`

**Step 3 : Adapter tasks/main.yml pour templater ce fichier**

**Step 4 : Supprimer l'ancien fichier JSON statique**

**Step 5 : Commit**
```bash
git add roles/n8n-provision/templates/workflows/creative-pipeline.json.j2
git add roles/n8n-provision/tasks/main.yml
git rm roles/n8n-provision/files/workflows/creative-pipeline.json
git commit -m "fix(creative-pipeline): use workstation Caddy URLs instead of Docker DNS (cross-host fix)"
```

---

## Task 2 : Corriger l'injection SQL dans asset-register.json

**Problème :** Les champs `type`, `provider`, `model`, `output_name`, `agent_id` sont interpolés directement dans le SQL.

**Solution :** Déplacer tous ces champs vers les paramètres `$N` de la requête.

**File:**
- Modify: `roles/n8n-provision/files/workflows/asset-register.json`

**Step 1 : Réécrire la requête SQL avec tous les champs paramétrés**

Requête corrigée (15 paramètres) :
```sql
INSERT INTO asset_provenance (
  asset_id, type, provider, model, prompt, output_name,
  result_url, render_id, agent_id, cost_usd, storage_path,
  generated_at, metadata
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb)
ON CONFLICT (asset_id) DO UPDATE
  SET metadata = EXCLUDED.metadata, result_url = EXCLUDED.result_url
RETURNING asset_id
```

queryParams (dans le même ordre) :
```javascript
[
  $('Parse & enrich').first().json.asset_id,
  $('Parse & enrich').first().json.type,
  $('Parse & enrich').first().json.provider,
  $('Parse & enrich').first().json.model,
  $('Parse & enrich').first().json.prompt,
  $('Parse & enrich').first().json.output_name,
  $('Parse & enrich').first().json.result_url,
  $('Parse & enrich').first().json.render_id,
  $('Parse & enrich').first().json.agent_id,
  $('Parse & enrich').first().json.cost_usd,
  $('Parse & enrich').first().json.storage_path,
  $('Parse & enrich').first().json.timestamp,
  JSON.stringify($('Parse & enrich').first().json)
]
```

**Step 2 : Commit**
```bash
git add roles/n8n-provision/files/workflows/asset-register.json
git commit -m "fix(asset-register): parameterize all SQL fields to prevent injection"
```

---

## Task 3 : Supprimer le role mission-control

**Contexte :** Le role `roles/mission-control/` est présent dans `main` et toutes les branches. Il n'est plus référencé dans aucun playbook. Kaneo le remplace. Mission Control avait été ajouté sur une ancienne branche fusionnée dans main (commit `e483de5 fix(mission-control): DATABASE_PATH + workspace paths + DB migration`).

**Files:**
- Delete: `roles/mission-control/` (tout le dossier)

**Step 1 : Supprimer avec git rm**
```bash
git rm -r roles/mission-control/
git commit -m "chore: remove mission-control role — replaced by Kaneo (PM)"
```

---

## Task 4 : Supprimer `| default('latest')` dans docker-compose-creative.yml.j2

**File:**
- Modify: `roles/comfyui/templates/docker-compose-creative.yml.j2`

**Step 1 :** Remplacer `{{ remotion_version | default('latest') }}` par `{{ remotion_version }}`

**Step 2 :** Remplacer les `| default(...)` pour les variables déjà définies dans remotion/defaults/main.yml :
- `{{ remotion_data_dir | default('/opt/workstation/data/remotion') }}` → `{{ remotion_data_dir }}`
- `{{ remotion_memory_limit | default('512M') }}` → `{{ remotion_memory_limit }}`
- `{{ remotion_cpu_limit | default('2.0') }}` → `{{ remotion_cpu_limit }}`
- `{{ remotion_memory_reservation | default('256M') }}` → `{{ remotion_memory_reservation }}`

**Step 3 : Commit**
```bash
git add roles/comfyui/templates/docker-compose-creative.yml.j2
git commit -m "fix(remotion): remove | default('latest') fallbacks — variables defined in defaults"
```

---

## Task 5 : Ajouter réseau nommé dans docker-compose-creative.yml.j2

**File:**
- Modify: `roles/comfyui/templates/docker-compose-creative.yml.j2`

**Step 1 :** Ajouter `networks: [creative]` à chaque service et déclarer le réseau en bas :

```yaml
networks:
  creative:
    name: workstation_creative
    driver: bridge
```

Et dans chaque service :
```yaml
networks:
  - creative
```

**Step 2 : Commit**
```bash
git add roles/comfyui/templates/docker-compose-creative.yml.j2
git commit -m "fix(creative-studio): add named Docker network per project convention"
```

---

## Task 6 : Corriger le healthcheck ComfyUI (timeout urllib)

**File:**
- Modify: `roles/comfyui/templates/docker-compose-creative.yml.j2`

**Step 1 :** Ajouter `timeout=8` dans l'appel urlopen :
```
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8188/system_stats', timeout=8)"
```

**Step 2 : Commit en même temps que Task 5** (regrouper si possible)

---

## Task 7 : Commiter les fichiers non-trackés existants

**Files:**
- `docs/REX-MISSION-CONTROL-OPENCLAW-2026-02-20.md` (non tracké)
- `bootstrap.sh` (CRLF — vérifier si diff réel ou juste line endings)

**Step 1 : Vérifier bootstrap.sh**
```bash
git diff --ignore-cr-at-eol bootstrap.sh
```

Si diff vide → juste CRLF, ignorer. Sinon commiter.

**Step 2 : Commiter le REX**
```bash
git add docs/REX-MISSION-CONTROL-OPENCLAW-2026-02-20.md
git commit -m "docs: REX Mission Control → OpenClaw 2026-02-20"
```

---

## Task 8 : Créer le tag v1.6.0 et la release GitHub

**Résumé du contenu depuis v1.5.0 :**
```
e483de5 fix(mission-control): DATABASE_PATH + workspace paths + DB migration
1670136 fix(caddy): force HTTP/1.1 pour reverse_proxy OpenClaw (WebSocket)
8db2294 docs: HTTP/2+WebSocket piege dans TROUBLESHOOTING section 11
114a205 feat: AI Creative Studio — phases 6.5, 7, 9, 10, 12, 12.7
372771b feat: Phase 8 + 11 — Kaneo CI/CD + n8n bridge workflows
30550e1 feat: Phases 13+14 — Asset provenance, monitoring RPi & dashboards
+ fixes Tasks 1-7
```

**Step 1 : Créer le tag annoté**
```bash
git tag -a v1.6.0 -m "feat: AI Creative Studio — ComfyUI + Remotion + n8n pipelines + asset provenance

Phases 6.5-14 : Workstation Pi AI Creative Studio
- ComfyUI v0.3.27 (ARM64 CPU-only, Docker)
- Remotion v4.0.259 (video rendering, Docker)
- n8n creative-pipeline workflow (image + video, local + cloud)
- n8n asset-register workflow (provenance Kaneo + PostgreSQL)
- Kaneo (remplace Mission Control comme PM tool)
- Monitoring RPi + dashboards Grafana creative-studio
- Phase 13 : Asset provenance
- Phase 14 : RPi monitoring

Fixes :
- DNS cross-host corrigé (Docker DNS → Caddy HTTPS)
- SQL injection corrigé dans asset-register
- mission-control supprimé (remplacé par Kaneo)
- Docker network nommé ajouté
- remotion_version | default('latest') supprimé"
```

**Step 2 : Créer la release GitHub**
```bash
gh release create v1.6.0 \
  --title "v1.6.0 — AI Creative Studio" \
  --notes "..." \
  --latest
```

---

## Task 9 : Push vers origin/main

```bash
git push github-seko main
git push github-seko --tags
```

---

## Task 10 : Supprimer les branches CC obsolètes

Les 3 branches CC sont en retard sur main sans commits uniques — ce sont des worktrees Claude Code résiduels.

```bash
git branch -d CC/confident-hertz
git branch -d CC/gifted-lichterman
git branch -d CC/nostalgic-dubinsky
```

(Pas de `push --delete` car ces branches ne sont pas sur origin)
