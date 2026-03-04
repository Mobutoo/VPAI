# Design — Seko-Finance AI Dashboard (Application Next.js)

**Date** : 2026-03-04
**Auteur** : Claude Opus 4.6 + Sekoul
**Statut** : Approuve
**Scope** : Application Next.js complete (5 phases) — repo separe `Mobutoo/seko-finance`

---

## 1. Contexte

L'infrastructure Ansible pour deployer Seko-Finance est 100% prete dans VPAI :
- Role `seko-finance` (env file, handler, molecule)
- Docker Compose (container, reseaux, healthcheck, limites)
- Caddy reverse proxy VPN-only sur `nzimbu.ewutelo.cloud`
- DNS OVH configure
- Vault avec `vault_firefly_pat` (a remplir apres premier boot Firefly)

Il reste a **construire l'application Next.js** qui sera packagee en image Docker et pushee sur GHCR.

### Documents de reference

- PRD Seko-Finance v1.0 (Mars 2026)
- Design doc infrastructure : `docs/plans/2026-03-04-sure-to-firefly-design.md`

---

## 2. Decisions

| Decision | Choix | Raison |
|----------|-------|--------|
| Repo | `Mobutoo/seko-finance` (nouveau, prive) | Separation des concerns — VPAI = infra, seko-finance = app |
| Package manager | pnpm | Rapide, disk-efficient, lockfile strict |
| Architecture | Hybride (Server + Client Components) | First paint rapide + interactions fluides |
| Data fetching | TanStack Query v5 (client) + fetch direct (serveur) | Cache, pagination, refetch automatique |
| Chat SDK | Vercel AI SDK (`ai` + `@ai-sdk/openai`) | Compatible LiteLLM (OpenAI-format), streaming natif |
| Charts | Tremor Raw + Recharts | Headless, customisable, coherent avec Tailwind v4 |
| APIs externes | ECB (taux) + Yahoo Finance (bourse) | ECB gratuit/officiel, Yahoo pour les projections |
| CI/CD | GitHub Actions → GHCR | Build sur push to main, image taguee sha + latest |
| Tests | Vitest (unit) + Playwright (E2E) | Standard Next.js, rapide, fiable |

---

## 3. Architecture globale

```
                    VPN-only (Caddy ACL)
                           |
          +----------------+----------------+
          |                                 |
  nzimbu.ewutelo.cloud             lola.ewutelo.cloud
  (Seko-Finance Dashboard)         (Firefly III Admin)
          |                                 |
          v                                 v
  +---------------+               +---------------+
  | seko-finance  |               |  firefly-iii  |
  |  (port 3000)  |--/api/v1/*-->|  (port 8080)  |
  |  Next.js 15   |               |  Laravel/PHP  |
  +-------+-------+               +-------+-------+
          |                                |
          |         backend net            |
          +--------(172.20.2.0/24)---------+
          |                |               |
     +----+----+    +------+------+   +----+----+
     |   PG    |    |   Redis     |   | LiteLLM |
     | shared  |    |   shared    |   | (chat)  |
     +---------+    +-------------+   +---------+
```

### Data flow

1. **Server Components** fetchen Firefly III directement (serveur → serveur, pas de proxy)
2. **Client Components** passent par `/api/firefly/[...path]` (proxy qui ajoute le Bearer token)
3. **TanStack Query** cache les reponses client-side (`staleTime: 5min`, `refetchOnWindowFocus: true`)
4. **Chat** passe par `/api/chat` → LiteLLM (streaming SSE via Vercel AI SDK)

---

## 4. Repo Structure

