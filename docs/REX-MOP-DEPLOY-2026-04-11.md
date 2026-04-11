# REX — MOP Machinery v1.0 — Déploiement E2E — 2026-04-11

## Résumé

Déploiement complet de la stack MOP (Method Of Procedure) sur Sese-AI (javisi).
5 waves déployées, 8 tests E2E exécutés.

**Statut global : 8/8 PASS** (avec notes sur GOTENBERG_URL et permissions)

---

## Contexte

- **Environnement** : Sese-AI, OVH VPS 8 GB, Docker Compose
- **Stack déployée** : Gotenberg 8.30.1, Carbone 4.23.7, Typebot 3.16.1, n8n 2.7.3
- **Session précédente** : MOP1 (2026-04-11 matin) — n8n mop-generator-v1 + mop-webhook-render-v1 déployés et validés
- **Cette session** : Typebot flow, CSV, Excel, E2E tests

---

## Tests E2E

### Test #5 — CLI Gotenberg (HTML → PDF)

**Commande** :
```bash
GOTENBERG_URL=http://172.20.2.27:3000 mop-render-html /tmp/t.json -o /tmp/out.pdf
```

**Résultat** : PASS  
- `PDF document, version 1.4, 1 page(s)` — 33 378 bytes  
- ID alloué : MOP-2026-0019 → `/opt/javisi/data/mop/pdf/MOP-2026-0019.pdf`

**Note** : `GOTENBERG_URL` doit être setté à l'IP Docker interne (`172.20.2.27`) car port 3000 non exposé sur l'hôte. La valeur par défaut `localhost:3000` ne fonctionne pas hors container. **Correctif nécessaire** : soit exposer le port, soit ajuster la valeur par défaut dans le script.

---

### Test #6 — CLI Carbone (ODT → PDF)

**Commande** :
```bash
mop-render-odt /tmp/t.json -o /tmp/out.pdf
```

**Résultat** : PASS  
- `PDF document, version 1.7, 1 page(s)` — 29 654 bytes  
- ID alloué : MOP-2026-0020

**Note** : Carbone résout `http://carbone:3030` via Docker network — fonctionnel sans variable d'environnement supplémentaire.

---

### Test #7 — Concurrence (10 renders parallèles Gotenberg)

**Commande** :
```bash
for i in $(seq 1 10); do
  (cat /tmp/t.json | python3 -c "...ticket=TST-$i..." | \
   GOTENBERG_URL=http://172.20.2.27:3000 mop-render-html -o /tmp/conc-$i.pdf) &
done; wait
```

**Résultat** : PASS  
- 10/10 PDFs créés, chacun avec un ID unique (MOP-2026-0021 à MOP-2026-0030)  
- 28 IDs uniques dans le CSV (cumul toutes sessions)  
- Aucune collision d'ID (mécanisme lock/pending du alloc-and-append.sh fonctionne)

---

### Test #8 — JSON malformé (error handling)

**Commande** :
```bash
echo "not json" | mop-render-html -o /tmp/bad.pdf
```

**Résultat** : PASS  
- exit=5 (jq parse error), aucun PDF créé  
- Comportement attendu : fail-fast sur validation jq

---

### Test #9 — n8n Form → n8n Webhook → Gotenberg (happy path)

**Source** : Session MOP2, exec 11759 (2026-04-11 13:xx)

**Résultat** : PASS  
- `MOP-2026-0016.pdf` (32 KB), `status=success`, `lastNode=Done (PDF)`  
- Flow complet : n8n Form → mop-generator-v1 → mop-webhook-render-v1 → Gotenberg → PDF

---

### Test #10 — n8n Form → Error path (Gotenberg arrêté)

**Source** : Session MOP2, exec 11761 (2026-04-11 13:xx)

**Résultat** : PASS  
- `EAI_AGAIN gotenberg`, `lastNode=Done (Error)`  
- Branche erreur activée correctement

---

### Test #11 — Template re-upload ODT

**Statut** : NON TESTÉ — nécessite redéploiement Ansible avec `--tags carbone-template`. Reporté.

---

### Test #13 — Typebot SMTP fallback (MailHog magic-link)

**Source** : Task 3.2 (session MOP1/MOP2)

**Résultat** : PASS  
- Login Typebot builder via magic-link MailHog fonctionnel  
- Container `javisi_mailhog` Up, interface `mop-mail.ewutelo.cloud` accessible VPN-only

---

### Test #15 — Excel search (Windows local)

**Statut** : NON TESTÉ sur poste Windows  
- `mop-search.xlsm` généré (sheets `index` + `recherche` avec en-têtes)  
- `Module1.bas` commit avec la macro `SearchMOP`  
- Import VBA manuel requis (Alt+F11 → Fichier → Importer)  
- À valider sur poste NOC Windows avec CSV synchronisé

---

### Test #16 — Caddy ACL VPN-only (mop-dl)

**Commandes** :
```bash
# VPN (waza via Tailscale)
curl -s -o /dev/null -w '%{http_code}' https://mop-dl.ewutelo.cloud/MOP-2026-0001.pdf
# Non-VPN (IP publique)
curl -s --resolve 'mop-dl.ewutelo.cloud:443:137.74.114.167' -o /dev/null -w '%{http_code}' https://mop-dl.ewutelo.cloud/
```

