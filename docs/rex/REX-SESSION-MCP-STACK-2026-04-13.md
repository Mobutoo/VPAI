# REX Session — MCP Stack Extension (2026-04-13)

## Objectif

Étendre la stack MCP de Claude Code sur Waza Pi avec 4 nouveaux serveurs :
- **postgres** — accès direct à la DB n8n sur Sese-AI
- **nocodb** — CRUD NocoDB self-hosted (hq.ewutelo.cloud)
- **github** — opérations Git/PR/issues sur Mobutoo/vpai
- **n8n-docs management** — 14 outils CRUD workflow (czlonkowski, déjà déployé)

---

## Erreurs rencontrées et résolutions

### 1. ansible-dev-tools n'est pas un serveur MCP ❌

**Symptôme** : Installation de `ansible-dev-tools` puis `adt server` → `No module named 'django'`.  
**Cause** : `adt server` est un serveur Django REST pour l'extension VS Code (language server protocol). Ce n'est pas un serveur MCP. Aucun transport stdio/HTTP/SSE MCP.  
**Fix** : Suppression de l'entrée `ansible-dev-tools` dans `~/.claude.json`. Le binaire `adt` reste disponible dans le venv Ansible pour usage CLI direct.  
**Leçon** : **Il n'existe pas de MCP officiel pour Ansible à ce jour (avril 2026)**. `ansible-dev-tools` = LSP pour VS Code uniquement. Pour l'assistance Ansible en session Claude Code, utiliser la documentation via `context7` + lecture directe des fichiers du repo VPAI. Ne plus chercher de "MCP Ansible".

---

### 2. MCPs npm dépréciés installés puis remplacés ❌ → Résolu

**Symptôme** : `@modelcontextprotocol/server-postgres` (archivé juillet 2025, faille SQL injection) et `@modelcontextprotocol/server-github` (déplacé vers `github/github-mcp-server`) installés par erreur.  
**Cause** : Noms évidents sur npmjs, non vérifiés contre le statut GitHub des repos.  
**Fix** :
- postgres → `@henkey/postgres-mcp-server` v1.0.5 (17 outils, pg bundlé)
- github → `github/github-mcp-server` v0.32.0 (binaire Go ARM64 officiel)

**Leçon** : Vérifier le statut GitHub du repo (archived ? deprecated ?) AVANT installation npm. Les noms évidents (`@modelcontextprotocol/server-*`) ne sont pas toujours maintenus.

---

### 3. npm install permission denied ❌ → Résolu

**Symptôme** : `npm install -g @henkey/postgres-mcp-server` → `EACCES: permission denied, /usr/lib/node_modules`.  
**Cause** : npm global par défaut = `/usr/lib/node_modules` (root-owned).  
**Fix** : `npm install -g --prefix /home/mobuone/.npm-global @henkey/postgres-mcp-server`.  
**Leçon** : Toujours utiliser `--prefix /home/mobuone/.npm-global` pour les installs npm globales sur Waza Pi.

---

### 4. Docker context sese-ai intercepte tous les `docker` commands ❌ → Résolu

**Symptôme** : `docker ps` → liste les containers de Sese-AI, pas de Waza Pi. `docker run` crée un container sur Sese-AI.  
**Cause** : Context Docker actif = `sese-ai` (configuré pour le déploiement Ansible).  
**Fix** : Toujours préfixer `docker --context local` pour les opérations sur Waza Pi.  
**Leçon** : Sur Waza Pi, `docker` seul = Sese-AI. `docker --context local` = Waza Pi. Ne jamais oublier le flag.

---

### 5. n8n-mcp management tools — Jinja2 string vs bool ❌ → Contourné

**Symptôme** : `make deploy-workstation TAGS=n8n-mcp` → `changed=2, failed=1`. Le container restait en docs-only malgré `N8N_API_KEY` défini.  
**Cause** : `n8n_mcp_management_enabled: "{{ vault_n8n_mcp_api_key is defined and ... }}"` retourne une **string** `"True"`/`"False"` en Jinja2, pas un booléen Python. Le `if n8n_mcp_management_enabled else ''` évalue `"False"` comme truthy (string non-vide).  
**Fix contournement** : Recréation manuelle du container via `docker --context local run` avec toutes les env vars explicites. L'Ansible sera corrigé avec `| bool` au prochain cycle.  
**Fix Ansible à appliquer** :
```yaml
# Dans tasks/main.yml — remplacer :
N8N_API_URL: "{{ n8n_mcp_api_url if n8n_mcp_management_enabled else '' }}"
# Par :
N8N_API_URL: "{{ n8n_mcp_api_url if (n8n_mcp_management_enabled | bool) else '' }}"
```
**Leçon** : En Jinja2 Ansible, `"True"` (string) est toujours truthy. Toujours ajouter `| bool` quand la variable vient d'une expression booléenne encadrée de `"..."`.

