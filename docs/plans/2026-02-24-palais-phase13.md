# Palais Phase 13 — Multi-Node Health + Atelier Creatif

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Surveillance multi-noeud (VPS + Pi + VPN), carte reseau VPN, backup Zerobyte, dashboard Atelier Creatif (ComfyUI + Remotion), galerie d'assets generes.

**Architecture:** Health checks via n8n `stack-health` webhook + Headscale API pour topologie VPN. ComfyUI sur le Pi accessible via Tailscale IP. Assets stockes dans `deliverables/creative/`.

**Tech Stack:** SvelteKit 5, Headscale API, ComfyUI API, n8n webhooks, Drizzle ORM

**PRD Reference:** `docs/PRD-PALAIS.md` — Modules 11 (Multi-Node Health) + 12 (Atelier Creatif)

---

## Task 1: Modele `nodes` + `health_checks` + `backup_status`

**Files:**
- Modify: `roles/palais/files/app/src/lib/server/db/schema.ts`

Ajouter les tables :

```typescript
export const nodes = pgTable('nodes', {
  id: serial('id').primaryKey(),
  name: text('name').notNull(), // sese-ai, rpi5, seko-vpn
  tailscaleIp: text('tailscale_ip'),
  status: text('status').default('offline'), // online|offline
  lastSeenAt: timestamp('last_seen_at'),
  cpuPercent: real('cpu_percent'),
  ramPercent: real('ram_percent'),
  diskPercent: real('disk_percent'),
  temperature: real('temperature'), // nullable, Pi only
  createdAt: timestamp('created_at').defaultNow(),
});

export const healthChecks = pgTable('health_checks', {
  id: serial('id').primaryKey(),
  nodeId: integer('node_id').references(() => nodes.id),
  serviceName: text('service_name').notNull(),
  status: text('status').notNull(), // healthy|unhealthy|unknown
  responseTimeMs: integer('response_time_ms'),
  checkedAt: timestamp('checked_at').defaultNow(),
  details: jsonb('details'),
});

export const backupStatus = pgTable('backup_status', {
  id: serial('id').primaryKey(),
  nodeId: integer('node_id').references(() => nodes.id),
  lastBackupAt: timestamp('last_backup_at'),
  nextBackupAt: timestamp('next_backup_at'),
  sizeBytes: bigint('size_bytes', { mode: 'number' }),
  status: text('status').default('unknown'), // ok|failed|running
  details: jsonb('details'),
  updatedAt: timestamp('updated_at').defaultNow(),
});
```

Migration : `npx drizzle-kit generate && npx drizzle-kit migrate`

Commit: `feat(palais): nodes, health_checks, backup_status DB schema`

## Task 2: Seed des 3 noeuds

**Files:**
- Modify: `roles/palais/files/app/src/lib/server/db/seed.ts`

Ajouter seed pour les 3 noeuds :
```typescript
const nodesSeed = [
  { name: 'sese-ai', tailscaleIp: '{{ sese_ai_tailscale_ip }}' },
  { name: 'rpi5', tailscaleIp: '{{ workstation_pi_tailscale_ip }}' },
  { name: 'seko-vpn', tailscaleIp: '{{ seko_vpn_tailscale_ip }}' },
];
```

Commit: `feat(palais): seed 3 infrastructure nodes`

## Task 3: Health Check API + Webhook

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/health/nodes/+server.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/health/webhook/+server.ts`

`GET /api/v1/health/nodes` — retourne tous les noeuds avec dernier health check par service.

`POST /api/v1/health/webhook` — recoit le payload du workflow n8n `stack-health` :
```json
{
  "node": "sese-ai",
  "services": [
    { "name": "postgresql", "status": "healthy", "response_time_ms": 12 },
    { "name": "redis", "status": "healthy", "response_time_ms": 3 }
  ],
  "cpu_percent": 45.2,
  "ram_percent": 72.1,
  "disk_percent": 58.0
}
```

Insere les health checks, met a jour le noeud (status, metriques, last_seen_at).

Commit: `feat(palais): health check API + webhook receiver`

## Task 4: Integration Headscale API

**Files:**
- Create: `roles/palais/files/app/src/lib/server/health/headscale.ts`

Appeler `GET http://{{ seko_vpn_tailscale_ip }}:8080/api/v1/machine` avec API key Headscale.

Parser la reponse : extraire noeuds, IPs, lastSeen, online status. Retourner sous forme de topologie.

```typescript
export async function fetchVPNTopology(): Promise<VPNNode[]> {
  const res = await fetch(`${env.HEADSCALE_URL}/api/v1/machine`, {
    headers: { 'Authorization': `Bearer ${env.HEADSCALE_API_KEY}` }
  });
  const data = await res.json();
  return data.machines.map((m: any) => ({
    name: m.givenName,
    ip: m.ipAddresses?.[0],
    online: m.online,
    lastSeen: m.lastSeen,
  }));
}
```

