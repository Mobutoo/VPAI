# REX — Session 2026-02-23c (Session 11)

> **Thème** : Fix sous-agents sandbox (EACCES), Kaneo auth (404 → 200), plan mode idea-planning
> **Durée** : ~2h
> **Résultat** : Subagents opérationnels, Kaneo integration fonctionnelle, skill idea-planning renforcée

---

## Problèmes Résolus

### REX-48 — OpenClaw subagents : spawn docker EACCES

**Symptôme** : `Error: spawn docker EACCES` dans les lanes `subagent` et `session:agent:<name>:subagent:*`. Le Concierge rapporte "Subagent writer failed". Aucun sous-agent ne démarre.

**Cause** : Container OpenClaw (`node:1000`) ne peut pas accéder `/var/run/docker.sock` — socket appartient au groupe `docker` (GID 989 sur cette instance). Aucun `group_add` dans le docker-compose.

**Diagnostic** :
```bash
docker exec javisi_openclaw id
# AVANT : uid=1000(node) gid=1000(node) groups=1000(node)  ← pas de groupe docker
getent group docker  # → docker:x:989:mobuone
ls -la /var/run/docker.sock  # → srw-rw---- 1 root docker
```

**Fix** :
1. Ajout tâche Ansible dans `roles/docker-stack/tasks/main.yml` — détecte le GID dynamiquement :
   ```bash
   stat -c '%g' /var/run/docker.sock  # → 989
   ```
2. Ajout `group_add` dans `roles/docker-stack/templates/docker-compose.yml.j2` :
   ```yaml
   group_add:
     - "{{ docker_socket_gid | default('989') }}"
   ```
3. Redeploy `make deploy-role ROLE=docker-stack ENV=prod`

**Vérification** :
```bash
docker exec javisi_openclaw id
# APRÈS : uid=1000(node) gid=1000(node) groups=1000(node),989
```

---

### REX-49 — Kaneo auth : endpoint BetterAuth incorrect (404)

**Symptôme** : Rien n'apparaît dans Kaneo. Aucune tâche, aucun projet. Pas d'erreur visible (curl `-sf` masque les échecs).

**Cause** : Kaneo BetterAuth expose `/api/auth/sign-in/email` mais tous les fichiers (Messenger IDENTITY.md.j2 et 5 workflows n8n) utilisaient `/api/auth/sign-in` → HTTP 404 → COOKIE vide → toutes les opérations Kaneo échouent silencieusement.

**Fichiers corrigés** :
- `roles/openclaw/templates/agents/messenger/IDENTITY.md.j2` (2 occurrences)
- `roles/n8n-provision/files/workflows/code-review.json`
- `roles/n8n-provision/files/workflows/error-to-task.json`
- `roles/n8n-provision/files/workflows/github-autofix.json`
- `roles/n8n-provision/files/workflows/kaneo-agents-sync.json` (2 occurrences)
- `roles/n8n-provision/files/workflows/project-status.json`
- `roles/n8n-provision/templates/workflows/plan-dispatch.json.j2`

**Diagnostic rapide** :
```bash
# Tester depuis le container openclaw
docker exec javisi_openclaw curl -s -o /dev/null -w '%{http_code}' \
  -X POST http://kaneo-api:1337/api/auth/sign-in/email \
  -H 'Content-Type: application/json' \
  -d '{"email":"<email>","password":"<pass>"}'
# Attendu : 200. Si 404 → mauvais endpoint.
```

**Note sur les cookies** : Le flag `__Secure-` sur les cookies BetterAuth est une directive navigateur, pas curl. curl envoie ces cookies en HTTP interne sans problème.

---

### REX-50 — Kaneo workspace_member doublons

**Symptôme** : Chaque agent apparaît 2 fois dans la liste des membres Kaneo.

**Cause** : Double provisioning — rôle Ansible (`kaneo-agent-member-XX`) + workflow n8n (`agXXagXX...`) créent chacun une entrée.

**Fix ponctuel** :
```bash
docker exec javisi_postgresql psql -U kaneo -d kaneo -t \
  -c "DELETE FROM workspace_member WHERE id LIKE 'kaneo-agent-member-%';"
# → DELETE 8
```

---

### REX-51 — idea-planning : Pattern Plan-Then-Approve

**Symptôme** : Lors du test du mode plan, le Concierge ne posait pas de questions de qualification et ne présentait pas de plan à approuver avant d'agir.

**Cause** : La skill `idea-planning` et le `IDENTITY.md.j2` du Concierge manquaient d'une vraie séparation Phase Exploration → Phase Plan → Phase Exécution avec portes de validation explicites.

**Pattern implémenté** (inspiré du Plan Mode de Claude Code) :
```
[EXPLORATION]   Qualifier l'idée — 2-3 questions — RIEN créer
      ↓ (confirmation "go ?" REQUISE)
[PLAN]          Co-construction Explorer+CFO+Builder → plan JSON unifié
      ↓ (approbation explicite : bouton [✅ Approuver] OU "approuve"/"go"/"valide")
[EXÉCUTION]     create_idea_plan → approve_idea → dispatch Kaneo
```

**Fichiers modifiés** :
- `roles/openclaw/templates/skills/idea-planning/SKILL.md.j2` — ajout section "Principe Plan-Then-Approve" + porte de validation explicite + règles absolues renforcées
- `roles/openclaw/templates/agents/concierge/IDENTITY.md.j2` — ajout diagramme 3 phases avec règle d'immutabilité de l'ordre

---

## État post-session

| Composant | État |
|-----------|------|
| Subagents (sandbox docker) | ✅ Opérationnels — `groups=1000,989` |
| Kaneo auth (Messenger + n8n) | ✅ Corrigé — `/api/auth/sign-in/email` |
| Workspace members | ✅ Doublons supprimés — 12 membres uniques |
| idea-planning skill | ✅ Plan-Then-Approve implémenté |
| Telegram bot | ✅ Opérationnel (inchangé) |
