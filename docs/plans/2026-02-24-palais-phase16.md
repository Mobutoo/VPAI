# Palais Phase 16 — Nettoyage + Migration Kaneo

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrer les donnees Kaneo existantes vers Palais, desactiver le role Kaneo, nettoyer les references, importer les REX dans le Knowledge Graph.

**Architecture:** Script SQL one-shot pour migrer projets/taches/commentaires de la DB Kaneo vers Palais. DB Kaneo conservee en backup (pas supprimee). Role Ansible Kaneo desactive. REX existants importes comme noeuds memoire.

**Tech Stack:** SQL migration script, Ansible, Node.js seed scripts

**PRD Reference:** `docs/PRD-PALAIS.md` — Phase 16 (Nettoyage + Migration)

---

## Task 1: Script Migration Donnees Kaneo → Palais

**Files:**
- Create: `roles/palais/files/app/scripts/migrate-kaneo.ts`

Script Node.js qui lit depuis la DB Kaneo et insere dans Palais :

```typescript
// Connexions
const kaneoDb = postgres(process.env.KANEO_DATABASE_URL);
const palaisDb = postgres(process.env.DATABASE_URL);

// 1. Migrer les projets (workspaces Kaneo → projects Palais)
const kaneoProjects = await kaneoDb`SELECT * FROM projects`;
for (const p of kaneoProjects) {
  await palaisDb`INSERT INTO projects (name, slug, description, created_at)
    VALUES (${p.name}, ${slugify(p.name)}, ${p.description}, ${p.created_at})
    ON CONFLICT (slug) DO NOTHING`;
}

// 2. Migrer les taches
const kaneoTasks = await kaneoDb`SELECT * FROM tasks`;
for (const t of kaneoTasks) {
  const projectId = projectMapping[t.project_id];
  const columnId = columnMapping[t.status]; // map Kaneo status → Palais column
  await palaisDb`INSERT INTO tasks (project_id, column_id, title, description, status, priority, created_at)
    VALUES (${projectId}, ${columnId}, ${t.title}, ${t.description}, ${mapStatus(t.status)}, ${t.priority ?? 'none'}, ${t.created_at})
    ON CONFLICT DO NOTHING`;
}

// 3. Migrer les commentaires
const kaneoComments = await kaneoDb`SELECT * FROM comments`;
for (const c of kaneoComments) {
  const taskId = taskMapping[c.task_id];
  await palaisDb`INSERT INTO comments (task_id, author_type, content, created_at)
    VALUES (${taskId}, 'system', ${c.content}, ${c.created_at})`;
}
```

Flags : `--dry-run` pour tester sans ecrire, `--verbose` pour logs detailles.

Commit: `feat(palais): Kaneo → Palais data migration script`

## Task 2: Executer la Migration

Procedure :
1. Backup DB Kaneo : `pg_dump -U kaneo kaneo > kaneo_backup_$(date +%Y%m%d).sql`
2. Dry run : `npx tsx scripts/migrate-kaneo.ts --dry-run`
3. Verifier les logs, corriger les mappings si necessaire
4. Execution reelle : `npx tsx scripts/migrate-kaneo.ts`
5. Verifier dans Palais : projets, taches, commentaires visibles

Commit: `chore(palais): Kaneo data migration executed successfully`

## Task 3: Desactiver le Role Kaneo dans Ansible

**Files:**
- Modify: `playbooks/site.yml`

Commenter ou supprimer l'inclusion du role `kaneo` :

```yaml
# Anciennement:
# - role: kaneo
#   tags: [kaneo]

# Remplace par:
- role: palais
  tags: [palais]
```

Ne PAS supprimer le role `roles/kaneo/` — le garder en archive au cas ou.

Commit: `chore(ansible): disable Kaneo role, Palais replaces it`

## Task 4: Retirer Kaneo du Docker Compose

**Files:**
- Modify: `roles/docker-stack/templates/docker-compose.yml.j2`

Supprimer les services `kaneo-api` et `kaneo-web` du template Docker Compose.

Verifier que le service `palais` est bien present (ajoute en Phase 1).

Commit: `chore(docker): remove kaneo-api and kaneo-web services`

## Task 5: Retirer les Images Kaneo de versions.yml

**Files:**
- Modify: `inventory/group_vars/all/versions.yml`

Supprimer :
```yaml
# kaneo_api_image: "ghcr.io/kaneo-app/kaneo-api:x.x.x"
# kaneo_web_image: "ghcr.io/kaneo-app/kaneo-web:x.x.x"
```

Commit: `chore(versions): remove Kaneo image references`

## Task 6: Retirer le Block Caddy Kaneo

**Files:**
- Modify: `roles/caddy/templates/Caddyfile.j2`

Supprimer le block :
```caddyfile
# hq.{{ domain_name }} {
#     import vpn_only
#     reverse_proxy kaneo-web:5173
# }
```

Verifier que le block `{{ palais_subdomain }}.{{ domain_name }}` existe.

Commit: `chore(caddy): remove Kaneo reverse proxy block`

## Task 7: Nettoyer les Variables Kaneo

**Files:**
- Modify: `inventory/group_vars/all/main.yml`
- Modify: `inventory/group_vars/all/secrets.yml`

Supprimer de `main.yml` :
```yaml
# kaneo_subdomain, kaneo_db_name, kaneo_db_user, etc.
```

Supprimer de `secrets.yml` :
```yaml
# vault_kaneo_db_password, vault_kaneo_secret, etc.
```