Commit: `feat(palais): Headscale API integration for VPN topology`

## Task 5: Health Dashboard Page

**Files:**
- Create: `roles/palais/files/app/src/routes/health/+page.svelte`
- Create: `roles/palais/files/app/src/routes/health/+page.server.ts`

Layout :
- **Carte reseau VPN** : 3 noeuds positionnes (SVG), liens entre eux avec latence, couleur selon status (vert/rouge)
- **Par noeud** : carte avec CPU/RAM/disk (jauges), temperature Pi, liste services avec indicateur vert/rouge
- **Backup Zerobyte** : dernier backup, prochain, taille, status. Alerte si > 24h
- **Historique** : timeline des health checks (derniere heure)

Style : noeuds or sur fond sombre, liens cyan, alertes rouge/ambre.

Commit: `feat(palais): health dashboard with VPN topology + service status`

## Task 6: Backup Status Integration

**Files:**
- Create: `roles/palais/files/app/src/routes/api/v1/health/backup/+server.ts`

`GET /api/v1/health/backup` — retourne le status backup Zerobyte.

`POST /api/v1/health/backup/webhook` — recoit update depuis n8n/cron :
```json
{
  "last_backup_at": "2026-02-24T03:00:00Z",
  "next_backup_at": "2026-02-25T03:00:00Z",
  "size_bytes": 2147483648,
  "status": "ok"
}
```

Logique alerte : si `last_backup_at` > 24h, creer un insight `warning`.

Commit: `feat(palais): backup status API + alert on stale backup`

## Task 7: Atelier Creatif — ComfyUI Queue

**Files:**
- Create: `roles/palais/files/app/src/lib/server/creative/comfyui.ts`
- Create: `roles/palais/files/app/src/routes/api/v1/creative/comfyui/+server.ts`

Client ComfyUI :
```typescript
const COMFYUI_URL = `http://${env.WORKSTATION_PI_IP}:8188`;

export async function getComfyUIStatus() {
  const res = await fetch(`${COMFYUI_URL}/system_stats`);
  return res.json();
}

export async function getComfyUIHistory(limit = 20) {
  const res = await fetch(`${COMFYUI_URL}/history`);
  const data = await res.json();
  return Object.values(data).slice(0, limit);
}

export async function submitComfyUIPrompt(workflow: object) {
  const res = await fetch(`${COMFYUI_URL}/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: workflow })
  });
  return res.json();
}
```

API :
- `GET /api/v1/creative/comfyui` — status + queue + history
- `POST /api/v1/creative/comfyui/generate` — soumettre un prompt

Commit: `feat(palais): ComfyUI API client + creative endpoints`

## Task 8: Atelier Creatif — Dashboard Page

**Files:**
- Create: `roles/palais/files/app/src/routes/creative/+page.svelte`
- Create: `roles/palais/files/app/src/routes/creative/+page.server.ts`

Layout :
- **Queue ComfyUI** : taches en cours (spinner), en attente, terminees (thumbnails)
- **Quick Generate** : champ prompt + bouton → POST vers ComfyUI
- **Galerie** : grille de thumbnails des images generees, filtrables par date
- **Remotion** : section status des rendus video (via n8n `creative-pipeline`)

Clic sur un asset → preview pleine taille + bouton "Attacher comme livrable" (POST vers `/api/v1/tasks/:id/deliverables`).

Commit: `feat(palais): creative dashboard — ComfyUI queue + gallery`

## Task 9: Auto-attacher assets comme livrables

**Files:**
- Modify: `roles/palais/files/app/src/lib/server/creative/comfyui.ts`

Quand un job ComfyUI termine avec un `task_id` dans les metadata :
1. Copier l'image generee dans `deliverables/creative/`
2. Creer un enregistrement `deliverables` lie a la tache
3. Generer un `download_token`

Commit: `feat(palais): auto-attach ComfyUI outputs as task deliverables`

---

## Verification Checklist

- [ ] Table `nodes` avec 3 noeuds seedes
- [ ] Webhook health check recoit et stocke les donnees
- [ ] Integration Headscale retourne topologie VPN
- [ ] `/health` affiche carte reseau + status services + metriques
- [ ] Backup Zerobyte status visible + alerte si > 24h
- [ ] ComfyUI queue visible depuis Palais
- [ ] Quick generate envoie prompt au Pi via VPN
- [ ] Galerie affiche les images generees
- [ ] Assets attaches automatiquement aux taches source
