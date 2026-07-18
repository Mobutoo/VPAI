# REX — n8n Autoring (capture automatique)

Entrées ajoutées automatiquement par `scripts/n8n-authoring/rex-capture.sh` sur
tout échec `validate`/`deploy`/`verify` détecté par `scripts/n8n-validate-fallback.sh`
ou `scripts/deploy-workflow.sh`. Format : horodatage UTC, workflow, étape, erreur
brute, correction si connue. Opt-out : `REX_CAPTURE=0`. Ne modifie jamais le code
de sortie du script appelant (best-effort).

Doctrine d'usage : `docs/runbooks/RUNBOOK-N8N-AUTORING.md`.
Gotchas curés (build-time) : `docs/runbooks/GOTCHAS-N8N-2.30.md`.

---

## 2026-07-18T16:25:12Z — tests/fixtures/broken-workflow-dangling-connection.json — validate-structural

**Erreur brute :**
```
[N8N-VALIDATE-CLI] FAIL: cible de connexion inconnue: Node That Does Not Exist (depuis Start)
```


## 2026-07-18T16:25:29Z — tests/fixtures/broken-workflow-dangling-connection.json — deploy-missing-api-key

**Erreur brute :**
```
N8N_API_KEY not set
```


## 2026-07-18T17:19:06Z — code-review (TTO6eebHOVboM2MQ) — verify-runtime-process-env

**Erreur brute :**
```
Code node sandbox lève 'ReferenceError: process is not defined [line N]' via @n8n/task-runner (JsTaskRunner), CONFIRMÉ empiriquement (execution 33896, curl E2E probe 2026-07-18, branche GitHub PR nouvellement ajoutée), alors que roles/n8n/templates/n8n.env.j2 porte N8N_RUNNERS_ENABLED=false — dérive constatée entre le template repo et le conteneur javisi_n8n réellement déployé. Impacte potentiellement TOUT code node existant lisant process.env (SSH Pi: Run Review, Merge PR, Attach review report dans ce même workflow ; probablement github-autofix.json, launch-claude-code.json aussi — jamais exécutés en prod, 0 execution historique trouvée).
```

**Correction :** Contournement appliqué (sans toucher au conteneur/redémarrage, interdit pour ce chantier) : déplacer toute lecture de env var hors du Code node, vers une expression n8n {{ $env.VAR }} évaluée par le moteur principal dans un node IF (comparaison secret) ou Set (capture valeurs SSH avant le Code node exec()). Pattern déjà éprouvé ailleurs dans ce repo (memory-telegram-bot.json, node IF 'Validate Telegram Secret'). Root cause (pourquoi N8N_RUNNERS_ENABLED=false du template ne s'applique pas au conteneur live) non investiguée plus loin — hors scope, nécessite accès non accordé (pas de restart/inspect conteneur autorisé).


## 2026-07-18T17:19:06Z — code-review (TTO6eebHOVboM2MQ) — verify-runtime-ssh-credential

**Erreur brute :**
```
SSH fire-and-forget vers waza échoue: 'Identity file /home/node/.ssh/id_ed25519 not accessible: No such file or directory' puis 'Permission denied (publickey,password)' (exit 255), execution 33899 (curl E2E probe 2026-07-18). WORKSTATION_SSH_KEY_PATH résout au défaut Jinja '/home/node/.ssh/id_ed25519' (roles/n8n/templates/n8n.env.j2:184) car aucune variable workstation_ssh_key_path n'est définie dans inventory/group_vars/ — et aucun volume mount de clé SSH n'a été trouvé dans roles/n8n/. Ce chemin est donc un défaut jamais concrétisé par un vrai fichier monté dans javisi_n8n. Impact: le pattern SSH Code-node-exec (WORKSTATION_SSH_KEY_PATH/PI_USER/PI_IP) utilisé par 4 workflows (code-review branche Palais préexistante, launch-claude-code.json, github-autofix.json, + ma nouvelle branche GitHub PR) n'a jamais fonctionné en prod — 0 exécution historique sur ces 4 workflows avant ce chantier, donc jamais détecté.
```

**Correction :** Non corrigé (hors scope T4.2 — nécessite: monter un vrai fichier clé privée dans javisi_n8n via docker-compose volume + enregistrer la clé publique correspondante dans ~/.ssh/authorized_keys sur waza pour l'utilisateur mobuone, potentiellement + redémarrage conteneur n8n — INTERDIT pour ce chantier). Gate humain à lever avant que la branche GitHub PR (ou le reste du pipeline Palais/OpenClaw SSH) puisse fonctionner en conditions réelles.

