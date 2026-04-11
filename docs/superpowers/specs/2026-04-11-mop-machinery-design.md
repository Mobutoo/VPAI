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
- **Licence :** CCL (Carbone Community License) — self-hosting interne gratuit, pas de clé, pas de phone-home. Pas d'utilisation comme SaaS concurrent.
- **API (3 étapes) :**
  1. `POST /template` multipart `template=@mop.odt` → retourne `templateId` (UUID stable, persisté).
  2. `POST /render/{templateId}` JSON `{ "data": {...}, "convertTo": "pdf", "converter": "L" }` → retourne `renderId`.
  3. `GET /render/{renderId}` → binaire PDF (valide 1h, téléchargeable **une fois**).
- **Syntaxe template ODT :** `{d.field}`, `{d.status:ifEQ(major):show(MAJEUR):elseShow(mineur)}`, loops `{d[i].field} ... {d[i+1].field}`.
- **Limites** : `mem_limit: 1.5g` (LibreOffice subprocess par render).
- **Template storage** : volume `/app/template` → `/opt/vpai/data/carbone/template`.
- **Healthcheck** : `curl -s http://127.0.0.1:4000/status`.

### 3.3 Authoring #1 — n8n (voie A, ops direct)

- **Utilise n8n 2.7.3** déjà déployé.
- **Pattern :** `Form Trigger` → plusieurs `Form` nodes (pages) → `IF/Switch` entre pages pour incarner l'arbre décisionnel → `Merge/Set` (aggrégation des champs collectés sur N pages) → **2 branches de rendu** :
  - Branche Gotenberg : `Code` node (Jinja-like JS fill sur `mop.html`) → `HTTP Request` POST multipart Gotenberg → reçoit binaire.
  - Branche Carbone : `HTTP Request` POST JSON `/render/{templateId}` → GET `/render/{renderId}` → reçoit binaire.
- **Sortie** : `Form` node `operation: completion` avec `respondWith: returnBinary, inputDataFieldName: data` → **PDF téléchargé directement par le navigateur du technicien**.
- **Index CSV** : `Execute Command` node en parallèle → `flock -x /data/mop/index/.lock -c "echo '${CSV_ROW}' >> /data/mop/index/mops-index.csv"`. Le volume `/opt/vpai/data/mop/index` est monté dans n8n en lecture/écriture.
- **Choix du moteur** : dropdown en page 1 (`engine = gotenberg|carbone`), `Switch` node derrière.
- **Export versionné** : `scripts/n8n-workflows/mop-generator-v1.json`.

### 3.4 Authoring #2 — Typebot (voie B, drag-and-drop visuel)

- **Images pinnées :**
  - `baptistearno/typebot-builder:3.16.1`
  - `baptistearno/typebot-viewer:3.16.1`
- **Subdomaines :** `mop-build.<domain>` (builder) et `mop.<domain>` (viewer), **les deux VPN-only** via Caddy ACL standard VPAI (`{{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }}`).
- **DB :** nouvelle database `typebot` sur le cluster PG existant, provisionnée via `provision-postgresql.sh.j2`. Mot de passe : `{{ postgresql_password }}` (convention VPAI).
- **Auth :** SMTP magic link uniquement. **Piège connu** : plusieurs issues GitHub sur la fiabilité SMTP en self-hosted. Mitigation : tester dès le premier déploiement ; fallback = créer l'utilisateur directement en base si SMTP ko.
- **Flux** : chaque étape de l'arbre décisionnel = un bloc Typebot (Set Variable, Condition, Text Input, HTTP Request). Le bloc final = HTTP Request POST vers Gotenberg **ou** Carbone selon un chemin choisi en début de flux.
- **Sortie** : Typebot n'a **pas** de file-download block natif. Stratégie :
  1. n8n expose un webhook `POST /webhook/mop/render` qui accepte JSON, renvoie un URL court de téléchargement.
  2. Typebot appelle ce webhook et affiche l'URL dans un Text bubble final (cliquable).
  3. Le endpoint n8n écrit le PDF dans `/opt/vpai/data/mop/pdf/MOP-YYYY-NNNN.pdf` et renvoie l'URL `file://...` ou un chemin scp.
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
- **Post-task** : upload initial du template `mop.odt` via curl vers `/template` et persistance du `templateId` retourné dans `/opt/vpai/data/carbone/template-id.txt` (idempotent : si le fichier existe, skip).

### 4.3 `roles/typebot/`

