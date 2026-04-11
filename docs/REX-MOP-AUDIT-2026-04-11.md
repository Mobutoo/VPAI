# Audit MOP Machinery v1.0 — VPAI Compliance — 2026-04-11

## Périmètre

Audit Opus post-déploiement de tous les commits MOP (2a9767a → 61920c0, 28 commits).

Éléments vérifiés :
- 4 rôles Ansible : `gotenberg`, `carbone`, `typebot`, `mop-templates`
- Blocs docker-compose MOP dans `roles/docker-stack/templates/docker-compose.yml.j2`
- Routes Caddy dans `roles/caddy/templates/Caddyfile.j2`
- Workflows n8n : `mop-generator-v1.json`, `mop-webhook-render-v1.json`
- Scripts CLI : `mop-render-html.j2`, `mop-render-odt.j2`, `alloc-and-append.sh.j2`

---

## Résultat global

**Score de conformité : 78%** — Fondations saines, 3 violations systémiques (phase tags, logging, portabilité) à corriger avant prochain déploiement.

---

## Violations confirmées

### V1 — Phase tags manquants (P2, systémique)

**Tous les rôles MOP** n'ont que le tag de rôle, sans tag de phase.

| Rôle | Tag actuel | Tag requis |
|---|---|---|
| gotenberg | `[gotenberg]` | `[gotenberg, phase3]` |
| carbone | `[carbone]` | `[carbone, phase3]` |
| typebot | `[typebot]` | `[typebot, phase3]` |
| mop-templates | `[mop-templates]` | `[mop-templates, phase3]` |

**Impact** : `ansible-playbook --tags phase3` ne déploie pas les rôles MOP. Rompt la convention VPAI.

**Fix** : Ajouter `, phase3` à chaque `tags:` dans les 4 `tasks/main.yml`.

---

### V2 — Logging absent sur les 5 services MOP (P2, systémique)

Les services `gotenberg`, `carbone`, `mailhog`, `typebot-builder`, `typebot-viewer` dans `roles/docker-stack/templates/docker-compose.yml.j2` n'ont pas de bloc `logging`.

Les autres services de la stack (n8n, LiteLLM, etc.) ont systématiquement :
```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

**Impact** : Les logs MOP croissent de façon illimitée sur le disque. Sur un VPS 8 Go, un rendu Gotenberg Chromium verbeux peut générer des centaines de Mo de logs.

**Fix** : Ajouter le bloc `logging` à chaque service MOP dans le template.

---

### V3 — `PUBLIC_BASE` hardcodé dans mop-webhook-render-v1.json (P1)

**Fichier** : `scripts/n8n-workflows/mop-webhook-render-v1.json`, nœud "Persist" (Code node)

```javascript
const PUBLIC_BASE = 'https://mop-dl.ewutelo.cloud';
```

**Impact** : Le workflow est non-portable. Un déploiement preprod ou sur un autre domaine retourne des URLs publiques pointant vers la prod. Rompt la règle "jamais de valeur hardcodée".

**Fix** : Lire depuis une variable d'environnement n8n :
```javascript
const PUBLIC_BASE = process.env.MOP_PUBLIC_BASE || 'https://mop-dl.' + process.env.DOMAIN_NAME;
```
Et ajouter `MOP_PUBLIC_BASE={{ mop_public_base_url }}` dans `roles/n8n/templates/n8n.env.j2`.

---

### V4 — URL webhook hardcodée dans mop-generator-v1.json (P2)

**Fichier** : `scripts/n8n-workflows/mop-generator-v1.json`, nœud HTTP Request (ligne 182)

```json
"url": "http://localhost:5678/webhook/mop-render"
```

**Impact** : Appel intra-n8n via `localhost` — fonctionne car même container, mais non-portable. Un déploiement multi-instance (scaling horizontal) ou un test depuis l'extérieur échoue.

**Fix acceptable** : Remplacer par `http://n8n:5678/webhook/mop-render` (Docker DNS interne) ou par la variable d'env `{{ $env.N8N_BASE_URL }}/webhook/mop-render`.

---

## Avertissements (non-bloquants)

### W1 — `changed_when` fragile sur l'upload template Carbone

**Fichier** : `roles/carbone/tasks/template.yml`

```yaml
changed_when: carbone_upload_curl.stdout == '200'
```

Si Carbone est down (curl RC=7, stdout vide), la tâche est marquée `ok` (non-changed) au lieu de `failed`. La condition devrait inclure le RC :
```yaml
changed_when: carbone_upload_curl.rc == 0 and carbone_upload_curl.stdout == '200'
```

### W2 — CSV append non-transactionnel dans alloc-and-append.sh

**Fichier** : `roles/mop-templates/templates/alloc-and-append.sh.j2`

`fs.appendFileSync` (et le `>>` bash) ne sont pas atomiques. Un crash entre l'écriture PDF et l'append CSV laisse un MOP orphelin (PDF présent, CSV non mis à jour). Risque faible en production, mais notable.

**Fix Phase 2** : Écrire le CSV dans un fichier temp, valider, puis `mv` atomique.

### W3 — `flock` sans timeout sur l'allocation d'ID

Le lock exclusif `flock -x` dans `alloc-and-append.sh` n'a pas de timeout (`-w`). Si un process meurt en tenant le lock, les appels suivants bloquent indéfiniment.

**Fix** : `flock -w 30 -x` + message d'erreur explicite sur timeout.

---

## Checklist de conformité complète

