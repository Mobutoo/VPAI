# Seko-Finance AI Dashboard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a luxury fintech dashboard (Next.js 15) connected to Firefly III + LiteLLM, deployed via GHCR.

**Architecture:** Hybrid Server/Client Components. Server Components for initial data load, Client Components for interactivity. TanStack Query for client-side cache. Vercel AI SDK for chat streaming. Tremor Raw + Recharts for charts.

**Tech Stack:** Next.js 15, React 19, Tailwind CSS v4, Tremor Raw, Recharts, TanStack Query v5, Vercel AI SDK v4, Framer Motion, pnpm, TypeScript 5.7, Vitest, Playwright.

**Design doc:** `docs/plans/2026-03-04-seko-finance-app-design.md`

---

## Phase 1 — MVP

### Task 1: Scaffold Next.js project

**Context:** We're creating a brand new repo `Mobutoo/seko-finance`. All work happens in this new repo, NOT in VPAI.

**Step 1: Create GitHub repo and scaffold**

```bash
cd ~/projects  # or wherever you keep repos
mkdir seko-finance && cd seko-finance
git init
pnpx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir --no-import-alias --use-pnpm
```

Accept defaults. This creates the Next.js 15 scaffold with App Router + src/ directory.

**Step 2: Install core dependencies**

```bash
pnpm add @tremor/react recharts @radix-ui/react-dialog @radix-ui/react-select @radix-ui/react-tabs @radix-ui/react-tooltip @tanstack/react-query framer-motion date-fns clsx tailwind-merge lucide-react react-markdown
```

**Step 3: Install dev dependencies**

```bash
pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom @playwright/test prettier @next/bundle-analyzer
```

**Step 4: Configure `next.config.ts` for standalone output**

```typescript
// next.config.ts
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',
}

export default nextConfig
```

**Step 5: Create `.env.example`**

```env
# Firefly III (Docker internal or localhost for dev)
FIREFLY_URL=http://firefly-iii:8080
FIREFLY_PAT=

# LLM (Docker internal or localhost for dev)
LITELLM_URL=http://litellm:4000
LITELLM_KEY=
LLM_MODEL=deepseek-v3-free

# App
NEXT_PUBLIC_APP_NAME=Seko-Finance
NEXT_PUBLIC_CURRENCY=EUR
TZ=Europe/Paris
```

**Step 6: Create `.env.local` from example (gitignored)**

```bash
cp .env.example .env.local
# Fill in real values for local dev
```

**Step 7: Add Geist fonts**

Next.js 15 includes Geist by default via `next/font/google` or `next/font/local`. If the scaffold already has it, keep it. Otherwise:

```typescript
// src/app/layout.tsx — add to imports
import { GeistSans } from 'geist/font/sans'
import { GeistMono } from 'geist/font/mono'
```

If `geist` package not included:

```bash
pnpm add geist
```

**Step 8: Verify scaffold runs**

```bash
pnpm dev
# Open http://localhost:3000 — should see Next.js default page
```

**Step 9: Commit**

```bash
git add -A
git commit -m "feat: scaffold Next.js 15 project with dependencies"
```

---

### Task 2: Design system (globals.css + utility functions)

**Files:**
- Modify: `src/app/globals.css`
- Create: `src/lib/cn.ts`
- Create: `src/lib/formatters.ts`
- Create: `src/lib/constants.ts`
- Test: `tests/unit/formatters.test.ts`

**Step 1: Replace `globals.css` with design system**

```css
/* src/app/globals.css */
@import "tailwindcss";

:root {
  --bg: #09090B;
  --surface: #18181B;
  --surface-hover: #27272A;
  --border: #3F3F46;
  --text: #FAFAFA;
  --text-muted: #A1A1AA;
  --accent: #6366F1;
  --accent-hover: #818CF8;
  --success: #10B981;
  --warning: #F59E0B;
  --danger: #EF4444;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-geist-sans), system-ui, sans-serif;
}

/* Monospace for financial figures */
.font-mono {
  font-family: var(--font-geist-mono), ui-monospace, monospace;
}
```

**Step 2: Create `cn` utility**

```typescript
// src/lib/cn.ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

**Step 3: Create constants**

```typescript
// src/lib/constants.ts
export const CHART_COLORS = [
  '#6366F1', // indigo-500
  '#10B981', // emerald-500
  '#F59E0B', // amber-500
  '#F43F5E', // rose-500
  '#06B6D4', // cyan-500
  '#8B5CF6', // violet-500
] as const

export const FINANCE_SYSTEM_PROMPT = `Tu es un conseiller financier personnel. Tu as acces aux donnees financieres de l'utilisateur via Firefly III.
- Reponds en francais
- Les calculs financiers critiques doivent etre exacts
- Ne donne jamais de conseils d'investissement reglementes
- Ajoute un disclaimer pour les projections
- Sois concis, utilise des chiffres precis`

export const DEFAULT_STALE_TIME = 5 * 60 * 1000 // 5 minutes
```

**Step 4: Create formatters with tests (TDD)**

Write the test first:

```typescript
// tests/unit/formatters.test.ts
import { describe, it, expect } from 'vitest'
import { formatCurrency, formatPercent, formatDate } from '@/lib/formatters'

describe('formatCurrency', () => {
  it('formats EUR amounts in French locale', () => {
    // Note: non-breaking spaces in fr-FR locale
    expect(formatCurrency(1234.56)).toContain('1')
    expect(formatCurrency(1234.56)).toContain('234')
    expect(formatCurrency(1234.56)).toContain('56')
  })

  it('handles zero', () => {
    expect(formatCurrency(0)).toContain('0')
  })

  it('handles negative amounts', () => {
    expect(formatCurrency(-500)).toContain('500')
  })
})

describe('formatPercent', () => {
  it('formats positive percentages with sign', () => {
    expect(formatPercent(12.34)).toBe('+12,3\u202f%')
  })

  it('formats negative percentages', () => {
    expect(formatPercent(-5.67)).toBe('-5,7\u202f%')
  })

  it('formats zero', () => {
    expect(formatPercent(0)).toBe('0,0\u202f%')
  })
})

describe('formatDate', () => {
  it('formats date in French', () => {
    const result = formatDate(new Date(2026, 2, 4)) // March 4, 2026
    expect(result).toBe('4 mars 2026')
  })
})
```

**Step 5: Implement formatters**

```typescript
// src/lib/formatters.ts
import { format } from 'date-fns'
import { fr } from 'date-fns/locale'

const currencyFormatter = new Intl.NumberFormat('fr-FR', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const percentFormatter = new Intl.NumberFormat('fr-FR', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: 'exceptZero',
})

export function formatCurrency(amount: number): string {
  return currencyFormatter.format(amount)
}

export function formatPercent(value: number): string {
  return percentFormatter.format(value / 100)
}

export function formatDate(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return format(d, 'd MMMM yyyy', { locale: fr })
}

export function formatDateShort(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return format(d, 'd MMM', { locale: fr })
}
```

**Step 6: Configure Vitest**

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'
import path from 'path'

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: [],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```

Add to `package.json` scripts:

```json
{
  "scripts": {
    "test": "vitest",
    "test:run": "vitest run"
  }
}
```

**Step 7: Run tests**

```bash
pnpm test:run
# Expected: 6 tests pass
```

**Step 8: Commit**

```bash
git add -A
git commit -m "feat: design system, formatters, constants with tests"
```

---

### Task 3: Firefly III TypeScript types

**Files:**
- Create: `src/types/firefly.ts`

**Step 1: Create Firefly III API v1 types**

These types match the Firefly III JSON:API v1 response format.

```typescript
// src/types/firefly.ts

// --- JSON:API wrapper ---
export interface FireflyResponse<T> {
  data: T
  meta?: {
    pagination?: {
      total: number
      count: number
      per_page: number
      current_page: number
      total_pages: number
    }
  }
}

// --- Accounts ---
export interface FireflyAccount {
  id: string
  type: 'accounts'
  attributes: {
    name: string
    type: 'asset' | 'expense' | 'revenue' | 'liability'
    current_balance: string
    current_balance_date: string
    currency_code: string
    currency_symbol: string
    active: boolean
    account_role: string | null
    include_net_worth: boolean
  }
}

// --- Transactions ---
export interface FireflyTransaction {
  id: string
  type: 'transactions'
  attributes: {
    group_title: string | null
    transactions: FireflyTransactionSplit[]
  }
}

export interface FireflyTransactionSplit {
  type: 'withdrawal' | 'deposit' | 'transfer'
  date: string
  amount: string
  description: string
  currency_code: string
  source_name: string
  destination_name: string
  category_name: string | null
  budget_name: string | null
  tags: string[]
}

// --- Categories ---
export interface FireflyCategory {
  id: string
  type: 'categories'
  attributes: {
    name: string
    spent: { currency_code: string; sum: string }[]
    earned: { currency_code: string; sum: string }[]
  }
}

// --- Budgets ---
export interface FireflyBudget {
  id: string
  type: 'budgets'
  attributes: {
    name: string
    active: boolean
    auto_budget_amount: string | null
    auto_budget_period: string | null
  }
}

export interface FireflyBudgetLimit {
  id: string
  type: 'budget_limits'
  attributes: {
    start: string
    end: string
    amount: string
    spent: string
    currency_code: string
  }
}

// --- Summary ---
export interface FireflySummary {
  [key: string]: {
    key: string
    title: string
    monetary_value: number
    currency_code: string
    value_parsed: string
    local_icon: string
  }
}

// --- Insight ---
export interface FireflyInsightEntry {
  name: string
  id: number
  currency_code: string
  currency_id: number
  difference: string
  difference_float: number
}

// --- Piggy Banks ---
export interface FireflyPiggyBank {
  id: string
  type: 'piggy_banks'
  attributes: {
    name: string
    target_amount: string
    current_amount: string
    percentage: number
    active: boolean
  }
}

// --- Chart data ---
export interface FireflyChartData {
  [label: string]: {
    [date: string]: string
  }
}

// --- App-level types ---
export interface DateRange {
  start: Date
  end: Date
}

export interface TransactionFilters {
  dateRange?: DateRange
  category?: string
  account?: string
  type?: 'withdrawal' | 'deposit' | 'transfer'
  amountMin?: number
  amountMax?: number
  search?: string
  page?: number
  limit?: number
}
```

