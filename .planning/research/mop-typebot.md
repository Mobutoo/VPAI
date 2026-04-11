# Typebot — Validation pour NOC MOP Generator (Voie B)

**Date**: 2026-04-11
**Contexte**: Évaluation Typebot self-hosted comme drag-and-drop decision tree builder pour générer des MOP (Method of Procedure) en PDF via Gotenberg/Carbone. Alternative visuelle à n8n.

---

## 1. Version & Images Docker

- **Dernière version stable**: `v3.16.1` (publiée le 2026-04-09)
- **Images Docker Hub**:
  - `baptistearno/typebot-builder:3.16.1` (builder = éditeur visuel)
  - `baptistearno/typebot-viewer:3.16.1` (viewer = runtime chatbot)
- **Tags recommandés pour pin**: `3.16.1` ou `3.16` (minor-pinned). Éviter `:latest` (conforme convention repo).
- **ARM64**: Confirmé multi-arch — `amd64` ET `arm64` présents sur les tags `latest`, `3`, `3.16`, `3.16.1`.
- Source: Docker Hub API — `hub.docker.com/r/baptistearno/typebot-builder`

---

## 2. Self-Hosting — Docker Compose & Configuration

### Architecture: 2 services distincts

| Service | Port interne | Rôle |
|---|---|---|
| `typebot-builder` | 3000 (expose 8080) | Interface d'édition des flows |
| `typebot-viewer` | 3000 (expose 8081) | Runtime de présentation aux utilisateurs |

Les deux nécessitent des URLs HTTPS publiques distinctes (ex: `typebot.domain.com` + `bot.domain.com`).

### Variables d'environnement requises (builder)

| Variable | Requis | Description |
|---|---|---|
| `DATABASE_URL` | Oui | PostgreSQL DSN — `postgresql://user:pass@host:5432/dbname` |
| `ENCRYPTION_SECRET` | Oui | Clé 256-bit (32 chars), `openssl rand -base64 24` |
| `NEXTAUTH_URL` | Oui | URL publique builder: `https://typebot.domain.com` |
| `NEXT_PUBLIC_VIEWER_URL` | Oui | URL publique viewer: `https://bot.domain.com` |
| `SMTP_HOST` | Auth seul | Pour magic link email |
| `SMTP_PORT` | Auth seul | Défaut: 25 |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Auth seul | Credentials SMTP |
| `NEXT_PUBLIC_SMTP_FROM` | Auth seul | Adresse expéditeur |
| `REDIS_URL` | Optionnel | Rate limiting, uploads WhatsApp |
| `ADMIN_EMAIL` | Optionnel | Accès plan illimité pour cet email |
| `DISABLE_SIGNUP` | Optionnel | Bloquer les inscriptions après premier admin |

### PostgreSQL externe

Supporté nativement. Utiliser `DATABASE_URL` pointant vers l'instance existante (`{{ postgresql_host }}`). Aucune contrainte — Typebot gère ses propres migrations via Prisma.

**Attention**: nécessite une base dédiée (ex: `typebot`), pas partage de schéma avec n8n/LiteLLM.

---

## 3. Licence

- **Licence actuelle**: Functional Source License v1.1 (FSL-1.1-Apache-2.0) — "Fair Source"
- **Ce qui est autorisé**: Usage interne, self-hosting pour usage propre, modification du code
- **Ce qui est interdit**: Commercialiser l'accès à une instance Typebot, offrir du hosting Typebot comme service
- **Transition automatique**: Apache 2.0 deux ans après chaque release (code de 2024 est déjà Apache 2.0)
- **Verdict pour ce projet**: Usage interne NOC/MOP = **autorisé sans restriction commerciale**. Pas de problème pour self-hosting privé sur Sese-AI.
- Source: `github.com/baptisteArno/typebot.io/blob/main/LICENSE`

---

## 4. Capacités Decision Tree

### Branchements conditionnels
- **Condition blocks** (Logic): if/else visuel sur variables, réponses utilisateur, valeurs de webhook. Chaînable sans code.
- **Set Variable blocks**: stockage et manipulation de données à chaque étape.
- **Multi-page flows**: supporté — chaque groupe = page/étape du flow.

### Variables
- Variables persistantes sur toute la durée du flow. Injection dans URLs, corps de requêtes, messages.
- Capture des réponses API dans des variables pour branchements suivants.

