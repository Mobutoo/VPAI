# REX — Session 12 — 2026-02-25

**Durée** : ~6h (sessions multiples)
**Objectif initial** : Palais UI Phase 2 (6 features) + vider n8n et réimporter 27 workflows propres
**Résultat** : 12 features déployées, 27 workflows en prod, 3 bugs n8n documentés et corrigés

---

## Chronologie et Bugs Corrigés

### REX-50 — n8n REST API `/rest/login` retourne HTTP 400 en v2.7

**Symptôme** : Le script de nuke Ansible (`--tags n8n-nuke`) affichait `FOUND:0 / NUKE_COMPLETE` mais n8n contenait 123 workflows. Le nuke semblait réussir sans rien supprimer.

**Cause** : Le script Node.js appelle `/rest/login` avec `{emailOrLdapLoginId, password}`. En n8n 2.7.3, cet endpoint retourne HTTP 400 `Invalid email address` même avec des credentials valides. La session cookie n'est jamais obtenue → `/rest/workflows` retourne un tableau vide → `FOUND:0`.

**Diagnostic** :
```bash
# Compter les workflows directement en DB
docker exec javisi_postgresql psql -U n8n -d n8n \
  -c "SELECT COUNT(*) FROM workflow_entity;"
# → 123 (alors que l'API retournait FOUND:0)

# Confirmer via CLI
docker exec javisi_n8n n8n list:workflow 2>&1 | wc -l
# → 123
```

**Fix** : Remplacer l'approche REST API par CLI + DELETE PostgreSQL en ordre FK :
```bash
# 1. Désactiver tous les workflows
docker exec javisi_n8n n8n unpublish:workflow --all

# 2. Supprimer en ordre FK (pas de CASCADE pour éviter de toucher users/credentials)
docker exec javisi_postgresql psql -U n8n -d n8n -c "
  DELETE FROM webhook_entity;
  DELETE FROM workflows_tags;
  DELETE FROM workflow_statistics;
  DELETE FROM workflow_history;
  DELETE FROM workflow_published_version;
  DELETE FROM workflow_publish_history;
  DELETE FROM workflow_dependency;
  DELETE FROM shared_workflow;
  DELETE FROM execution_annotation_tags;
  DELETE FROM execution_annotations;
  DELETE FROM execution_metadata;
  DELETE FROM execution_data;
  DELETE FROM execution_entity;
  DELETE FROM workflow_entity;
"
```

**Commit** : `97536e5`

**Règle** : Ne jamais utiliser `/rest/login` pour les scripts de gestion n8n v2.7+. Utiliser `n8n CLI` ou `psql` direct. La DB n8n est accessible via `docker exec <project>_postgresql psql -U n8n -d n8n`.

---

### REX-51 — Ansible `tags: [never]` inopérant avec héritage de rôle

**Symptôme** : Les tâches nuke (`tags: [n8n-nuke, never]`) s'exécutaient à chaque `--tags n8n-provision`, causant un `failed=1` sur le nuke et un exit code 2 sur le déploiement.

**Cause** : Quand `site.yml` définit `- role: n8n-provision \n  tags: n8n-provision`, Ansible ajoute automatiquement le tag `n8n-provision` à **toutes** les tâches du rôle. Une tâche avec `tags: [n8n-nuke, never]` hérite donc de `n8n-provision`. Avec `--tags n8n-provision`, Ansible voit que le tag match → la tâche est exécutée malgré le `never`.

Le `never` ne "gagne" pas sur un tag hérité qui matche explicitement `--tags`.

**Fix** : Protéger les tâches destructives avec une variable `when:` :
```yaml
- name: "[nuke] Delete ALL workflows"
  # ...
  when: n8n_nuke_requested | default(false) | bool
  tags: [n8n-nuke]
```

Usage :
```bash
make deploy-role ROLE=n8n-provision ENV=prod EXTRA_VARS="n8n_nuke_requested=true"
```

**Commit** : `97536e5`

**Règle** : Pour toute tâche destructive dans un rôle : ne pas compter sur `tags: [never]` — utiliser `when: ma_variable | default(false) | bool`. Le `never` tag ne fonctionne QUE si aucun autre tag matchant n'est hérité.

---

### REX-52 — Tags n8n : format `["string"]` invalide → `null tagId` en DB