**Step 2: Commit**

```bash
git add src/types/firefly.ts
git commit -m "feat: add Firefly III API v1 TypeScript types"
```

---

### Task 4: API routes (health + Firefly proxy)

**Files:**
- Create: `src/app/api/health/route.ts`
- Create: `src/app/api/firefly/[...path]/route.ts`

**Step 1: Health route**

```typescript
// src/app/api/health/route.ts
export async function GET() {
  return Response.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
  })
}
```

**Step 2: Firefly proxy route**

```typescript
// src/app/api/firefly/[...path]/route.ts
import { NextRequest } from 'next/server'

const FIREFLY_URL = process.env.FIREFLY_URL
const FIREFLY_PAT = process.env.FIREFLY_PAT

async function proxyRequest(
  req: NextRequest,
  params: Promise<{ path: string[] }>,
  method: string
) {
  if (!FIREFLY_URL || !FIREFLY_PAT) {
    return Response.json(
      { error: 'Firefly III not configured' },
      { status: 503 }
    )
  }

  const { path } = await params
  const apiPath = path.join('/')
  const url = new URL(`/api/v1/${apiPath}`, FIREFLY_URL)
  url.search = new URL(req.url).search

  const headers: HeadersInit = {
    Authorization: `Bearer ${FIREFLY_PAT}`,
    Accept: 'application/vnd.api+json',
  }

  const init: RequestInit = { method, headers }

  if (method !== 'GET' && method !== 'HEAD') {
    const body = await req.text()
    if (body) {
      init.body = body
      headers['Content-Type'] = 'application/json'
    }
  }

  const res = await fetch(url, init)

  return new Response(res.body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(req, ctx.params, 'GET')
}

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(req, ctx.params, 'POST')
}

export async function PUT(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(req, ctx.params, 'PUT')
}

export async function DELETE(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(req, ctx.params, 'DELETE')
}
```

**Step 3: Test manually**

```bash
pnpm dev
curl http://localhost:3000/api/health
# Expected: {"status":"ok","timestamp":"..."}
```

**Step 4: Commit**

```bash
git add src/app/api/
git commit -m "feat: add health check and Firefly III proxy API routes"
```

---

### Task 5: Server-side Firefly client + TanStack Query hooks

**Files:**
- Create: `src/lib/firefly-client.ts`
- Create: `src/hooks/use-firefly.ts`
- Create: `src/app/providers.tsx`

**Step 1: Server-side Firefly client**

This is for Server Components to call Firefly III directly (no proxy needed server-side).

```typescript
// src/lib/firefly-client.ts
import type {
  FireflyResponse,
  FireflyAccount,
  FireflyTransaction,
  FireflySummary,
  FireflyInsightEntry,
  FireflyBudget,
  FireflyCategory,
  TransactionFilters,
} from '@/types/firefly'

const FIREFLY_URL = process.env.FIREFLY_URL
const FIREFLY_PAT = process.env.FIREFLY_PAT

async function fireflyFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
  if (!FIREFLY_URL || !FIREFLY_PAT) {
    throw new Error('Firefly III not configured')
  }

  const url = new URL(`/api/v1/${path}`, FIREFLY_URL)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  }

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${FIREFLY_PAT}`,
      Accept: 'application/vnd.api+json',
    },
    next: { revalidate: 300 }, // 5 min server cache
  })

  if (!res.ok) {
    throw new Error(`Firefly API error: ${res.status} ${res.statusText}`)
  }

  return res.json()
}

export async function getAccounts() {
  return fireflyFetch<FireflyResponse<FireflyAccount[]>>('accounts', { type: 'asset' })
}

export async function getSummary(start: string, end: string) {
  return fireflyFetch<FireflySummary>('summary/basic', { start, end })
}

export async function getTransactions(filters: TransactionFilters = {}) {
  const params: Record<string, string> = {}
  if (filters.dateRange) {
    params.start = filters.dateRange.start.toISOString().split('T')[0]
    params.end = filters.dateRange.end.toISOString().split('T')[0]
  }
  if (filters.type) params.type = filters.type
  if (filters.page) params.page = String(filters.page)
  if (filters.limit) params.limit = String(filters.limit)
  return fireflyFetch<FireflyResponse<FireflyTransaction[]>>('transactions', params)
}

export async function getCategories() {
  return fireflyFetch<FireflyResponse<FireflyCategory[]>>('categories')
}

export async function getBudgets() {
  return fireflyFetch<FireflyResponse<FireflyBudget[]>>('budgets')
}

export async function getInsightExpenseCategory(start: string, end: string) {
  return fireflyFetch<FireflyInsightEntry[]>('insight/expense/category', { start, end })
}

export async function getChartAccountOverview(start: string, end: string) {
  return fireflyFetch<Record<string, Record<string, string>>>('chart/account/overview', { start, end })
}
```

**Step 2: TanStack Query provider**

```typescript
// src/app/providers.tsx
'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { DEFAULT_STALE_TIME } from '@/lib/constants'

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: DEFAULT_STALE_TIME,
            refetchOnWindowFocus: true,
          },
        },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}
```

**Step 3: Client-side hooks**

```typescript
// src/hooks/use-firefly.ts
'use client'

import { useQuery } from '@tanstack/react-query'
import type {
  FireflyResponse,
  FireflyAccount,
  FireflyTransaction,
  FireflySummary,
  FireflyInsightEntry,
  FireflyBudget,
  FireflyBudgetLimit,
  FireflyCategory,
  FireflyPiggyBank,
  TransactionFilters,
} from '@/types/firefly'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`/api/firefly/${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export function useAccounts() {
  return useQuery({
    queryKey: ['accounts'],
    queryFn: () => apiFetch<FireflyResponse<FireflyAccount[]>>('accounts?type=asset'),
  })
}

export function useSummary(start: string, end: string) {
  return useQuery({
    queryKey: ['summary', start, end],
    queryFn: () => apiFetch<FireflySummary>(`summary/basic?start=${start}&end=${end}`),
  })
}

export function useTransactions(filters: TransactionFilters) {
  const params = new URLSearchParams()
  if (filters.dateRange) {
    params.set('start', filters.dateRange.start.toISOString().split('T')[0])
    params.set('end', filters.dateRange.end.toISOString().split('T')[0])
  }
  if (filters.type) params.set('type', filters.type)
  if (filters.page) params.set('page', String(filters.page))
  if (filters.limit) params.set('limit', String(filters.limit))

  return useQuery({
    queryKey: ['transactions', filters],
    queryFn: () => apiFetch<FireflyResponse<FireflyTransaction[]>>(`transactions?${params}`),
    staleTime: 2 * 60 * 1000, // 2 min
  })
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: () => apiFetch<FireflyResponse<FireflyCategory[]>>('categories'),
    staleTime: 30 * 60 * 1000, // 30 min
  })
}

export function useBudgets() {
  return useQuery({
    queryKey: ['budgets'],
    queryFn: () => apiFetch<FireflyResponse<FireflyBudget[]>>('budgets'),
  })
}

export function useBudgetLimits(budgetId: string) {
  return useQuery({
    queryKey: ['budget-limits', budgetId],
    queryFn: () => apiFetch<FireflyResponse<FireflyBudgetLimit[]>>(`budgets/${budgetId}/limits`),
    enabled: !!budgetId,
  })
}

export function useInsightExpense(start: string, end: string) {
  return useQuery({
    queryKey: ['insight-expense', start, end],
    queryFn: () => apiFetch<FireflyInsightEntry[]>(`insight/expense/category?start=${start}&end=${end}`),
  })
}

export function usePiggyBanks() {
  return useQuery({
    queryKey: ['piggy-banks'],
    queryFn: () => apiFetch<FireflyResponse<FireflyPiggyBank[]>>('piggy-banks'),
    staleTime: 10 * 60 * 1000,
  })
}

export function useNetWorth(start: string, end: string) {
  return useQuery({
    queryKey: ['net-worth', start, end],
    queryFn: () => apiFetch<Record<string, Record<string, string>>>(`chart/account/overview?start=${start}&end=${end}`),
    staleTime: 10 * 60 * 1000,
  })
}
```

**Step 4: Commit**

```bash
git add src/lib/firefly-client.ts src/hooks/use-firefly.ts src/app/providers.tsx
git commit -m "feat: Firefly client, TanStack Query hooks, providers"
```

---

### Task 6: Layout components (Sidebar + AppShell + PageHeader)

