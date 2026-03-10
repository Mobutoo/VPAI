# Strategie domaines — paultaffe.com / .net / .fr

> Acquis chez OVH le 2025-03-10. Remplacent jemeforme.ai a terme.

## Principe

| Domaine | Role | Public |
|---------|------|--------|
| **paultaffe.com** | Vitrine commerciale + app client | Oui |
| **paultaffe.net** | Infrastructure technique / ops | Non |
| **paultaffe.fr** | SEO France + isolation client (sous-domaines per-client) | Oui |

### Pourquoi isoler les clients sur le .fr ?

Les sous-domaines clients (`{client_id}.paultaffe.fr`) hebergent du contenu
et des services controles par les clients (agents, webhooks, API).
En cas de compromission, spam ou abus sur un compte client :

- La reputation DNS/IP du `.com` (marque commerciale) est **protegee**
- Les blacklists DNS affectent le `.fr` mais pas le site vitrine ni le support
- Le `.com` reste propre pour les emails commerciaux (delivrabilite Brevo)
- On peut suspendre le wildcard `*.paultaffe.fr` sans impact sur l'activite

### Strategie SEO multi-domaines

Le `.fr` dispose de sa propre landing page (pas de redirection 301 vers .com).

**Pourquoi ne pas rediriger ?**

- Un ccTLD `.fr` beneficie d'un bonus de classement dans les recherches
  Google.fr (signal geographique fort)
- Une landing page propre permet de cibler des mots-cles differents
  ("cloud souverain", "hebergement France", "IaaS conforme RGPD")
- Consolider tout sur le `.com` gaspillerait l'avantage SEO du ccTLD

**Positionnement par domaine :**

| Domaine | Angle SEO | Cible |
|---------|-----------|-------|
| paultaffe.com | "IaaS for agencies", marque internationale | Monde francophone |
| paultaffe.fr | "Cloud souverain France", conformite RGPD, proximite | France metropolitaine |

**Configuration technique :**

- `hreflang` croise entre les deux domaines :
  - `.com` : `<link rel="alternate" hreflang="x-default" href="https://paultaffe.com/" />`
  - `.fr` : `<link rel="alternate" hreflang="fr-FR" href="https://paultaffe.fr/" />`
  - Chaque domaine reference l'autre via hreflang
- `robots.txt` propre a chaque domaine (pas de noindex sur le .fr)
- Sitemap distinct par domaine

### Referencement IA — Generative Engine Optimization (GEO)

Les moteurs de recherche IA (ChatGPT Search, Perplexity, Google AI Overviews,
Mistral Le Chat) remplacent progressivement les requetes Google classiques.
Etre cite dans une reponse IA = visibilite directe sans clic.

**Pourquoi c'est critique pour un IaaS :**

Les prospects posent des questions comme "quel hebergeur cloud souverain en France"
ou "alternative europeenne a AWS pour agences". Si Paul Taffe n'apparait pas
dans les reponses IA, il n'existe pas pour cette audience.

**Actions par domaine :**

| Domaine | Action GEO | Objectif |
|---------|-----------|----------|
| paultaffe.com | `llms.txt` + `llms-full.txt` a la racine | Fournir aux LLMs un resume structure de l'offre |
| paultaffe.com | Schema.org `Organization` + `Product` + `Service` | Donnees structurees lisibles par les crawlers IA |
| paultaffe.com | Page `/about` avec faits citables (chiffres, specs) | Favoriser les citations dans les reponses IA |
| paultaffe.fr | `llms.txt` specifique marche francais | Cibler les requetes en francais sur la souverainete |
| terrasse.paultaffe.com | Contenu FAQ structure (question → reponse) | Format ideal pour extraction par les LLMs |

**Fichier `llms.txt` (standard emergent) :**

Fichier texte a la racine du site, lisible par les LLMs qui crawlent le web.
Format inspire de robots.txt mais destine aux modeles de langage.