```
seko-finance/
├── .github/workflows/
│   └── docker-publish.yml        # Build → GHCR on push to main
├── Dockerfile                    # Multi-stage (deps → builder → runner)
├── docker-compose.yml            # Dev local
├── .env.example
├── pnpm-lock.yaml
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── public/
│   └── fonts/                    # Geist Variable + Geist Mono
├── src/
│   ├── app/
│   │   ├── layout.tsx            # RootLayout (sidebar, providers, fonts)
│   │   ├── page.tsx              # Redirect → /dashboard
│   │   ├── globals.css           # CSS variables, Tailwind imports
│   │   ├── api/
│   │   │   ├── firefly/[...path]/route.ts   # Proxy transparent Firefly III
│   │   │   ├── chat/route.ts                # Chat IA (Vercel AI SDK)
│   │   │   └── health/route.ts              # Healthcheck Docker
│   │   ├── dashboard/page.tsx
│   │   ├── transactions/page.tsx
│   │   ├── budgets/page.tsx
│   │   ├── analytics/page.tsx
│   │   ├── projections/
│   │   │   ├── page.tsx                     # Hub (cards cliquables)
│   │   │   ├── immobilier/page.tsx
│   │   │   └── vehicule/page.tsx
│   │   ├── chat/page.tsx
│   │   └── settings/page.tsx
│   ├── components/
│   │   ├── layout/               # Sidebar, AppShell, PageHeader
│   │   ├── ui/                   # KPICard, DataTable, FilterBar, Card
│   │   ├── charts/               # Chart wrappers (AreaChart, DonutChart, etc.)
│   │   └── chat/                 # ChatWidget, ChatMessage, ChatInput
│   ├── hooks/
│   │   ├── use-firefly.ts        # TanStack Query hooks
│   │   └── use-chat.ts           # Vercel AI SDK useChat wrapper
│   ├── lib/
│   │   ├── firefly-client.ts     # Server-side Firefly fetch helper
│   │   ├── formatters.ts         # Currency, date, percentage
│   │   ├── calculations.ts       # Immo/vehicule calculations pures
│   │   └── constants.ts          # System prompt, chart colors
│   └── types/
│       └── firefly.ts            # TypeScript types Firefly III API v1
├── tests/
│   ├── unit/                     # Vitest
│   └── e2e/                      # Playwright
└── PRD.md
```

---

## 5. Tech Stack

### Dependencies

| Package | Version | Usage |
|---------|---------|-------|
| `next` | 15.x | Framework |
| `react` / `react-dom` | 19.x | UI |
| `@tremor/react` | latest (Raw) | Composants dashboard headless |
| `recharts` | ^2.15 | Engine de graphiques |
| `@radix-ui/react-*` | latest | Dialog, Select, Tabs, Tooltip |
| `@tanstack/react-query` | ^5.x | Cache/fetch client |
| `ai` | ^4.x | Vercel AI SDK (streaming chat) |
| `@ai-sdk/openai` | ^1.x | Provider LiteLLM (OpenAI-compatible) |
| `framer-motion` | ^12.x | Animations (fade-in, slide-up) |
| `date-fns` | ^4.x | Formatage dates (locale fr) |
| `tailwindcss` | ^4.x | Styles |
| `clsx` + `tailwind-merge` | latest | Class merging |
| `yahoo-finance2` | ^2.x | Donnees boursieres (projections) |
| `react-markdown` | ^9.x | Rendu markdown chat |
| `lucide-react` | ^0.5 | Icones |

### DevDependencies

| Package | Usage |
|---------|-------|
| `typescript` ^5.7 | Typage |
| `vitest` ^3.x | Tests unitaires |
| `@testing-library/react` ^16 | Tests composants |
| `@playwright/test` ^1.50 | Tests E2E |
| `eslint` ^9 + `eslint-config-next` | Linting |
| `prettier` ^3 | Formatage |

### Pas de state manager global

TanStack Query gere le cache serveur. React Context suffit pour l'etat UI (sidebar collapsed, theme, filtres globaux DateRange).

---

## 6. Design System

### Palette (dark mode par defaut)

```css
:root {
  --bg:            #09090B;  /* zinc-950 */
  --surface:       #18181B;  /* zinc-900 */
  --surface-hover: #27272A;  /* zinc-800 */
  --border:        #3F3F46;  /* zinc-700 */
  --text:          #FAFAFA;  /* zinc-50 */
  --text-muted:    #A1A1AA;  /* zinc-400 */
  --accent:        #6366F1;  /* indigo-500 */
  --accent-hover:  #818CF8;  /* indigo-400 */
  --success:       #10B981;  /* emerald-500 */
  --warning:       #F59E0B;  /* amber-500 */
  --danger:        #EF4444;  /* red-500 */
}
```

