# Alerte sécurité — Credentials dans JSONL de sessions

**Date :** 2026-04-12  
**Priorité :** Haute (traiter avant déploiement session-analyst en production)  
**Contexte :** Découvert lors de la session 9b825eb9 — un grep sur GITEA_TOKEN a retourné des credentials flash-infra depuis un JSONL de session passée.

---

## Problème

Les fichiers JSONL de sessions Claude Code (`~/.claude/projects/<slug>/<id>.jsonl`) contiennent **en clair** tout ce qui a été affiché dans la session : tool results, output de commandes, contenu de fichiers lus.

Si un subagent lit un `.env` (secrets.yml, n8n.env, etc.) pendant une session, ces credentials se retrouvent **mot pour mot** dans le JSONL. Ces fichiers sont ensuite ingérés par `session-analyst.py` → NocoDB, Qdrant, Loki.

### Credentials trouvés dans un JSONL flash-infra (exemple)
```
GITEA_API_TOKEN=136ad25...
NOCODB_API_KEY=f831db3...
N8N_ENCRYPTION_KEY=21908ae...
QDRANT_OPS_API_KEY=749e526...
N8N_DASHBOARD_API_KEY=f4PMBm...
NETBIRD_MGMT_API_KEY=nbp_Hd...
EVENT_ROUTER_API_KEY=9weF...
```

### Surface d'exposition si non traité
| Destination | Risque |
|------------|--------|
| NocoDB `summary` field | Credentials indexés, requêtables via API NocoDB |
| Qdrant `sessions_v1` | Credentials dans vecteur + payload, searchable |
| Loki | Credentials dans logs structurés, visibles dans Grafana |
| Langfuse Cloud (Track A) | **Critique** — credentials partent vers un service externe |

---

## Solutions (3 niveaux — à implémenter dans session-analyst.py)

### Niveau 1 — Scrubbing pré-ingestion (obligatoire)

Avant toute push vers une destination, passer le contenu textuel (summary, logs) dans un filtre regex.

```python
import re

# Patterns de secrets courants
SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|token|secret|password|encryption[_-]?key|auth)\s*[:=]\s*\S+'),
    re.compile(r'(?i)[a-z0-9]{32,}'),   # hash-like strings > 32 chars
    re.compile(r'nbp_[a-zA-Z0-9]+'),    # NetBird tokens
    re.compile(r'sk-[a-zA-Z0-9]+'),     # OpenAI/LiteLLM keys
    re.compile(r'ghp_[a-zA-Z0-9]+'),    # GitHub tokens
    re.compile(r'ghs_[a-zA-Z0-9]+'),    # GitHub app tokens
]

REDACTED = "[REDACTED]"

def scrub_secrets(text: str) -> str:
    """Remplace les patterns de secrets avant ingestion."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text
```

**Où appliquer :** sur `summary`, les logs Loki, les payloads n8n — **jamais** sur les champs métriques (tokens, cost, etc.).

---

### Niveau 2 — Exclusion de sessions sensibles (optionnel)

Détecter les sessions qui ont lu des fichiers sensibles et les exclure de l'ingestion Qdrant/NocoDB `summary`.

```python
SENSITIVE_INDICATORS = [
    # Patterns dans le JSONL lui-même (tool_results)
    re.compile(r'ENCRYPTION_KEY\s*='),
    re.compile(r'VAULT_PASSWORD'),
    re.compile(r'-----BEGIN .* PRIVATE KEY-----'),
]

def is_session_sensitive(jsonl_path: Path) -> bool:
    """Retourne True si la session contient des patterns de credentials."""
    content = jsonl_path.read_text(errors='replace')
    return any(p.search(content) for p in SENSITIVE_INDICATORS)
```

Si `is_session_sensitive()` → `True` :
- Ingérer quand même les **métriques** (tokens, cost, durée, tool_distribution) → VictoriaMetrics uniquement
- **Ne pas** pousser vers Loki, NocoDB summary, Qdrant, Langfuse Cloud
- Logger l'événement : `"session_skipped_sensitive": true`

---

### Niveau 3 — Nettoyage batch des JSONL (futur)

Script séparé `scripts/scrub-jsonl-history.py` pour nettoyer les JSONL existants :

```python
# Scan tous les JSONL, remplace les secrets in-place
# Crée .bak avant modification
# Log les fichiers modifiés dans scrub-report.json
```

**Attention :** modifier les JSONL existants = risque de perte de contexte de sessions passées. À faire uniquement sur les champs `content[].text` des tool_results, jamais sur les champs structurés.

---

## Règle de priorité

```
Métriques structurées (tokens/cost/tools) → toujours OK → VictoriaMetrics + NocoDB champs numériques
Texte libre (summary/logs/résumé)         → scrub obligatoire avant toute destination
Payload Langfuse Cloud (Track A)          → scrub AVANT envoi (externe)
```

---

## Actions avant déploiement session-analyst

- [ ] Implémenter `scrub_secrets()` dans `src/utils/scrubber.py`
- [ ] Appliquer sur `generate_summary()` output
- [ ] Appliquer sur payload Loki `values[].message`
- [ ] Appliquer sur payload n8n webhook `summary`
- [ ] Appliquer sur payload Langfuse trace `input`/`output`
- [ ] Ajouter test unitaire : summary avec credentials → toujours REDACTED après scrub
- [ ] Décider : activer `is_session_sensitive()` comme guard ou s'appuyer uniquement sur scrub

---

*Note créée le 2026-04-12 — à traiter dans Plan 10-B1 (session-analyst enhanced)*