**Files:**
- Create: `src/components/layout/sidebar.tsx`
- Create: `src/components/layout/app-shell.tsx`
- Create: `src/components/layout/page-header.tsx`
- Modify: `src/app/layout.tsx`
- Create: `src/app/page.tsx` (redirect)

**Step 1: Sidebar**

```typescript
// src/components/layout/sidebar.tsx
'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  ArrowLeftRight,
  Wallet,
  BarChart3,
  TrendingUp,
  MessageCircle,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/cn'

const NAV_ITEMS = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { href: '/budgets', label: 'Budgets', icon: Wallet },
  { href: '/analytics', label: 'Analytics', icon: BarChart3 },
  { href: '/projections', label: 'Projections', icon: TrendingUp },
  { href: '/chat', label: 'Chat IA', icon: MessageCircle },
  { href: '/settings', label: 'Settings', icon: Settings },
] as const

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const pathname = usePathname()

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 flex h-screen flex-col border-r border-zinc-800 bg-zinc-950 transition-all duration-200',
        collapsed ? 'w-16' : 'w-60'
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center border-b border-zinc-800 px-4">
        {!collapsed && (
          <span className="text-lg font-semibold text-zinc-50">
            {process.env.NEXT_PUBLIC_APP_NAME || 'Seko-Finance'}
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-2">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150',
                active
                  ? 'bg-zinc-800 text-zinc-50'
                  : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-50'
              )}
            >
              <Icon className="h-5 w-5 shrink-0" />
              {!collapsed && <span>{label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex h-12 items-center justify-center border-t border-zinc-800 text-zinc-400 hover:text-zinc-50"
      >
        {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
      </button>
    </aside>
  )
}
```

**Step 2: AppShell**

```typescript
// src/components/layout/app-shell.tsx
import { Sidebar } from './sidebar'

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-zinc-950">
      <Sidebar />
      <main className="ml-60 min-h-screen p-6">
        {children}
      </main>
    </div>
  )
}
```

**Step 3: PageHeader**

```typescript
// src/components/layout/page-header.tsx
interface PageHeaderProps {
  title: string
  description?: string
  children?: React.ReactNode // for action buttons
}

export function PageHeader({ title, description, children }: PageHeaderProps) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-zinc-400">{description}</p>
        )}
      </div>
      {children && <div className="flex items-center gap-3">{children}</div>}
    </div>
  )
}
```

**Step 4: Update root layout**

```typescript
// src/app/layout.tsx
import type { Metadata } from 'next'
import { GeistSans } from 'geist/font/sans'
import { GeistMono } from 'geist/font/mono'
import { Providers } from './providers'
import { AppShell } from '@/components/layout/app-shell'
import './globals.css'

export const metadata: Metadata = {
  title: process.env.NEXT_PUBLIC_APP_NAME || 'Seko-Finance',
  description: 'Dashboard financier personnel connecte a Firefly III',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="fr" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  )
}
```

**Step 5: Root page redirect**

```typescript
// src/app/page.tsx
import { redirect } from 'next/navigation'

export default function Home() {
  redirect('/dashboard')
}
```

**Step 6: Verify**

```bash
pnpm dev
# Open http://localhost:3000 — should redirect to /dashboard with sidebar visible
```

**Step 7: Commit**

```bash
git add src/components/layout/ src/app/layout.tsx src/app/page.tsx
git commit -m "feat: layout components (Sidebar, AppShell, PageHeader)"
```

---

### Task 7: UI components (KPICard, Card, Skeleton)

**Files:**
- Create: `src/components/ui/card.tsx`
- Create: `src/components/ui/kpi-card.tsx`
- Create: `src/components/ui/skeleton.tsx`

**Step 1: Card component**

```typescript
// src/components/ui/card.tsx
import { cn } from '@/lib/cn'

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

export function Card({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-zinc-800 bg-zinc-900 p-6',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}
```

**Step 2: KPICard component**

```typescript
// src/components/ui/kpi-card.tsx
'use client'

import { motion } from 'framer-motion'
import { cn } from '@/lib/cn'
import { Card } from './card'
import { formatCurrency, formatPercent } from '@/lib/formatters'

interface KPICardProps {
  title: string
  value: number
  format?: 'currency' | 'percent' | 'score'
  delta?: number // percentage change vs previous period
  icon?: React.ReactNode
}

export function KPICard({ title, value, format = 'currency', delta, icon }: KPICardProps) {
  const formattedValue =
    format === 'currency'
      ? formatCurrency(value)
      : format === 'percent'
        ? formatPercent(value)
        : `${value}/100`

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card>
        <div className="flex items-center justify-between">
          <p className="text-sm text-zinc-400">{title}</p>
          {icon && <div className="text-zinc-500">{icon}</div>}
        </div>
        <p className="mt-2 text-2xl font-semibold font-mono text-zinc-50">
          {formattedValue}
        </p>
        {delta !== undefined && (
          <p
            className={cn(
              'mt-1 text-sm font-mono',
              delta > 0 ? 'text-emerald-500' : delta < 0 ? 'text-red-500' : 'text-zinc-400'
            )}
          >
            {formatPercent(delta)} vs mois precedent
          </p>
        )}
      </Card>
    </motion.div>
  )
}
```

**Step 3: Skeleton loader**

```typescript
// src/components/ui/skeleton.tsx
import { cn } from '@/lib/cn'

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-lg bg-zinc-800', className)}
      {...props}
    />
  )
}

export function KPICardSkeleton() {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="mt-3 h-8 w-32" />
      <Skeleton className="mt-2 h-4 w-20" />
    </div>
  )
}
```

**Step 4: Commit**

```bash
git add src/components/ui/
git commit -m "feat: UI components (Card, KPICard, Skeleton)"
```

---

### Task 8: Chart wrapper components

**Files:**
- Create: `src/components/charts/area-chart.tsx`
- Create: `src/components/charts/donut-chart.tsx`
- Create: `src/components/charts/bar-list.tsx`
- Create: `src/components/charts/budget-progress.tsx`

**Step 1: AreaChart wrapper**

```typescript
// src/components/charts/area-chart.tsx
'use client'

import {
  AreaChart as RechartsAreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { CHART_COLORS } from '@/lib/constants'
import { formatCurrency, formatDateShort } from '@/lib/formatters'

interface AreaChartProps {
  data: Array<Record<string, unknown>>
  index: string
  categories: string[]
  colors?: string[]
  valueFormatter?: (value: number) => string
  height?: number
}

export function AreaChart({
  data,
  index,
  categories,
  colors = CHART_COLORS,
  valueFormatter = formatCurrency,
  height = 300,
}: AreaChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsAreaChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
        <XAxis
          dataKey={index}
          tickFormatter={formatDateShort}
          tick={{ fill: '#A1A1AA', fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tickFormatter={(v) => valueFormatter(v)}
          tick={{ fill: '#A1A1AA', fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={80}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#18181B',
            border: '1px solid #3F3F46',
            borderRadius: '8px',
            color: '#FAFAFA',
          }}
          formatter={(value: number) => valueFormatter(value)}
        />
        {categories.map((cat, i) => (
          <Area
            key={cat}
            type="monotone"
            dataKey={cat}
            stroke={colors[i % colors.length]}
            fill={colors[i % colors.length]}
            fillOpacity={0.1}
            strokeWidth={2}
          />
        ))}
      </RechartsAreaChart>
    </ResponsiveContainer>
  )
}
```

**Step 2: DonutChart wrapper**

```typescript
// src/components/charts/donut-chart.tsx
'use client'

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { CHART_COLORS } from '@/lib/constants'
import { formatCurrency } from '@/lib/formatters'

interface DonutChartProps {
  data: Array<{ name: string; value: number }>
  colors?: string[]
  height?: number
}

export function DonutChart({
  data,
  colors = CHART_COLORS,
  height = 300,
}: DonutChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
        >
          {data.map((_, i) => (
            <Cell key={i} fill={colors[i % colors.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: '#18181B',
            border: '1px solid #3F3F46',
            borderRadius: '8px',
            color: '#FAFAFA',
          }}
          formatter={(value: number) => formatCurrency(Math.abs(value))}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
```

**Step 3: BarList**

```typescript
// src/components/charts/bar-list.tsx
'use client'

import { cn } from '@/lib/cn'
import { formatCurrency } from '@/lib/formatters'
import { CHART_COLORS } from '@/lib/constants'

interface BarListProps {
  data: Array<{ name: string; value: number }>
  maxItems?: number
}

export function BarList({ data, maxItems = 5 }: BarListProps) {
  const sorted = [...data]
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, maxItems)

  const maxValue = Math.max(...sorted.map((d) => Math.abs(d.value)), 1)

  return (
    <div className="space-y-3">
      {sorted.map((item, i) => (
        <div key={item.name}>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="text-zinc-300">{item.name}</span>
            <span className="font-mono text-zinc-400">
              {formatCurrency(Math.abs(item.value))}
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-zinc-800">
            <div
              className="h-2 rounded-full transition-all duration-500"
              style={{
                width: `${(Math.abs(item.value) / maxValue) * 100}%`,
                backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
```

**Step 4: BudgetProgress**