### Typographie

- **Titres + corps** : Geist Variable (sans-serif) via `next/font/local`
- **Chiffres/montants** : Geist Mono (monospace)

### Layout

- Sidebar fixe gauche : 240px (expanded) / 64px (collapsed), icones Lucide
- Header : DateRangePicker global + breadcrumb
- Content : padding 24px, max-width fluide
- Cards : `border border-zinc-800 bg-zinc-900 rounded-xl p-6`

### Animations

- Cards : Framer Motion `y: 8 → 0, opacity: 0 → 1, duration: 0.3s`
- Hovers : `transition-colors duration-150`
- Chat widget : slide-in bas-droite
- Skeleton loaders pendant fetch

### Couleurs graphiques

```
indigo-500, emerald-500, amber-500, rose-500, cyan-500, violet-500
```

### Formatage

- Montants : `Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })`
- Pourcentages : `+12,3%` (signe explicite, 1 decimale)
- Dates : `date-fns` locale `fr` → `4 mars 2026`

### Principes

- Espacement genereux
- Bordures subtiles (1px, zinc-700/800)
- Ombres quasi-inexistantes (bordures a la place)
- Tone : Luxury fintech (Mercury, Linear, Ramp, Stripe)

---

## 7. Pages detaillees

### 7.1 — Dashboard (`/dashboard`) — Phase 1

**Server Component** charge les KPIs initiaux via `firefly-client.ts`.

```
Dashboard Page (Server)
├── KPIRow (Client) — 5 cards
│   ├── Solde total (GET /summary/basic) + delta %
│   ├── Depenses du mois + sparkline 30j
│   ├── Revenus du mois + sparkline 30j
│   ├── Taux d'epargne (calcule) + jauge
│   └── Score sante financiere (calcule par IA) + badge
├── ChartsGrid (Client)
│   ├── AreaChart — Evolution soldes 6 mois
│   ├── DonutChart — Repartition depenses par categorie
│   └── BarList — Top 5 categories du mois
├── BudgetProgress (Client) — ProgressBar ×N par budget
└── RecentTransactions (Client) — Table 5 lignes
```

**Interactions** :
- DateRangePicker global filtre toute la page (invalide TanStack queries)
- Clic DonutChart segment → filtre transactions
- Clic budget → `/budgets/{id}`
- Bouton "Ask AI" → ouvre chat widget

### 7.2 — Transactions (`/transactions`) — Phase 1

```
Transactions Page (Server — charge page 1)
├── FilterBar (Client)
│   ├── DateRangePicker
│   ├── Select categorie
│   ├── Select compte
│   ├── Select type (depense/revenu/transfert)
│   └── Inputs montant min/max
├── SearchBar (Client) — Full-text → /search/transactions
├── TransactionsTable (Client) — Pagine, tri par colonne
│   └── Colonnes : Date, Description, Montant, Categorie, Budget, Compte, Tags
│   └── Badge "AI categorized" si applicable
├── Pagination (Client) — TanStack Query paginated
└── ExportCSV (Client) — Bouton export
```

### 7.3 — Budgets (`/budgets`) — Phase 3

```
Budgets Page (Server)
├── BudgetGrid (Client) — Cards par budget
│   └── BudgetCard : ProgressBar + montant consomme/alloue
│       Couleurs : vert <75%, orange 75-100%, rouge >100%
├── BudgetComparison (Client) — BarChart groupe (alloue vs realise)
└── BudgetTrend (Client) — LineChart 6 mois evolution consommation
```

### 7.4 — Analytics (`/analytics`) — Phase 3

```
Analytics Page (Server)
├── Tabs : [Vue Globale | Categories | Patrimoine | Epargne]
│
├── Tab "Vue Globale"
│   ├── RevenusVsDepenses — BarChart groupe 12 mois
│   └── Heatmap — Grid CSS jour×semaine (intensite = montant)
│
├── Tab "Categories"
│   ├── CategoriesTrend — AreaChart empile (top 6 categories, 12 mois)
│   └── SankeyDiagram — D3.js custom (revenus → comptes → categories)
│
├── Tab "Patrimoine"
│   └── NetWorthChart — AreaChart evolution patrimoine net
│
└── Tab "Epargne"
    └── PiggyBanks — ProgressBar + Tracker par objectif
```