**Symptôme** : Import du workflow `OpenClaw — Plan Dispatch` retournait :
```
An error occurred while importing workflows.
null value in column "tagId" of relation "workflows_tags" violates not-null constraint
```

**Cause** : Le template `plan-dispatch.json.j2` avait les tags en format plain strings :
```json
"tags": ["openclaw", "kaneo", "idea-planning"]
```

n8n s'attend à des objets avec la clé `name` :
```json
"tags": [{ "name": "openclaw" }, { "name": "kaneo" }, { "name": "idea-planning" }]
```

Lors de l'import, n8n essaie de résoudre les tags par `id` → `null` car une string n'a pas de `id` → violation de contrainte FK.

**Fix** : Changer le format dans `roles/n8n-provision/templates/workflows/plan-dispatch.json.j2`.

**Commit** : `53a9048`

**Règle** : Dans tous les JSON de workflows n8n : `"tags": [{"name": "tag-name"}]`. Ne jamais utiliser les formats `["string"]` ou `[{"id": null, "name": "..."}]`.

---

### REX-53 — Ghost agent `main` / seedAgentBios : source de données corrompues

**Symptôme** : Un agent fantôme avec `id: 'main'` apparaissait dans Palais à chaque redémarrage du serveur. Il n'existait dans aucun workflow OpenClaw.

**Cause** : La fonction `seedAgentBios()` dans `roles/palais/files/app/src/lib/server/db/seed.ts` créait/updatait hardcodé des agents au démarrage, dont `id: 'main'`. Résidu d'une phase de développement antérieure.

**Fix** :
1. Supprimer le ghost existant en DB : `DELETE FROM agents WHERE id = 'main';`
2. Supprimer `seedAgentBios()` de `seed.ts` et son import dans `hooks.server.ts`

**Commit** : `fe67b6e`

**Règle** : Les données initiales des agents viennent exclusivement des événements `agent.registered` WebSocket depuis OpenClaw. Pas de seed hardcodé.

---

## Features Déployées (Palais UI Phase 2)

| # | Feature | Commits |
|---|---------|---------|
| 1 | Ghost agent cleanup + seedAgentBios supprimé | `fe67b6e` |
| 2 | Handler WebSocket `agent.registered` → update DB | `fe67b6e` |
| 3 | PATCH `/api/v1/agents/[id]` (bio + persona) | `73d8b7c` |
| 4 | AgentCard redesign : format 2:3 portrait + SVG ring animé (busy state) | `73d8b7c` |
| 5 | Icônes Adinkra SVG : Akoma (Missions), Fawohodie (Ideas), Sankofa (Memory) | `98f2c7f` |
| 6 | Health webhook : champ `local_ip` auto-reporté par les nœuds | `92ab2c5` |
| 7 | PATCH `/api/v1/health/nodes/[name]` (localIp + description) | `92ab2c5` |
| 8 | Page Health : affichage LAN/VPN IPs + positions dynamiques | `92ab2c5` |

---

## n8n — Réimport des 27 Workflows

**Contexte** : 123 workflows dupliqués existaient en DB (imports répétés lors des sessions de développement). Nuke manuel requis car REST API cassée.

**Procédure qui a fonctionné** :
```bash
# 1. Nuke manuel (après avoir confirmé que n8n CLI retourne 0 en DB)
docker exec javisi_n8n n8n unpublish:workflow --all
docker exec javisi_postgresql psql -U n8n -d n8n -c "DELETE FROM workflow_entity; ..."

# 2. Vider les checksums pour forcer le réimport
rm -rf /opt/javisi/configs/n8n/workflow-checksums/

# 3. Redéployer
make deploy-role ROLE=n8n-provision ENV=prod
```

**Résultat** : 27 workflows présents, actifs, checksums à jour.

---

## Etat Post-Session

| Composant | Etat |
|-----------|------|
| Palais — AgentCard 2:3 portrait | ✅ Déployé |
| Palais — Icônes Adinkra | ✅ Déployé |
| Palais — VPN/LAN IPs sur Health | ✅ Déployé |
| Palais — PATCH agents + nodes | ✅ Déployé |
| n8n — 27 workflows | ✅ En prod |
| n8n — nuke Ansible | ✅ Réécrit (CLI+DB, guard `n8n_nuke_requested`) |
| n8n — Plan Dispatch tags | ✅ Corrigé |
| Ghost agent `main` | ✅ Supprimé (ne réapparaît plus) |