```typescript
// src/components/charts/budget-progress.tsx
'use client'

import { cn } from '@/lib/cn'
import { formatCurrency } from '@/lib/formatters'

interface BudgetProgressProps {
  name: string
  spent: number
  limit: number
  currency?: string
}

export function BudgetProgress({ name, spent, limit }: BudgetProgressProps) {
  const percentage = limit > 0 ? (spent / limit) * 100 : 0
  const color =
    percentage < 75
      ? 'bg-emerald-500'
      : percentage < 100
        ? 'bg-amber-500'
        : 'bg-red-500'

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-zinc-300">{name}</span>
        <span className="font-mono text-zinc-400">
          {formatCurrency(spent)} / {formatCurrency(limit)}
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-zinc-800">
        <div
          className={cn('h-2 rounded-full transition-all duration-500', color)}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
    </div>
  )
}
```

**Step 5: Commit**

```bash
git add src/components/charts/
git commit -m "feat: chart components (AreaChart, DonutChart, BarList, BudgetProgress)"
```

---

### Task 9: Dashboard page

**Files:**
- Create: `src/app/dashboard/page.tsx`

**Step 1: Build the dashboard**

```typescript
// src/app/dashboard/page.tsx
import { Suspense } from 'react'
import { PageHeader } from '@/components/layout/page-header'
import { DashboardContent } from './dashboard-content'
import { KPICardSkeleton } from '@/components/ui/skeleton'

export default function DashboardPage() {
  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Vue d'ensemble de vos finances"
      />
      <Suspense
        fallback={
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <KPICardSkeleton key={i} />
            ))}
          </div>
        }
      >
        <DashboardContent />
      </Suspense>
    </div>
  )
}
```

**Step 2: Dashboard content (Client Component)**

```typescript
// src/app/dashboard/dashboard-content.tsx
'use client'

import { useState } from 'react'
import { startOfMonth, endOfMonth, subMonths, format } from 'date-fns'
import { Wallet, TrendingDown, TrendingUp, PiggyBank, Heart } from 'lucide-react'
import { KPICard } from '@/components/ui/kpi-card'
import { Card } from '@/components/ui/card'
import { AreaChart } from '@/components/charts/area-chart'
import { DonutChart } from '@/components/charts/donut-chart'
import { BarList } from '@/components/charts/bar-list'
import { BudgetProgress } from '@/components/charts/budget-progress'
import { useSummary, useInsightExpense, useBudgets, useTransactions } from '@/hooks/use-firefly'
import { formatCurrency, formatDateShort } from '@/lib/formatters'
import { KPICardSkeleton } from '@/components/ui/skeleton'

function formatISO(date: Date) {
  return format(date, 'yyyy-MM-dd')
}

export function DashboardContent() {
  const now = new Date()
  const start = formatISO(startOfMonth(now))
  const end = formatISO(endOfMonth(now))
  const prevStart = formatISO(startOfMonth(subMonths(now, 1)))
  const prevEnd = formatISO(endOfMonth(subMonths(now, 1)))

  const { data: summary, isLoading: summaryLoading } = useSummary(start, end)
  const { data: prevSummary } = useSummary(prevStart, prevEnd)
  const { data: expenses, isLoading: expensesLoading } = useInsightExpense(start, end)
  const { data: budgets } = useBudgets()
  const { data: recentTx } = useTransactions({ limit: 5 })

  if (summaryLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <KPICardSkeleton key={i} />
        ))}
      </div>
    )
  }

  // Extract values from summary (Firefly format: "balance-in-EUR", "spent-in-EUR", etc.)
  const balance = summary?.['balance-in-EUR']?.monetary_value ?? 0
  const spent = Math.abs(summary?.['spent-in-EUR']?.monetary_value ?? 0)
  const earned = summary?.['earned-in-EUR']?.monetary_value ?? 0
  const savingsRate = earned > 0 ? ((earned - spent) / earned) * 100 : 0

  const prevSpent = Math.abs(prevSummary?.['spent-in-EUR']?.monetary_value ?? 0)
  const spentDelta = prevSpent > 0 ? ((spent - prevSpent) / prevSpent) * 100 : 0

  // Expense categories for charts
  const categoryData = (expenses ?? []).map((e) => ({
    name: e.name,
    value: Math.abs(e.difference_float),
  }))

  return (
    <div className="space-y-6">
      {/* KPI Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title="Solde total"
          value={balance}
          icon={<Wallet className="h-5 w-5" />}
        />
        <KPICard
          title="Depenses du mois"
          value={spent}
          delta={spentDelta}
          icon={<TrendingDown className="h-5 w-5" />}
        />
        <KPICard
          title="Revenus du mois"
          value={earned}
          icon={<TrendingUp className="h-5 w-5" />}
        />
        <KPICard
          title="Taux d'epargne"
          value={savingsRate}
          format="percent"
          icon={<PiggyBank className="h-5 w-5" />}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            Repartition des depenses
          </h3>
          {categoryData.length > 0 ? (
            <DonutChart data={categoryData} />
          ) : (
            <p className="py-12 text-center text-sm text-zinc-500">Aucune donnee</p>
          )}
        </Card>
        <Card>
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            Top depenses du mois
          </h3>
          {categoryData.length > 0 ? (
            <BarList data={categoryData} />
          ) : (
            <p className="py-12 text-center text-sm text-zinc-500">Aucune donnee</p>
          )}
        </Card>
      </div>

      {/* Recent Transactions */}
      <Card>
        <h3 className="mb-4 text-sm font-medium text-zinc-400">
          Dernieres transactions
        </h3>
        <div className="space-y-3">
          {(recentTx?.data ?? []).slice(0, 5).map((tx) => {
            const split = tx.attributes.transactions[0]
            if (!split) return null
            const amount = parseFloat(split.amount)
            const isExpense = split.type === 'withdrawal'
            return (
              <div key={tx.id} className="flex items-center justify-between border-b border-zinc-800 pb-3 last:border-0">
                <div>
                  <p className="text-sm text-zinc-200">{split.description}</p>
                  <p className="text-xs text-zinc-500">
                    {split.category_name ?? 'Non categorise'} · {formatDateShort(split.date)}
                  </p>
                </div>
                <span className={`font-mono text-sm ${isExpense ? 'text-red-400' : 'text-emerald-400'}`}>
                  {isExpense ? '-' : '+'}{formatCurrency(Math.abs(amount))}
                </span>
              </div>
            )
          })}
          {(!recentTx?.data || recentTx.data.length === 0) && (
            <p className="py-4 text-center text-sm text-zinc-500">Aucune transaction</p>
          )}
        </div>
      </Card>
    </div>
  )
}
```

**Step 3: Verify**

```bash
pnpm dev
# Open http://localhost:3000/dashboard — should show KPI cards + charts (empty data if no Firefly connected)
```

**Step 4: Commit**

```bash
git add src/app/dashboard/
git commit -m "feat: dashboard page with KPIs, charts, recent transactions"
```

---

### Task 10: Transactions page

**Files:**
- Create: `src/app/transactions/page.tsx`
- Create: `src/app/transactions/transactions-content.tsx`
- Create: `src/components/ui/data-table.tsx`

**Step 1: DataTable component**

```typescript
// src/components/ui/data-table.tsx
'use client'

import { cn } from '@/lib/cn'

interface Column<T> {
  key: string
  header: string
  render: (row: T) => React.ReactNode
  className?: string
  sortable?: boolean
}

interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  onSort?: (key: string) => void
  sortKey?: string
  sortDir?: 'asc' | 'desc'
}

export function DataTable<T>({
  columns,
  data,
  onSort,
  sortKey,
  sortDir,
}: DataTableProps<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-zinc-800">
            {columns.map((col) => (
              <th
                key={col.key}
                className={cn(
                  'px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500',
                  col.sortable && 'cursor-pointer hover:text-zinc-300',
                  col.className
                )}
                onClick={() => col.sortable && onSort?.(col.key)}
              >
                {col.header}
                {sortKey === col.key && (
                  <span className="ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={i}
              className="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30"
            >
              {columns.map((col) => (
                <td key={col.key} className={cn('px-4 py-3 text-sm', col.className)}>
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
          {data.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-12 text-center text-sm text-zinc-500"
              >
                Aucune transaction
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
```

**Step 2: Transactions content**