Le Sankey est le seul composant D3.js custom (package `d3-sankey` + SVG).
Le Heatmap est un grid CSS avec `background-color` interpolee.

### 7.5 — Projections (`/projections`) — Phase 4

#### Hub (`/projections`)

Page avec cards cliquables : Immobilier, Vehicule, (Investissement futur).

#### Immobilier (`/projections/immobilier`)

```
ImmobilierPage (Client)
├── Tabs : [Achat Residence | Location Longue Duree | Location Courte (Airbnb)]
│
├── Tab "Achat Residence"
│   ├── Inputs : prix bien, apport, duree pret, taux (pre-rempli ECB)
│   ├── AutoFill : revenus + charges + epargne depuis Firefly
│   ├── Resultats :
│   │   ├── Capacite d'emprunt
│   │   ├── Mensualite estimee
│   │   ├── Reste a vivre
│   │   ├── Timeline atteinte apport (AreaChart)
│   │   └── 3 scenarios optimiste/realiste/pessimiste (BarChart)
│   └── Bouton "Demander a l'IA son avis" → envoie resultats au chat
│
├── Tab "Location Longue Duree"
│   ├── Inputs :
│   │   ├── Prix d'achat + frais notaire (auto ~8%)
│   │   ├── Apport + montant emprunte + taux + duree
│   │   ├── Loyer mensuel estime (input ou estimation par m2)
│   │   ├── Charges : copro, taxe fonciere, assurance PNO, gestion locative (%)
│   │   ├── Vacance locative estimee (% annuel, default 5%)
│   │   └── Regime fiscal : Micro-foncier (30%) vs Reel
│   ├── Resultats :
│   │   ├── Rendement brut : (loyer×12) / prix achat
│   │   ├── Rendement net : (loyer - charges - vacance) / (prix + frais)
│   │   ├── Rendement net-net : apres imposition
│   │   ├── Cash-flow mensuel : loyer - mensualite - charges
│   │   ├── TRI (taux de rendement interne) sur 10/15/20 ans
│   │   └── Point mort : nb annees pour recuperer l'apport
│   └── Graphiques :
│       ├── AreaChart — Evolution patrimoine net (capital rembourse + plus-value)
│       └── BarChart — Cash-flow mensuel sur la duree du pret
│
└── Tab "Location Courte (Airbnb)"
    ├── Inputs :
    │   ├── Memes inputs achat que LCD
    │   ├── Prix/nuit moyen
    │   ├── Taux d'occupation estime (%, default 65%)
    │   ├── Charges specifiques : menage/nuit, commission plateforme (15%), linge
    │   ├── Reglementation : nb nuits max/an (120j residence principale)
    │   └── Regime fiscal : Micro-BIC (50%) vs Reel (LMNP)
    ├── Resultats :
    │   ├── CA brut annuel : prix/nuit × nuits occupees
    │   ├── CA net : apres commissions + charges variables
    │   ├── Rendement net : CA net / (prix + frais + meubles)
    │   ├── Cash-flow mensuel (moyenne annualisee)
    │   └── Comparaison LCD vs Airbnb (Table cote a cote)
    └── Graphiques :
        ├── BarChart — Revenus mensuels (saisonnalite si estime)
        └── Table comparative — LCD vs Airbnb vs pas d'investissement
```

**Calculs** : Tous en TypeScript pur (pas de LLM). Le LLM intervient uniquement pour l'interpretation via bouton "Demander a l'IA son avis".

**Fiscalite francaise** :
- LCD : Micro-foncier (abattement 30%) vs Reel
- Airbnb/LMNP : Micro-BIC (abattement 50%) vs Reel
- Disclaimer systematique : "Ceci n'est pas un conseil fiscal"

#### Vehicule (`/projections/vehicule`)