Garder les variables `palais_*` qui les remplacent.

Commit: `chore(vars): remove Kaneo variables from inventory`

## Task 8: Archiver les Sections Kaneo du TROUBLESHOOTING.md

**Files:**
- Modify: `docs/TROUBLESHOOTING.md`

Deplacer les sections relatives a Kaneo dans une section "Archive — Kaneo (remplace par Palais)" en fin de document. Ne pas supprimer — garder pour reference historique.

Ajouter une section "Palais" avec :
- Healthcheck : `curl -sf https://palais.<domain>/api/health`
- Logs : `docker logs palais --tail 50`
- DB : `docker exec postgresql psql -U palais -d palais -c 'SELECT count(*) FROM tasks'`
- Restart : `docker restart palais`

Commit: `docs: archive Kaneo sections, add Palais to TROUBLESHOOTING.md`

## Task 9: Importer REX dans le Knowledge Graph

**Files:**
- Create: `roles/palais/files/app/scripts/seed-memory-rex.ts`

Lire les fichiers REX existants et creer des noeuds memoire :

```typescript
const rexFiles = [
  { path: 'docs/REX-FIRST-DEPLOY-2026-02-15.md', title: 'REX Premier Deploiement' },
  { path: 'docs/REX-SESSION-2026-02-18.md', title: 'REX Session 8 — Split DNS, Budget' },
  { path: 'docs/REX-SESSION-2026-02-23.md', title: 'REX Session 9 — Creative Stack Pi' },
  { path: 'docs/REX-SESSION-2026-02-23b.md', title: 'REX Session 10 — OpenClaw Breaking Changes' },
];

for (const rex of rexFiles) {
  const content = fs.readFileSync(rex.path, 'utf-8');
  // Creer noeud episodique
  await fetch(`${PALAIS_URL}/api/v1/memory/nodes`, {
    method: 'POST',
    headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: 'episodic',
      content: content.slice(0, 2000), // Truncate for embedding
      summary: rex.title,
      entity_type: 'deployment',
      tags: ['rex', 'deployment', 'troubleshooting'],
      created_by: 'system'
    })
  });
}
```

Aussi importer les sections cles du TROUBLESHOOTING.md comme noeuds semantiques.

Commit: `feat(palais): seed Knowledge Graph with existing REX documents`

## Task 10: Importer TROUBLESHOOTING.md dans le Knowledge Graph

**Files:**
- Modify: `roles/palais/files/app/scripts/seed-memory-rex.ts`

Parser les sections du TROUBLESHOOTING.md (44+ sections) et creer un noeud par section :

```typescript
const troubleshooting = fs.readFileSync('docs/TROUBLESHOOTING.md', 'utf-8');
const sections = parseSections(troubleshooting); // Split par ## headers

for (const section of sections) {
  await fetch(`${PALAIS_URL}/api/v1/memory/nodes`, {
    method: 'POST',
    headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: 'procedural',
      content: section.content.slice(0, 2000),
      summary: section.title,
      entity_type: 'error',
      tags: ['troubleshooting', section.service],
      created_by: 'system'
    })
  });
}
```

Commit: `feat(palais): seed Knowledge Graph with TROUBLESHOOTING.md sections`

## Task 11: Backup DB Kaneo (ne pas supprimer)

Procedure :
1. `pg_dump -U kaneo kaneo > /backups/kaneo_final_$(date +%Y%m%d).sql`
2. Copier le dump dans le repertoire backup Zerobyte
3. Ne PAS executer `DROP DATABASE kaneo` — garder en lecture seule
4. Documenter dans RUNBOOK.md la procedure de restauration si necessaire

Commit: `chore: backup Kaneo database (kept for reference)`

## Task 12: Verification Finale E2E

Tests a executer apres migration :

```bash
# 1. Palais healthy
curl -sf https://palais.<domain>/api/health
# → {"status":"ok"}

# 2. Donnees migrees
curl -H "X-API-Key: <key>" https://palais.<domain>/api/v1/projects
# → Projets migres depuis Kaneo visibles

# 3. Kaneo services down
docker ps | grep kaneo
# → Aucun resultat

# 4. Knowledge Graph seede
curl -H "X-API-Key: <key>" -X POST https://palais.<domain>/api/v1/memory/search \
  -d '{"query": "Caddy 403"}'
# → Noeuds du TROUBLESHOOTING.md

# 5. Ansible idempotent
make deploy-prod
# → 0 changed pour les roles Palais

# 6. Telegram fonctionnel
# → Envoyer "/status" sur Telegram → Concierge → Palais → reponse
```

Commit: `test(e2e): full migration verification passed`

---

## Verification Checklist

- [ ] Script migration Kaneo → Palais execute avec succes
- [ ] Projets, taches, commentaires visibles dans Palais
- [ ] Role Kaneo desactive dans site.yml
- [ ] Services kaneo-api et kaneo-web retires du docker-compose
- [ ] Images Kaneo retirees de versions.yml
- [ ] Block Caddy Kaneo supprime
- [ ] Variables Kaneo nettoyees
- [ ] TROUBLESHOOTING.md : sections Kaneo archivees, section Palais ajoutee
- [ ] REX importes dans le Knowledge Graph
- [ ] TROUBLESHOOTING.md importe dans le Knowledge Graph
- [ ] DB Kaneo backupee (pas supprimee)
- [ ] E2E : Telegram → Palais fonctionnel
- [ ] Ansible : 0 changed a la 2eme execution