```typescript
// src/app/transactions/transactions-content.tsx
'use client'

import { useState, useMemo } from 'react'
import { startOfMonth, endOfMonth, format } from 'date-fns'
import { Download, Search } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { DataTable } from '@/components/ui/data-table'
import { useTransactions } from '@/hooks/use-firefly'
import { formatCurrency, formatDateShort } from '@/lib/formatters'
import { cn } from '@/lib/cn'
import type { FireflyTransactionSplit } from '@/types/firefly'

export function TransactionsContent() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('')

  const now = new Date()
  const start = startOfMonth(now)
  const end = endOfMonth(now)

  const { data, isLoading } = useTransactions({
    dateRange: { start, end },
    type: typeFilter as 'withdrawal' | 'deposit' | 'transfer' | undefined,
    page,
    limit: 25,
  })

  // Flatten transactions (each can have multiple splits)
  const rows = useMemo(() => {
    if (!data?.data) return []
    return data.data.flatMap((tx) =>
      tx.attributes.transactions.map((split) => ({
        id: tx.id,
        ...split,
      }))
    ).filter((row) =>
      !search || row.description.toLowerCase().includes(search.toLowerCase())
    )
  }, [data, search])

  const totalPages = data?.meta?.pagination?.total_pages ?? 1

  const columns = [
    {
      key: 'date',
      header: 'Date',
      sortable: true,
      render: (row: FireflyTransactionSplit & { id: string }) => (
        <span className="text-zinc-300">{formatDateShort(row.date)}</span>
      ),
    },
    {
      key: 'description',
      header: 'Description',
      render: (row: FireflyTransactionSplit & { id: string }) => (
        <span className="text-zinc-200">{row.description}</span>
      ),
    },
    {
      key: 'amount',
      header: 'Montant',
      className: 'text-right',
      sortable: true,
      render: (row: FireflyTransactionSplit & { id: string }) => {
        const amount = parseFloat(row.amount)
        const isExpense = row.type === 'withdrawal'
        return (
          <span className={cn('font-mono', isExpense ? 'text-red-400' : 'text-emerald-400')}>
            {isExpense ? '-' : '+'}{formatCurrency(Math.abs(amount))}
          </span>
        )
      },
    },
    {
      key: 'category',
      header: 'Categorie',
      render: (row: FireflyTransactionSplit & { id: string }) => (
        <span className="text-zinc-400">{row.category_name ?? '—'}</span>
      ),
    },
    {
      key: 'account',
      header: 'Compte',
      render: (row: FireflyTransactionSplit & { id: string }) => (
        <span className="text-zinc-400">
          {row.type === 'withdrawal' ? row.source_name : row.destination_name}
        </span>
      ),
    },
  ]

  // CSV export
  function exportCSV() {
    const header = 'Date,Description,Montant,Type,Categorie,Compte\n'
    const csv = rows.map((r) =>
      `${r.date},"${r.description}",${r.amount},${r.type},${r.category_name ?? ''},${r.source_name}`
    ).join('\n')
    const blob = new Blob([header + csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `transactions-${format(now, 'yyyy-MM')}.csv`
    a.click()
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Rechercher..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 py-2 pl-10 pr-4 text-sm text-zinc-200 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 focus:outline-none"
        >
          <option value="">Tous types</option>
          <option value="withdrawal">Depenses</option>
          <option value="deposit">Revenus</option>
          <option value="transfer">Transferts</option>
        </select>
        <button
          onClick={exportCSV}
          className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
        >
          <Download className="h-4 w-4" />
          CSV
        </button>
      </div>

      {/* Table */}
      <Card className="p-0">
        <DataTable columns={columns} data={rows} />
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="rounded-lg border border-zinc-700 px-3 py-1 text-sm text-zinc-400 hover:bg-zinc-800 disabled:opacity-50"
          >
            Precedent
          </button>
          <span className="text-sm text-zinc-500">
            Page {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="rounded-lg border border-zinc-700 px-3 py-1 text-sm text-zinc-400 hover:bg-zinc-800 disabled:opacity-50"
          >
            Suivant
          </button>
        </div>
      )}
    </div>
  )
}
```

**Step 3: Transactions page**

```typescript
// src/app/transactions/page.tsx
import { PageHeader } from '@/components/layout/page-header'
import { TransactionsContent } from './transactions-content'

export default function TransactionsPage() {
  return (
    <div>
      <PageHeader
        title="Transactions"
        description="Historique et recherche de transactions"
      />
      <TransactionsContent />
    </div>
  )
}
```

**Step 4: Commit**

```bash
git add src/app/transactions/ src/components/ui/data-table.tsx
git commit -m "feat: transactions page with filters, table, pagination, CSV export"
```

---

### Task 11: Settings page

**Files:**
- Create: `src/app/settings/page.tsx`

**Step 1: Build settings page**

```typescript
// src/app/settings/page.tsx
'use client'

import { useState } from 'react'
import { PageHeader } from '@/components/layout/page-header'
import { Card } from '@/components/ui/card'
import { CheckCircle, XCircle, Loader2 } from 'lucide-react'

export default function SettingsPage() {
  const [fireflyStatus, setFireflyStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')
  const [llmStatus, setLlmStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')

  async function testFirefly() {
    setFireflyStatus('loading')
    try {
      const res = await fetch('/api/firefly/about')
      setFireflyStatus(res.ok ? 'ok' : 'error')
    } catch {
      setFireflyStatus('error')
    }
  }

  async function testLLM() {
    setLlmStatus('loading')
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [{ role: 'user', content: 'ping' }] }),
      })
      setLlmStatus(res.ok ? 'ok' : 'error')
    } catch {
      setLlmStatus('error')
    }
  }

  const StatusIcon = ({ status }: { status: string }) => {
    if (status === 'loading') return <Loader2 className="h-5 w-5 animate-spin text-zinc-400" />
    if (status === 'ok') return <CheckCircle className="h-5 w-5 text-emerald-500" />
    if (status === 'error') return <XCircle className="h-5 w-5 text-red-500" />
    return null
  }

  return (
    <div>
      <PageHeader title="Settings" description="Configuration des connexions" />

      <div className="max-w-2xl space-y-4">
        <Card>
          <h3 className="text-sm font-medium text-zinc-300">Firefly III</h3>
          <p className="mt-1 text-xs text-zinc-500">
            {process.env.NEXT_PUBLIC_APP_NAME} se connecte a Firefly III pour les donnees financieres.
          </p>
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={testFirefly}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500"
            >
              Tester la connexion
            </button>
            <StatusIcon status={fireflyStatus} />
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-zinc-300">LiteLLM (Chat IA)</h3>
          <p className="mt-1 text-xs text-zinc-500">
            Modele : {process.env.LLM_MODEL || 'non configure'}
          </p>
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={testLLM}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500"
            >
              Tester la connexion
            </button>
            <StatusIcon status={llmStatus} />
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-zinc-300">Devise</h3>
          <p className="mt-2 font-mono text-zinc-200">
            {process.env.NEXT_PUBLIC_CURRENCY || 'EUR'}
          </p>
        </Card>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add src/app/settings/
git commit -m "feat: settings page with connection tests"
```

---

### Task 12: Dockerfile + docker-compose.yml (dev)

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

**Step 1: Dockerfile**

```dockerfile
# Dockerfile
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

**Step 2: .dockerignore**

```
node_modules
.next
.git
*.md
tests
.env.local
```

**Step 3: docker-compose.yml (dev)**

```yaml
# docker-compose.yml — dev local
services:
  dashboard:
    build: .
    ports:
      - "3100:3000"
    env_file: .env.local
    restart: unless-stopped
```

**Step 4: Verify Docker build**

```bash
docker build -t seko-finance .
# Should build successfully
```

**Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: Dockerfile multi-stage + docker-compose dev"
```

---

## Phase 2 — Chat IA

### Task 13: Chat API route

**Files:**
- Create: `src/app/api/chat/route.ts`

**Step 1: Install AI SDK dependencies (if not already)**

```bash
pnpm add ai @ai-sdk/openai
```

**Step 2: Create chat route**

```typescript
// src/app/api/chat/route.ts
import { createOpenAI } from '@ai-sdk/openai'
import { streamText } from 'ai'
import { FINANCE_SYSTEM_PROMPT } from '@/lib/constants'

const litellm = createOpenAI({
  baseURL: process.env.LITELLM_URL,
  apiKey: process.env.LITELLM_KEY ?? '',
})

export async function POST(req: Request) {
  const { messages } = await req.json()

  const result = streamText({
    model: litellm(process.env.LLM_MODEL || 'deepseek-v3-free'),
    system: FINANCE_SYSTEM_PROMPT,
    messages,
  })

  return result.toDataStreamResponse()
}
```

**Step 3: Commit**

```bash
git add src/app/api/chat/
git commit -m "feat: chat API route with Vercel AI SDK + LiteLLM"
```

---

### Task 14: Chat components + widget

**Files:**
- Create: `src/components/chat/chat-message.tsx`
- Create: `src/components/chat/chat-input.tsx`
- Create: `src/components/chat/chat-widget.tsx`
- Modify: `src/app/layout.tsx` (add widget)

**Step 1: ChatMessage**

```typescript
// src/components/chat/chat-message.tsx
import ReactMarkdown from 'react-markdown'
import { cn } from '@/lib/cn'

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
}

export function ChatMessage({ role, content }: ChatMessageProps) {
  return (
    <div className={cn('flex gap-3', role === 'user' ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[80%] rounded-xl px-4 py-3 text-sm',
          role === 'user'
            ? 'bg-indigo-600 text-white'
            : 'bg-zinc-800 text-zinc-200'
        )}
      >
        {role === 'assistant' ? (
          <ReactMarkdown
            className="prose prose-invert prose-sm max-w-none"
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            }}
          >
            {content}
          </ReactMarkdown>
        ) : (
          <p>{content}</p>
        )}
      </div>
    </div>
  )
}
```

**Step 2: ChatInput**

```typescript
// src/components/chat/chat-input.tsx
'use client'

import { useState, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'

interface ChatInputProps {
  onSubmit: (message: string) => void
  isLoading: boolean
}

export function ChatInput({ onSubmit, isLoading }: ChatInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }, [value])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!value.trim() || isLoading) return
    onSubmit(value.trim())
    setValue('')
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSubmit(e)
          }
        }}
        placeholder="Posez une question sur vos finances..."
        rows={1}
        className="flex-1 resize-none rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none"
      />
      <button
        type="submit"
        disabled={!value.trim() || isLoading}
        className="rounded-lg bg-indigo-600 p-3 text-white hover:bg-indigo-500 disabled:opacity-50"
      >
        <Send className="h-4 w-4" />
      </button>
    </form>
  )
}
```

**Step 3: ChatWidget (floating panel)**