```
VehiculePage (Client)
├── Inputs : prix, type (neuf/occasion), financement
├── Comparaison : Comptant vs Credit vs LOA vs LLD (Table)
├── TCO : assurance + entretien + carburant (BarChart)
└── Impact budget mensuel : ProgressBar (budget actuel + nouvelle charge)
```

#### APIs externes

- **ECB** : `https://data-api.ecb.europa.eu/service/data/FM/...` — taux d'interet, gratuit, cache 24h
- **Yahoo Finance** : `yahoo-finance2` npm — donnees boursieres pour module Investissement (futur)

### 7.6 — Chat IA (`/chat` + widget) — Phase 2

#### Architecture

```
Widget flottant (bas-droite)  <->  Page /chat (plein ecran)
         |                              |
    ChatWidget (Client)          ChatPage (Client)
         |                              |
         +----------+------------------+
                    |
            useChat() (Vercel AI SDK)
                    |
            POST /api/chat/route.ts
                    |
            LiteLLM (OpenAI-compatible)
              model: deepseek-v3-free
```

#### `/api/chat/route.ts`

```typescript
import { createOpenAI } from '@ai-sdk/openai'
import { streamText } from 'ai'

const litellm = createOpenAI({
  baseURL: process.env.LITELLM_URL,
  apiKey: process.env.LITELLM_KEY,
})

export async function POST(req) {
  const { messages } = await req.json()
  const result = streamText({
    model: litellm(process.env.LLM_MODEL || 'deepseek-v3-free'),
    system: FINANCE_SYSTEM_PROMPT,
    messages,
  })
  return result.toDataStreamResponse()
}
```

#### Widget Chat

- Bouton flottant bas-droite (icone `MessageCircle` Lucide)
- Panel slide-in (400px largeur, 60vh hauteur)
- `useChat()` gere messages, streaming, loading
- Historique persiste `localStorage`
- Suggestions contextuelles selon page active
- Rendu Markdown via `react-markdown`
- Bouton "Ouvrir en plein ecran" → `/chat`

#### Page `/chat`

- Layout plein ecran : messages (70%) + suggestions (30%)
- Input autosize en bas
- Meme hook `useChat()`, meme historique

#### System Prompt

```
Tu es un conseiller financier personnel. Tu as acces aux donnees
financieres de l'utilisateur via Firefly III.
- Reponds en francais
- Les calculs financiers critiques doivent etre exacts
- Ne donne jamais de conseils d'investissement reglementes
- Ajoute un disclaimer pour les projections
- Sois concis, utilise des chiffres precis
```

**Note Phase 2** : Le chat n'a PAS d'acces direct aux donnees Firefly (pas de function calling/MCP). L'integration MCP viendrait en evolution future via OpenClaw.

### 7.7 — Settings (`/settings`) — Phase 1

- URL instance Firefly III (read-only, env var)
- Devise par defaut
- Modele LLM prefere (dropdown via LiteLLM `/models`)
- Test de connexion Firefly + LiteLLM (boutons "Tester")

---

## 8. API Routes

### `/api/firefly/[...path]` — Proxy transparent

```typescript
export async function GET(req, { params }) {
  const path = (await params).path.join('/')
  const fireflyUrl = process.env.FIREFLY_URL
  const token = process.env.FIREFLY_PAT

  const url = new URL(`/api/v1/${path}`, fireflyUrl)
  url.search = new URL(req.url).search

  const res = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Accept': 'application/vnd.api+json',
    },
  })

  return new Response(res.body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
```

Supporte GET, POST, PUT, DELETE (meme pattern).

### `/api/health` — Healthcheck

```typescript
export async function GET() {
  return Response.json({ status: 'ok', timestamp: new Date().toISOString() })
}
```

### TanStack Query Hooks (`hooks/use-firefly.ts`)

