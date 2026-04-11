# MOP Machinery — NOC Procedure Generation Pipeline

> Industrialise la génération de fiches d'intervention NOC (MetroConnect/OTN) à partir de données brutes, via deux voies d'authoring (n8n + Typebot) et deux moteurs de rendu (Gotenberg HTML + Carbone ODT), le tout callable en CLI et exploitable offline via fichier Excel+macro.

**Date:** 2026-04-11
**Statut:** Draft → à faire valider
**Scope:** Phase 1 (machinerie de génération). Phase 2 (ingestion regex d'historique mails) sera spécifiée séparément.

---

## 1. Problème

Le technicien NOC reçoit un mail d'incident (alarme + description + périmètre), doit parcourir un arbre décisionnel stable (supervision Vizi → périmètre → vérifications site distant / astreinte mainteneur / opérateur) et appliquer une procédure (MOP) avec 5-6 sous-procédures récurrentes. Aujourd'hui tout est manuel. On cherche :

1. Une **machinerie** (plumbing) qui prend des données d'incident brutes + un choix de périmètre et produit une MOP PDF soignée, repérée dans un index.
2. Deux voies d'authoring du flux décisionnel en parallèle (**n8n** pour la version Ops tout-de-suite, **Typebot** pour un drag-and-drop visuel plus expressif).
3. Deux moteurs de rendu en parallèle (**Gotenberg HTML/CSS** si un template Canva → HTML fait mieux, **Carbone ODT** si le user préfère WYSIWYG LibreOffice).
4. Les deux moteurs **callables en CLI** directement (pas seulement depuis n8n/Typebot).
5. Une **zone REX** dans le template (incidents récurrents 2-3 ans → aider les techniciens avec causes racines/pièges).
6. **Aucun site web**. Les PDF vont dans un répertoire, accompagnés d'un fichier Excel + macro VBA de recherche par mots-clés.
7. Déploiement sur Sese-AI (OVH 8 GB, amd64) **via Tailscale**, derrière Caddy VPN-only, conforme aux conventions VPAI.

**Contrainte utilisateur :** en retard sur un projet pro ; la machinerie doit être en service vite (matinée). Le contenu des MOP est écrit par le user, pas par le système.

---

## 2. Architecture à haut niveau

```
        ┌─────────────────────────────────────────────────────┐
        │                      SESE-AI                        │
        │                                                      │
        │  ┌──────────┐      ┌────────────┐     ┌───────────┐ │
        │  │ Gotenberg│      │  Carbone   │     │  Typebot  │ │
        │  │ :3000    │      │  :4000     │     │  builder  │ │
        │  │ HTML→PDF │      │  ODT→PDF   │     │  +viewer  │ │
        │  └────┬─────┘      └─────┬──────┘     └─────┬─────┘ │
        │       │                  │                   │      │
        │       └──────┬───────────┘                   │      │
        │              │                               │      │
        │         ┌────┴────┐                          │      │
        │         │   n8n   │◄──── appels HTTP ────────┘      │
        │         │  (voie  │                                  │
        │         │    A)   │                                  │
        │         └────┬────┘                                  │
        │              │                                       │
        │              ▼                                       │
        │  /opt/vpai/data/mop/                                 │
        │    ├── index/mops-index.csv   (flock append)         │
        │    ├── pdf/MOP-YYYY-NNNN.pdf  (sortie)               │
        │    └── templates/                                    │
        │        ├── mop.html + mop.css                        │
        │        └── mop.odt                                   │
        └─────────────────────────────────────────────────────┘
                           │
                           │ Tailscale
                           ▼
                     ┌──────────────┐
                     │ Waza (user)  │
                     │  • scp PDFs  │
                     │  • Excel +   │
                     │    macro VBA │
                     └──────────────┘
```

Les trois nouveaux conteneurs sont attachés aux réseaux existants (`backend` interne pour le dialogue inter-services, `frontend` pour Caddy → Typebot uniquement). **Gotenberg et Carbone ne sont jamais exposés publiquement** : seuls Typebot builder/viewer passent par Caddy VPN-only.

---

## 3. Composants

### 3.1 Moteur de rendu #1 — Gotenberg (HTML/CSS → PDF)

- **Image pinnée :** `gotenberg/gotenberg:8.30.1` (release 2026-04-06, multi-arch)
- **Port interne :** 3000, exposé uniquement sur `backend`
- **Endpoint unique :** `POST /forms/chromium/convert/html` multipart
  - `index.html` (obligatoire, plat)
  - `mop.css`, `logo.svg`, `icons/*.svg` (assets plats)
  - options : `printBackground=true`, `marginTop/Bottom=0.5in`, etc.
- **Hyperliens** : préservés par Chromium → les liens internes `SP-01`, `SP-02` vers d'autres MOP fonctionnent en PDF.
- **Limites** : `mem_limit: 1g`, `cpus: 1.0`. Chromium se recycle tous les 100 renders.
- **Healthcheck** : `wget -qO- http://127.0.0.1:3000/health`

### 3.2 Moteur de rendu #2 — Carbone (ODT → PDF)

- **Image pinnée :** `carbone/carbone-ee:full-4.26.3` (release 2026-04-09, 262 MB, LibreOffice inclus, multi-arch)
- **Port interne :** 4000, exposé uniquement sur `backend`
- **Licence :** Carbone Enterprise Edition image, **utilisable gratuitement en self-hosted interne sans `CARBONE_EE_LICENSE`** (les features EE — barcodes, charts, dynamic images — restent désactivées, ce qui nous suffit). Pas de phone-home. Usage interne d'entreprise = OK ; interdit uniquement de revendre en SaaS concurrent de Carbone Cloud.
- **API (3 étapes) :**
  1. `POST /template` multipart `template=@mop.odt` → retourne `templateId` (UUID stable, persisté sur disque dans `/app/template`).
  2. `POST /render/{templateId}` JSON `{ "data": {...}, "convertTo": "pdf", "converter": "L" }` → retourne `renderId`.
  3. `GET /render/{renderId}` → binaire PDF. En self-hosted, les renders persistent dans `/app/render` jusqu'au redémarrage du conteneur ; pas de limite "1h / download once" (celle-ci est propre au Carbone Cloud SaaS). Notre pattern reste "fetch immédiat après render" par hygiène.
- **Syntaxe template ODT :** `{d.field}`, `{d.status:ifEQ(major):show(MAJEUR):elseShow(mineur)}`, loops `{d[i].field} ... {d[i+1].field}`.
- **Limites** : `mem_limit: 1.5g` (LibreOffice subprocess par render).
- **Template storage** : volume `/app/template` → `/opt/vpai/data/carbone/template`. Volume `/app/render` → `/opt/vpai/data/carbone/render`.
- **Healthcheck** : `curl -s http://127.0.0.1:4000/status`.
- **Invalidation templateId** : le post-task Ansible stocke un hash SHA256 du `mop.odt` source à côté de `template-id.txt`. À chaque run du playbook, si le hash diffère, ré-upload et réécriture des deux fichiers. Sinon skip (idempotent).

### 3.3 Authoring #1 — n8n (voie A, ops direct)

- **Utilise n8n 2.7.3** déjà déployé. VPAI a `NODE_FUNCTION_ALLOW_BUILTIN=fs,path,crypto,child_process,http` dans `n8n.env.j2` → les Code nodes peuvent invoquer `child_process.execSync()` directement, ce qui dispense d'`Execute Command` (dont la disponibilité varie selon versions).
- **Pattern :** `Form Trigger` → plusieurs `Form` nodes (pages) → `IF/Switch` entre pages pour incarner l'arbre décisionnel → `Set` node (aggrégation des champs collectés sur N pages) → **2 branches de rendu** :
  - Branche Gotenberg : `Code` node (template literal JS remplissant `mop.html` depuis le JSON) → `HTTP Request` POST multipart Gotenberg → reçoit binaire.
  - Branche Carbone : `HTTP Request` POST JSON `/render/{templateId}` → `HTTP Request` GET `/render/{renderId}` → reçoit binaire.
- **Sortie** : `Form` node `operation: completion` avec `respondWith: returnBinary, inputDataFieldName: data` → **PDF téléchargé directement par le navigateur du technicien**.
- **Allocation ID + index CSV (atomique)** : un `Code` node invoque `execSync('/scripts/mop/alloc-and-append.sh', { input: JSON.stringify(payload) })` avant le rendu. Le helper bash (mounté depuis l'hôte en RO dans n8n à `/scripts/mop/`) fait : `flock -x /data/mop/index/.lock` → lit le dernier ID `MOP-YYYY-NNNN` du CSV → incrémente → append la nouvelle ligne → imprime le nouvel ID sur stdout. Tout se passe sous un seul verrou, **la race condition lire-incrémenter-écrire est éliminée**. Le même helper est utilisé par les CLI wrappers et par le webhook Typebot — **source unique de vérité** pour l'allocation d'ID et l'index.
- **Volume monté** : le bloc compose n8n dans `docker-stack/templates/docker-compose.yml.j2` DOIT ajouter :
  ```yaml
  - /opt/{{ project_name }}/data/mop:/data/mop
  - /opt/{{ project_name }}/scripts/mop:/scripts/mop:ro
  ```
- **Choix du moteur** : dropdown en page 1 (`engine = gotenberg|carbone`), `Switch` node derrière.
- **Error handling** : chaque `HTTP Request` de rendu a un `IF` downstream sur `$response.statusCode === 200`. Si KO → `Write Binary File` déposé dans `/data/mop/dead-letter/{id}.json` + `HTTP Request` Telegram alert (réutilise le canal budget existant) + `Form` completion avec message d'erreur clair au technicien. Pas de ligne CSV orpheline : le helper bash ne valide la ligne que sur succès final (voir `alloc-and-append.sh` : allocate retourne l'ID en phase 1, confirm-append en phase 2 après succès rendu).
- **Export versionné** : `scripts/n8n-workflows/mop-generator-v1.json`.

### 3.4 Authoring #2 — Typebot (voie B, drag-and-drop visuel)

- **Images pinnées :**
  - `baptistearno/typebot-builder:3.16.1`
  - `baptistearno/typebot-viewer:3.16.1`
- **Subdomaines :** `mop-build.<domain>` (builder) et `mop.<domain>` (viewer), **les deux VPN-only** via Caddy avec le snippet `(vpn_only)` existant, qui injecte automatiquement les 2 CIDRs (`caddy_vpn_cidr` + `caddy_docker_frontend_cidr`). **Ne jamais** écrire une règle `not client_ip` inline — piège VPAI documenté.
- **DB :** nouvelle database `typebot` sur le cluster PG existant, provisionnée via le pattern VPAI standard (rôle rend un script `provision-typebot-db.sh.j2` depuis `templates/`, puis `ansible.builtin.command` l'exécute avec `changed_when` basé sur un marqueur idempotent). Mot de passe user `typebot` = `{{ postgresql_password }}` (convention VPAI partagée).
- **Auth :** SMTP magic link uniquement. **Piège connu** : plusieurs issues GitHub sur la fiabilité SMTP en self-hosted. Mitigation : tester dès le premier déploiement ; fallback = insérer l'utilisateur directement en base PG (table `user`, session via NEXTAUTH_SECRET) si SMTP ko.
- **Flux** : chaque étape de l'arbre décisionnel = un bloc Typebot (Set Variable, Condition, Text Input, HTTP Request). Le bloc final = HTTP Request POST vers le webhook n8n `POST /webhook/mop/render` (pas directement Gotenberg/Carbone — simplifie la logique et factorise le rendu côté n8n).
- **Sortie** : Typebot n'a **pas** de file-download block natif. Stratégie :
  1. Typebot appelle `POST https://<n8n_host>/webhook/mop/render` avec le JSON consolidé.
  2. Le webhook n8n appelle Gotenberg/Carbone, écrit le PDF dans `/opt/vpai/data/mop/pdf/MOP-YYYY-NNNN.pdf`, allocue l'ID via `alloc-and-append.sh`, et retourne **une URL HTTPS VPN-only** du type `https://mop-dl.<domain>/pdf/MOP-YYYY-NNNN.pdf`.
  3. Typebot affiche cette URL dans un Text bubble final (cliquable par le technicien dans son navigateur, sur VPN).
- **Caddy route `mop-dl.<domain>`** : nouvelle route VPN-only servant statiquement `/opt/vpai/data/mop/pdf/` via `file_server` Caddy. Pas de listing, `file_server browse off`. Même snippet `(vpn_only)`.
- **Pas d'URL `file://`** : exclu explicitement (l'ancienne idée était une erreur). Tout passe par HTTPS VPN-only.
- **Versionnage** : export JSON manuel depuis l'UI Typebot → committé dans `scripts/typebot/mop-generator-v1.json`. Import = création d'un nouveau bot (pas de mise à jour in-place).

### 3.5 Templates MOP

**Maîtrisés par le user**, livrés en version bootstrap neutre :

- `roles/mop-templates/files/mop.html` — template HTML responsive A4 print, typographie claire, en-tête, métadonnées incident, arbre décisionnel, étapes numérotées, **zone REX** (3 colonnes : causes fréquentes / pièges / temps moyen), pied de page avec contacts d'escalade.
- `roles/mop-templates/files/mop.css` — feuille de style print imprimable, palette sobre, `@page { size: A4; margin: 1.5cm }`.
- `roles/mop-templates/files/mop.odt` — équivalent ODT (éditable LibreOffice WYSIWYG) avec placeholders `{d.xxx}` alignés sur la même structure JSON.
- `roles/mop-templates/files/contacts.yml` — annuaire placeholder (sites TH3/TH2/LF, mainteneurs Ribbon + IT supervision, opérateurs voie TH/LF + OOB, templates emails accusé/clôture). Toutes les valeurs = `"{{ À REMPLIR }}"`.

**Schéma JSON unique** (consommé identiquement par Gotenberg et Carbone) :

```json
{
  "type": "mop_principal",
  "id": "MOP-2026-0042",
  "title": "Alarme LOS voie TH site TH2",
  "keywords": ["los", "voie-th", "th2", "lien", "optique"],
  "perimeter": "lien_optique_prod",
  "severity": "major",
  "incident": {
    "ticket": "INC-12345",
    "date": "2026-04-11T14:30:00",
    "equipment": "Ribbon-xxx",
    "site": "TH2",
    "raw_email_subject": "...",
    "raw_email_body": "..."
  },
  "steps": [
    {"n": 1, "title": "Confirmer l'alarme sur Vizi", "desc": "...", "link_sp": "SP-01"},
    {"n": 2, "title": "Vérifier état de la carte", "desc": "...", "link_sp": "SP-02"}
  ],
  "rex": {
    "similar_cases_count": 12,
    "root_causes": ["fibre débranchée", "transceiver SFP défectueux", "coupure OLP"],
    "pitfalls": ["ne pas redémarrer avant validation distant", "vérifier OOB en parallèle"],
    "mean_resolution_time": "1h20"
  },
  "escalation": {
    "primary_contact": "op-th-a",
    "fallback": "mainteneur-ribbon",
    "coordinator_site_distant": "TH2"
  }
}
```

### 3.6 CLI wrappers

Deux scripts bash dans `scripts/mop/` livrés par le playbook :

- **`scripts/mop/mop-render-html`** — lit un JSON sur stdin ou en arg, génère `index.html` via `jinja2-cli` (rempli depuis `mop.html.j2`), POST multipart vers Gotenberg, écrit le PDF dans `-o output.pdf`. Append la ligne CSV index via `flock`.
- **`scripts/mop/mop-render-odt`** — lit un JSON, POST `/render/{templateId}` vers Carbone (templateId stable stocké dans `/opt/vpai/data/carbone/template-id.txt`), GET le render, écrit le PDF. Append CSV.

Exemples :

```bash
# Gotenberg
cat incident.json | scripts/mop/mop-render-html -o /tmp/MOP-2026-0042.pdf

# Carbone
scripts/mop/mop-render-odt incident.json -o /tmp/MOP-2026-0042.pdf
```

Les deux scripts sont idempotents et font le append CSV avec `flock` pour éviter toute corruption sous concurrence.

### 3.7 Index CSV + Excel macro

- **Fichier** : `/opt/vpai/data/mop/index/mops-index.csv` (séparateur `;`, encoding UTF-8 BOM pour Excel).
- **Schéma** :
  ```
  id;title;keywords;severity;perimeter;filename;sub_procs;created_at
  MOP-2026-0001;"LOS voie TH TH2";"los;voie-th;th2";major;lien_prod;MOP-2026-0001.pdf;SP-01,SP-02;2026-04-11T14:35
  ```
- **Excel .xlsm** : `scripts/mop/mop-search.xlsm` — deux feuilles : `index` (lien live vers le CSV via Power Query) + `recherche` (cellule mot-clé + macro VBA qui filtre lignes et propose le chemin PDF à ouvrir).
- **Distribution** : le user rapatrie le CSV + les PDFs via `rsync` ou `scp` sur son poste bureau cible, et ouvre l'Excel qui pointe sur le CSV local.

---

## 4. Rôles Ansible à créer

Convention VPAI : chaque nouveau service = 1 rôle minimal (dirs + env + handler) + un bloc service dans `roles/docker-stack/templates/docker-compose.yml.j2` + image pinnée dans `versions.yml`.

### 4.1 `roles/gotenberg/`

- `defaults/main.yml` — `gotenberg_config_dir`, `gotenberg_memory_limit: "1g"`, `gotenberg_cpu_limit: "1.0"`.
- `tasks/main.yml` — crée les dirs `/opt/vpai/configs/gotenberg`, `/opt/vpai/data/mop/pdf`, `/opt/vpai/data/mop/index`. Pas d'env file (Gotenberg se pilote via CLI args dans docker-compose).
- `handlers/main.yml` — `Restart gotenberg stack` (pattern VPAI `state: present, recreate: always`).
- Pas de template (conf zéro, tout en args dans compose).
- **Bloc compose** ajouté à `docker-compose.yml.j2` : image, restart, `cap_drop: ALL + cap_add: [CHOWN, SETGID, SETUID]`, `networks: [backend]`, `read_only: true, tmpfs: [/tmp]`, limites, healthcheck.

### 4.2 `roles/carbone/`

- `defaults/main.yml` — `carbone_config_dir`, `carbone_data_dir`, `carbone_memory_limit: "1.5g"`.
- `tasks/main.yml` — crée les dirs, monte `/opt/vpai/data/carbone/template` et `/opt/vpai/data/carbone/render` (UID 1000).
- `handlers/main.yml` — `Restart carbone stack`.
- **Bloc compose** : image, `networks: [backend]`, volumes persistants, limites, healthcheck `curl /status`.
- **Capabilities** : LibreOffice headless a besoin de plus que le minimum strict. Config VPAI : `cap_drop: ALL` + `cap_add: [CHOWN, SETUID, SETGID, DAC_OVERRIDE, FOWNER]`. `DAC_OVERRIDE`/`FOWNER` sont la convention VPAI pour tout service qui écrit dans ses volumes persistants (même pattern que NocoDB).
- **Post-task idempotent** (upload + hash SHA256) :
  1. Calculer `sha256sum mop.odt` → comparer au contenu de `/opt/vpai/data/carbone/template-hash.txt`.
  2. Si hash identique ET `template-id.txt` existe → skip (changed: false).
  3. Sinon → curl `POST /template` → écrire le nouveau `templateId` dans `template-id.txt` → écrire le nouveau hash dans `template-hash.txt`. Les deux fichiers sont réécrits atomiquement (même task block). Changed: true.

### 4.3 `roles/typebot/`

- `defaults/main.yml` — `typebot_config_dir`, `typebot_db_name: "typebot"`, subdomaines, limites.
- `tasks/main.yml` — crée dirs, dépose `typebot.env.j2` (ENCRYPTION_SECRET, **NEXTAUTH_SECRET**, NEXTAUTH_URL, SMTP_HOST, SMTP_USER, SMTP_PASSWORD, DATABASE_URL), s'assure de la DB PG via `provision-postgresql.sh.j2`.
- `templates/typebot.env.j2` — tous les secrets via `{{ typebot_xxx }}` lus depuis `secrets.yml` (vault).
- `handlers/main.yml` — `Restart typebot stack` (recreate: always pour env_file).
- **Blocs compose** : `typebot-builder` et `typebot-viewer`, chacun sur `backend` + `frontend` (Caddy accède via frontend).
- **Bloc Caddy** : 3 nouvelles routes — `mop-build.<domain>` (builder), `mop.<domain>` (viewer), **et `mop-dl.<domain>`** (file_server statique vers `/opt/vpai/data/mop/pdf/`, `browse off`), **les trois** avec le snippet `(vpn_only)` VPAI (2 CIDRs : `caddy_vpn_cidr` + `caddy_docker_frontend_cidr`). La route `mop-dl.<domain>` est servie par Caddy directement (pas de conteneur), montage `/opt/vpai/data/mop/pdf` en RO dans le conteneur Caddy.

### 4.4 `roles/mop-templates/`

- Pas de service Docker. Rôle de distribution de templates et scripts CLI.
- `files/mop.html`, `mop.css`, `mop.odt`, `contacts.yml`, `contacts.yml.example`.
- `files/mop-render-html`, `mop-render-odt`, `alloc-and-append.sh` (scripts bash exécutables).
- `tasks/main.yml` :
  1. Installe `jinja2-cli` et `pyyaml` via `ansible.builtin.pip` (user-level, pas root-global) — dépendance des CLI wrappers HTML.
  2. Installe `flock` (paquet `util-linux`, déjà présent sur Debian 13 de base mais asserté idempotent).
  3. Copie les templates vers `/opt/vpai/data/mop/templates/` (mode `"0644"`).
  4. Copie `alloc-and-append.sh` vers `/opt/vpai/scripts/mop/alloc-and-append.sh` (mode `"0755"`) — monté RO dans n8n à `/scripts/mop/`.
  5. Copie les CLI wrappers `mop-render-html` / `mop-render-odt` vers `/usr/local/bin/` (mode `"0755"`).
  6. Crée les dirs `/opt/vpai/data/mop/{pdf,index,dead-letter}` (mode `"0755"`, owner UID 1000).
  7. Initialise `/opt/vpai/data/mop/index/mops-index.csv` avec l'en-tête si absent (idempotent : `creates:` guard).

### 4.5 Ajouts à `versions.yml`

```yaml
gotenberg_image: "gotenberg/gotenberg:8.30.1"
carbone_image: "carbone/carbone-ee:full-4.26.3"
typebot_builder_image: "baptistearno/typebot-builder:3.16.1"
typebot_viewer_image: "baptistearno/typebot-viewer:3.16.1"
```

### 4.6 Ajouts à `playbooks/site.yml`

Phase 3 (applications), après `nocodb` :

```yaml
- role: gotenberg
  tags: [gotenberg, phase3]
- role: carbone
  tags: [carbone, phase3]
- role: typebot
  tags: [typebot, phase3]
- role: mop-templates
  tags: [mop-templates, phase3]
```

### 4.7 Secrets à ajouter à `secrets.yml` (vault)

```yaml
vault_typebot_encryption_secret: "<32 char random base64>"
vault_typebot_nextauth_secret: "<32 char random base64>"
vault_typebot_smtp_host: "..."
vault_typebot_smtp_port: 587
vault_typebot_smtp_user: "..."
vault_typebot_smtp_password: "..."
vault_typebot_smtp_from: "..."
vault_typebot_admin_email: "..."
```

`vault_typebot_nextauth_secret` est **indispensable** : sans lui, Typebot génère une clé random à chaque redémarrage et invalide toutes les sessions existantes. Il sert aussi à signer manuellement un cookie de session si SMTP tombe (fallback documenté §3.4).

(À remplir par le user via `ansible-vault edit`.)

---

## 5. Flux de données — Voie A n8n détaillé

```
  ┌─────────────────────────────────────────────────────┐
  │ 1. Form Trigger "MOP Generator"                     │
  │    Page 1:                                          │
  │     - ticket_id (text)                              │
  │     - subject (text)                                │
  │     - raw_email (textarea)                          │
  │     - engine (dropdown: gotenberg | carbone)        │
  │     - severity (dropdown: minor|major|critical)     │
  │                                                     │
  │ 2. Form page 2: Périmètre                           │
  │     - perimeter (dropdown: lien_optique_prod,       │
  │                             equipment_prod,         │
  │                             site_distant,           │
  │                             oob_supervision,        │
  │                             lightsoft_mgmt,         │
  │                             alimentation)           │
  │                                                     │
  │ 3. Switch (sur perimeter) → 1 branche par périmètre │
  │                                                     │
  │ 4. Form pages 3..N (spécifiques au périmètre)       │
  │    Ex: si lien_optique_prod → voie (TH|LF),         │
  │                              site (TH3|TH2|LF),     │
  │                              carte (transport|SFP|  │
  │                                      OLP),          │
  │                              steps_to_execute       │
  │                                                     │
  │ 5. Merge/Set → JSON consolidé (schéma §3.5)         │
  │                                                     │
  │ 6. Code node (phase 1 : allocate-only)              │
  │    execSync('/scripts/mop/alloc-and-append.sh',     │
  │      ['allocate'], { input: JSON.stringify(json) }) │
  │    → retourne id MOP-YYYY-NNNN sur stdout           │
  │    Sous flock -x /data/mop/index/.lock              │
  │                                                     │
  │ 7. IF engine == gotenberg                           │
  │    → Code: remplir mop.html via template literal    │
  │    → HTTP Request: multipart POST Gotenberg         │
  │      http://gotenberg:3000/forms/chromium/convert/  │
  │        html                                          │
  │    → Binary data reçue                              │
  │                                                     │
  │    ELSE (engine == carbone)                         │
  │    → HTTP Request: POST http://carbone:4000/render/ │
  │       {{ $env.CARBONE_TEMPLATE_ID }}                │
  │    → HTTP Request: GET .../render/{renderId}        │
  │    → Binary data reçue                              │
  │                                                     │
  │ 8. IF statusCode == 200                             │
  │    → Write Binary File → /data/mop/pdf/{id}.pdf     │
  │    → Code node (phase 2 : confirm-append)           │
  │      execSync('/scripts/mop/alloc-and-append.sh',   │
  │        ['confirm', id], { input: meta })            │
  │      → commit de la ligne CSV sous flock            │
  │    ELSE                                             │
  │    → Write Binary File → /data/mop/dead-letter/     │
  │      {id}.json                                      │
  │    → HTTP Request Telegram alert                    │
  │    → Code node execSync('alloc-and-append.sh rollback
  │      ', id) libère l'ID (ou marque abandoned)       │
  │    → Form completion avec message erreur            │
  │                                                     │
  │ 9. Form completion: respondWith=returnBinary,       │
  │     inputDataFieldName=data                         │
  │    → le PDF est téléchargé par le navigateur        │
  └─────────────────────────────────────────────────────┘
```

**Note sur `alloc-and-append.sh`** : il a 3 sous-commandes (`allocate`, `confirm`, `rollback`), toutes prenant un verrou `flock -x /data/mop/index/.lock` de durée ms. Le CSV final ne contient que les lignes confirmées. Les IDs alloués mais non confirmés sont trackés dans `.pending` (fichier plat) — purge au démarrage ou après 1h. Même exécutable partagé par n8n (via volume RO), CLI wrappers, et webhook Typebot (via execSync dans un Code node n8n upstream du rendu).

---

## 6. Sécurité et conventions VPAI

- **Tous services** sur `backend` (interne), seul Typebot exposé via `frontend` → Caddy VPN-only.
- **cap_drop: ALL** + `cap_add` minimal (CHOWN/SETGID/SETUID si besoin fichiers).
- **read_only: true** pour Gotenberg (tmpfs /tmp), Carbone a besoin de `/app/template` et `/app/render` en RW.
- **Pas de `:latest`** — toutes images pinnées.
- **Handlers** : `state: present, recreate: always` (pattern env_file VPAI).
- **Healthchecks** sur les 3 services.
- **Shell tasks** : `set -euo pipefail`, `executable: /bin/bash`, FQCN Ansible.
- **Caddy ACL** : snippet `(vpn_only)` avec 2 CIDRs obligatoires (VPN + Docker frontend bridge) — règle critique VPAI.
- **Secrets** : jamais en clair, tous dans `secrets.yml` vault.

---

## 7. Tests E2E

Matrice à valider sur Sese-AI après déploiement :

| # | Voie | Moteur | Attendu |
|---|------|--------|---------|
| 1 | n8n  | Gotenberg | PDF téléchargé + ligne CSV + hyperliens SP-* cliquables |
| 2 | n8n  | Carbone   | PDF téléchargé + ligne CSV + REX zone rendue |
| 3 | Typebot | Gotenberg | URL PDF cliquable (`https://mop-dl...`) en fin de flow + ligne CSV |
| 4 | Typebot | Carbone   | URL PDF cliquable + ligne CSV |
| 5 | CLI  | Gotenberg | `mop-render-html < input.json` → PDF disque + CSV |
| 6 | CLI  | Carbone   | `mop-render-odt input.json` → PDF disque + CSV |
| 7 | Concurrence haute | — | 10 générations parallèles via `seq 10 \| xargs -P10 -I{} mop-render-html` → 10 IDs distincts séquentiels, 10 lignes CSV, 0 collision, 0 ligne tronquée (assertion `wc -l` + `awk` d'unicité) |
| 8 | JSON malformé | CLI | stdin JSON invalide → exit non-zéro, PDF non créé, pas de ligne CSV, pas d'ID alloué (pending vide) |
| 9 | Gotenberg 500 / down | n8n | Render échoue → pas de ligne CSV, fichier `dead-letter/{id}.json` créé, alert Telegram envoyée, ID rollback |
| 10 | Carbone OOM | n8n | Render tue LibreOffice → même chemin dead-letter que #9 |
| 11 | ODT template modifié | Ansible rerun | Re-run du playbook après édition `mop.odt` → hash diffère → re-upload → nouveau `templateId` → `template-id.txt` mis à jour |
| 12 | ODT template inchangé | Ansible rerun | Re-run du playbook sans modification → hash identique → skip (changed: false) |
| 13 | Typebot SMTP down | Typebot | Magic link non reçu → fallback documenté (insert direct user en PG) fonctionne, session créée via NEXTAUTH_SECRET |
| 14 | Disk full `/data/mop/pdf` | CLI | `df` full → error clair, pas de ligne CSV partielle (phase confirm skip sur I/O error) |
| 15 | Excel macro | — | Recherche "los" → liste MOP pertinents avec chemin PDF |
| 16 | Caddy ACL | — | Depuis hors-VPN : `curl https://mop-dl.<domain>/pdf/` → 403. Depuis VPN : 200 + PDF téléchargé |

---

## 8. Décisions / Arbitrages

| Sujet | Décision | Pourquoi |
|-------|----------|----------|
| 2 moteurs de rendu | Gotenberg + Carbone en parallèle | User veut comparer et garder les deux (WYSIWYG vs HTML) |
| 2 voies authoring | n8n + Typebot en parallèle | Explicitement demandé |
| Pas de site web | Aucun hôte public, tout VPN ou offline | Explicitement demandé |
| Index CSV flock | Helper bash `alloc-and-append.sh` sous flock, appelé depuis n8n Code `execSync`, CLI wrappers, et webhook Typebot (source unique de vérité) | CSV doit être un vrai fichier, consommable par Excel offline ; race condition read-increment-write éliminée par un seul verrou ; pas de dépendance à un node n8n `Execute Command` dont la disponibilité varie |
| Typebot PDF delivery canal | Route Caddy `mop-dl.<domain>` file_server RO VPN-only | Typebot n'a pas de file-download block natif ; HTTPS VPN-only préféré à `file://` (navigateur refuse) |
| Schéma JSON unique | Un seul schéma pour les 2 moteurs | Évite divergence et facilite migration d'un moteur à l'autre |
| Template owner | User écrit le contenu, la machinerie livre juste le plumbing | Explicitement demandé |
| Zone REX | Bloc dédié dans le template | Incidents récurrents 2-3 ans |
| Annuaire contacts | Placeholder `contacts.yml` versionné avec `"{{ À REMPLIR }}"` | User comble lui-même |
| Typebot PDF delivery | URL via webhook n8n (pas de file download natif) | Limitation Typebot, workaround idiomatique |
| Phase 2 (ingestion mails) | Spec séparée, 100% regex, aucun LLM | Données confidentielles |

---

## 9. Anti-pièges anticipés

| Risque | Mitigation |
|--------|-----------|
| ~~Carbone render URL valide 1h, téléchargeable 1 fois~~ | **Comportement SaaS Cloud uniquement** ; en self-hosted, fetch immédiat après `POST /render` reste la bonne hygiène |
| n8n Form ne sait pas append CSV nativement | Code node + `execSync('/scripts/mop/alloc-and-append.sh')` (VPAI active `NODE_FUNCTION_ALLOW_BUILTIN=fs,child_process`) |
| Race condition ID allocation (read-increment-write) | Tout passe sous `flock -x` dans `alloc-and-append.sh` — atomique par nature, une seule source de vérité partagée n8n/CLI/Typebot |
| Ligne CSV orpheline si rendu échoue | Phase allocate (réserve ID en `.pending`) → phase confirm après succès rendu → phase rollback sur erreur ; seule la confirm écrit dans le CSV |
| Typebot SMTP magic link peu fiable en self-hosted | Tester dès J1 ; fallback = insert user direct en PG avec `NEXTAUTH_SECRET` stable (sinon sessions invalidées à chaque restart) |
| Typebot PDF delivery (pas de download block) | Webhook n8n → retourne URL `https://mop-dl.<domain>/pdf/{id}.pdf` → Caddy file_server VPN-only |
| Typebot `file://` URL | **Exclu** : navigateurs bloquent `file://` depuis origin HTTPS. Utiliser HTTPS VPN-only |
| Caddy VPN ACL oublie 1 des 2 CIDRs sur nouvelles routes | Utiliser le snippet `(vpn_only)` existant, pas de règles inline |
| Gotenberg Chromium recycle tous les 100 renders | Pas un problème en pratique ; documenter dans runbook |
| `{{.Names}}` Jinja collision en commandes Ansible | Scripts bash hors templates, pas d'échappement nécessaire |
| Handler env_file `state: restarted` ne recharge pas | `state: present, recreate: always` (convention VPAI documentée) |
| UID/GID volumes Carbone | Mount UID 1000 comme NocoDB (pattern VPAI) |
| Carbone capabilities insuffisantes pour LibreOffice | `cap_add: [CHOWN, SETUID, SETGID, DAC_OVERRIDE, FOWNER]` (convention VPAI pour services qui écrivent dans volumes) |
| Template `mop.odt` stale après édition | Post-task compare SHA256 `mop.odt` ↔ `template-hash.txt` ; si différent → re-upload + réécriture atomique des 2 fichiers |
| n8n Code node ne voit pas l'host filesystem | Volume mount explicite dans `docker-compose.yml.j2` n8n : `/opt/{{project_name}}/data/mop:/data/mop` + `/opt/{{project_name}}/scripts/mop:/scripts/mop:ro` |

---

## 10. Livrables

Les 4 vagues d'implémentation seront détaillées dans le plan (étape suivante, skill `writing-plans`) :

1. **Vague 1 — Rôles Ansible** : `gotenberg`, `carbone`, `typebot`, `mop-templates` + maj `docker-stack/templates/docker-compose.yml.j2` + `versions.yml` + `playbooks/site.yml` + `secrets.yml` (clés vault).
2. **Vague 2 — Templates + CLI** : `mop.html`, `mop.css`, `mop.odt`, `contacts.yml`, scripts `mop-render-html`, `mop-render-odt`.
3. **Vague 3 — Workflows** : `scripts/n8n-workflows/mop-generator-v1.json`, `scripts/typebot/mop-generator-v1.json`, webhook n8n `POST /webhook/mop/render` pour Typebot.
4. **Vague 4 — Index + Excel** : `scripts/mop/mops-index.csv` (schéma + 1 ligne exemple), `scripts/mop/mop-search.xlsm` avec macro VBA.

Puis **déploiement via Tailscale** (`make deploy-role ROLE=gotenberg/carbone/typebot/mop-templates ENV=prod`), **import n8n/Typebot**, **E2E matrice §7**.

---

## 11. Phase 2 (future spec séparée)

Ingestion regex-only (confidentialité) de l'historique mails + fichiers Excel pour enrichir la zone REX des templates. Calibrage sur un fil mail type fourni par le user. Zéro LLM. À specifier après stabilisation de la Phase 1.

---

## 12. Validation & prochaine étape

Cette spec est rédigée sur base :
- des trois agents de recherche (Gotenberg 8.30.1, Carbone 4.26.3 community, Typebot 3.16.1) dont les sorties sont dans `.planning/research/mop-{gotenberg-n8n,carbone,typebot}.md` ;
- de l'inspection des conventions VPAI (rôle `nocodb`, `docker-stack`, `playbooks/site.yml`, `versions.yml`) ;
- d'une recherche Qdrant sans REX préexistant sur ces 3 composants.

Aucune supposition technique n'a été prise : chaque version, endpoint, syntaxe et limitation est sourcée.

**Prochaine étape :** invoquer le skill `writing-plans` pour produire un plan d'implémentation détaillé par vague.