```typescript
// src/components/chat/chat-widget.tsx
'use client'

import { useState } from 'react'
import { useChat } from 'ai/react'
import { usePathname, useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { MessageCircle, X, Maximize2 } from 'lucide-react'
import { ChatMessage } from './chat-message'
import { ChatInput } from './chat-input'

const PAGE_SUGGESTIONS: Record<string, string[]> = {
  '/dashboard': [
    'Resume mes depenses du mois',
    'Quel est mon taux d\'epargne ?',
    'Compare mes depenses au mois dernier',
  ],
  '/transactions': [
    'Quelles sont mes plus grosses depenses ?',
    'Combien j\'ai depense en restaurants ?',
  ],
  '/budgets': [
    'Quels budgets sont proches du depassement ?',
    'Recommande des ajustements budgetaires',
  ],
}

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const { messages, append, isLoading } = useChat()

  const suggestions = PAGE_SUGGESTIONS[pathname] ?? [
    'Comment vont mes finances ?',
    'Fais-moi un bilan de la semaine',
  ]

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-6 right-6 z-50 rounded-full bg-indigo-600 p-4 text-white shadow-lg hover:bg-indigo-500"
      >
        {open ? <X className="h-5 w-5" /> : <MessageCircle className="h-5 w-5" />}
      </button>

      {/* Chat panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            className="fixed bottom-24 right-6 z-50 flex h-[60vh] w-[400px] flex-col rounded-xl border border-zinc-700 bg-zinc-900 shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
              <span className="text-sm font-medium text-zinc-200">Chat IA</span>
              <button
                onClick={() => { setOpen(false); router.push('/chat') }}
                className="text-zinc-400 hover:text-zinc-200"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 && (
                <div className="space-y-2">
                  <p className="text-xs text-zinc-500">Suggestions :</p>
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => append({ role: 'user', content: s })}
                      className="block w-full rounded-lg border border-zinc-700 px-3 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-800"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
              {messages.map((m) => (
                <ChatMessage key={m.id} role={m.role as 'user' | 'assistant'} content={m.content} />
              ))}
            </div>

            {/* Input */}
            <div className="border-t border-zinc-800 p-4">
              <ChatInput
                onSubmit={(msg) => append({ role: 'user', content: msg })}
                isLoading={isLoading}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
```

**Step 4: Add widget to layout**

In `src/app/layout.tsx`, add `<ChatWidget />` inside `<Providers>` after `<AppShell>`:

```typescript
import { ChatWidget } from '@/components/chat/chat-widget'
// ... in the return:
<Providers>
  <AppShell>{children}</AppShell>
  <ChatWidget />
</Providers>
```

**Step 5: Commit**

```bash
git add src/components/chat/ src/app/layout.tsx
git commit -m "feat: chat widget (floating panel, suggestions, markdown rendering)"
```

---

### Task 15: Chat full-screen page

**Files:**
- Create: `src/app/chat/page.tsx`

**Step 1: Full-screen chat page**

```typescript
// src/app/chat/page.tsx
'use client'

import { useChat } from 'ai/react'
import { PageHeader } from '@/components/layout/page-header'
import { ChatMessage } from '@/components/chat/chat-message'
import { ChatInput } from '@/components/chat/chat-input'

export default function ChatPage() {
  const { messages, append, isLoading } = useChat()

  return (
    <div className="flex h-[calc(100vh-48px)] flex-col">
      <PageHeader title="Chat IA" description="Posez des questions sur vos finances" />

      <div className="flex flex-1 gap-6 overflow-hidden">
        {/* Messages area */}
        <div className="flex flex-1 flex-col">
          <div className="flex-1 overflow-y-auto space-y-4 pb-4">
            {messages.length === 0 && (
              <div className="flex h-full items-center justify-center">
                <p className="text-zinc-500">Commencez une conversation...</p>
              </div>
            )}
            {messages.map((m) => (
              <ChatMessage key={m.id} role={m.role as 'user' | 'assistant'} content={m.content} />
            ))}
          </div>
          <div className="border-t border-zinc-800 pt-4">
            <ChatInput
              onSubmit={(msg) => append({ role: 'user', content: msg })}
              isLoading={isLoading}
            />
          </div>
        </div>

        {/* Suggestions sidebar */}
        <div className="hidden w-64 shrink-0 lg:block">
          <h3 className="mb-3 text-sm font-medium text-zinc-400">Suggestions</h3>
          <div className="space-y-2">
            {[
              'Resume mes depenses du mois',
              'Compare au mois precedent',
              'Quel budget est depasse ?',
              'Fais un bilan de la semaine',
              'Est-ce que je peux me permettre un achat a 200€ ?',
            ].map((s) => (
              <button
                key={s}
                onClick={() => append({ role: 'user', content: s })}
                className="block w-full rounded-lg border border-zinc-700 px-3 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-800"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add src/app/chat/
git commit -m "feat: full-screen chat page with suggestions sidebar"
```

---

## Phase 3 — Analytics & Budgets

### Task 16: Budgets page

**Files:**
- Create: `src/app/budgets/page.tsx`
- Create: `src/app/budgets/budgets-content.tsx`

**Step 1: Build budgets content**

```typescript
// src/app/budgets/budgets-content.tsx
'use client'

import { useBudgets } from '@/hooks/use-firefly'
import { Card } from '@/components/ui/card'
import { BudgetProgress } from '@/components/charts/budget-progress'

export function BudgetsContent() {
  const { data, isLoading } = useBudgets()

  if (isLoading) return <p className="text-zinc-500">Chargement...</p>

  const budgets = data?.data ?? []

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {budgets.map((b) => (
          <Card key={b.id}>
            <BudgetProgress
              name={b.attributes.name}
              spent={0} // Will be filled when budget limits hook is integrated
              limit={parseFloat(b.attributes.auto_budget_amount ?? '0')}
            />
          </Card>
        ))}
        {budgets.length === 0 && (
          <p className="col-span-full py-12 text-center text-sm text-zinc-500">
            Aucun budget configure dans Firefly III
          </p>
        )}
      </div>
    </div>
  )
}
```

**Step 2: Budget page wrapper**

```typescript
// src/app/budgets/page.tsx
import { PageHeader } from '@/components/layout/page-header'
import { BudgetsContent } from './budgets-content'

export default function BudgetsPage() {
  return (
    <div>
      <PageHeader title="Budgets" description="Suivi budgetaire mensuel" />
      <BudgetsContent />
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add src/app/budgets/
git commit -m "feat: budgets page with progress cards"
```

---

### Task 17: Analytics page (4 tabs)

**Files:**
- Create: `src/app/analytics/page.tsx`
- Create: `src/app/analytics/analytics-content.tsx`

**Step 1: Build analytics with tabs**

```typescript
// src/app/analytics/analytics-content.tsx
'use client'

import { useState } from 'react'
import { startOfYear, endOfMonth, format, subMonths } from 'date-fns'
import { Card } from '@/components/ui/card'
import { AreaChart } from '@/components/charts/area-chart'
import { useInsightExpense, useNetWorth, usePiggyBanks } from '@/hooks/use-firefly'
import { cn } from '@/lib/cn'
import { formatCurrency } from '@/lib/formatters'

const TABS = ['Vue Globale', 'Categories', 'Patrimoine', 'Epargne'] as const

export function AnalyticsContent() {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>('Vue Globale')

  const now = new Date()
  const yearStart = format(startOfYear(now), 'yyyy-MM-dd')
  const monthEnd = format(endOfMonth(now), 'yyyy-MM-dd')
  const sixMonthsAgo = format(subMonths(now, 6), 'yyyy-MM-dd')

  const { data: expenses } = useInsightExpense(yearStart, monthEnd)
  const { data: netWorth } = useNetWorth(sixMonthsAgo, monthEnd)
  const { data: piggyBanks } = usePiggyBanks()

  return (
    <div className="space-y-6">
      {/* Tab navigation */}
      <div className="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-1">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'rounded-md px-4 py-2 text-sm transition-colors',
              activeTab === tab
                ? 'bg-zinc-800 text-zinc-50'
                : 'text-zinc-400 hover:text-zinc-200'
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'Vue Globale' && (
        <Card>
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            Depenses par categorie (12 mois)
          </h3>
          <p className="py-12 text-center text-sm text-zinc-500">
            Graphiques avances — a implementer avec les donnees Firefly
          </p>
        </Card>
      )}

      {activeTab === 'Patrimoine' && (
        <Card>
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            Evolution du patrimoine net
          </h3>
          <p className="py-12 text-center text-sm text-zinc-500">
            Net worth chart — a implementer
          </p>
        </Card>
      )}

      {activeTab === 'Epargne' && (
        <Card>
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            Objectifs d'epargne
          </h3>
          <div className="space-y-4">
            {(piggyBanks?.data ?? []).map((pb) => (
              <div key={pb.id} className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-zinc-300">{pb.attributes.name}</span>
                  <span className="font-mono text-zinc-400">
                    {formatCurrency(parseFloat(pb.attributes.current_amount))} /
                    {formatCurrency(parseFloat(pb.attributes.target_amount))}
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-zinc-800">
                  <div
                    className="h-2 rounded-full bg-indigo-500"
                    style={{ width: `${Math.min(pb.attributes.percentage, 100)}%` }}
                  />
                </div>
              </div>
            ))}
            {(!piggyBanks?.data || piggyBanks.data.length === 0) && (
              <p className="py-8 text-center text-sm text-zinc-500">
                Aucun objectif d'epargne (piggy bank) dans Firefly III
              </p>
            )}
          </div>
        </Card>
      )}

      {activeTab === 'Categories' && (
        <Card>
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            Tendances par categorie
          </h3>
          <p className="py-12 text-center text-sm text-zinc-500">
            Sankey + tendances — a implementer
          </p>
        </Card>
      )}
    </div>
  )
}
```