| Hook | Endpoint | staleTime |
|------|----------|-----------|
| `useAccounts()` | `/accounts?type=asset` | 5min |
| `useSummary(start, end)` | `/summary/basic` | 5min |
| `useTransactions(filters)` | `/transactions` + pagination | 2min |
| `useCategories()` | `/categories` | 30min |
| `useBudgets()` | `/budgets` + `/budgets/{id}/limits` | 5min |
| `useInsightExpense(start, end)` | `/insight/expense/category` | 5min |
| `usePiggyBanks()` | `/piggy-banks` | 10min |
| `useNetWorth(start, end)` | `/chart/account/overview` | 10min |

---

## 9. CI/CD

### Dockerfile

```dockerfile
FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@latest --activate

FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

### GitHub Actions (`.github/workflows/docker-publish.yml`)

```yaml
on:
  push:
    branches: [main]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          push: true
          tags: |
            ghcr.io/mobutoo/seko-finance:latest
            ghcr.io/mobutoo/seko-finance:sha-${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

## 10. Tests

### Unit (Vitest)

- `lib/formatters.ts` : formatage montants, dates, pourcentages
- `lib/calculations.ts` : calculs immo (rendement, TRI, cash-flow)
- `hooks/use-firefly.ts` : mock fetch, verification queries
- Composants isoles : KPICard, BudgetCard (render + snapshot)

### E2E (Playwright)

- Dashboard charge sans erreur
- Navigation sidebar fonctionne
- Transactions : filtres + pagination
- Chat : widget s'ouvre, message s'envoie, reponse arrive
- Settings : test connexion Firefly

---

## 11. Variables d'environnement

```env
# Firefly III (backend Docker network)
FIREFLY_URL=http://firefly-iii:8080
FIREFLY_PAT=eyJ...

# LLM (backend Docker network)
LITELLM_URL=http://litellm:4000
LITELLM_KEY=sk-...
LLM_MODEL=deepseek-v3-free

# App
NEXT_PUBLIC_APP_NAME=Seko-Finance
NEXT_PUBLIC_CURRENCY=EUR
NODE_ENV=production
TZ=Europe/Paris
```

---

## 12. Roadmap & Phases

### Phase 1 — MVP

- Squelette Next.js 15 + Tremor Raw + Tailwind v4
- Layout (sidebar, AppShell, providers)
- Proxy API Firefly III (`/api/firefly/[...path]`)
- Healthcheck (`/api/health`)
- Dashboard principal (5 KPIs + 3 graphiques + budget progress + recent transactions)
- Page transactions (table + filtres + pagination + recherche + export CSV)
- Dark mode par defaut
- Settings page (connexion test)
- Dockerfile + docker-compose dev
- `.env.example`

### Phase 2 — Chat IA

- Endpoint `/api/chat` (Vercel AI SDK + LiteLLM)
- Widget chat flottant (panel slide-in)
- Page `/chat` plein ecran
- Suggestions contextuelles par page
- Historique localStorage
- Rendu Markdown reponses

### Phase 3 — Analytics & Budgets

- Page budgets (cards + ProgressBar + comparaison + tendance)
- Page analytics (4 tabs)
- Sankey diagram (D3.js)
- Heatmap depenses
- Net worth chart
- Piggy banks / objectifs epargne

### Phase 4 — Projections

- Hub projections
- Module immobilier (achat + LCD + Airbnb)
- Module vehicule (comptant vs credit vs LOA vs LLD)
- Integration ECB (taux)
- Calculs fiscalite francaise (micro-foncier, micro-BIC, reel)
- Bouton "Demander a l'IA son avis"

### Phase 5 — Production

- CI/CD GitHub Actions → GHCR
- Tests unitaires (Vitest)
- Tests E2E (Playwright)
- Bundle analyzer + optimisations
- Pin image GHCR sur SHA dans VPAI versions.yml

---

## 13. Risques et mitigations

| Risque | Mitigation |
|--------|------------|
| API Firefly III lente sur gros volumes | TanStack Query cache 5min, pagination |
| Hallucination LLM sur les montants | Calculs en code TS, LLM = interpretation |
| Yahoo Finance API instable | Fallback gracieux, donnees optionnelles |
| Token LLM couteux | deepseek-v3-free par defaut (eco budget) |
| Firefly III API breaking changes | Types TS stricts, proxy versione |

---

*Approuve le 2026-03-04*