- `defaults/main.yml` — `typebot_config_dir`, `typebot_db_name: "typebot"`, subdomaines, limites.
- `tasks/main.yml` — crée dirs, dépose `typebot.env.j2` (ENCRYPTION_SECRET, NEXTAUTH_URL, SMTP_HOST, SMTP_USER, SMTP_PASSWORD, DATABASE_URL), s'assure de la DB PG via `provision-postgresql.sh.j2`.
- `templates/typebot.env.j2` — tous les secrets via `{{ typebot_xxx }}` lus depuis `secrets.yml` (vault).
- `handlers/main.yml` — `Restart typebot stack` (recreate: always pour env_file).
- **Blocs compose** : `typebot-builder` et `typebot-viewer`, chacun sur `backend` + `frontend` (Caddy accède via frontend).
- **Bloc Caddy** : 2 nouvelles routes `mop-build.<domain>` et `mop.<domain>`, **les deux** avec le snippet `(vpn_only)` VPAI (2 CIDRs : `caddy_vpn_cidr` + `caddy_docker_frontend_cidr`).

### 4.4 `roles/mop-templates/`

- Pas de service Docker. Rôle de distribution de templates et scripts CLI.
- `files/mop.html`, `mop.css`, `mop.odt`, `contacts.yml`, `contacts.yml.example`.
- `files/mop-render-html`, `mop-render-odt` (scripts bash exécutables).
- `tasks/main.yml` — copie vers `/opt/vpai/data/mop/templates/` + `/usr/local/bin/mop-render-*` (mode `"0755"`).

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
vault_typebot_encryption_secret: "<32 char random>"
vault_typebot_smtp_host: "..."
vault_typebot_smtp_port: 587
vault_typebot_smtp_user: "..."
vault_typebot_smtp_password: "..."
vault_typebot_smtp_from: "..."
vault_typebot_admin_email: "..."
```

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
  │ 6. Code node → allouer id MOP-YYYY-NNNN             │
  │    (lire CSV, +1 sur max, formater)                 │
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
  │ 8. Write Binary File → /data/mop/pdf/{id}.pdf       │
  │                                                     │
  │ 9. Execute Command: append index CSV                │
  │    flock -x /data/mop/index/.lock -c "echo ..."     │
  │                                                     │
  │ 10. Form completion: respondWith=returnBinary,      │
  │      inputDataFieldName=data                        │
  │     → le PDF est téléchargé par le navigateur       │
  └─────────────────────────────────────────────────────┘
```

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
| 3 | Typebot | Gotenberg | URL PDF cliquable en fin de flow + ligne CSV |
| 4 | Typebot | Carbone   | URL PDF cliquable + ligne CSV |
| 5 | CLI  | Gotenberg | `mop-render-html < input.json` → PDF disque + CSV |
| 6 | CLI  | Carbone   | `mop-render-odt input.json` → PDF disque + CSV |
| 7 | Concurrence | — | 2 générations simultanées → CSV non corrompu (flock) |
| 8 | Excel macro | — | Recherche "los" → liste MOP pertinents avec chemin PDF |

---

## 8. Décisions / Arbitrages

| Sujet | Décision | Pourquoi |
|-------|----------|----------|
| 2 moteurs de rendu | Gotenberg + Carbone en parallèle | User veut comparer et garder les deux (WYSIWYG vs HTML) |
| 2 voies authoring | n8n + Typebot en parallèle | Explicitement demandé |
| Pas de site web | Aucun hôte public, tout VPN ou offline | Explicitement demandé |
| Index CSV flock | Execute Command + flock plutôt que NocoDB | CSV doit être un vrai fichier, consommable par Excel offline |
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
| Carbone render URL valide 1h, téléchargeable 1 fois | n8n récupère immédiatement après POST /render et stocke binaire |
| n8n Form ne sait pas append CSV nativement | Execute Command + flock sur volume monté |
| Typebot SMTP magic link peu fiable en self-hosted | Tester dès J1 ; fallback = insert user direct en PG |
| Caddy VPN ACL oublie 1 des 2 CIDRs sur nouvelles routes | Utiliser le snippet `(vpn_only)` existant, pas de règles inline |
| Gotenberg Chromium recycle tous les 100 renders | Pas un problème en pratique ; documenter dans runbook |
| Concurrence écriture CSV | `flock -x` obligatoire dans tous les appends (n8n + CLI) |
| `{{.Names}}` Jinja collision en commandes Ansible | Scripts bash hors templates, pas d'échappement nécessaire |
| Handler env_file `state: restarted` ne recharge pas | `state: present, recreate: always` (convention VPAI documentée) |
| UID/GID volumes Carbone | Mount UID 1000 comme NocoDB (pattern VPAI) |
| Template `mop.odt` première upload | Post-task idempotent : skip si `template-id.txt` existe |

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