**Step 2: Page wrapper**

```typescript
// src/app/analytics/page.tsx
import { PageHeader } from '@/components/layout/page-header'
import { AnalyticsContent } from './analytics-content'

export default function AnalyticsPage() {
  return (
    <div>
      <PageHeader title="Analytics" description="Visualisations avancees" />
      <AnalyticsContent />
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add src/app/analytics/
git commit -m "feat: analytics page with 4 tabs (overview, categories, patrimoine, epargne)"
```

---

## Phase 4 — Projections

### Task 18: Financial calculations library

**Files:**
- Create: `src/lib/calculations.ts`
- Test: `tests/unit/calculations.test.ts`

**Step 1: Write tests first (TDD)**

```typescript
// tests/unit/calculations.test.ts
import { describe, it, expect } from 'vitest'
import {
  calculateMortgage,
  calculateRendementBrut,
  calculateRendementNet,
  calculateCashFlow,
  calculateTRI,
  calculateAirbnbRevenue,
  calculateVehicleTCO,
} from '@/lib/calculations'

describe('calculateMortgage', () => {
  it('calculates monthly payment for a standard loan', () => {
    // 200k over 20 years at 3.5%
    const result = calculateMortgage(200000, 3.5, 20)
    expect(result.mensualite).toBeCloseTo(1159.92, 0)
    expect(result.coutTotal).toBeCloseTo(278381, 0)
  })

  it('handles zero interest rate', () => {
    const result = calculateMortgage(120000, 0, 10)
    expect(result.mensualite).toBeCloseTo(1000, 0)
  })
})

describe('calculateRendementBrut', () => {
  it('calculates gross yield', () => {
    // 800€/month rent, 200k purchase
    expect(calculateRendementBrut(800, 200000)).toBeCloseTo(4.8, 1)
  })
})

describe('calculateRendementNet', () => {
  it('calculates net yield after charges', () => {
    const result = calculateRendementNet({
      loyerMensuel: 800,
      prixAchat: 200000,
      fraisNotaire: 16000,
      chargesAnnuelles: 3000,
      vacancePercent: 5,
    })
    expect(result).toBeGreaterThan(0)
    expect(result).toBeLessThan(5) // should be less than gross
  })
})

describe('calculateCashFlow', () => {
  it('calculates monthly cash flow', () => {
    const cf = calculateCashFlow(800, 1160, 250)
    expect(cf).toBe(-610) // 800 - 1160 - 250
  })
})

describe('calculateAirbnbRevenue', () => {
  it('calculates annual Airbnb revenue', () => {
    const result = calculateAirbnbRevenue({
      prixNuit: 80,
      tauxOccupation: 65,
      commissionPlatforme: 15,
      menageParNuit: 20,
      nuitsMaxAn: 365,
    })
    expect(result.caBrut).toBeCloseTo(80 * 0.65 * 365, 0)
    expect(result.caNet).toBeLessThan(result.caBrut)
  })
})

describe('calculateVehicleTCO', () => {
  it('calculates total cost of ownership', () => {
    const result = calculateVehicleTCO({
      prix: 25000,
      assuranceAnnuelle: 800,
      entretienAnnuel: 600,
      carburantMensuel: 150,
      dureeAns: 5,
    })
    expect(result.tcoTotal).toBeGreaterThan(25000)
    expect(result.coutMensuel).toBeGreaterThan(0)
  })
})
```

**Step 2: Run tests — should fail**

```bash
pnpm test:run tests/unit/calculations.test.ts
# Expected: FAIL — module not found
```

**Step 3: Implement calculations**

```typescript
// src/lib/calculations.ts

/** Monthly mortgage payment */
export function calculateMortgage(principal: number, annualRate: number, years: number) {
  const n = years * 12
  if (annualRate === 0) {
    const mensualite = principal / n
    return { mensualite, coutTotal: principal, interetsTotal: 0 }
  }
  const r = annualRate / 100 / 12
  const mensualite = (principal * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1)
  const coutTotal = mensualite * n
  return { mensualite, coutTotal, interetsTotal: coutTotal - principal }
}

/** Gross rental yield (%) */
export function calculateRendementBrut(loyerMensuel: number, prixAchat: number): number {
  return ((loyerMensuel * 12) / prixAchat) * 100
}

/** Net rental yield (%) */
export function calculateRendementNet(params: {
  loyerMensuel: number
  prixAchat: number
  fraisNotaire: number
  chargesAnnuelles: number
  vacancePercent: number
}): number {
  const { loyerMensuel, prixAchat, fraisNotaire, chargesAnnuelles, vacancePercent } = params
  const loyerAnnuelNet = loyerMensuel * 12 * (1 - vacancePercent / 100) - chargesAnnuelles
  return (loyerAnnuelNet / (prixAchat + fraisNotaire)) * 100
}

/** Monthly cash flow: rent - mortgage - charges */
export function calculateCashFlow(
  loyerMensuel: number,
  mensualite: number,
  chargesMensuelles: number
): number {
  return loyerMensuel - mensualite - chargesMensuelles
}

/** Internal Rate of Return (simplified Newton method) */
export function calculateTRI(
  investissement: number,
  cashFlows: number[],
  maxIterations = 100
): number {
  let rate = 0.05
  for (let i = 0; i < maxIterations; i++) {
    let npv = -investissement
    let dnpv = 0
    for (let t = 0; t < cashFlows.length; t++) {
      const factor = Math.pow(1 + rate, t + 1)
      npv += cashFlows[t] / factor
      dnpv -= (t + 1) * cashFlows[t] / Math.pow(1 + rate, t + 2)
    }
    if (Math.abs(npv) < 0.01) break
    rate -= npv / dnpv
  }
  return rate * 100
}

/** Net-net yield after French tax */
export function calculateRendementNetNet(
  rendementNet: number,
  regime: 'micro-foncier' | 'reel' | 'micro-bic',
  trancheMarginalImpot = 30
): number {
  const abattement =
    regime === 'micro-foncier' ? 30 : regime === 'micro-bic' ? 50 : 0
  if (regime === 'reel') {
    // Simplified: real regime depends on deductible charges, estimate 70% taxed
    return rendementNet * (1 - trancheMarginalImpot / 100 * 0.7)
  }
  const revenuImposable = rendementNet * (1 - abattement / 100)
  return rendementNet - revenuImposable * (trancheMarginalImpot / 100)
}

/** Airbnb annual revenue */
export function calculateAirbnbRevenue(params: {
  prixNuit: number
  tauxOccupation: number // percentage
  commissionPlatforme: number // percentage
  menageParNuit: number
  nuitsMaxAn: number
}) {
  const { prixNuit, tauxOccupation, commissionPlatforme, menageParNuit, nuitsMaxAn } = params
  const nuitsOccupees = Math.round(nuitsMaxAn * (tauxOccupation / 100))
  const caBrut = prixNuit * nuitsOccupees
  const commissions = caBrut * (commissionPlatforme / 100)
  const menageTotal = menageParNuit * nuitsOccupees
  const caNet = caBrut - commissions - menageTotal
  return { caBrut, caNet, nuitsOccupees, commissions, menageTotal }
}

/** Vehicle Total Cost of Ownership */
export function calculateVehicleTCO(params: {
  prix: number
  assuranceAnnuelle: number
  entretienAnnuel: number
  carburantMensuel: number
  dureeAns: number
}) {
  const { prix, assuranceAnnuelle, entretienAnnuel, carburantMensuel, dureeAns } = params
  const coutAnnuel = assuranceAnnuelle + entretienAnnuel + carburantMensuel * 12
  const tcoTotal = prix + coutAnnuel * dureeAns
  const coutMensuel = tcoTotal / (dureeAns * 12)
  return { tcoTotal, coutMensuel, coutAnnuel }
}
```

**Step 4: Run tests — should pass**

```bash
pnpm test:run tests/unit/calculations.test.ts
# Expected: 7 tests pass
```

**Step 5: Commit**

```bash
git add src/lib/calculations.ts tests/unit/calculations.test.ts
git commit -m "feat: financial calculations library with unit tests (mortgage, yields, TRI, TCO)"
```

---

### Task 19: Projections hub + Immobilier page

**Files:**
- Create: `src/app/projections/page.tsx`
- Create: `src/app/projections/immobilier/page.tsx`

**Step 1: Hub page**

```typescript
// src/app/projections/page.tsx
import Link from 'next/link'
import { Building2, Car } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card } from '@/components/ui/card'

const MODULES = [
  {
    href: '/projections/immobilier',
    title: 'Immobilier',
    description: 'Achat residence, location longue duree, Airbnb',
    icon: Building2,
  },
  {
    href: '/projections/vehicule',
    title: 'Vehicule',
    description: 'Comptant, credit, LOA, LLD — cout total de possession',
    icon: Car,
  },
]

export default function ProjectionsPage() {
  return (
    <div>
      <PageHeader title="Projections" description="Simulations financieres" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {MODULES.map(({ href, title, description, icon: Icon }) => (
          <Link key={href} href={href}>
            <Card className="cursor-pointer transition-colors hover:border-zinc-600">
              <Icon className="mb-3 h-8 w-8 text-indigo-500" />
              <h3 className="text-lg font-medium text-zinc-200">{title}</h3>
              <p className="mt-1 text-sm text-zinc-400">{description}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
```