### HTTP Request block (Webhook)
- Requêtes HTTP vers APIs externes (Gotenberg, Carbone, etc.)
- Corps JSON dynamique avec variables: `{"incident_id": "{{IncidentId}}", "perimeter": "{{Perimeter}}"}`
- Capture de la réponse dans des variables (ex: stocker l'URL du PDF retourné)
- Timeout par défaut 10s, configurable en "Advanced params"
- Méthodes HTTP: GET/POST supportés (headers et body custom documentés)
- **Limitation**: pas de support natif réponse binaire — le webhook doit retourner une URL, pas un blob PDF

### Retour PDF à l'utilisateur
- Pas de bloc "file download" natif dédié
- **Pattern recommandé**: HTTP Request block → capture URL PDF → Text bubble ou Embed bubble affiche le lien/iframe
- L'Embed bubble peut rendre un PDF via URL (Google Drive, hébergement direct)
- Pour un vrai bouton de téléchargement: injecter l'URL dans un message texte avec Markdown ou HTML personnalisé

---

## 5. Export/Import de Flows

- **Export JSON**: UI builder → menu (3 points, haut droite) → "Export flow" → fichier `.json`
- **Import JSON**: lors de la création d'un nouveau typebot → "Import a file"
- **Limitation import**: l'import crée un **nouveau** bot, il ne met pas à jour un bot existant
- **API programmatique**: API REST disponible (`/api/v1/typebots`). Un workflow n8n community démontre la synchronisation bidirectionnelle Typebot ↔ GitHub via l'API Typebot (export JSON + commit git automatisé)
- **Versionning git**: faisable via API — exporter les flows JSON + commit dans le repo VPAI
- Source: `docs.typebot.com/editor/export-import`, `n8n.io/workflows/5899`

---

## 6. Authentification Self-Hosted

- **Magic link email seul** (sans Google/GitHub): supporté — configurer SMTP uniquement
- Aucun provider OAuth externe obligatoire
- **Piège connu**: problèmes fréquents de non-envoi du magic link en self-hosted (issues GitHub #1279, #942) — tester SMTP dès le déploiement initial
- **DISABLE_SIGNUP**: activer après création du compte admin pour fermer l'inscription publique
- **ADMIN_EMAIL**: déverrouille le plan illimité pour l'email spécifié

---

## 7. Reverse Proxy Caddy

- Typebot tourne en HTTP non-chiffré sur les ports 3000 internes → Caddy gère TLS
- Aucun problème connu spécifique à Caddy documenté dans les sources officielles
- **Contrainte critique**: builder et viewer nécessitent **deux sous-domaines HTTPS distincts** (pas de path-based routing). Exemple: `typebot.ewutelo.cloud` + `bot.ewutelo.cloud`
- Headers à passer: standard proxy headers (`X-Forwarded-For`, `X-Real-IP`). Typebot est Next.js — pas de configuration spéciale requise.
- Selon convention VPAI (VPN-only): les deux sous-domaines peuvent être mis sous ACL VPN avec le snippet `(vpn_only)` habituel (2 CIDRs: VPN + docker frontend)

---

## 8. Points Bloquants / Risques

| Risque | Sévérité | Mitigation |
|---|---|---|
| Magic link SMTP fiable requis | Moyen | Tester avec Mailhog en dev, SMTP externe en prod |
| 2 sous-domaines distincts obligatoires | Faible | Provisionner `typebot.*` et `bot.*` dans Caddy + DNS |
| Import JSON = nouveau bot uniquement | Faible | Utiliser l'API pour sync git plutôt que l'UI |
| Pas de file download block natif | Faible | Retourner URL PDF via HTTP Request → Text bubble |
| License FSL (pas AGPL) | Aucun | Usage interne autorisé |

**Verdict**: Typebot est **viable** pour ce use case. Aucun blocage technique majeur. La limitation principale (retour PDF) se contourne via URL dans un Text bubble. Le double sous-domaine est la contrainte infra à prévoir.

---

## Sources

- [Docker Hub — baptistearno/typebot-builder](https://hub.docker.com/r/baptistearno/typebot-builder)
- [Typebot Self-Hosting Docker Docs](https://docs.typebot.com/self-hosting/deploy/docker)
- [Typebot Configuration Docs](https://docs.typebot.com/self-hosting/configuration)
- [Typebot License (FSL-1.1)](https://github.com/baptisteArno/typebot.io/blob/main/LICENSE)
- [Typebot is now Fair Source (blog)](https://www.typebot.com/blog/typebot-is-now-fair-source)
- [HTTP Request Block Docs](https://docs.typebot.com/editor/blocks/integrations/http-request)
- [Export/Import Docs](https://docs.typebot.com/editor/export-import)
- [n8n workflow — Typebot ↔ GitHub sync](https://n8n.io/workflows/5899-automatic-typebot-flows-two-way-sync-with-github-using-typebot-api/)
- [GitHub Releases — typebot.io](https://github.com/baptisteArno/typebot.io/releases)