```
# paultaffe.com/llms.txt

> Paul Taffe est un fournisseur IaaS europeen specialise dans
> le cloud souverain pour agences digitales et PME francophones.

## Offre
- Infrastructure as a Service (IaaS) sur serveurs Hetzner en Allemagne
- VM dediees par client (isolation totale, pas de multi-tenant)
- Stack pre-configuree : Docker, monitoring, backup, VPN
- Support inclus via ticketing (Zammad) et base de connaissance (Discourse)

## Marche
- Cible : agences digitales, ESN, PME francophones
- Zones : France, Belgique, Suisse, Afrique francophone, Quebec
- Conformite : RGPD, donnees hebergees en UE exclusivement

## Liens
- Site : https://paultaffe.com
- Documentation : https://docs.paultaffe.com
- Status : https://status.paultaffe.com
- Support : https://help.paultaffe.com

## Contact
- Email : hello@paultaffe.com

## Documentation detaillee
- [Documentation complete](https://paultaffe.com/llms-full.txt)
```

**Schema.org (JSON-LD) sur paultaffe.com :**

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Paul Taffe",
  "url": "https://paultaffe.com",
  "description": "Fournisseur IaaS europeen — cloud souverain pour agences et PME",
  "foundingDate": "2025",
  "areaServed": ["FR", "BE", "CH", "CA", "SN", "CI", "MA"],
  "knowsAbout": ["IaaS", "Cloud souverain", "RGPD", "Docker", "Infrastructure"],
  "hasOfferCatalog": {
    "@type": "OfferCatalog",
    "name": "Offres IaaS",
    "itemListElement": [
      {
        "@type": "Offer",
        "name": "VM Sovereign",
        "description": "VM dediee isolee avec stack pre-configuree"
      }
    ]
  }
}
```

**Bonnes pratiques GEO :**

- Ecrire du contenu **factuel et citable** (chiffres, comparaisons, specs techniques)
- Utiliser des **listes a puces et tableaux** (format prefere des LLMs pour extraction)
- Inclure des **questions-reponses explicites** dans les pages docs/FAQ
- Publier des **articles de blog techniques** (guides, benchmarks, comparatifs)
  qui peuvent etre references comme source par les IA
- Eviter le contenu marketing vague — les LLMs privilegient les sources
  qui donnent des reponses precises
- Mettre a jour `llms.txt` a chaque evolution de l'offre

**Monitoring GEO :**

| Outil | Usage | Frequence |
|-------|-------|-----------|
| Perplexity.ai | Tester les requetes cibles et verifier si Paul Taffe apparait | Hebdomadaire |
| ChatGPT (web browsing) | Memes requetes, verifier les citations | Hebdomadaire |
| Google AI Overviews | Verifier la presence dans les reponses enrichies | Hebdomadaire |
| Search Console | Suivre les impressions et clics depuis Google | Quotidien |

**Requetes cibles a monitorer :**

- "hebergeur cloud souverain France"
- "alternative europeenne AWS"
- "IaaS RGPD conforme"
- "hebergement agence digitale France"
- "cloud prive PME Europe"
- "infrastructure Docker managee"

---

## paultaffe.com — Marque commerciale

Tout ce que Paul Taffe controle directement. Reputation protegee.

| Sous-domaine | Service | VM | Remplace |
|---|---|---|---|
| `paultaffe.com` | Site vitrine / landing page | — | *nouveau* |
| `app.paultaffe.com` | Dashboard client (portail unifie) | Service Desk | `portail.jemeforme.ai` |
| `help.paultaffe.com` | Zammad (ticketing) | Service Desk | `help.jemeforme.ai` |
| `terrasse.paultaffe.com` | Discourse (forum communaute — "La Terrasse") | Service Desk | `agence.jemeforme.ai` |
| `status.paultaffe.com` | Gatus (status page) | Service Desk | `status.jemeforme.ai` |
| `api.paultaffe.com` | API publique (provisioning) | Master | *Phase 3* |

## paultaffe.net — Infrastructure ops

Acces restreint, usage interne et ops uniquement.

| Sous-domaine | Service | VM | Remplace |
|---|---|---|---|
| `vpn.paultaffe.net` | NetBird management | Master | `netbird.jemeforme.ai` |
| `auth.paultaffe.net` | Zitadel SSO | Master | `auth.jemeforme.ai` |
| `monitor.paultaffe.net` | Grafana / VictoriaMetrics | Master | — |
| `chat.paultaffe.net` | Revolt (comms internes) | Master | `chat.jemeforme.ai` |
| `registry.paultaffe.net` | Docker Registry cache | Gateway | — |
| `n8n.paultaffe.net` | Workflows ops | Master | — |
| `admin.paultaffe.net` | NocoDB (admin flotte) | Master | — |

## paultaffe.fr — Landing France + sous-domaines clients

### Landing page (racine)

`paultaffe.fr` sert une landing page SEO dediee au marche francais.
Angle : cloud souverain, RGPD, datacenter Hetzner/OVH en Europe.
Tout sous-domaine non identifie redirige vers `paultaffe.com`.

### Sous-domaines clients (isoles)

Chaque client recoit `{client_id}.paultaffe.fr` et `*.{client_id}.paultaffe.fr`.
Le trafic client pointe **directement vers la VM Sovereign** (pas via Gateway).

**Pourquoi direct et pas via Gateway ?**

Le wildcard DNS `*.paultaffe.fr` ne matche qu'un seul niveau de sous-domaine
(RFC 4592). Il matche `acme42.paultaffe.fr` mais PAS `api.acme42.paultaffe.fr`.
Pour les sub-subdomaines, il faut un wildcard per-client `*.acme42.paultaffe.fr`.
Puisqu'on cree des records DNS par client au provisioning de toute facon, autant
pointer directement vers la VM Sovereign — zero hop supplementaire, client autonome.

**Records DNS crees au provisioning (via API OVH) :**

```
# Crees automatiquement par le Master a POST /api/studios
acme42             A    <IP_SOVEREIGN>     # base domain client
*.acme42           A    <IP_SOVEREIGN>     # wildcard sub-subdomains
```

**Routing : Sovereign Caddy (direct, auto-TLS Let's Encrypt) :**

| Sous-domaine | Service | Qui configure |
|---|---|---|
| `acme42.paultaffe.fr` | Landing client (optionnel) | Ansible (base) |
| `agent.acme42.paultaffe.fr` | Flash Agent (API client) | Ansible (base) |
| `flow.acme42.paultaffe.fr` | Activepieces (workflows) | Ansible (base) |
| `llm.acme42.paultaffe.fr` | LiteLLM (proxy multi-LLM) | Ansible (base) |
| `hooks.acme42.paultaffe.fr` | Webhooks entrants | Client (custom) |
| `api.acme42.paultaffe.fr` | API custom du client | Client (custom) |
| `n8n.acme42.paultaffe.fr` | n8n (installe par le client) | Client (custom) |
| `scraper.acme42.paultaffe.fr` | Service de scraping | Client (custom) |

Les sub-subdomains "Client (custom)" sont configures par le client via des
fichiers Caddyfile dans `/mnt/data/caddy/custom/*.caddy` (import automatique).

### Domaines personnalises (custom domains)

Un client peut utiliser son propre nom de domaine en plus de `*.{client_id}.paultaffe.fr`.

**Procedure client :**

1. Le client ajoute un record DNS sur son propre domaine :
   `api.mycorp.com  A  <IP_SOVEREIGN>`  (l'IP est dans son dashboard)
2. Le client cree un fichier `/mnt/data/caddy/custom/mycorp.caddy` :
   ```
   api.mycorp.com {
       reverse_proxy localhost:9000
   }
   ```
3. Caddy auto-provisionne le certificat TLS (Let's Encrypt HTTP-01)
4. Le domaine est operationnel en < 2 minutes, aucune intervention Flash Studio

**Architecture Caddyfile Sovereign :**

```
/etc/caddy/Caddyfile                    ← Base (gere par Ansible, read-only)
  │
  ├── acme42.paultaffe.fr { ... }       ← Services de base (openclaw, activepieces...)
  ├── flow.acme42.paultaffe.fr { ... }
  ├── llm.acme42.paultaffe.fr { ... }
  │
  └── import /mnt/data/caddy/custom/*.caddy  ← Custom (gere par le client)
        │
        ├── hooks.caddy                  ← hooks.acme42.paultaffe.fr
        ├── api.caddy                    ← api.acme42.paultaffe.fr
        └── mycorp.caddy                 ← api.mycorp.com (domaine perso)
```

**Contraintes custom domains :**

- Le client est responsable de son DNS (record A ou CNAME vers IP Sovereign)
- Le certificat TLS est provisionne automatiquement par Caddy (Let's Encrypt)
- Le CAA record du domaine client doit autoriser `letsencrypt.org` (ou etre absent)
- Flash Studio ne fournit pas de support DNS pour les domaines custom
- En cas de suspension client, les domaines custom cessent de repondre (Sovereign eteint)

### Securite

- Wildcard `*.paultaffe.fr` sur la Gateway = **parking/catch-all** pour les clients
  non-provisionnes ou en sommeil. Tout sous-domaine inconnu → page parking
- Records per-client (`acme42`, `*.acme42`) → direct vers Sovereign : client autonome
- Caddy TLS On-Demand avec `ask` endpoint sur la Gateway pour valider les domaines
  contre la liste des clients actifs (empeche l'abus de certificats)
- Les Sovereign n'ont PAS de TLS On-Demand (pas de wildcard catch-all) :
  seuls les domaines explicites dans le Caddyfile obtiennent un certificat
- Isolation par client : suspension possible sans impacter les autres
- Pas d'email envoye depuis le `.fr` — zero impact reputation Brevo

---

## Emails (Brevo)

| Type | Domaine | Adresse | Usage |
|------|---------|---------|-------|
| Commercial | paultaffe.com | `hello@paultaffe.com` | Marketing, newsletters, onboarding |
| Transactionnel | paultaffe.com | `noreply@paultaffe.com` | Notifications, alertes tickets, confirmations |
| Ops interne | paultaffe.net | `ops@paultaffe.net` | Alertes monitoring, CI/CD, Telegram fallback |

**paultaffe.fr n'envoie jamais de mail** — pas de SPF/DKIM configure.

### Authentification email

Configurer sur Brevo pour les 2 domaines expediteurs :

- **SPF** : `v=spf1 include:sendinblue.com ~all`
- **DKIM** : cle fournie par Brevo
- **DMARC** : `v=DMARC1; p=quarantine; rua=mailto:dmarc@paultaffe.com`

---

## Gestion DNS

### Registrar : OVH

Les 3 domaines sont chez OVH. Deux options pour le DNS :

| Option | Avantage | Inconvenient |
|--------|----------|--------------|
| **A. DNS chez OVH** + plugin Caddy `caddy-dns/ovh` | Tout centralise chez OVH | Changer le plugin Caddy (actuellement namecheap) |
| **B. Deleguer NS vers Namecheap** | Garder le setup Caddy actuel | DNS split entre 2 providers |

**Recommandation : Option A** — migrer vers `caddy-dns/ovh` (deja utilise dans mobutoo-infra).

### Variables Ansible

```yaml
# inventory/hosts.yml — apres migration
domain_base: "paultaffe.com"        # marque commerciale
infra_domain: "paultaffe.net"       # infrastructure ops
client_domain: "paultaffe.fr"       # sous-domaines clients (isole)
```

### Records DNS a creer

#### paultaffe.com (OVH)

```
@              A      <IP_SERVICE_DESK>      # site vitrine
app            A      <IP_SERVICE_DESK>
help           A      <IP_SERVICE_DESK>
terrasse       A      <IP_SERVICE_DESK>
status         A      <IP_SERVICE_DESK>
api            A      <IP_MASTER>
```

#### paultaffe.net (OVH)

```
vpn            A      <IP_MASTER>
auth           A      <IP_MASTER>
monitor        A      <IP_MASTER>
chat           A      <IP_MASTER>
n8n            A      <IP_MASTER>
admin          A      <IP_MASTER>
registry       A      <IP_GATEWAY>
```

#### paultaffe.fr (OVH)

```
# Records statiques (crees manuellement)
@              A      <IP_GATEWAY>           # landing page France SEO
*              A      <IP_GATEWAY>           # catch-all → parking page (clients inconnus/en sommeil)

# Records dynamiques (crees par Master API au provisioning de chaque client)
# Exemple pour le client "acme42" :
acme42         A      <IP_SOVEREIGN_ACME42>  # base domain client
*.acme42       A      <IP_SOVEREIGN_ACME42>  # wildcard sub-subdomains (hooks, api, n8n...)
```

**Resolution DNS (priorite) :**
- `api.acme42.paultaffe.fr` → matche `*.acme42` → direct Sovereign ✅
- `acme42.paultaffe.fr` → matche `acme42` (explicite, priorite sur `*`) → direct Sovereign ✅
- `inconnu.paultaffe.fr` → matche `*` (catch-all) → Gateway → parking page

---

## Strategie geographique (GEO)

### Localisation infrastructure actuelle

| VM | Datacenter | Localisation | Latence France |
|----|-----------|--------------|----------------|
| Master | Hetzner `nbg1-dc3` | Nuremberg, Allemagne | ~15 ms |
| Gateway | Hetzner `nbg1-dc3` | Nuremberg, Allemagne | ~15 ms |
| Service Desk | Hetzner `nbg1-dc3` | Nuremberg, Allemagne | ~15 ms |
| Sovereign (client) | Hetzner `nbg1` ou `fsn1` | Nuremberg / Falkenstein, Allemagne | ~15 ms |

Tous les serveurs sont en **UE (Allemagne)** — conforme RGPD, pas de transfert hors UE.

### Souverainete des donnees

| Exigence | Statut | Detail |
|----------|--------|--------|
| Donnees en UE | OK | Hetzner datacenters en Allemagne et Finlande |
| Pas de transfert hors UE | OK | Aucun service cloud US (pas d'AWS/GCP/Azure) |
| Sous-traitant RGPD | A formaliser | DPA (Data Processing Agreement) avec Hetzner |
| Hebergeur HDS (sante) | Non | Hetzner n'est pas certifie HDS — exclure les clients sante |
| SecNumCloud (ANSSI) | Non | Pas requis pour le marche cible (PME/agences) |

### Strategie CDN

Pour les assets statiques (landing pages .com et .fr, docs, status page) :

| Option | Avantage | Inconvenient |
|--------|----------|--------------|
| **A. Pas de CDN** | Simple, zero cout | Latence ~15 ms depuis la France (acceptable) |
| **B. Bunny CDN** (UE) | PoPs europeens, RGPD-friendly, pas cher | Service supplementaire a gerer |
| **C. Cloudflare proxy** | CDN + DDoS gratuit | Donnees transitent par infra US (RGPD discutable) |

**Recommandation : Option A** pour le lancement (latence Hetzner DE → France deja excellente).
Passer a l'option B si la base client s'etend hors Europe ou si le trafic augmente.

### Routage geographique des clients

Les VM Sovereign des clients sont provisionnees dans le datacenter le plus proche :

| Marche client | Datacenter Hetzner | Location |
|---------------|--------------------|----------|
| France / Europe Ouest | `nbg1` (Nuremberg) | Allemagne |
| Europe Nord | `hel1` (Helsinki) | Finlande |
| USA (futur) | `ash` (Ashburn) | Virginie, USA |

Le choix du datacenter est stocke dans la config client et utilise
par le playbook Ansible lors du provisioning :

```yaml
# Exemple group_vars client
sovereign_datacenter: "nbg1-dc3"    # ou hel1-dc2, ash-dc1
sovereign_location: "nbg1"          # pour les volumes
```

### DNS et geo-routing

| Domaine | Strategie DNS |
|---------|---------------|
| paultaffe.com | A record unique → IP Service Desk (Nuremberg) |
| paultaffe.net | A record unique → IP Master (Nuremberg) |
| paultaffe.fr (racine) | A record → IP Gateway (Nuremberg) |
| `*.paultaffe.fr` (catch-all) | Wildcard → IP Gateway (Nuremberg) → parking page |
| `{client}.paultaffe.fr` | A record explicite → IP Sovereign du client (direct) |
| `*.{client}.paultaffe.fr` | Wildcard per-client → IP Sovereign du client (direct) |
| `custom.client.com` | A record gere par le client → IP Sovereign du client (direct) |

Le trafic client va **directement vers la VM Sovereign** (pas via Gateway).
Le wildcard `*.paultaffe.fr` sur la Gateway ne sert que de catch-all pour
les clients non-provisionnes ou en sommeil (page parking).

**Avantages du routage direct :**
- Zero latence supplementaire (pas de hop Gateway)
- Client autonome : configure ses sub-subdomains et domaines custom sans Flash Studio
- Pas de SPOF : si la Gateway tombe, le trafic client continue de fonctionner
- Philosophie IaaS : le client controle son infrastructure

**Evolution future** : si le trafic justifie un Gateway par region (Helsinki),
il suffira de provisionner les Sovereign dans la bonne region — le trafic
est deja direct, pas de geo-routing necessaire sur la Gateway.

### Conformite geo par marche

| Marche | Exigences | Domaine a utiliser |
|--------|-----------|-------------------|
| France | RGPD, AFNIC, donnees en UE | paultaffe.fr |
| UE hors France | RGPD, donnees en UE | paultaffe.com |
| Suisse | LPD (equiv. RGPD), donnees en UE accepte | paultaffe.com |
| Afrique francophone | Pas de contrainte locale stricte | paultaffe.com |
| Canada (Quebec) | Loi 25 (privacy), donnees hors CA accepte si consent | paultaffe.com |

---

## Securite DNS

### DNSSEC

Activer DNSSEC sur les 3 domaines chez OVH (support natif).
Protege contre le DNS spoofing et le cache poisoning.

### CAA Records

Restreindre les autorites de certification autorisees a emettre des certificats :

```
# Sur les 3 domaines
@   CAA   0 issue "letsencrypt.org"
@   CAA   0 issuewild "letsencrypt.org"
@   CAA   0 iodef "mailto:security@paultaffe.com"
```

### Protection anti-transfert

- **Verrou de transfert** active sur les 3 domaines chez OVH
- **WHOIS privacy** active (gratuit chez OVH pour .com et .net)
- Note : `.fr` impose les coordonnees du titulaire via AFNIC (pas de WHOIS privacy complet)

---

## Monitoring et renouvellement

### Renouvellement automatique

Activer le renouvellement automatique chez OVH pour les 3 domaines.
Configurer une alerte 90 jours, 30 jours et 7 jours avant expiration.

### Monitoring DNS

| Check | Outil | Frequence |
|-------|-------|-----------|
| Resolution DNS (A records) | Gatus | 5 min |
| Expiration TLS (certificats Let's Encrypt) | Gatus endpoint SSL | 12h |
| Expiration domaines | Alerte OVH + check cron | Quotidien |
| DNSSEC validation | Gatus ou cron externe | Quotidien |
| Blacklist check (IP/domaine) | MXToolbox ou cron | Hebdomadaire |

### Monitoring certificats TLS

Ajouter dans Gatus les checks suivants :

```yaml
- name: "TLS paultaffe.com"
  url: "https://paultaffe.com"
  conditions:
    - "[CERTIFICATE_EXPIRATION] > 720h"

- name: "TLS paultaffe.fr"
  url: "https://paultaffe.fr"
  conditions:
    - "[CERTIFICATE_EXPIRATION] > 720h"
```

---

## Gouvernance des sous-domaines

### Convention de nommage

| Type | Pattern | Exemple |
|------|---------|---------|
| Service interne | `{service}.paultaffe.net` | `monitor.paultaffe.net` |
| Service client-facing | `{service}.paultaffe.com` | `help.paultaffe.com` |
| Client (base) | `{client_id}.paultaffe.fr` | `acme42.paultaffe.fr` |
| Client (sub-service) | `{service}.{client_id}.paultaffe.fr` | `api.acme42.paultaffe.fr` |
| Client (custom domain) | domaine du client | `api.mycorp.com` |

**Sub-subdomains pre-configures (Ansible) :**

| Sub-subdomain | Service |
|---------------|---------|
| `agent.{client_id}.paultaffe.fr` | Flash Agent API |
| `flow.{client_id}.paultaffe.fr` | Activepieces |
| `llm.{client_id}.paultaffe.fr` | LiteLLM |
| `vault.{client_id}.paultaffe.fr` | Vaultwarden |
| `monitor.{client_id}.paultaffe.fr` | Grafana |
| `finance.{client_id}.paultaffe.fr` | Firefly III |

**Sub-subdomains custom (client configure) :**

| Sub-subdomain | Service |
|---------------|---------|
| `hooks.{client_id}.paultaffe.fr` | Webhooks entrants |
| `api.{client_id}.paultaffe.fr` | API custom |
| `n8n.{client_id}.paultaffe.fr` | n8n (installe par le client) |
| `scraper.{client_id}.paultaffe.fr` | Service de scraping |
| `{custom}.{client_id}.paultaffe.fr` | N'importe quel service |

### Regles

- Les `client_id` doivent etre alphanumeriques + tirets (regex: `^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$`)
- Les sous-domaines reserves sont interdits aux clients : `www`, `mail`, `ftp`, `admin`, `status`
- Le endpoint `ask` de Caddy TLS On-Demand sur la Gateway valide contre la liste des clients actifs
- Les domaines custom sont configures par le client (DNS A record + fichier Caddyfile custom)
- Flash Studio ne gere PAS le DNS des domaines custom — responsabilite du client

---

## Reception email (MX)

Meme si on envoie via Brevo, il faut pouvoir **recevoir** des emails
(reponses clients, bounces, abuse reports).

| Domaine | Solution MX | Usage |
|---------|-------------|-------|
| paultaffe.com | OVH MX ou Brevo inbound | Recevoir reponses, support, abuse@ |
| paultaffe.net | OVH MX ou forward | Recevoir alertes ops, postmaster@ |
| paultaffe.fr | Pas de MX (ou null MX) | Aucun email attendu |

### Adresses obligatoires (RFC 2142)

```
postmaster@paultaffe.com   → forward ops
abuse@paultaffe.com        → forward ops
security@paultaffe.com     → forward ops
postmaster@paultaffe.net   → ops inbox
```

---

## Conformite legale

### Mentions obligatoires (.fr — AFNIC)

Le `.fr` est soumis a la reglementation AFNIC :
- Le titulaire doit etre identifiable (personne morale ou physique en UE)
- Les coordonnees du titulaire sont publiques dans le WHOIS AFNIC
- Mentions legales sur la landing page paultaffe.fr (CGU, editeur, hebergeur)

### RGPD

- Banniere cookies sur paultaffe.com et paultaffe.fr
- Politique de confidentialite accessible sur les deux domaines
- Les sous-domaines clients heritent de la politique du client
  (responsabilite du sous-traitant a definir dans les CGU)

---

## Plan de migration depuis jemeforme.ai

| Phase | Action | Delai |
|-------|--------|-------|
| 1. DNS | Creer tous les records A/CNAME sur paultaffe.com, .net et .fr chez OVH | J+0 |
| 2. Brevo | Authentifier paultaffe.com et paultaffe.net (SPF/DKIM/DMARC) | J+0 |
| 3. Caddy | Remplacer `caddy-dns/namecheap` par `caddy-dns/ovh` dans les Dockerfiles | J+1 |
| 4. Ansible | Mettre a jour `domain_base`, `infra_domain`, `client_domain` | J+1 |
| 5. Deploiement | Redeployer Master, Gateway, Service Desk avec les nouveaux domaines | J+1 |
| 6. Coexistence | Garder jemeforme.ai avec redirects 301 | J+1 → J+180 |
| 7. SEO .fr | Deployer landing page paultaffe.fr + hreflang + sitemap | J+7 |
| 8. Deprecation | Supprimer jemeforme.ai (ne pas renouveler) | J+365 |

### Redirects de coexistence (Caddy)

```caddyfile
# Pendant la periode de transition (6 mois)
help.jemeforme.ai {
    redir https://help.paultaffe.com{uri} permanent
}
agence.jemeforme.ai {
    redir https://docs.paultaffe.com{uri} permanent
}
status.jemeforme.ai {
    redir https://status.paultaffe.com{uri} permanent
}
portail.jemeforme.ai {
    redir https://app.paultaffe.com{uri} permanent
}
netbird.jemeforme.ai {
    redir https://vpn.paultaffe.net{uri} permanent
}
auth.jemeforme.ai {
    redir https://auth.paultaffe.net{uri} permanent
}
*.jemeforme.ai {
    redir https://{labels.1}.paultaffe.fr{uri} permanent
}
```

---

## Axes futurs

- **DNS secondaire** : ajouter un provider DNS secondaire (ex: Cloudflare en secondaire)
  pour la resilience en cas de panne OVH DNS
- **PTR records** (reverse DNS) : configurer sur les IP Hetzner pour
  ameliorer la delivrabilite email (`mail.paultaffe.com` → IP)
- **Sous-domaine staging** : `staging.paultaffe.net` pour les previews de deploiement
- **Domain age SEO** : commencer a publier du contenu sur .com et .fr des maintenant
  pour accumuler de l'anciennete de domaine avant le lancement commercial