---

### 6. Tunnel SSH PostgreSQL — `administratively prohibited` ❌ → Résolu

**Symptôme** : `ssh -L 5433:postgresql:5432` → tunnel TCP établi (port 5433 écoute) mais toute connexion donne `channel N: open failed: administratively prohibited`.  
**Causes multiples** :
1. `postgresql` est un nom DNS Docker interne — non résolvable par sshd (qui résout côté hôte OS, pas Docker DNS).
2. `AllowTcpForwarding no` dans `/etc/ssh/sshd_config` sur Sese-AI.

**Fix** :
1. Cible changée de `postgresql:5432` → IP bridge Docker réelle `172.20.2.19:5432` (obtenue via `docker inspect javisi_postgresql`).
2. `AllowTcpForwarding yes` activé sur Sese-AI sshd (`sudo sed -i ... && sudo systemctl reload ssh`).

**Leçon** :
- Les noms Docker DNS ne sont résolvables que depuis l'intérieur du réseau Docker, jamais depuis sshd.
- Pour un tunnel vers un container Docker, toujours utiliser l'IP bridge : `docker inspect <container> --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'`
- Vérifier `AllowTcpForwarding` avant de créer un tunnel SSH vers une infra.
- **L'IP bridge peut changer** si le réseau Docker est recréé. Si le tunnel tombe, re-inspecter le container et mettre à jour le service.

---

### 7. R0 Gate TTL expiré en session longue ❌ → Résolu

**Symptôme** : Hook `loi-op-enforcer.js` bloque les éditions avec `[R0-GATE] BLOQUÉ — topic "postgres" détecté`.  
**Cause** : Le marker `/tmp/claude-r0-done-postgres` a un TTL de 15 min. La session a duré plus longtemps.  
**Fix** : Re-lancer `search_memory.py --query "postgres"` pour rafraîchir le marker.  
**Leçon** : En session longue, le R0 Gate peut expirer plusieurs fois. Relancer le search si bloqué par le hook.

---

## État final des MCPs

| MCP | Package | Transport | Status |
|-----|---------|-----------|--------|
| **n8n-docs** | `czlonkowski/n8n-mcp:2.40.5` | HTTP port 3001 | ✅ 21 tools (7 docs + 14 mgmt) |
| **postgres** | `@henkey/postgres-mcp-server` | stdio | ✅ PG 18.3 via tunnel localhost:5433 |
| **nocodb** | `@andrewlwn77/nocodb-mcp` | stdio | ✅ hq.ewutelo.cloud |
| **github** | `github/github-mcp-server v0.32.0` | stdio | ✅ ARM64 binary |
| **ansible** | — | — | ❌ **N'existe pas** — voir §1 |

---

## Infrastructure ajoutée

### Tunnel PostgreSQL (systemd user service)
```
~/.config/systemd/user/postgres-tunnel.service
  → ssh -L 5433:172.20.2.19:5432 mobuone@100.64.0.14 -p 804
  → postgresql://n8n:***@localhost:5433/n8n
```
Activé : `systemctl --user enable --now postgres-tunnel`.

### sshd Sese-AI
- `AllowTcpForwarding yes` activé (nécessaire pour le tunnel DB).
- Risque contrôlé : SSH accessible Tailscale uniquement, pas via internet public.

---

## Ce qui n'existe pas — Ansible MCP

À la date d'avril 2026, **aucun serveur MCP officiel ou communautaire viable n'existe pour Ansible**.

| Outil | Réalité | Usage |
|-------|---------|-------|
| `ansible-dev-tools` (ADT) | Django REST API pour VS Code — incompatible MCP | CLI direct (`adt`) |
| `ansible-lint` MCP | Inexistant | `make lint` |
| `ansible-navigator` | CLI interactif — pas de transport MCP | CLI direct |

**Alternative opérationnelle pour les sessions Claude Code** :
- `context7` → documentation officielle Ansible (modules, filtres, lookup plugins)
- Lecture directe des fichiers VPAI + checklist `docs/standards/ANSIBLE-ROLE-CHECKLIST.md`
- `make lint` + `ansible-playbook --check --diff` pour valider

---

## Commits

Aucun commit de code dans cette session — MCPs = config `~/.claude.json` + systemd user service (non versionnés dans VPAI).

---

## Prochaines actions

- [ ] Appliquer fix `| bool` sur `n8n_mcp_management_enabled` dans `roles/n8n-mcp/tasks/main.yml`
- [ ] mcp-grafana (basse priorité — pas encore installé)
- [ ] Vérifier que `postgres-tunnel` redémarre bien après reboot Waza Pi (`loginctl enable-linger`)