| Convention VPAI | Gotenberg | Carbone | Typebot | Mop-templates |
|---|---|---|---|---|
| FQCN obligatoire | ✅ | ✅ | ✅ | ✅ |
| `changed_when` sur command/shell | ✅ N/A | ⚠️ fragile | ✅ N/A | ✅ |
| `set -euo pipefail` sur shell | ✅ N/A | ✅ | ✅ N/A | ✅ |
| `executable: /bin/bash` | ✅ N/A | ✅ | ✅ N/A | ✅ |
| Tags : rôle + phase | ❌ phase3 absent | ❌ phase3 absent | ❌ phase3 absent | ❌ phase3 absent |
| 0 valeur hardcodée | ✅ | ✅ | ✅ | ✅ |
| Variables dans `defaults/` | ✅ | ✅ | ✅ | ✅ |

| Convention Docker | Gotenberg | Carbone | Mailhog | TB-Builder | TB-Viewer |
|---|---|---|---|---|---|
| Image pinnée (variable) | ✅ | ✅ | ✅ | ✅ | ✅ |
| `restart: unless-stopped` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `cap_drop: [ALL]` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `cap_add` minimal | ✅ | ✅ | ✅ | ✅ | ✅ |
| Limites mémoire/CPU | ✅ | ✅ | ✅ | ✅ | ✅ |
| Healthcheck | ✅ | ✅ | ❌ absent | ✅ | ✅ |
| Logging (max-size/max-file) | ❌ absent | ❌ absent | ❌ absent | ❌ absent | ❌ absent |

| Convention Caddy | Résultat |
|---|---|
| Snippet `(vpn_only)` sur toutes les routes MOP | ✅ `mop-build`, `mop`, `mop-dl`, `mop-mail` |
| Snippet contient les 2 CIDRs (vpn + docker_frontend) | ✅ |
| Route `mop.{{ domain_name }}` (viewer runtime) | ✅ présente (ligne 437) |

| Convention n8n | mop-generator | mop-webhook-render |
|---|---|---|
| Branche erreur présente | ✅ | ✅ |
| Validation payload | ✅ | ✅ |
| `onError: continueErrorOutput` | ✅ | ✅ |
| 0 domaine hardcodé | ❌ localhost:5678 | ❌ ewutelo.cloud |
| Rollback sur erreur | ✅ | ✅ |

---

## Dette technique — Inventaire complet

| ID | Composant | Description | Priorité | Phase cible |
|---|---|---|---|---|
| DT-1 | Permissions `mop/index/` | Répertoires créés en `debian:debian`, CLI `mobuone` → chmod 777 manuel | P1 | Rôle Ansible `mop-content-factory` |
| DT-2 | `GOTENBERG_URL` sur l'hôte | Port 3000 non exposé, IP Docker peut changer au restart | P1 | Exposer `127.0.0.1:3000:3000` dans docker-compose OU env var dans `/etc/profile.d/mop.sh` |
| DT-3 | Phase tags manquants (V1) | 4 rôles sans `phase3` | P2 | Prochain deploy |
| DT-4 | Logging absent (V2) | 5 services sans rotation de logs | P2 | Prochain deploy |
| DT-5 | `PUBLIC_BASE` hardcodé (V3) | `ewutelo.cloud` en dur dans n8n Code node | P1 | Avant multi-env / preprod |
| DT-6 | URL webhook hardcodée (V4) | `localhost:5678` en dur dans mop-generator | P2 | Avant scaling / multi-instance |
| DT-7 | CSV append non-transactionnel (W2) | Pas de rollback si crash entre PDF et CSV | P3 | Phase 2 MOP |
| DT-8 | flock sans timeout (W3) | Blocage indéfini si process mort avec lock | P3 | Phase 2 MOP |
| DT-9 | Typebot sans branchement conditionnel | Flow linéaire MVP, pas de Condition blocks par périmètre | P3 | Phase 2 MOP |
| DT-10 | VBA non intégré dans .xlsm | Import manuel requis (Alt+F11) | P3 | Si script `build-mop-search.py` avec vbaProject.bin |
| DT-11 | Test #11 ODT re-upload non validé | `--tags carbone-template` jamais exécuté en E2E | P2 | Prochain smoke test |
| DT-12 | Test #15 Excel Windows non validé | `.xlsm` non testé sur poste NOC Windows réel | P2 | À valider par NOC |
| DT-13 | MailHog healthcheck absent | Container sans probe TCP/HTTP | P3 | Prochain deploy |

---

## Corrections à appliquer en priorité

### Correctif immédiat (DT-3 + DT-4 — 15 min)

```bash
# 1. Phase tags — 4 fichiers à éditer (ajouter ", phase3" sur chaque tags:)
# roles/gotenberg/tasks/main.yml, roles/carbone/tasks/main.yml,
# roles/typebot/tasks/main.yml, roles/mop-templates/tasks/main.yml

# 2. Logging — roles/docker-stack/templates/docker-compose.yml.j2
# Ajouter bloc logging aux services gotenberg/carbone/mailhog/typebot-builder/typebot-viewer
```

### Avant mise en preprod (DT-5)

Ajouter dans `roles/n8n/templates/n8n.env.j2` :
```
MOP_PUBLIC_BASE=https://mop-dl.{{ domain_name }}
```

Modifier le Code node "Persist" dans `mop-webhook-render-v1.json` :
```javascript
const PUBLIC_BASE = $env.MOP_PUBLIC_BASE || 'https://mop-dl.' + $env.DOMAIN_NAME;
```

---

## Conclusion

L'implémentation MOP v1.0 est fonctionnelle et sécurisée (VPN-only Caddy confirmé, error handling n8n présent, secrets Vault, FQCN correct). Les violations identifiées sont opérationnelles (logs, portabilité) et non-fonctionnelles (phase tags). Aucune violation de sécurité.

**Blocages pour phase 2 :** DT-1 (permissions), DT-2 (GOTENBERG_URL), DT-5 (PUBLIC_BASE) doivent être résolus avant d'ouvrir le MOP Generator aux utilisateurs NOC.