**Step 2: Immobilier page (3 tabs — full implementation)**

This is a large component. Create it as a Client Component with tabs for Achat, LCD, and Airbnb. Each tab has input forms and results calculated via `calculations.ts`. The full code is ~300 lines — implement it using the `calculateMortgage`, `calculateRendementBrut`, `calculateRendementNet`, `calculateCashFlow`, `calculateAirbnbRevenue` functions from `src/lib/calculations.ts`.

Key structure:

```typescript
// src/app/projections/immobilier/page.tsx
'use client'

import { useState } from 'react'
import { PageHeader } from '@/components/layout/page-header'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/cn'
import { formatCurrency, formatPercent } from '@/lib/formatters'
import {
  calculateMortgage,
  calculateRendementBrut,
  calculateRendementNet,
  calculateRendementNetNet,
  calculateCashFlow,
  calculateAirbnbRevenue,
} from '@/lib/calculations'

const TABS = ['Achat Residence', 'Location Longue Duree', 'Location Courte (Airbnb)'] as const

export default function ImmobilierPage() {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>('Achat Residence')

  // Shared inputs
  const [prix, setPrix] = useState(200000)
  const [apport, setApport] = useState(20000)
  const [duree, setDuree] = useState(20)
  const [taux, setTaux] = useState(3.5)

  // LCD inputs
  const [loyerMensuel, setLoyerMensuel] = useState(800)
  const [chargesAnnuelles, setChargesAnnuelles] = useState(3000)
  const [vacance, setVacance] = useState(5)
  const [regimeFiscal, setRegimeFiscal] = useState<'micro-foncier' | 'reel'>('micro-foncier')

  // Airbnb inputs
  const [prixNuit, setPrixNuit] = useState(80)
  const [tauxOccupation, setTauxOccupation] = useState(65)

  const fraisNotaire = Math.round(prix * 0.08)
  const emprunt = prix + fraisNotaire - apport
  const mortgage = calculateMortgage(emprunt, taux, duree)

  // Render tabs + forms + results using the calculation functions
  // Include disclaimer: "Ceci n'est pas un conseil fiscal ni financier"
  // Include "Demander a l'IA son avis" button linking to chat

  return (
    <div>
      <PageHeader title="Immobilier" description="Simulations immobilieres" />
      {/* Tab bar + content — implement fully using above state + calculations */}
      <div className="text-xs text-zinc-500 mt-8">
        ⚠️ Ceci n'est pas un conseil fiscal ni financier. Consultez un professionnel.
      </div>
    </div>
  )
}
```

**Note to implementer:** The full implementation of this page is ~300 lines of JSX with input fields, calculated results, and charts. Use the calculation functions from Task 18. Create a clean form layout with labeled inputs and a results section below each tab.

**Step 3: Commit**

```bash
git add src/app/projections/
git commit -m "feat: projections hub + immobilier page (achat, LCD, Airbnb)"
```

---

### Task 20: Vehicule page

**Files:**
- Create: `src/app/projections/vehicule/page.tsx`

**Step 1: Build vehicule projection page**

Similar pattern to immobilier. Uses `calculateVehicleTCO` and `calculateMortgage` (for credit comparison). Inputs: prix, type, financement mode. Outputs: comparison table (Comptant vs Credit vs LOA vs LLD), TCO BarChart, budget impact ProgressBar.

**Step 2: Commit**

```bash
git add src/app/projections/vehicule/
git commit -m "feat: vehicule projection page (TCO, credit comparison)"
```

---

## Phase 5 — Production

### Task 21: GitHub Actions CI/CD

**Files:**
- Create: `.github/workflows/docker-publish.yml`
- Create: `.github/workflows/ci.yml`

**Step 1: Docker publish workflow**

```yaml
# .github/workflows/docker-publish.yml
name: Build & Push Docker Image

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

**Step 2: CI workflow (lint + test)**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: latest

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm test:run
      - run: pnpm build
```

**Step 3: Commit**

```bash
git add .github/
git commit -m "feat: CI/CD workflows (lint+test+build, Docker push to GHCR)"
```

---

### Task 22: Unit tests (Vitest)

**Files:**
- Already done: `tests/unit/formatters.test.ts` (Task 2)
- Already done: `tests/unit/calculations.test.ts` (Task 18)
- Create: `tests/unit/firefly-types.test.ts`

**Step 1: Add type validation tests**

```typescript
// tests/unit/firefly-types.test.ts
import { describe, it, expect } from 'vitest'
import type { FireflyAccount, FireflyTransaction, FireflySummary } from '@/types/firefly'

describe('Firefly types', () => {
  it('FireflyAccount has expected shape', () => {
    const account: FireflyAccount = {
      id: '1',
      type: 'accounts',
      attributes: {
        name: 'Compte courant',
        type: 'asset',
        current_balance: '1234.56',
        current_balance_date: '2026-03-04',
        currency_code: 'EUR',
        currency_symbol: '€',
        active: true,
        account_role: 'defaultAsset',
        include_net_worth: true,
      },
    }
    expect(account.attributes.name).toBe('Compte courant')
    expect(parseFloat(account.attributes.current_balance)).toBe(1234.56)
  })

  it('FireflyTransaction has splits', () => {
    const tx: FireflyTransaction = {
      id: '42',
      type: 'transactions',
      attributes: {
        group_title: null,
        transactions: [
          {
            type: 'withdrawal',
            date: '2026-03-04',
            amount: '42.50',
            description: 'Courses Carrefour',
            currency_code: 'EUR',
            source_name: 'Compte courant',
            destination_name: 'Carrefour',
            category_name: 'Alimentation',
            budget_name: 'Courses',
            tags: [],
          },
        ],
      },
    }
    expect(tx.attributes.transactions).toHaveLength(1)
    expect(tx.attributes.transactions[0].type).toBe('withdrawal')
  })
})
```

**Step 2: Run all tests**

```bash
pnpm test:run
# Expected: All tests pass (formatters + calculations + types)
```

**Step 3: Commit**

```bash
git add tests/
git commit -m "test: add Firefly type validation tests"
```

---

### Task 23: Playwright E2E tests

**Files:**
- Create: `playwright.config.ts`
- Create: `tests/e2e/smoke.spec.ts`

**Step 1: Configure Playwright**

```typescript
// playwright.config.ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  retries: 1,
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'pnpm dev',
    port: 3000,
    reuseExistingServer: true,
  },
})
```

Add to `package.json`:

```json
{
  "scripts": {
    "test:e2e": "playwright test"
  }
}
```

**Step 2: Smoke test**

```typescript
// tests/e2e/smoke.spec.ts
import { test, expect } from '@playwright/test'

test('health endpoint returns ok', async ({ request }) => {
  const res = await request.get('/api/health')
  expect(res.status()).toBe(200)
  const body = await res.json()
  expect(body.status).toBe('ok')
})

test('root redirects to dashboard', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL('/dashboard')
})

test('sidebar navigation works', async ({ page }) => {
  await page.goto('/dashboard')
  await page.click('a[href="/transactions"]')
  await expect(page).toHaveURL('/transactions')
})

test('dashboard page loads', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page.locator('h1')).toContainText('Dashboard')
})

test('settings page loads', async ({ page }) => {
  await page.goto('/settings')
  await expect(page.locator('h1')).toContainText('Settings')
})
```

**Step 3: Install Playwright browsers**

```bash
pnpm exec playwright install --with-deps chromium
```

**Step 4: Run E2E tests**

```bash
pnpm test:e2e
# Expected: 5 tests pass
```

**Step 5: Commit**

```bash
git add playwright.config.ts tests/e2e/
git commit -m "test: Playwright E2E smoke tests"
```

---

### Task 24: Final — Push to GitHub + Pin image in VPAI

**Step 1: Create GitHub repo**

```bash
gh repo create Mobutoo/seko-finance --private --source=. --remote=origin --push
```

**Step 2: Push**

```bash
git push -u origin main
```

**Step 3: Wait for GitHub Actions to build the Docker image**

Check `https://github.com/Mobutoo/seko-finance/actions` — the `docker-publish.yml` workflow should trigger and push the image to GHCR.

**Step 4: Pin image SHA in VPAI**

Once the image is built, get the SHA:

```bash
gh api /orgs/mobutoo/packages/container/seko-finance/versions --jq '.[0].name'
```

Then in VPAI `inventory/group_vars/all/versions.yml`, replace `latest` with the pinned tag:

```yaml
seko_finance_image: "ghcr.io/mobutoo/seko-finance:sha-<commit>"
```

**Step 5: Deploy to production**

```bash
cd ~/seko/VPAI
source .venv/bin/activate
make deploy-role ROLE=seko-finance ENV=prod
```

---

## Summary

| Phase | Tasks | Key deliverables |
|-------|-------|-----------------|
| Phase 1 — MVP | 1-12 | Scaffold, design system, Firefly proxy, hooks, dashboard, transactions, settings, Docker |
| Phase 2 — Chat IA | 13-15 | Chat API route, widget flottant, page plein ecran |
| Phase 3 — Analytics | 16-17 | Budgets page, analytics (4 tabs) |
| Phase 4 — Projections | 18-20 | Calculations lib (TDD), immobilier (3 tabs), vehicule |
| Phase 5 — Production | 21-24 | CI/CD, unit tests, E2E tests, deploy |

**Total: 24 tasks**