**Résultat** : PASS  
- VPN : 200 (taille=23 590 bytes) ✓  
- Non-VPN : 403 ✓  
- Snippet `(vpn_only)` correctement appliqué au domaine `mop-dl.ewutelo.cloud`

---

## Problèmes rencontrés et correctifs

### P1 — Permissions `/opt/javisi/data/mop/index/`

**Symptôme** : `Permission denied` sur `.lock`, `.pending/`, `mops-index.csv`  
**Cause** : Répertoire créé par `debian:debian` (uid 1000), CLI appelée par `mobuone` (uid 1001)  
**Fix appliqué** : `chmod 777` manuellement sur le répertoire et sous-répertoires  
**Correctif permanent nécessaire** : Le rôle Ansible `mop-content-factory` ou le handler de déploiement doit créer ces répertoires avec `mode: "0777"` ou utiliser un groupe partagé (`docker`).

### P2 — GOTENBERG_URL non accessible depuis l'hôte

**Symptôme** : `curl: (7) Failed to connect to localhost port 3000` quand la CLI est appelée depuis l'hôte  
**Cause** : Port 3000 non exposé (Docker network uniquement), défaut `localhost:3000` invalide hors container  
**Workaround** : `export GOTENBERG_URL=http://172.20.2.27:3000` (IP interne Docker — peut changer au restart)  
**Correctif permanent** : Soit exposer le port `127.0.0.1:3000:3000` dans docker-compose, soit configurer `GOTENBERG_URL` via `/etc/profile.d/mop.sh` ou dans le rôle Ansible.

### P3 — n8n import:workflow → DRAFT seulement (session antérieure, résolu)

**Symptôme** : Workflow importé mais ancienne version exécutée  
**Cause** : `import:workflow` ne met à jour que `workflow_entity.nodes` (DRAFT), pas `workflow_history`  
**Fix** : `n8n publish:workflow --id=<WF_ID>` + double restart  
**Documenté** : `.planning/research/mop-gotenberg-n8n.md` P11-P12

---

## Livrables créés cette session

| Fichier | Description |
|---|---|
| `scripts/n8n-workflows/mop-generator-v1.json` | Workflow n8n 8 nœuds (form multi-step → PDF) |
| `scripts/typebot/mop-generator-v1.json` | Flow Typebot v6.1, 7 groupes (ID: cmnue3spm00051drwymwqg57l) |
| `scripts/mop/mops-index.csv` | CSV bootstrap avec BOM UTF-8 + en-tête |
| `scripts/mop/mop-search.xlsm` | Classeur Excel (sheets index + recherche) |
| `scripts/mop/Module1.bas` | Macro VBA SearchMOP (import manuel dans Excel) |
| `scripts/mop/deploy-mop-generator.sh` | Script de déploiement n8n (9 étapes, publish:workflow) |

---

---

## Découverte Typebot v6.1 — Types de blocs (bundle reverse-engineering)

**Source** : inspection bundle `/app/apps/builder/.next/server/chunks/[root-of-the-server]__f4b2d21c._.js` dans `javisi_typebot_builder`

Les discriminateurs Zod pour les blocs Typebot v3.16.1 (schéma v6.1) ne sont pas documentés publiquement. Valeurs découvertes :

| Catégorie | `type` string (API) | Usage |
|---|---|---|
| Bubble | `"text"` | Bulle de texte |
| Input | `"text input"` | Champ texte (`options.variableId` pour stocker la valeur) |
| Input | `"choice input"` | Boutons choix (items v6 : `{id, content, outgoingEdgeId}`) |
| Integration | `"Webhook"` | HTTP Request block (`IntegrationBlockType.HTTP_REQUEST`) — options: `webhook.{url,method,body,headers}` + `responseVariableMapping` |
| Logic | `"Set variable"` | Set Variable (capital S+V) |
| Logic | `"Condition"` | Condition block (capital C) |
| Logic | `"webhook"` | Webhook logic block (lowercase — différent de l'HTTP Request) |

**optionBaseSchema** (module 938666) : `variableId: string optional` est au niveau de `options` directement pour tous les blocs input.

**Edges** : `{id, from: {blockId|eventId}, to: {groupId}}` — les items de `choice input` portent leur propre `outgoingEdgeId`.

---

## Dette technique identifiée

1. **Permissions MOP data dirs** : répertoires créés en `debian:debian`, CLI en `mobuone`. Fixer dans rôle Ansible.
2. **GOTENBERG_URL** : non configurée par défaut sur l'hôte. Documenter dans RUNBOOK.md.
3. **Typebot flow sans branchement conditionnel** : flow linéaire MVP. Phase 2 : ajouter `Condition` blocks par périmètre.
4. **Excel VBA non intégré dans .xlsm** : import manuel requis. Considérer un script `build-mop-search.py` avec vbaProject.bin.
5. **Test #11 (template ODT re-upload)** et **#15 (Excel Windows)** non validés — à reporter en smoke tests manuels.
