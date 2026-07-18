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

