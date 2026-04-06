# REX Session 21 — StoryEngine v1.5 Production Hardening (2026-04-06)

## Objectif

Livrer le milestone **v1.5 Production Hardening** — 5 phases de durcissement sur la v1.4.5 deployee a `story.ewutelo.cloud`. Aucune feature utilisateur ajoutee, uniquement de l'infra, de la securite et de la fiabilite.

Phases executees en autonomie (overnight, GO explicite de l'utilisateur) via le framework GSD (plan → execute → verify → deploy).

## Ce qui a ete fait

### v1.5-01 — Alembic Migrations (v1.5.0-alembic → v1.5.1)

| Deliverable | Commit | Detail |
|-------------|--------|--------|
| Migration 003 baseline | `a0d2e95` | Stamp baseline sur schema existant (user, workspace, project, scene, etc.) — `alembic stamp` sans DDL |
| Migration 005 token columns | `a0d2e95` | `reset_token`, `reset_token_expires`, `verify_token`, `email_verified` sur User |
| Suppression `create_all()` | `a0d2e95` | Plus de `Base.metadata.create_all()` dans startup API — Alembic est l'unique mecanisme |
| Validation Docker ephemere | `db14e7d` | Script `validate_migration.sh` : monte PG ephemere, seed avec dump prod, `alembic upgrade head`, verifie colonnes + row count |
| Deploy prod | `v1.5.1` | `pg_dump` snapshot avant, `alembic upgrade head` sur prod, verification colonnes OK |

### v1.5-02 — Email Service (v1.5.1)

| Deliverable | Commit | Detail |
|-------------|--------|--------|
| EmailService Brevo | shipping | `send_password_reset()`, `send_verification_email()` via Brevo HTTPS API |
| Token logic | shipping | `reset_token` + `verify_token` : single-use, 1h expiry, SHA-256 hash en DB |
| 3 pages frontend | shipping | `/forgot-password`, `/reset-password`, `/verify-email` + lien depuis login |
| Anti-enumeration | shipping | `/forgot-password` retourne toujours 200, meme si email inconnu |

### v1.5-03 — Audit Log Wiring (v1.5.2)

| Deliverable | Commit | Detail |
|-------------|--------|--------|
| Audit worker Taskiq | `ac01a76` | `audit_log_task` — fire-and-forget, zero latence sur le request path |
| AuditAction enum | `ac01a76` | 15 actions : login/register/logout + CRUD (create/update/delete) + export |
| 6 auth call sites | `0f03cc1` | login, register, logout, forgot-password, reset-password, verify-email |
| 14 CRUD call sites | `02b77c4` | projects, scenes, entities, facts, drafts, briefs, export |
| GET /audit-logs enhanced | `2b37211` | RBAC (owner/admin only), filters (user_id, action, from_date, to_date), cursor pagination |

### v1.5-04 — Rate Limiting + LLM Quota (v1.5.2)

| Deliverable | Commit | Detail |
|-------------|--------|--------|
| Redis sliding window | `3bc1005` | ZSET sorted sets, per-role limits (viewer=60, editor=300, admin/owner=1000 req/min) |
| AI endpoint limits | `3bc1005` | suggest=10, consistency=20, extract-claims=5 req/min (independant du global) |
| X-RateLimit-* headers | `3bc1005` | `Limit`, `Remaining`, `Reset` sur chaque reponse non-exclue |
| Exclusions | `3bc1005` | GET, /api/health, autosave drafts, WebSocket — jamais comptes |
| Fail-open | `3bc1005` | Redis down → requete passe (log warning) |
| `enforce_budget()` | `0111434` | Remplace le soft check par `QuotaExceededError` → HTTP 402 |
| GET /quota/llm | `0111434` | `{used, limit, reset_at}` pour affichage frontend |

### v1.5-05 — CSP Headers (v1.5.3)

| Deliverable | Commit | Detail |
|-------------|--------|--------|
| Next.js middleware | `e8dba46` | `crypto.randomUUID()` nonce, 10 directives CSP, `x-nonce` header propagation |
| Layout nonce | `c6dc15c` | `layout.tsx` async, lit `x-nonce` via `headers()`, `<meta property="csp-nonce">` |
| Report-only default | `e8dba46` | `Content-Security-Policy-Report-Only` — toggle via `SE_CSP_ENFORCE=true` |
| CSP report endpoint | `6c8397e` | `POST /api/v1/csp-report` — log violations, retourne 204, pas d'auth |
| Middleware location fix | `cd0ef1f` | Next.js avec `src/app/` exige `src/middleware.ts`, pas racine projet |

## Etat actuel

- **5/5 phases shipped** — v1.5.1, v1.5.2, v1.5.3 deployees sur prod
- **245 tests passing** (hors 2 pre-existants : weasyprint arm64, test_export_invalid_format)
- **E2E Playwright** verifie sur prod : register → create project → editor → entity @mention → graph XYFlow → CSP headers (5 pages) → rate limit headers → quota endpoint → cleanup
- **Zero console errors, zero CSP violations**
- CSP en report-only — passage enforce prevu 2026-04-08 apres 48h monitoring

## Architecture validee

### Redis sliding window rate limiting (ZSET)

Pattern : une sorted set par `{role}:{user_id}:{minute_bucket}`. Chaque requete ajoute un membre `{timestamp}:{uuid[:8]}` avec score = timestamp. `ZREMRANGEBYSCORE` evince les entrees hors fenetre. `ZCARD` donne le count courant. Pipeline Redis (4 ops atomiques) pour minimiser les roundtrips.

Avantage vs compteur simple : pas de probleme aux frontieres de minute (pas de "burst 600 en 2 secondes autour du rollover"). La fenetre glissante est continue.

Fail-open : si Redis est down, la requete passe. Rate limiting est un mecanisme de protection, pas un mur de securite — mieux vaut servir que bloquer.

### Hard quota enforcement (402 vs 429)

Decision cle : **402 Payment Required** pour le depassement de quota LLM, **429 Too Many Requests** pour le rate limiting. La distinction est semantique :
- 429 = "reviens dans N secondes" (temporaire, mecanique)
- 402 = "ton budget est epuise" (business logic, upgrade possible)

`enforce_budget()` leve `QuotaExceededError` (custom exception → 402) au lieu de retourner un objet `{exceeded: bool}`. Pattern fail-fast : pas de code appelant qui oublie de checker le retour.

### CSP nonce via Next.js middleware

Next.js 15 App Router + `src/` directory : le `middleware.ts` doit etre dans `src/`, pas a la racine du projet. Le middleware genere un nonce UUID, l'injecte dans les request headers (`x-nonce`), le lit cote serveur dans `layout.tsx` via `headers()`. Le nonce est unique par requete — pas de cache, pas de replay.

`strict-dynamic` : les scripts charges par un script nonce sont automatiquement autorises. Evite de lister chaque chunk Next.js individuellement.

`style-src 'unsafe-inline'` : necessaire car TipTap/ProseMirror genere des styles inline (tiptap#6261, upstream non resolu). Compromis accepte — XSS via CSS est un vecteur faible compare a script injection.

### Matcher config : simple strings, pas d'objets

Le middleware matcher de Next.js 15 utilise `path-to-regexp` en interne. Les objets avec `{ type: "header", missing: [...] }` et `as const` provoquent des erreurs d'analyse statique au build. Solution : une simple regex string couvre 100% du besoin. KISS.

## Fichiers critiques

| Fichier | Role |
|---------|------|
| `apps/api/src/story_engine/middleware/rate_limit.py` | Sliding window Redis + exclusions + fail-open |
| `apps/api/src/story_engine/services/token_budget.py` | `enforce_budget()` + `get_reset_at()` + `check_budget()` |
| `apps/api/src/story_engine/api/routes/quota.py` | GET /api/v1/quota/llm |
| `apps/api/src/story_engine/api/routes/csp.py` | POST /api/v1/csp-report |
| `apps/api/src/story_engine/api/routes/audit.py` | GET /api/v1/audit-logs (RBAC + filters) |
| `apps/web/src/middleware.ts` | CSP nonce generation + report-only/enforce toggle |
| `apps/web/src/app/layout.tsx` | Nonce propagation via headers() → meta tag |
| `apps/api/src/story_engine/main.py` | App factory — tous les routers + rate_limit_middleware |

## Lecons transversales App Factory

1. **Redis ZSET sliding window** : pattern reutilisable pour tout rate limiting. Plus robuste que le compteur avec TTL (pas de burst aux frontieres). Candidat `app-factory-patterns`.
2. **402 vs 429 distinction** : semantique claire pour le frontend — 429 = retry automatique, 402 = afficher un message "quota epuise, upgrade". Pattern API a documenter.
3. **Fail-open rate limiting** : design defensif — le rate limiter ne doit jamais devenir un SPOF. Si Redis est down, mieux vaut servir sans limites que bloquer 100% du trafic.
4. **CSP middleware placement Next.js** : `src/middleware.ts` quand le projet utilise `src/app/`. Documentation Next.js ambigue — piege confirme.
5. **Matcher config : strings > objects** : le format objet avec `as const` et `missing` array provoque des build failures silencieuses (manifest vide). Regex string simple = fiable.
6. **enforce_budget() fail-fast** : lever une exception au lieu de retourner un booleen. Elimine la classe de bugs "j'ai oublie de checker le retour". Pattern applicable a toute validation business-critical.
7. **Audit fire-and-forget Taskiq** : `kiq()` sans `await` sur le result = zero impact latence. Le worker peut echouer sans affecter la reponse HTTP. Pattern pour tout logging/telemetrie non-critique.
8. **E2E Playwright sur prod** : register un compte test → tester tous les flows → cleanup. Autonome, pas besoin de credentials pre-existants. Pattern pour tout smoke test post-deploy.

## Metriques

| Metrique | Valeur |
|----------|--------|
| Phases | 5 |
| Plans GSD | 10 |
| Commits | ~30 |
| Tests ajoutes | ~50 |
| Temps total (overnight) | ~4h |
| Tags | v1.5.0-alembic, v1.5.1, v1.5.2, v1.5.3 |

## Prochaines etapes

1. **CSP enforce mode** : 2026-04-08, set `SE_CSP_ENFORCE=true` + redeploy
2. **Indexer ce REX** dans Qdrant `app-factory-rex`
3. **Update NocoDB** : 5 phases v1.5, project row `phases_completed` → 20
4. **Milestone v1.6** : Edition Pro + Claims Pipeline (rollback facts, promote, smart replace, claims table)
